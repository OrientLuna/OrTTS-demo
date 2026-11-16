"""Catalog-backed speech tasks. Native handles stay on the task worker thread."""
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import wave
from array import array

from desktop.audio import write_wav
from desktop.download import check_cancel, guarded_target, package_lock, receive_file
from desktop.engine import Audio, default_library
from desktop.models import Cancelled


def resources():
    return Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]


def catalog(library=None):
    root = resources() / "runtime/models"
    models = json.loads((root / "catalog.example.json").read_text())["models"]
    models += [m for m in json.loads((root / "asr-android-experiment.json").read_text())["models"]
               if m["family"] == "streaming_paraformer"]
    lib = C.CDLL(str(library or default_library()))
    if not hasattr(lib, "ortts_speech_catalog_json"):
        return []
    lib.ortts_speech_catalog_json.restype = C.c_char_p
    capabilities = json.loads(lib.ortts_speech_catalog_json())
    families = set(capabilities.get("tts", []) + capabilities.get("asr", []) + capabilities.get("compatibility_asr", {}).get("families", []))
    return [m for m in models if m.get("demo_enabled") and m["family"] in families
            and (m["family"] != "streaming_paraformer" or hasattr(lib, "ortts_asr_stream_create"))]


def verify_asset(path, asset, cancel):
    if not path.is_file() or path.stat().st_size != asset["bytes"]:
        return False
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(1024 * 1024):
            check_cancel(cancel)
            h.update(block)
    return h.hexdigest() == asset["sha256"]


def prepare(model, root, cancel, notify, source=None, download=False):
    """Reuse the existing resumable, SHA-pinned, no-clobber asset installer."""
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with package_lock(root):
        for asset in model["assets"]:
            check_cancel(cancel)
            target = guarded_target(root, asset["path"])
            notify("status", "校验：" + asset["path"])
            if verify_asset(target, asset, cancel):
                continue
            if target.exists():
                raise ValueError("本地文件校验失败，请移走后重新导入：" + str(target))
            if source is None and not download:
                raise ValueError("请先下载或导入所选模型")
            target.parent.mkdir(parents=True, exist_ok=True)
            local = None
            if source is not None:
                candidates = [Path(source) / asset["path"]]
                # Accept either the catalog root or the model's own directory.
                prefix = Path(model["model_path"])
                try:
                    candidates.append(Path(source) / Path(asset["path"]).relative_to(prefix))
                except ValueError:
                    candidates.append(Path(source) / Path(asset["path"]).name)
                local = next((p for p in candidates if p.is_file()), None)
                if local is None:
                    raise ValueError("导入目录缺少：" + asset["path"])
            receive_file(root, target, asset, asset["url"], local,
                         lambda text: notify("status", text), cancel,
                         lambda received, transferred, phase: notify("status", f"{phase} · {target.name} · {received / asset['bytes']:.0%}"))


class Config(C.Structure):
    _fields_ = [("size", C.c_uint32), ("family", C.c_char_p), ("path", C.c_char_p),
                ("threads", C.c_int32), ("streaming", C.c_int32), ("options", C.c_void_p),
                ("option_count", C.c_size_t), ("espeak", C.c_char_p), ("data", C.c_char_p),
                ("max_frames", C.c_size_t)]


class Request(C.Structure):
    _fields_ = [("size", C.c_uint32), ("text", C.c_char_p), ("language", C.c_char_p),
                ("voice", C.c_char_p), ("seed_set", C.c_int32), ("seed", C.c_uint64),
                ("options", C.c_void_p), ("option_count", C.c_size_t), ("reference", C.c_void_p),
                ("frames", C.c_size_t), ("rate", C.c_int32), ("channels", C.c_int32), ("reference_text", C.c_char_p)]


class StreamConfig(C.Structure):
    _fields_ = [("size", C.c_uint32), ("update", C.c_uint32), ("partial", C.c_uint32),
                ("limit", C.c_uint32), ("silence", C.c_uint32), ("energy", C.c_float)]


class Event(C.Structure):
    _fields_ = [("size", C.c_uint32), ("endpoint", C.c_int32), ("segment", C.c_uint64),
                ("start", C.c_uint64), ("end", C.c_uint64), ("revision", C.c_uint64),
                ("text", C.c_char_p), ("language", C.c_char_p)]


TextCallback = C.CFUNCTYPE(C.c_int, C.c_void_p, C.POINTER(Event))
PCMCallback = C.CFUNCTYPE(C.c_int, C.c_void_p, C.POINTER(C.c_float), C.c_size_t, C.c_int32, C.c_int32)


class SpeechTask:
    def __init__(self, library, cancel, notify):
        self.lib = C.CDLL(str(library or default_library()))
        self.cancelled, self.notify = cancel, notify
        self.lock = threading.Lock()
        self.handle, self.kind = C.c_void_p(), None
        p, n, f = C.c_void_p, C.c_size_t, C.POINTER(C.c_float)
        signatures = {
            "ortts_last_error": ([], C.c_char_p),
            "ortts_tts_synthesize": ([p, C.POINTER(Request), PCMCallback, p, C.POINTER(p)], C.c_int),
            "ortts_speech_audio_samples": ([p], f), "ortts_speech_audio_frames": ([p], n),
            "ortts_speech_audio_sample_rate": ([p], C.c_int32), "ortts_speech_audio_channels": ([p], C.c_int32),
            "ortts_speech_audio_free": ([p], None), "ortts_transcript_text": ([p], C.c_char_p),
            "ortts_transcript_free": ([p], None),
            "ortts_asr_run": ([p, f, n, C.c_char_p, C.POINTER(p)], C.c_int),
            "ortts_asr_stream_create": ([C.POINTER(Config), C.POINTER(StreamConfig), C.POINTER(p)], C.c_int),
            "ortts_asr_stream_accept": ([p, f, n, TextCallback, p], C.c_int),
            "ortts_asr_stream_finish": ([p, TextCallback, p], C.c_int),
        }
        for kind in ("tts", "asr", "asr_stream"):
            for action in ("cancel", "free"):
                signatures[f"ortts_{kind}_{action}"] = ([p], None)
            if kind != "asr_stream":
                signatures[f"ortts_{kind}_create"] = ([C.POINTER(Config), C.POINTER(p)], C.c_int)
        for name, (args, result) in signatures.items():
            fn = getattr(self.lib, name, None)
            if fn is None:
                continue  # Additive APIs may be absent in older runtimes.
            fn.argtypes, fn.restype = args, result

    def check(self, code):
        if code:
            message = (self.lib.ortts_last_error() or b"Native error").decode("utf-8", "replace")
            if code == 4:
                raise Cancelled(message)
            raise RuntimeError(message)
        check_cancel(self.cancelled)

    def cancel(self):
        self.cancelled.set()
        with self.lock:
            if self.handle:
                cancel = getattr(self.lib, f"ortts_{self.kind}_cancel", None)
                if cancel:
                    cancel(self.handle)

    def run(self, model, root, output, text="", voice="", audio=None):
        check_cancel(self.cancelled)
        stream = model["family"] in ("moonshine_asr", "streaming_paraformer") and hasattr(self.lib, "ortts_asr_stream_create")
        kind = "tts" if model["task"] == "tts" else "asr_stream" if stream else "asr"
        cfg = Config(C.sizeof(Config), model["family"].encode(), os.fsencode(Path(root) / model["model_path"]), 2, int(stream))
        if model.get("external_espeak"):
            base = resources()
            lib_name = "libespeak-ng.dylib" if sys.platform == "darwin" else "libespeak-ng.so.1"
            library = base / "native" / lib_name
            data = base / "espeak-ng-data"
            if not getattr(sys, "frozen", False):
                if sys.platform == "darwin":
                    library, data = Path("/opt/homebrew/lib/libespeak-ng.dylib"), Path("/opt/homebrew/share/espeak-ng-data")
                else:
                    library = next((p for p in (Path("/usr/lib/x86_64-linux-gnu/libespeak-ng.so.1"), Path("/usr/lib/aarch64-linux-gnu/libespeak-ng.so.1"), Path("/usr/lib/libespeak-ng.so.1")) if p.is_file()), library)
                    data = next((p for p in (Path("/usr/lib/x86_64-linux-gnu/espeak-ng-data"), Path("/usr/lib/aarch64-linux-gnu/espeak-ng-data"), Path("/usr/share/espeak-ng-data")) if p.is_dir()), data)
            if not library.is_file() or not data.is_dir():
                raise ValueError("此模型需要随 App 打包的 eSpeak NG")
            cfg.espeak, cfg.data = os.fsencode(library), os.fsencode(data)
        handle = C.c_void_p()
        result = C.c_void_p()
        self.notify("status", "正在加载模型…")
        try:
            if stream:
                settings = StreamConfig(C.sizeof(StreamConfig), 200, 400, 15000, 0 if model["family"] == "streaming_paraformer" else 800, .003)
                code = self.lib.ortts_asr_stream_create(C.byref(cfg), C.byref(settings), C.byref(handle))
            else:
                code = getattr(self.lib, f"ortts_{kind}_create")(C.byref(cfg), C.byref(handle))
            with self.lock:
                self.handle, self.kind = handle, kind
            self.check(code)
            if kind == "tts":
                self.notify("status", "正在合成…")
                request = Request(C.sizeof(Request), text.encode(), b"zh" if voice.startswith("z") else b"en", voice.encode() or None, 1, 42)
                callback = PCMCallback()
                self.check(self.lib.ortts_tts_synthesize(handle, C.byref(request), callback, None, C.byref(result)))
                frames = self.lib.ortts_speech_audio_frames(result)
                rate = self.lib.ortts_speech_audio_sample_rate(result)
                if self.lib.ortts_speech_audio_channels(result) != 1 or not 0 < frames <= rate * 600:
                    raise ValueError("无效的合成音频")
                samples = C.string_at(self.lib.ortts_speech_audio_samples(result), frames * 4)
                check_cancel(self.cancelled)
                write_wav(Audio(samples, rate, 0), output)
                self.notify("audio", str(output))
            else:
                pcm = read_audio(audio, self.cancelled)
                self.notify("status", f"正在识别 {len(pcm)/16000:.2f} 秒音频…")
                values = (C.c_float * len(pcm)).from_buffer(pcm)
                if stream:
                    finals = {}
                    def on_text(user, ptr):
                        event = ptr.contents
                        value = (event.text or b"").decode("utf-8", "replace")
                        if event.endpoint:
                            finals[event.segment] = value
                        lines = [finals[k] for k in sorted(finals)]
                        if not event.endpoint:
                            lines.append("识别中：" + value)
                        self.notify("text", "\n".join(lines))
                        return int(self.cancelled.is_set())
                    callback = TextCallback(on_text)
                    for offset in range(0, len(pcm), 1600):
                        check_cancel(self.cancelled)
                        chunk = C.cast(C.byref(values, offset * 4), C.POINTER(C.c_float))
                        self.check(self.lib.ortts_asr_stream_accept(handle, chunk, min(1600, len(pcm)-offset), callback, None))
                    self.check(self.lib.ortts_asr_stream_finish(handle, callback, None))
                else:
                    self.check(self.lib.ortts_asr_run(handle, values, len(pcm), None, C.byref(result)))
                    self.notify("text", (self.lib.ortts_transcript_text(result) or b"").decode("utf-8", "replace"))
        finally:
            if result:
                (self.lib.ortts_speech_audio_free if kind == "tts" else self.lib.ortts_transcript_free)(result)
            with self.lock:
                self.handle = C.c_void_p()
                if handle:
                    getattr(self.lib, f"ortts_{kind}_free")(handle)


def read_audio(path, cancel):
    """System decoder handles WAV/CAF/MP3/M4A; native ASR receives 16k mono only."""
    with tempfile.TemporaryDirectory(prefix="ortts-audio-") as temp:
        converted = Path(temp) / "input.wav"
        if sys.platform == "darwin":
            subprocess.run(["/usr/bin/afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(path), str(converted)], check=True, capture_output=True, timeout=90)
        else:
            use_direct = False
            if str(path).lower().endswith(".wav"):
                try:
                    with wave.open(str(path), "rb") as w:
                        use_direct = (w.getnchannels() == 1 and w.getframerate() == 16000 and w.getsampwidth() == 2)
                except wave.Error:
                    use_direct = False
            if use_direct:
                converted = Path(path)
            else:
                subprocess.run(["ffmpeg", "-y", "-i", str(path), "-ar", "16000", "-ac", "1", "-sample_fmt", "s16", str(converted)], check=True, capture_output=True, timeout=90)
        check_cancel(cancel)
        with wave.open(str(converted), "rb") as wav:
            if wav.getnframes() > 16000 * 60 or not wav.getnframes():
                raise ValueError("请选择 0–60 秒的音频文件")
            pcm = array("h", wav.readframes(wav.getnframes()))
            if sys.byteorder != "little":
                pcm.byteswap()
        return array("f", (v / 32768 for v in pcm))
