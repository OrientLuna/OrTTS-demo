"""Opt-in real GUI/native acceptance. ALSA null is NOT an audible device test."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import time
import tkinter as tk
from tkinter import filedialog
import wave

from desktop.app import App
from desktop.audio import write_wav
from desktop.engine import Audio
from linux.audio import StreamPlayer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    app = App(root, args.library, args.output / "state", stream_player=StreamPlayer("null"))
    report = {"status": "running", "platform": platform.platform(), "audible_test": "not performed; ALSA null",
              "library_sha256": hashlib.sha256(args.library.read_bytes()).hexdigest(), "checks": [], "audio": []}
    stage, seen_chunks = 0, 0
    pcm_blocks = []
    started = time.monotonic()
    original_sink = app.worker.pcm_sink

    def sink(pcm, rate):
        nonlocal seen_chunks
        seen_chunks += 1
        pcm_blocks.append(pcm)
        original_sink(pcm, rate)
    app.worker.pcm_sink = sink

    def text(value):
        app.text.delete("1.0", "end")
        app.text.insert("1.0", value)

    def record(name):
        info = app.last_audio.copy()
        assert info["chunks"] > 0 and info["first_pcm_ms"] >= 0
        with wave.open(str(app.wav)) as wav:
            assert wav.getframerate() == 24000 and wav.getnchannels() == 1
            assert wav.getnframes() > 0
        callback_wav = args.output / f"{name}-callback.wav"
        write_wav(Audio(b"".join(pcm_blocks), 24000, 0), callback_wav)
        assert callback_wav.read_bytes() == app.wav.read_bytes(), "PCM callbacks lost/duplicated tail samples"
        info["callback_matches_complete_wav"] = True
        pcm_blocks.clear()
        info["name"] = name
        report["audio"].append(info)

    def capture(name):
        from PIL import ImageGrab
        root.update_idletasks()
        x, y = root.winfo_rootx(), root.winfo_rooty()
        ImageGrab.grab(bbox=(x, y, x + root.winfo_width(), y + root.winfo_height())).save(args.output / name)

    def tick():
        nonlocal stage, seen_chunks
        try:
            if time.monotonic() - started > 900:
                raise TimeoutError("GUI smoke timed out")
            if app.last_error:
                raise RuntimeError(app.last_error)
            if stage == 0:
                capture("window.png")
                app.import_directory(args.model)
                stage = 1
            elif stage == 1 and not app.busy:
                assert app.pack and app.pack.variants == ("P3",)
                assert "male" in app.pack.voices
                report["checks"].append("trusted_q4_import_four_voices_p3_only")
                text("你好，欢迎使用本地语音合成。")
                app.synthesize()
                stage = 2
            elif stage == 2 and not app.busy:
                record("female_short")
                assert seen_chunks > 0
                capture("synthesis.png")
                destination = args.output / "saved.wav"
                original = filedialog.asksaveasfilename
                filedialog.asksaveasfilename = lambda **kw: str(destination)
                try:
                    app.save()
                finally:
                    filedialog.asksaveasfilename = original
                assert destination.read_bytes() == app.wav.read_bytes()
                app.play()
                report["checks"].append("gui_stream_callbacks_save_replay")
                app.voice.set("男声1")
                text("今天我们在电脑上体验本地语音合成。模型不需要连接云端推理，输入文字后就可以生成声音。你可以选择不同的音色，也可以随时停止播放，最后把完整的语音保存下来。")
                app.synthesize()
                stage = 3
            elif stage == 3 and not app.busy:
                record("male_long")
                report["checks"].append("male_long_stream_eof")
                app.release()
                stage = 4
            elif stage == 4 and not app.busy:
                assert not app.worker.engine.handle
                text("这是一段用来测试流式停止的文字，收到第一段声音后我们将停止合成。")
                seen_chunks = 0
                app.synthesize()
                stage = 5
            elif stage == 5 and seen_chunks:
                app.stop()
                stage = 6
            elif stage == 6 and not app.busy:
                report["checks"].append("release_reload_cancel_at_pcm_boundary")
                assert not app.player.active
                pcm_blocks.clear()
                text("停止后可以继续合成。")
                app.synthesize()
                stage = 7
            elif stage == 7 and not app.busy:
                record("after_cancel")
                assert app.last_audio["loads"] == 3
                report["checks"].append("post_cancel_handle_reuse")
                report["status"] = "passed"
                app.close()
                return
        except Exception as exc:
            report.update(status="failed", error=str(exc))
            app.close()
            return
        root.after(50, tick)

    root.after(200, tick)
    root.mainloop()
    report["worker_joined"] = not app.worker.thread.is_alive()
    report["elapsed_seconds"] = time.monotonic() - started
    (args.output / "REPORT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str), flush=True)
    if report["status"] != "passed" or not report["worker_joined"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
