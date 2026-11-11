"""Small offline fixtures; no network, GPU or model downloads."""
import hashlib
import io
import json
import os
import shutil
import sys
from pathlib import Path
import struct
import threading
import time
from tempfile import TemporaryDirectory
from unittest import TestCase, mock, skipUnless

from desktop.download import download_error, download_pack, package_lock, parse_manifest, SecureRedirect
from desktop.models import Cancelled, PACKAGES
from linux.audio import StreamPlayer


class DownloadTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "model"
        self.files = {"native/dequant/MANIFEST.json": b"{}", "voices/female.f32": struct.pack("f", 0.1)}
        self.doc = {"schema": "ortts-download-manifest-v1", "model_id": "OrientLuna/OrTTS-Qwen3-LFM-0.6B",
                    "revision": "test", "runtime": {"decoder": {"dequant_manifest": "native/dequant/MANIFEST.json"}},
                    "files": [{"path": n, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
                              for n, b in self.files.items()]}
        self.pin()
        self.requests = []
        self.opener = mock.patch("desktop.download.open_https", side_effect=self.open)
        self.opener.start()
        self.addCleanup(self.opener.stop)

    def pin(self):
        self.manifest = json.dumps(self.doc).encode()
        patcher = mock.patch.dict(PACKAGES, {"Q4": ("fixture", "test", hashlib.sha256(self.manifest).hexdigest())})
        patcher.start()
        self.addCleanup(patcher.stop)

    def open(self, url):
        self.requests.append(url)
        if url.endswith("DOWNLOAD_MANIFEST.json"):
            return io.BytesIO(self.manifest)
        return io.BytesIO(next(b for n, b in self.files.items() if url.endswith(n)))

    def test_complete_and_offline_cache_reuse(self):
        pack = download_pack(self.root, "Q4", "ModelScope")
        self.assertTrue(pack.unchanged())
        self.assertEqual(len(self.requests), 3)
        self.requests.clear()
        download_pack(self.root, "Q4", "ModelScope")
        self.assertEqual(self.requests, [])

    def test_cross_version_file_reuse_without_network_payload(self):
        source = Path(self.temp.name) / "old"
        for n, b in self.files.items():
            p = source / n
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b)
        download_pack(self.root, "Q4", "Hugging Face", reuse_roots=[source])
        self.assertEqual(len(self.requests), 1)
        self.assertNotEqual((source / "voices/female.f32").stat().st_ino,
                            (self.root / "voices/female.f32").stat().st_ino)

    def test_wrong_manifest_sha(self):
        with mock.patch.dict(PACKAGES, {"Q4": ("fixture", "test", "0" * 64)}):
            with self.assertRaisesRegex(ValueError, "清单 SHA256"):
                download_pack(self.root, "Q4", "ModelScope")
        self.assertFalse((self.root / "DOWNLOAD_MANIFEST.json").exists())

    def test_wrong_file_sha_preserves_partial(self):
        self.files["voices/female.f32"] = b"oops"
        with self.assertRaisesRegex(ValueError, "SHA256"):
            download_pack(self.root, "Q4", "ModelScope")
        self.assertFalse((self.root / "voices/female.f32").exists())
        self.assertTrue(list(self.root.rglob("*.part*")))

    def test_cancel_preserves_verified_files(self):
        cancel = threading.Event()
        def progress(text):
            if "voices/female" in text:
                cancel.set()
        with self.assertRaises(Cancelled):
            download_pack(self.root, "Q4", "ModelScope", progress, cancel)
        self.assertEqual((self.root / "native/dequant/MANIFEST.json").read_bytes(), b"{}")
        self.assertFalse((self.root / "voices/female.f32").exists())

    def test_existing_bad_file_untouched(self):
        path = self.root / "voices/female.f32"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"OLD!")
        with self.assertRaisesRegex(ValueError, "原样保留"):
            download_pack(self.root, "Q4", "ModelScope")
        self.assertEqual(path.read_bytes(), b"OLD!")

    def test_path_escape_rejected_before_payload(self):
        self.doc["files"][0]["path"] = "../escape"
        self.pin()
        with self.assertRaisesRegex(ValueError, "越界"):
            download_pack(self.root, "Q4", "ModelScope")
        self.assertEqual(len(self.requests), 1)

    def test_symlink_target_rejected(self):
        self.root.mkdir()
        (self.root / "voices").symlink_to(Path(self.temp.name))
        with self.assertRaisesRegex(ValueError, "软链接|越界"):
            download_pack(self.root, "Q4", "ModelScope")

    def test_short_response_not_published(self):
        self.files["voices/female.f32"] = b""
        with self.assertRaisesRegex(ValueError, "下载未完成"):
            download_pack(self.root, "Q4", "ModelScope")
        self.assertFalse((self.root / "voices/female.f32").exists())

    @skipUnless(os.environ.get("DISPLAY"), "requires X display or xvfb-run")
    def test_gui_download_worker_import_and_close(self):
        import tkinter as tk
        from desktop.app import App
        window = tk.Tk()
        # Default desktop entry has NO streaming backend: downloads must still work.
        app = App(window, state_dir=Path(self.temp.name) / "settings")
        try:
            with mock.patch("desktop.app.messagebox.askyesno", return_value=True), \
                    mock.patch("desktop.app.filedialog.askdirectory", return_value=self.temp.name):
                app.download()
            deadline = time.monotonic() + 10
            while app.busy and time.monotonic() < deadline:
                window.update()
                time.sleep(0.01)
            self.assertFalse(app.busy)
            self.assertIsNone(app.last_error)
            self.assertIsNotNone(app.pack)
            self.assertEqual(app.voice.get(), "女声1")
            self.assertEqual(len(self.requests), 3)
            self.assertEqual(json.loads(app.config_path.read_text())["verified_directories"], [str(app.pack.root)])
            self.assertEqual(str(app.progress.cget("mode")), "determinate")
            self.assertEqual(app.progress.cget("value"), 100)
            self.assertEqual(app.model_status.get(), "已校验 · 1 个音色")
        finally:
            app.close()
            deadline = time.monotonic() + 10
            while app.worker.thread.is_alive() and time.monotonic() < deadline:
                window.update()
                time.sleep(0.01)
            self.assertFalse(app.worker.thread.is_alive())
            try:
                window.destroy()
            except tk.TclError:
                pass

    def partial(self, content=b"ab", whole=b"abcd"):
        self.files["voices/female.f32"] = whole
        self.doc["files"][1].update(bytes=len(whole), sha256=hashlib.sha256(whole).hexdigest())
        self.pin()
        path = self.root / "voices" / f".ortts-{hashlib.sha256(whole).hexdigest()}.part"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def response(self, content, status=206, content_range="bytes 2-3/4"):
        response = io.BytesIO(content)
        response.status = status
        response.headers = {"Content-Range": content_range}
        return response

    def resume_opener(self, response):
        def open(url, offset=0):
            if offset:
                self.assertEqual(offset, 2)
                return response
            return self.open(url)
        return mock.patch("desktop.download.open_https", side_effect=open)

    def test_valid_206_resume(self):
        part = self.partial()
        events = []
        with self.resume_opener(self.response(b"cd")):
            pack = download_pack(self.root, "Q4", "ModelScope", transfer=events.append)
        self.assertTrue(pack.unchanged())
        self.assertFalse(part.exists())
        self.assertEqual((self.root / "voices/female.f32").read_bytes(), b"abcd")
        self.assertIn("断点续传", [e["phase"] for e in events])
        self.assertEqual(events[-1]["completed"], events[-1]["total"])

    def test_range_ignored_does_not_append_full_file(self):
        part = self.partial()
        with self.resume_opener(self.response(b"abcd", status=200)):
            download_pack(self.root, "Q4", "ModelScope")
        self.assertEqual((self.root / "voices/female.f32").read_bytes(), b"abcd")
        self.assertEqual(next(part.parent.glob("*.range-ignored-*")).read_bytes(), b"ab")

    def test_wrong_content_range_leaves_prefix_untouched(self):
        part = self.partial()
        with self.resume_opener(self.response(b"cd", content_range="bytes 1-2/4")):
            with self.assertRaisesRegex(ValueError, "范围不匹配"):
                download_pack(self.root, "Q4", "ModelScope")
        self.assertEqual(part.read_bytes(), b"ab")
        self.assertFalse((part.parent / "female.f32").exists())

    def test_bad_partial_sha_is_quarantined_not_promoted(self):
        part = self.partial(b"XX")
        with self.resume_opener(self.response(b"cd")):
            with self.assertRaisesRegex(ValueError, "SHA256"):
                download_pack(self.root, "Q4", "ModelScope")
        self.assertFalse(part.exists())
        self.assertEqual(next(part.parent.glob("*.bad-sha-*")).read_bytes(), b"XXcd")
        download_pack(self.root, "Q4", "ModelScope")
        self.assertEqual((part.parent / "female.f32").read_bytes(), b"abcd")

    def test_full_partial_sha_reused_without_payload(self):
        part = self.partial(b"abcd")
        download_pack(self.root, "Q4", "ModelScope")
        self.assertFalse(part.exists())
        self.assertEqual(len(self.requests), 2)  # Manifest and bridge only.

    def test_partial_symlink_rejected(self):
        part = self.partial()
        part.unlink()
        outside = Path(self.temp.name) / "outside"
        outside.write_bytes(b"keep")
        part.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "越界|软链接"):
            download_pack(self.root, "Q4", "ModelScope")
        self.assertEqual(outside.read_bytes(), b"keep")

    def test_cancellation_after_chunk_resumes_only_remaining_bytes(self):
        part = self.partial(content=b"", whole=b"a" * (1024 * 1024 + 4))
        cancel = threading.Event()
        def transfer(value):
            if value["file"] == "voices/female.f32" and value["completed"] > 2:
                cancel.set()
        with self.assertRaises(Cancelled):
            download_pack(self.root, "Q4", "ModelScope", cancel=cancel, transfer=transfer)
        self.assertEqual(part.stat().st_size, 1024 * 1024)
        cancel.clear()
        def open(url, offset=0):
            if offset:
                self.assertEqual(offset, 1024 * 1024)
                return self.response(b"aaaa", content_range=f"bytes {offset}-{offset + 3}/{offset + 4}")
            return self.open(url)
        with mock.patch("desktop.download.open_https", side_effect=open):
            download_pack(self.root, "Q4", "ModelScope", cancel=cancel)
        self.assertEqual((part.parent / "female.f32").stat().st_size, 1024 * 1024 + 4)

    def test_http_errors_are_actionable(self):
        from urllib.error import HTTPError, URLError
        self.assertIn("切换", download_error(HTTPError("https://example.invalid", 401, "Unauthorized", {}, None)))
        self.assertIn("网络", download_error(URLError("offline")))

    def test_same_directory_writer_lock(self):
        self.root.mkdir()
        with package_lock(self.root):
            with self.assertRaisesRegex(RuntimeError, "另一实例"):
                download_pack(self.root, "Q4", "ModelScope")
        self.assertEqual(self.requests, [])
        download_pack(self.root, "Q4", "ModelScope")

    def test_https_downgrade_rejected_before_following(self):
        with self.assertRaisesRegex(ValueError, "重定向"):
            SecureRedirect().redirect_request(None, None, 302, "", {}, "http://example.invalid")

    def wait_ui(self, window, condition):
        deadline = time.monotonic() + 10
        while not condition() and time.monotonic() < deadline:
            window.update()
            time.sleep(0.01)
        self.assertTrue(condition(), "GUI/worker did not reach expected state")

    def gui(self):
        import tkinter as tk
        from desktop.app import App
        window = tk.Tk()
        app = App(window, state_dir=Path(self.temp.name) / "settings")
        def cleanup():
            app.close()
            self.wait_ui(window, lambda: not app.worker.thread.is_alive())
            try:
                window.destroy()
            except tk.TclError:
                pass
        self.addCleanup(cleanup)
        return window, app

    @skipUnless(os.environ.get("DISPLAY"), "requires X display or xvfb-run")
    def test_gui_decline_download_never_connects(self):
        window, app = self.gui()
        with mock.patch("desktop.app.messagebox.askyesno", return_value=False), \
                mock.patch("desktop.app.filedialog.askdirectory") as choose:
            app.download()
        self.assertEqual(self.requests, [])
        choose.assert_not_called()
        self.assertFalse(app.busy)

    @skipUnless(os.environ.get("DISPLAY"), "requires X display or xvfb-run")
    def test_gui_http_failure_reenables_controls(self):
        from urllib.error import HTTPError
        window, app = self.gui()
        with mock.patch("desktop.app.messagebox.askyesno", return_value=True), \
                mock.patch("desktop.app.filedialog.askdirectory", return_value=self.temp.name), \
                mock.patch("desktop.download.open_https", side_effect=HTTPError("https://example.invalid", 401, "Unauthorized", {}, None)):
            app.download()
            self.wait_ui(window, lambda: not app.busy)
        self.assertIn("401", app.last_error)
        self.assertIn("切换", app.status.get())
        self.assertEqual(str(app.download_button.cget("state")), "normal")
        self.assertEqual(str(app.synth_button.cget("state")), "disabled")
        self.assertIsNone(app.pack)

    @skipUnless(os.environ.get("DISPLAY"), "requires X display or xvfb-run")
    def test_gui_cancel_then_continue(self):
        window, app = self.gui()
        reading, release = threading.Event(), threading.Event()
        class Delayed(io.BytesIO):
            def read(self, size=-1):
                reading.set()
                release.wait(5)
                return super().read(size)
        def open(url, offset=0):
            if url.endswith("voices/female.f32"):
                return Delayed(self.files["voices/female.f32"])
            return self.open(url)
        with mock.patch("desktop.app.messagebox.askyesno", return_value=True), \
                mock.patch("desktop.app.filedialog.askdirectory", return_value=self.temp.name), \
                mock.patch("desktop.download.open_https", side_effect=open):
            try:
                app.download()
                self.wait_ui(window, reading.is_set)
                self.assertEqual(app.stop_button.cget("text"), "取消下载")
                app.stop()
                release.set()
                self.wait_ui(window, lambda: not app.busy)
                self.assertIsNone(app.pack)
                self.assertIsNone(app.last_error)
                self.assertIn("取消", app.status.get())
                self.assertEqual(str(app.download_button.cget("state")), "normal")
                app.download()
                self.wait_ui(window, lambda: not app.busy)
                self.assertIsNotNone(app.pack)
                self.assertIsNone(app.last_error)
                self.assertEqual(len([u for u in self.requests if "MANIFEST.json" in u and "dequant" not in u]), 1)
            finally:
                release.set()

    @skipUnless(os.environ.get("DISPLAY"), "requires X display or xvfb-run")
    def test_gui_cancel_during_network_timeout_is_not_error(self):
        window, app = self.gui()
        connecting, release = threading.Event(), threading.Event()
        def timeout(url, offset=0):
            connecting.set()
            release.wait(5)
            raise TimeoutError("network timed out after cancel")
        with mock.patch("desktop.app.messagebox.askyesno", return_value=True), \
                mock.patch("desktop.app.filedialog.askdirectory", return_value=self.temp.name), \
                mock.patch("desktop.download.open_https", side_effect=timeout):
            try:
                app.download()
                self.wait_ui(window, connecting.is_set)
                app.stop()
                release.set()
                self.wait_ui(window, lambda: not app.busy)
                self.assertIsNone(app.last_error)
                self.assertIn("取消", app.status.get())
            finally:
                release.set()


class StreamTests(TestCase):
    @skipUnless(sys.platform.startswith("linux") and shutil.which("aplay"), "requires Linux alsa-utils")
    def test_alsa_null_pcm_eof_and_stop(self):
        player = StreamPlayer("null")
        self.addCleanup(player.stop)
        for i in range(2):
            player.start_stream()
            player.feed(struct.pack("2400f", *([0.1] * 2400)), 24000)
            if i == 0:
                player.finish()
                player.thread.join(10)
                self.assertFalse(player.thread.is_alive())
                self.assertTrue(player.poll())
            else:
                player.stop()
                self.assertIsNone(player.process)

    def test_callback_queue_bounded(self):
        import queue
        player = StreamPlayer()
        player.active = True
        player.pending = queue.Queue(maxsize=1)
        player.feed(b"\x00" * 4, 24000)
        player.feed(b"\x00" * 4, 24000)
        self.assertTrue(player.aborted.is_set())
        with self.assertRaisesRegex(RuntimeError, "队列已满"):
            player.poll()
        player.stop()
