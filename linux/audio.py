"""Bounded PCM queue; only the playback thread writes to the ALSA subprocess."""
from array import array
import math
import queue
import shutil
import subprocess
import sys
import threading

from desktop.audio import Player


class StreamPlayer(Player):
    def __init__(self, device=None):
        super().__init__()
        self.device = device
        self.thread = None
        self.pending = None
        self.aborted = threading.Event()
        self.errors = queue.Queue()
        self.finished = queue.Queue()
        self.active = False

    def start_stream(self):
        self.stop()
        self.aborted.clear()
        self.pending = queue.Queue(maxsize=128)
        self.active = True
        self.thread = threading.Thread(target=self._play_stream, name="ortts-playback", daemon=False)
        self.thread.start()

    def play(self, path):
        if not self.device:
            return super().play(path)
        self.stop()
        command = shutil.which("aplay")
        if not command:
            raise RuntimeError("未找到 aplay，仍可保存 WAV")
        self.process = subprocess.Popen([command, "-q", "-D", self.device, str(path)],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    def feed(self, pcm, rate):
        if rate != 24000:
            raise ValueError("只支持 24 kHz PCM")
        if self.active and not self.aborted.is_set():
            try:
                self.pending.put_nowait(pcm)
            except queue.Full:
                # Never block the native callback or grow memory without bounds.
                self.errors.put("播放队列已满，本次流式播放停止；合成结果仍可保存。")
                self.aborted.set()

    def finish(self):
        if self.active and not self.aborted.is_set():
            try:
                self.pending.put_nowait(None)
            except queue.Full:
                self.errors.put("播放队列已满，停止播放；完整 WAV 仍可保存。")
                self.aborted.set()

    def _play_stream(self):
        process = None
        try:
            command = shutil.which("aplay")
            if not command:
                raise RuntimeError("未找到 aplay，请安装 alsa-utils；仍可保存 WAV")
            args = [command, "-q", "-t", "raw", "-f", "S16_LE", "-r", "24000", "-c", "1"]
            if self.device:
                args += ["-D", self.device]
            # No stderr pipe: an unattended backend must never fill a pipe and deadlock.
            process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
            self.process = process
            while not self.aborted.is_set():
                try:
                    block = self.pending.get(timeout=0.1)
                except queue.Empty:
                    continue
                if block is None:
                    break
                floats = array("f")
                floats.frombytes(block)
                if not all(math.isfinite(v) for v in floats):
                    raise ValueError("播放数据包含 NaN/Inf")
                pcm = array("h", (round(max(-1., min(1., v)) * 32767) for v in floats))
                if sys.byteorder != "little":
                    pcm.byteswap()
                process.stdin.write(pcm.tobytes())
            process.stdin.close()
            if self.aborted.is_set() and process.poll() is None:
                process.terminate()
            code = process.wait(timeout=15)
            if code and not self.aborted.is_set():
                raise RuntimeError(f"音频设备不可用 (aplay {code})；仍可保存 WAV")
            if not self.aborted.is_set():
                self.finished.put(True)
        except Exception as exc:
            if not self.aborted.is_set():
                self.errors.put(f"流式播放失败：{exc}；仍可保存 WAV")
        finally:
            if process:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                if process.stdin and not process.stdin.closed:
                    try:
                        process.stdin.close()
                    except OSError:
                        pass
            self.active = False

    def poll(self):
        try:
            raise RuntimeError(self.errors.get_nowait())
        except queue.Empty:
            pass
        if self.thread is not None:
            if self.thread.is_alive():
                return None
            self.thread.join()
            self.thread = None
            self.process = None
            try:
                return self.finished.get_nowait()
            except queue.Empty:
                return None
        return super().poll()

    def stop(self):
        if self.thread is not None:
            self.aborted.set()
            # Break a blocked pipe write before joining its owner.
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()
            self.thread.join(timeout=3)
            if self.thread.is_alive() and self.process is not None:
                self.process.kill()
                self.thread.join(timeout=3)
            if self.thread.is_alive():
                raise RuntimeError("播放线程未能安全退出")
            self.thread = None
            self.process = None
        self.active = False
        self.pending = None
        for events in (self.errors, self.finished):
            while True:
                try:
                    events.get_nowait()
                except queue.Empty:
                    break
        super().stop()
