"""Single queue-driven owner of native engine and model verification."""
from pathlib import Path
import queue
import threading
import time
import traceback

from desktop.audio import write_wav
from desktop.engine import Engine
from desktop.models import Cancelled, verify_pack


class Worker:
    def __init__(self, output_dir, library=None, idle_seconds=300, pcm_sink=None):
        self.commands = queue.Queue()
        self.events = queue.Queue()
        self.cancelled = threading.Event()
        self.closing = threading.Event()
        self.engine_lock = threading.Lock()
        self.engine = None
        self.output_dir = Path(output_dir)
        self.library = library
        self.pcm_sink = pcm_sink
        self.idle_seconds = idle_seconds
        self.thread = threading.Thread(target=self._run, name="ortts-inference", daemon=False)
        self.thread.start()

    def submit(self, action, **args):
        self.cancelled.clear()
        self.commands.put((action, args))

    def cancel(self):
        self.cancelled.set()
        with self.engine_lock:
            if self.engine:
                self.engine.cancel()

    def shutdown(self):
        self.closing.set()
        self.cancel()
        self.commands.put(("quit", {}))

    def _status(self, text):
        self.events.put(("status", text))

    def _transfer(self, value):
        now = time.monotonic()
        if now - getattr(self, "last_transfer", 0) >= 0.1 or value["completed"] == value["total"]:
            self.last_transfer = now
            self.events.put(("transfer", value))

    def _run(self):
        pack = None
        last_used = time.monotonic()
        try:
            while not self.closing.is_set():
                try:
                    action, args = self.commands.get(timeout=1)
                except queue.Empty:
                    if self.engine and self.engine.handle and time.monotonic() - last_used > self.idle_seconds:
                        self.engine.close()
                        self._status("空闲已释放模型，下次合成会重新加载")
                    continue
                if action == "quit" or self.closing.is_set():
                    break
                try:
                    if action == "download":
                        from desktop.download import download_pack
                        if self.engine:
                            self.engine.close()
                        pack = None
                        pack = download_pack(args["directory"], args["package"], args["channel"],
                                             self._status, self.cancelled, args.get("reuse_roots", ()), self._transfer)
                        self.events.put(("imported", pack))
                    elif action == "import":
                        if self.engine:
                            self.engine.close()
                        pack = None
                        pack = verify_pack(args["directory"], args["package"], self._status, self.cancelled)
                        self.events.put(("imported", pack))
                    elif action == "unload":
                        if self.engine:
                            self.engine.close()
                        self._status("模型已释放，下次合成将重新加载")
                        self.events.put(("unloaded", None))
                    elif action == "release":
                        if self.engine:
                            self.engine.close()
                        pack = None
                        self.events.put(("released", None))
                    elif action == "synthesize":
                        if pack is None:
                            raise ValueError("请先校验并导入本地模型目录")
                        if not pack.unchanged():
                            if self.engine:
                                self.engine.close()
                            pack = verify_pack(pack.root, pack.package, self._status, self.cancelled)
                        if self.cancelled.is_set():
                            raise Cancelled("已停止")
                        if self.engine is None:
                            engine = Engine(self.library)
                            with self.engine_lock:
                                self.engine = engine
                        self._status("加载模型 / 流式合成中…" if self.pcm_sink else "加载模型 / 合成中…（离线推理停止可能需等待当前计算结束）")
                        self.engine.load(pack, args["variant"], args["voice"], args["threads"], streaming=self.pcm_sink is not None,
                                         cancel=self.cancelled)
                        audio = self.engine.synthesize(args["text"], self.cancelled, pcm_sink=self.pcm_sink)
                        self.output_dir.mkdir(parents=True, exist_ok=True)
                        path = self.output_dir / f"ortts-{time.time_ns()}.wav"
                        write_wav(audio, path)
                        if self.cancelled.is_set():
                            path.unlink(missing_ok=True)
                            raise Cancelled("已停止")
                        self.events.put(("audio", {"path": path, "seconds": len(audio.f32) / 4 / audio.sample_rate,
                                                   "api_ms": audio.api_ms, "loads": self.engine.loads,
                                                   "first_pcm_ms": audio.first_pcm_ms, "chunks": audio.chunks}))
                    else:
                        raise ValueError(f"未知任务：{action}")
                except Cancelled:
                    message = "下载已取消，可以选择相同位置继续。" if action == "download" else "校验已取消，原文件未修改。" if action == "import" else "已停止"
                    if action == "synthesize" and self.engine and self.engine.handle:
                        message = "已停止 · 模型保持加载，可继续合成"
                    self.events.put(("cancelled", message))
                except Exception as exc:
                    if self.cancelled.is_set() and action in ("download", "import"):
                        self.events.put(("cancelled", "操作已取消，已有文件与断点保留。"))
                    else:
                        if action == "download":
                            from desktop.download import download_error
                            message = download_error(exc)
                        else:
                            message = str(exc)
                        self.events.put(("error", message))
                        self.output_dir.mkdir(parents=True, exist_ok=True)
                        with (self.output_dir.parent / "desktop-errors.log").open("a") as log:
                            traceback.print_exc(file=log)
                finally:
                    last_used = time.monotonic()
                    self.events.put(("done", None))
        finally:
            with self.engine_lock:
                if self.engine:
                    self.engine.close()
                    self.engine = None
            self.events.put(("closed", None))
