"""Finite, clipped PCM16 WAV export and system playback, no extra audio backend."""
from array import array
from pathlib import Path
import math
import shutil
import subprocess
import sys
import wave


def write_wav(audio, path):
    floats = array("f")
    floats.frombytes(audio.f32)
    if not floats or not all(math.isfinite(v) for v in floats):
        raise ValueError("音频为空或包含 NaN/Inf")
    pcm = array("h", (round(max(-1.0, min(1.0, v)) * 32767) for v in floats))
    if sys.byteorder != "little":
        pcm.byteswap()
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(audio.sample_rate)
        wav.writeframes(pcm.tobytes())


class Player:
    def __init__(self):
        self.process = None

    def play(self, path):
        self.stop()
        command = "/usr/bin/afplay" if sys.platform == "darwin" else shutil.which("aplay")
        if not command:
            raise RuntimeError("未找到系统播放器，仍可保存 WAV")
        self.process = subprocess.Popen([command, str(Path(path).resolve())],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    def poll(self):
        if self.process is None or self.process.poll() is None:
            return None
        process, self.process = self.process, None
        error = process.communicate()[1].decode("utf-8", "replace").strip()
        if process.returncode:
            raise RuntimeError(f"播放失败 ({process.returncode})：{error}；仍可保存 WAV")
        return True

    def stop(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
            try:
                self.process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.communicate()
            self.process = None
