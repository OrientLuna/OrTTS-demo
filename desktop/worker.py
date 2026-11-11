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
    def __init__(self, output_dir, library=None, idle_seconds=300):
        self.commands = queue.Queue()
        self.events = queue.Queue()
        self.cancelled = threading.Event()
        self.closing = threading.Event()
        self.engine_lock = threading.Lock()
        self.engine = None
        self.output_dir = Path(output_dir)
        self.library = library
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
                    if action == "import":
                        if self.engine:
                            self.engine.close()
                        pack = None
                        pack = verify_pack(args["directory"], args["package"], self._status, self.cancelled)
                        self.events.put(("imported", pack))
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
                        self._status("加载模型 / 合成中…（离线推理停止可能需等待当前计算结束）")
                        self.engine.load(pack, args["variant"], args["voice"], args["threads"])
                        audio = self.engine.synthesize(args["text"], self.cancelled)
                        self.output_dir.mkdir(parents=True, exist_ok=True)
                        path = self.output_dir / f"ortts-{time.time_ns()}.wav"
                        write_wav(audio, path)
                        if self.cancelled.is_set():
                            path.unlink(missing_ok=True)
                            raise Cancelled("已停止")
                        self.events.put(("audio", {"path": path, "seconds": len(audio.f32) / 4 / audio.sample_rate,
                                                   "api_ms": audio.api_ms, "loads": self.engine.loads}))
                    else:
                        raise ValueError(f"未知任务：{action}")
                except Cancelled:
                    self.events.put(("cancelled", "已停止"))
                except Exception as exc:
                    self.events.put(("error", str(exc)))
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
