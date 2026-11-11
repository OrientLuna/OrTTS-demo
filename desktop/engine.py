"""Explicit ctypes ABI1 binding. Create/use/close on one worker thread."""
import ctypes as C
from dataclasses import dataclass
from pathlib import Path
import os
import sys
import threading

from desktop.models import Cancelled


class Config(C.Structure):
    _fields_ = [("struct_size", C.c_uint32), ("asset_root", C.c_char_p),
                ("variant", C.c_char_p), ("speaker_f32", C.c_char_p),
                ("bridge_manifest_sha256", C.c_char_p), ("threads", C.c_int32),
                ("streaming", C.c_int32)]


class Request(C.Structure):
    _fields_ = [("struct_size", C.c_uint32), ("text", C.c_char_p),
                ("seed", C.c_uint64), ("max_tokens", C.c_int32)]


class Metrics(C.Structure):
    _fields_ = [("api_ms", C.c_double), ("callback_ms", C.c_double),
                ("generation_ms", C.c_double), ("first_pcm_ms", C.c_double),
                ("chunks", C.c_size_t)]


Callback = C.CFUNCTYPE(C.c_int, C.c_void_p, C.POINTER(C.c_float), C.c_size_t, C.c_int32)


def default_library():
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "native" / "libortts.dylib"
    return Path(__file__).resolve().parents[1] / "build/pc-engine-macos/install/lib/libortts.dylib"


@dataclass
class Audio:
    f32: bytes
    sample_rate: int
    api_ms: float


class Engine:
    def __init__(self, library=None):
        self.owner = threading.get_ident()
        self.lock = threading.Lock()
        self.handle = C.c_void_p()
        self.key = None
        self.loads = 0
        self.lib = C.CDLL(str(Path(library or default_library()).resolve()))
        signatures = {
            "ortts_abi_version": ([], C.c_uint32),
            "ortts_last_error": ([], C.c_char_p),
            "ortts_engine_create": ([C.POINTER(Config), C.POINTER(C.c_void_p)], C.c_int),
            "ortts_engine_synthesize": ([C.c_void_p, C.POINTER(Request), Callback, C.c_void_p, C.POINTER(C.c_void_p)], C.c_int),
            "ortts_engine_cancel": ([C.c_void_p], None),
            "ortts_engine_free": ([C.c_void_p], None),
            "ortts_audio_samples": ([C.c_void_p], C.POINTER(C.c_float)),
            "ortts_audio_sample_count": ([C.c_void_p], C.c_size_t),
            "ortts_audio_sample_rate": ([C.c_void_p], C.c_int32),
            "ortts_audio_metrics": ([C.c_void_p, C.POINTER(Metrics)], C.c_int),
            "ortts_audio_free": ([C.c_void_p], None),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.lib, name)
            fn.argtypes, fn.restype = args, result
        if self.lib.ortts_abi_version() != 1:
            raise RuntimeError("不支持的 OrTTS ABI（需要 ABI1）")

    def _owner(self):
        if threading.get_ident() != self.owner:
            raise RuntimeError("引擎操作必须在固定 worker 线程")

    def _check(self, status):
        if status:
            message = (self.lib.ortts_last_error() or b"Unknown runtime error").decode("utf-8", "replace")
            if status == 4:
                raise Cancelled(message)
            raise RuntimeError(f"OrTTS ({status}): {message}")

    def load(self, pack, variant="P3", voice="female", threads=4):
        self._owner()
        if variant not in pack.variants or voice not in pack.voices or not 1 <= threads <= 8:
            raise ValueError("当前模型不支持所选变体、音色或线程数")
        key = (pack.root, pack.manifest_sha256, variant, voice, threads)
        if self.key == key:
            return
        self.close()
        # Config owns its bytes through the synchronous create call.
        cfg = Config(C.sizeof(Config), os.fsencode(pack.root), variant.encode(),
                     os.fsencode(pack.root / "voices" / f"{voice}.f32"),
                     pack.bridge_sha256.encode(), threads, 0)
        handle = C.c_void_p()
        self._check(self.lib.ortts_engine_create(C.byref(cfg), C.byref(handle)))
        with self.lock:
            self.handle, self.key = handle, key
        self.loads += 1

    def synthesize(self, text, cancel, max_tokens=513):
        self._owner()
        if not self.handle or not text.strip() or not 1 <= max_tokens <= 513:
            raise ValueError("请先加载模型并输入文字")
        if cancel.is_set():
            raise Cancelled("已停止")
        req = Request(C.sizeof(Request), text.encode("utf-8"), 42, max_tokens)
        result = C.c_void_p()
        try:
            self._check(self.lib.ortts_engine_synthesize(self.handle, C.byref(req), Callback(), None, C.byref(result)))
            if cancel.is_set():
                raise Cancelled("已停止，丢弃本次结果")
            count = self.lib.ortts_audio_sample_count(result)
            rate = self.lib.ortts_audio_sample_rate(result)
            ptr = self.lib.ortts_audio_samples(result)
            if not ptr or not 0 < count <= 24000 * 600 or rate != 24000:
                raise RuntimeError("运行时返回无效音频")
            metrics = Metrics()
            self._check(self.lib.ortts_audio_metrics(result, C.byref(metrics)))
            return Audio(C.string_at(ptr, count * C.sizeof(C.c_float)), rate, metrics.api_ms)
        finally:
            if result:
                self.lib.ortts_audio_free(result)

    def cancel(self):
        # Only cross-thread operation; lock excludes free/replacement, not inference.
        with self.lock:
            if self.handle:
                self.lib.ortts_engine_cancel(self.handle)

    def close(self):
        self._owner()
        with self.lock:
            if self.handle:
                self.lib.ortts_engine_free(self.handle)
                self.handle = C.c_void_p()
            self.key = None
