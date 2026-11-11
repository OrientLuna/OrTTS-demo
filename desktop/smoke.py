"""Opt-in acceptance tests against real local weights; never download models."""
from pathlib import Path
import ctypes
import json
import platform
import threading
import time
import wave

from desktop.audio import Player, write_wav
from desktop.engine import Config, Engine, Request, default_library
from desktop.models import Cancelled, PACKAGES, sha256_file, verify_pack


def save_report(args, report):
    text = json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text)
    print(text, flush=True)


def run(args):
    output = Path(args.state_dir or Path.home() / "Library/Application Support/OrTTS Desktop") / "smoke"
    output.mkdir(parents=True, exist_ok=True)
    lib = args.library or default_library()
    report = {"platform": platform.platform(), "machine": platform.machine(),
              "library": str(lib), "library_sha256": sha256_file(lib),
              "config_size": ctypes.sizeof(Config), "request_size": ctypes.sizeof(Request), "checks": []}
    engine = None
    try:
        pack = verify_pack(args.smoke, args.package)
        report.update(model_revision=PACKAGES[args.package][1], model_sha256=pack.manifest_sha256,
                      bridge_sha256=pack.bridge_sha256, voices=pack.voices)
        report["checks"].append("full_manifest_and_file_verification")
        engine = Engine(lib)
        cancel = threading.Event()
        engine.load(pack)
        for name, text in [("zh", "你好，欢迎使用本地语音合成。"), ("en", "Hello, welcome to local speech synthesis.")]:
            audio = engine.synthesize(text, cancel)
            path = output / f"{name}.wav"
            write_wav(audio, path)
            with wave.open(str(path)) as wav:
                assert wav.getnchannels() == 1 and wav.getsampwidth() == 2 and wav.getframerate() == 24000
                assert wav.getnframes() > 0
            report[name] = {"path": str(path), "frames": len(audio.f32) // 4, "sample_rate": audio.sample_rate}
        assert engine.loads == 1
        report["checks"].append("zh_en_pcm16_and_handle_reuse")
        player = Player()
        try:
            player.play(output / "zh.wav")
            player.process.communicate(timeout=120)
            player.poll()
            report["checks"].append("afplay_complete")
            player.play(output / "en.wav")
            player.stop()
            report["checks"].append("afplay_stop")
        finally:
            player.stop()
        engine.close()
        engine.load(pack, voice=pack.voices[-1])
        assert engine.loads == 2
        write_wav(engine.synthesize("模型已重新加载。", cancel), output / "reload.wav")
        report["checks"].append("release_reload_other_voice")
        # Offline cancel can only discard the result; do not promise immediate interruption.
        timer = threading.Timer(0.2, lambda: (cancel.set(), engine.cancel()))
        timer.start()
        try:
            try:
                engine.synthesize("这是一段用于验证安全停止的测试文字。", cancel)
                raise AssertionError("Cancellation did not discard the result")
            except Cancelled:
                report["checks"].append("cross_thread_offline_cancel")
        finally:
            timer.join()
        cancel.clear()
        write_wav(engine.synthesize("停止后可以继续合成。", cancel), output / "after-cancel.wav")
        report["checks"].append("synthesis_after_cancel")
        if "P5" in pack.variants:
            engine.load(pack, variant="P5")
            write_wav(engine.synthesize("这是标准版本的语音测试。", cancel), output / "p5.wav")
            report["checks"].append("p5_variant_switch_and_synthesis")
        report["status"] = "passed"
    except Exception as exc:
        report.update(status="failed", error=str(exc))
        raise
    finally:
        if engine:
            engine.close()
        save_report(args, report)


def ui_run(app, args):
    """Drive real Tk event/worker queues including save, playback, cancel and close."""
    from tkinter import filedialog
    report = {"checks": [], "status": "running"}
    started = time.monotonic()
    stage = 0
    due = 0
    app.autoplay.set(False)
    app.package.set(PACKAGES[args.package][0])
    app.import_directory(args.ui_smoke)

    def tick():
        nonlocal stage, due
        try:
            if time.monotonic() - started > 600:
                raise TimeoutError("GUI smoke timeout")
            if app.last_error:
                raise RuntimeError(app.last_error)
            if stage == 0 and not app.busy:
                assert app.pack and app.voice.get() == "女声1"
                assert len(app.voice_box.cget("values")) == len(app.pack.voices)
                report["checks"].append("window_import_actual_voices")
                app.synthesize()
                stage = 1
            elif stage == 1 and not app.busy:
                assert app.wav and app.wav.is_file()
                destination = app.home / "gui-saved.wav"
                original = filedialog.asksaveasfilename
                filedialog.asksaveasfilename = lambda **kw: str(destination)
                try:
                    app.save()
                finally:
                    filedialog.asksaveasfilename = original
                assert destination.read_bytes() == app.wav.read_bytes()
                report["checks"].append("gui_synthesis_save_wav")
                app.play()
                due = time.monotonic() + 0.5
                stage = 2
            elif stage == 2 and time.monotonic() >= due:
                assert app.player.process is not None
                app.stop()
                assert app.player.process is None
                report["checks"].append("gui_play_and_stop")
                app.text.delete("1.0", "end")
                app.text.insert("1.0", "Hello, this is the desktop demo.")
                app.synthesize()
                stage = 3
            elif stage == 3 and not app.busy:
                assert app.last_audio["loads"] == 1
                report["checks"].append("gui_english_reuse")
                app.synthesize()
                due = time.monotonic() + 0.3
                stage = 4
            elif stage == 4 and time.monotonic() >= due:
                app.stop()
                report["checks"].append("gui_cancel_requested")
                stage = 5
            elif stage == 5 and not app.busy:
                app.synthesize()
                due = time.monotonic() + 0.3
                stage = 6
            elif stage == 6 and time.monotonic() >= due:
                app.close()
                stage = 7
            elif stage == 7 and not app.worker.thread.is_alive():
                report["checks"].append("gui_exit_during_inference_joined")
                report["status"] = "passed"
                save_report(args, report)
                return
        except Exception as exc:
            report.update(status="failed", error=str(exc))
            save_report(args, report)
            app.close()
            return
        # Worker may destroy Tk before this callback runs again; completion is also
        # recorded by the Destroy hook below after the worker has actually joined.
        app.root.after(100, tick)

    def destroyed(event):
        if event.widget is app.root and report["status"] == "running":
            if stage == 7 and not app.worker.thread.is_alive():
                report["checks"].append("gui_exit_during_inference_joined")
                report["status"] = "passed"
            else:
                report.update(status="failed", error="Unexpected window destruction")
            save_report(args, report)

    app.root.bind("<Destroy>", destroyed, add=True)
    app.root.after(100, tick)
    return report
