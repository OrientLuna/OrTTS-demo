"""Host-side safety tests; synthetic manifests are trusted only within each test."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main, mock
import ctypes
import hashlib
import json
import math
import struct
import subprocess
import threading
from types import SimpleNamespace
import wave

from desktop.audio import Player, write_wav
from desktop.engine import Audio, Config, Engine, Metrics, Request
from desktop.models import Cancelled, PACKAGES, safe_path, verify_pack
from desktop.worker import Worker
from desktop.packaging.build_macos import git_metadata


class ModelTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="ortts-desktop-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.data = {"native/model.gguf": b"model", "native/dequant/MANIFEST.json": b"{}",
                     "voices/female.f32": struct.pack("f", 0.5)}
        for name, data in self.data.items():
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)

    def trust_manifest(self, transform=lambda d: None):
        doc = {"schema": "ortts-download-manifest-v1", "revision": PACKAGES["Q4"][1],
               "model_id": "OrientLuna/OrTTS-Qwen3-LFM-0.6B",
               "runtime": {"decoder": {"dequant_manifest": "native/dequant/MANIFEST.json"}},
               "files": [{"path": k, "bytes": len(v), "sha256": hashlib.sha256(v).hexdigest()}
                         for k, v in self.data.items()]}
        transform(doc)
        data = json.dumps(doc).encode()
        (self.root / "DOWNLOAD_MANIFEST.json").write_bytes(data)
        patcher = mock.patch.dict(PACKAGES, {"Q4": ("test only", doc["revision"], hashlib.sha256(data).hexdigest())})
        patcher.start()
        self.addCleanup(patcher.stop)
        return doc

    def test_verified_bridge_is_from_trusted_entry(self):
        doc = self.trust_manifest()
        pack = verify_pack(self.root, "Q4")
        self.assertEqual(pack.bridge_sha256, doc["files"][1]["sha256"])
        self.assertEqual(pack.voices, ("female",))
        self.assertEqual(pack.variants, ("P3",))
        self.assertTrue(pack.unchanged())

    def test_wrong_package_rejected(self):
        self.trust_manifest()
        with self.assertRaisesRegex(ValueError, "清单 SHA256"):
            verify_pack(self.root, "Q8")

    def test_missing_manifest(self):
        with self.assertRaisesRegex(ValueError, "完整模型目录"):
            verify_pack(self.root, "Q4")

    def test_missing_file(self):
        self.trust_manifest()
        (self.root / "native/model.gguf").unlink()
        with self.assertRaises(FileNotFoundError):
            verify_pack(self.root, "Q4")

    def test_size_rejected(self):
        self.trust_manifest()
        (self.root / "native/model.gguf").write_bytes(b"longer model")
        with self.assertRaisesRegex(ValueError, "大小"):
            verify_pack(self.root, "Q4")

    def test_same_size_tamper_rejected(self):
        self.trust_manifest()
        (self.root / "native/model.gguf").write_bytes(b"MODEL")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            verify_pack(self.root, "Q4")

    def test_changed_model_invalidates_cache(self):
        self.trust_manifest()
        pack = verify_pack(self.root, "Q4")
        (self.root / "native/model.gguf").write_bytes(b"MODEL")
        self.assertFalse(pack.unchanged())

    def test_changed_manifest_invalidates_cache(self):
        self.trust_manifest()
        pack = verify_pack(self.root, "Q4")
        (self.root / "DOWNLOAD_MANIFEST.json").write_bytes(b"{}")
        self.assertFalse(pack.unchanged())

    def test_traversal_paths_rejected(self):
        for name in ["../outside", "/absolute", "native/../model", "native//model", "./model", "native\\model", ""]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_path(self.root, name)

    def test_escaping_symlink_rejected(self):
        with TemporaryDirectory() as other:
            (self.root / "outside").symlink_to(other, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "越界"):
                safe_path(self.root, "outside/model")

    def test_missing_bridge_entry_rejected(self):
        self.trust_manifest(lambda d: d["files"].pop(1))
        with self.assertRaisesRegex(ValueError, "bridge/dequant"):
            verify_pack(self.root, "Q4")

    def test_duplicate_entry_rejected(self):
        self.trust_manifest(lambda d: d["files"].append(d["files"][0]))
        with self.assertRaisesRegex(ValueError, "重复路径"):
            verify_pack(self.root, "Q4")

    def test_cancel_verification(self):
        self.trust_manifest()
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            verify_pack(self.root, "Q4", cancel=cancel)


class AudioAndABITests(TestCase):
    def test_natural_arm64_layout(self):
        self.assertEqual(ctypes.sizeof(Config), 48)
        self.assertEqual(Config.asset_root.offset, 8)
        self.assertEqual(ctypes.sizeof(Request), 32)
        self.assertEqual(Request.seed.offset, 16)
        self.assertEqual(ctypes.sizeof(Metrics), 40)

    def test_wav_clips_and_encodes_little_endian(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "test.wav"
            write_wav(Audio(struct.pack("5f", -2, -0.5, 0, 0.5, 2), 24000, 0), path)
            with wave.open(str(path)) as wav:
                self.assertEqual(wav.getparams()[:4], (1, 2, 24000, 5))
                self.assertEqual(struct.unpack("<5h", wav.readframes(5)), (-32767, -16384, 0, 16384, 32767))

    def test_nonfinite_audio_rejected(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "NaN/Inf"):
                write_wav(Audio(struct.pack("f", value), 24000, 0), "unused.wav")

    def test_empty_audio_rejected(self):
        with self.assertRaises(ValueError):
            write_wav(Audio(b"", 24000, 0), "unused.wav")

    def test_missing_library_is_actionable(self):
        with self.assertRaises(OSError):
            Engine("/nonexistent/ortts.dylib")

    def test_player_does_not_use_shell(self):
        with mock.patch("desktop.audio.subprocess.Popen") as popen:
            player = Player()
            player.play("空 格.wav")
            self.assertIsInstance(popen.call_args.args[0], list)
            self.assertNotIn("shell", popen.call_args.kwargs)

    def test_worker_reports_bad_import_and_joins(self):
        with TemporaryDirectory() as directory:
            worker = Worker(Path(directory) / "outputs")
            try:
                worker.submit("import", directory=directory, package="Q4")
                errors = []
                while True:
                    event, value = worker.events.get(timeout=10)
                    if event == "error":
                        errors.append(value)
                    if event == "done":
                        break
                self.assertTrue(errors)
            finally:
                worker.shutdown()
                worker.thread.join(timeout=10)
                self.assertFalse(worker.thread.is_alive())


class BuildMetadataTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="ortts-git-metadata-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "--quiet", "--template=")
        (self.root / ".gitignore").write_text("/generated/\n")
        (self.root / "tracked").write_text("initial\n")
        self.git("add", ".gitignore", "tracked")
        self.git("-c", "user.name=Metadata Test", "-c", "user.email=test@example.invalid",
                 "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
                 "commit", "--quiet", "-m", "Initial test fixture")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root)

    def test_clean_repository(self):
        data = git_metadata(self.root)
        self.assertEqual(data["git_head"], self.git("rev-parse", "HEAD").decode().strip())
        self.assertFalse(data["working_tree"]["dirty"])

    def test_unstaged_change(self):
        (self.root / "tracked").write_text("modified\n")
        state = git_metadata(self.root)["working_tree"]
        self.assertTrue(state["dirty"])
        self.assertEqual(state["unstaged_files"], 1)
        self.assertEqual(state["staged_files"], 0)

    def test_staged_change(self):
        (self.root / "tracked").write_text("staged\n")
        self.git("add", "tracked")
        state = git_metadata(self.root)["working_tree"]
        self.assertTrue(state["dirty"])
        self.assertEqual(state["staged_files"], 1)
        self.assertEqual(state["unstaged_files"], 0)

    def test_untracked_source_is_dirty(self):
        (self.root / "new-source.py").write_text("pass\n")
        state = git_metadata(self.root)["working_tree"]
        self.assertTrue(state["dirty"])
        self.assertEqual(state["untracked_files"], 1)

    def test_ignored_output_does_not_make_repository_dirty(self):
        (self.root / "generated").mkdir()
        (self.root / "generated/output").write_text("not source\n")
        state = git_metadata(self.root)["working_tree"]
        self.assertFalse(state["dirty"])
        self.assertEqual(state["untracked_files"], 0)


class CancellationHostTests(TestCase):
    def engine(self):
        engine = Engine.__new__(Engine)
        engine.owner = threading.get_ident()
        engine.lock = threading.Lock()
        engine.handle = ctypes.c_void_p()
        engine.loading_token = ctypes.c_void_p()
        engine.key = None
        engine.loads = 0
        engine.cancellable_create = True
        engine.lib = SimpleNamespace(
            ortts_cancel_token_create=mock.Mock(return_value=17),
            ortts_cancel_token_request=mock.Mock(),
            ortts_cancel_token_free=mock.Mock(),
            ortts_engine_free=mock.Mock(),
            ortts_last_error=lambda: b"cancelled",
        )
        return engine

    def pack(self):
        return SimpleNamespace(root=Path("/model"), manifest_sha256="a" * 64,
                               bridge_sha256="b" * 64, voices=("female",), variants=("P3",))

    def test_loading_token_published_for_cross_thread_cancel_and_freed(self):
        engine = self.engine()
        def create(cfg, token, output):
            self.assertEqual(engine.loading_token.value, 17)
            engine.cancel()
            return 4
        engine.lib.ortts_engine_create_cancellable = create
        with self.assertRaises(Cancelled):
            engine.load(self.pack())
        engine.lib.ortts_cancel_token_request.assert_called_once()
        engine.lib.ortts_cancel_token_free.assert_called_once()
        self.assertFalse(engine.loading_token)
        self.assertFalse(engine.handle)
        self.assertEqual(engine.loads, 0)

    def test_late_loading_cancel_frees_unpublished_engine(self):
        engine = self.engine()
        cancel = threading.Event()
        def create(cfg, token, output):
            output._obj.value = 99
            cancel.set()
            return 0
        engine.lib.ortts_engine_create_cancellable = create
        with self.assertRaises(Cancelled):
            engine.load(self.pack(), cancel=cancel)
        engine.lib.ortts_engine_free.assert_called_once()
        self.assertFalse(engine.handle)

    def test_precancelled_load_does_not_create_token(self):
        engine = self.engine()
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            engine.load(self.pack(), cancel=cancel)
        engine.lib.ortts_cancel_token_create.assert_not_called()

    def test_existing_handle_reused_without_token_or_reload(self):
        engine = self.engine()
        pack = self.pack()
        engine.handle = ctypes.c_void_p(99)
        engine.key = (pack.root, pack.manifest_sha256, "P3", "female", 4, False)
        engine.load(pack)
        engine.lib.ortts_cancel_token_create.assert_not_called()
        engine.lib.ortts_engine_free.assert_not_called()
        self.assertEqual(engine.handle.value, 99)


if __name__ == "__main__":
    main()
