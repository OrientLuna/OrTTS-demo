"""Opt-in real-window acceptance of installed speech panels; no downloads."""
from pathlib import Path
import time
from tkinter import filedialog

from desktop.smoke import save_report


def ui_run(app, args):
    report = {"status": "running", "checks": [], "scope": "Tk panels, real models, local import, playback and cancellation; dialogs supplied by test"}
    cases = [(panel, index) for panel in app.speech_panels for index in range(len(panel.models))]
    started = time.monotonic()
    stage, current, deadline = "select", 0, 0
    panel = None

    def dialog_call(name, value, action):
        old = getattr(filedialog, name)
        setattr(filedialog, name, lambda **kwargs: str(value))
        try:
            action()
        finally:
            setattr(filedialog, name, old)

    def start_run():
        if panel.task == "asr":
            dialog_call("askopenfilename", args.speech_fixture, panel.run)
        else:
            panel.run_button.invoke()

    def tick():
        nonlocal panel, stage, current, deadline
        try:
            if time.monotonic() - started > 1200:
                raise TimeoutError("Speech GUI suite timed out")
            if panel and panel.last_error:
                raise RuntimeError(panel.last_error)
            if stage == "select":
                if current == len(cases):
                    report["status"] = "passed"
                    save_report(args, report)
                    app.close()
                    return
                panel, index = cases[current]
                app.notebook.select(panel)
                panel.model.current(index)
                panel.changed()
                model = panel.selected()
                source = args.speech_extra_assets if model["family"] == "streaming_paraformer" else args.speech_ui_smoke
                dialog_call("askdirectory", source, panel.import_model)
                stage = "import"
            elif stage == "import" and not panel.busy:
                report["checks"].append({"model": panel.selected()["id"], "action": "local_import_verified"})
                if panel.task == "tts":
                    panel.text.delete("1.0", "end")
                    panel.text.insert("1.0", "你好，欢迎使用本地语音合成。" if panel.voice.get().startswith("z") else "Hello, welcome to local speech synthesis.")
                start_run()
                stage = "result"
            elif stage == "result" and not panel.busy:
                model = panel.selected()
                if panel.task == "tts":
                    assert panel.last_audio and Path(panel.last_audio).stat().st_size > 44
                    assert panel.player.process is not None, "Playback did not start"
                    destination = app.home / (model["id"] + "-saved.wav")
                    dialog_call("asksaveasfilename", destination, panel.save)
                    assert destination.read_bytes() == Path(panel.last_audio).read_bytes()
                    stage = "playback"
                else:
                    value = panel.text.get("1.0", "end").strip()
                    assert value and "识别中：" not in value, value
                    destination = app.home / (model["id"] + "-saved.txt")
                    dialog_call("asksaveasfilename", destination, panel.save)
                    assert destination.read_text().strip() == value
                    report["checks"].append({"model": model["id"], "action": "recognition_final_and_save", "text": value})
                    start_run()
                    panel.stop_button.invoke()
                    stage = "cancel"
            elif stage == "playback" and panel.player.process is None:
                report["checks"].append({"model": panel.selected()["id"], "action": "synthesis_save_and_playback_drain"})
                start_run()
                panel.stop_button.invoke()
                stage = "cancel"
            elif stage == "cancel" and not panel.busy:
                assert panel.cancelled.is_set()
                assert not panel.thread.is_alive()
                report["checks"].append({"model": panel.selected()["id"], "action": "stop_and_worker_join"})
                start_run()
                stage = "retry"
            elif stage == "retry" and not panel.busy:
                assert not panel.cancelled.is_set()
                if panel.task == "asr":
                    assert panel.text.get("1.0", "end").strip()
                else:
                    assert panel.last_audio
                    panel.stop_button.invoke()
                report["checks"].append({"model": panel.selected()["id"], "action": "retry_succeeded"})
                current += 1
                stage = "select"
        except Exception as exc:
            report.update(status="failed", error=str(exc), stage=stage)
            save_report(args, report)
            app.close()
            return
        app.root.after(80, tick)

    def destroyed(event):
        if event.widget is app.root and report["status"] == "running":
            report.update(status="failed", error="Unexpected window destruction")
            save_report(args, report)

    app.root.bind("<Destroy>", destroyed, add=True)
    app.root.after(100, tick)
    return report
