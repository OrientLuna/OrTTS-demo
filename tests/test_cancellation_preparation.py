"""Cancellation lock and preparation safety, without models or a compiler."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

from tools import prepare_cancellable_runtime
from tools.source_identity import verify_mtmd_sources

ROOT = Path(__file__).resolve().parents[1]


class CancellationPreparationTests(TestCase):
    def test_every_mtmd_file_is_verified_not_just_last_entry(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mtmd").mkdir()
            expected = {}
            for name in ("first.cpp", "last.cpp"):
                (root / "mtmd" / name).write_bytes(b"verified")
                expected[name] = hashlib.sha256(b"verified").hexdigest()
            verify_mtmd_sources(root / "audio.cpp", expected, {})
            (root / "mtmd/first.cpp").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "first.cpp"):
                verify_mtmd_sources(root / "audio.cpp", expected, {})

    def test_mtmd_overlay_requires_matching_base_and_output(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mtmd").mkdir()
            (root / "mtmd/clip.cpp").write_bytes(b"patched")
            before = hashlib.sha256(b"base").hexdigest()
            after = hashlib.sha256(b"patched").hexdigest()
            changes = {"clip.cpp": {"base_sha256": before, "sha256": after}}
            verify_mtmd_sources(root / "audio.cpp", {"clip.cpp": before}, changes)
            with self.assertRaisesRegex(ValueError, "base identity"):
                verify_mtmd_sources(root / "audio.cpp", {"clip.cpp": "0" * 64}, changes)

    def test_locked_patches_match_repository(self):
        lock = json.loads((ROOT / "vendor/cancellation.lock.json").read_text())
        for key in ("patch", "mtmd_patch"):
            self.assertEqual(hashlib.sha256((ROOT / lock[key]).read_bytes()).hexdigest(), lock[key + "_sha256"])
        for key in ("files", "mtmd_files"):
            entries = lock[key]
            self.assertEqual(len({e["path"] for e in entries}), len(entries))
            self.assertTrue(all(len(e["sha256"]) == 64 for e in entries))

    def test_invalid_source_does_not_create_output(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            with mock.patch.object(prepare_cancellable_runtime, "identity", side_effect=ValueError("bad source")):
                with self.assertRaisesRegex(ValueError, "bad source"):
                    prepare_cancellable_runtime.prepare(Path(directory), output)
            self.assertFalse(output.exists())

    def test_existing_output_is_not_overwritten(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            output.mkdir()
            sentinel = output / "user-work"
            sentinel.write_text("keep")
            with mock.patch.object(prepare_cancellable_runtime, "identity"):
                with self.assertRaisesRegex(ValueError, "fresh output"):
                    prepare_cancellable_runtime.prepare(Path(directory), output)
            self.assertEqual(sentinel.read_text(), "keep")
