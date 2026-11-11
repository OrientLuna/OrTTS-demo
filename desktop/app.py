#!/usr/bin/env python3
"""Run with python -m desktop.app, or use the packaged macOS .app."""
from pathlib import Path
import argparse
import json
import os
import queue
import shutil
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# Also support PyInstaller's script entry point.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop.audio import Player
from desktop.models import PACKAGES, VOICE_NAMES
from desktop.worker import Worker


def user_directory():
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/OrTTS Desktop"
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "OrTTS Desktop"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "ortts-desktop"


class App:
    def __init__(self, root, library=None, state_dir=None):
        self.root = root
        self.home = Path(state_dir or user_directory())
        self.home.mkdir(parents=True, exist_ok=True)
        self.config_path = self.home / "settings.json"
        try:
            config = json.loads(self.config_path.read_text())
            if not isinstance(config, dict):
                config = {}
        except (OSError, ValueError):
            config = {}
        self.worker = Worker(self.home / "outputs", library)
        self.player = Player()
        self.busy = False
        self.closing = False
        self.pack = None
        self.wav = None
        self.last_audio = None
        self.last_error = None
        root.title("OrTTS 语音合成")
        root.geometry("820x600")
        root.minsize(720, 540)
        root.protocol("WM_DELETE_WINDOW", self.close)
        frame = ttk.Frame(root, padding=24)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(6, weight=1)
        ttk.Label(frame, text="OrTTS 语音合成", font=("Helvetica", 23, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(frame, text="本地 CPU 推理 · 模型无需复制 · 合成后播放", foreground="#666666").grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 20))
        ttk.Label(frame, text="模型版本").grid(row=2, column=0, sticky="w", padx=(0, 12))
        self.package = tk.StringVar(value=PACKAGES["Q4"][0])
        self.package_box = ttk.Combobox(frame, textvariable=self.package, values=[p[0] for p in PACKAGES.values()], state="readonly")
        self.package_box.grid(row=2, column=1, columnspan=2, sticky="ew")
        self.package_box.bind("<<ComboboxSelected>>", self.invalidate)
        ttk.Label(frame, text="模型目录").grid(row=3, column=0, sticky="w", pady=12)
        self.directory = tk.StringVar(value=config.get("directory", ""))
        self.directory_entry = ttk.Entry(frame, textvariable=self.directory, state="readonly")
        self.directory_entry.grid(row=3, column=1, sticky="ew", padx=(0, 8))
        self.import_button = ttk.Button(frame, text="选择并校验…", command=self.choose_directory)
        self.import_button.grid(row=3, column=2)
        options = ttk.Frame(frame)
        options.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(0, 12))
        ttk.Label(options, text="推理版本").pack(side="left")
        self.variant = tk.StringVar(value="P3")
        self.variant_box = ttk.Combobox(options, textvariable=self.variant, values=["P3"], width=7, state="readonly")
        self.variant_box.pack(side="left", padx=(8, 20))
        ttk.Label(options, text="音色").pack(side="left")
        self.voice = tk.StringVar(value="")
        self.voice_box = ttk.Combobox(options, textvariable=self.voice, values=[], width=9, state="disabled")
        self.voice_box.pack(side="left", padx=(8, 20))
        ttk.Label(options, text="CPU 线程").pack(side="left")
        self.threads = tk.StringVar(value="4")
        self.thread_box = ttk.Combobox(options, textvariable=self.threads, values=list(map(str, range(1, 9))), width=4, state="readonly")
        self.thread_box.pack(side="left", padx=8)
        ttk.Label(frame, text="合成文本（建议一至三句，中英文均可）").grid(row=5, column=0, columnspan=3, sticky="w", pady=(4, 8))
        text_frame = ttk.Frame(frame)
        text_frame.grid(row=6, column=0, columnspan=3, sticky="nsew")
        self.text = tk.Text(text_frame, wrap="word", font=("Helvetica", 15), padx=12, pady=12, height=8, undo=True)
        scrollbar = ttk.Scrollbar(text_frame, command=self.text.yview)
        scrollbar.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.pack(fill="both", expand=True)
        self.text.insert("1.0", "你好，欢迎使用 OrTTS 本地语音合成。")
        buttons = ttk.Frame(frame)
        buttons.grid(row=7, column=0, columnspan=3, sticky="ew", pady=16)
        self.synth_button = ttk.Button(buttons, text="合成语音", command=self.synthesize)
        self.synth_button.pack(side="left")
        self.play_button = ttk.Button(buttons, text="播放", command=self.play)
        self.play_button.pack(side="left", padx=8)
        self.save_button = ttk.Button(buttons, text="保存 WAV…", command=self.save)
        self.save_button.pack(side="left")
        self.stop_button = ttk.Button(buttons, text="停止", command=self.stop)
        self.stop_button.pack(side="left", padx=8)
        self.autoplay = tk.BooleanVar(value=True)
        ttk.Checkbutton(buttons, text="合成后自动播放", variable=self.autoplay).pack(side="right")
        self.status = tk.StringVar(value="请选择对应版本的完整模型目录；默认 Q4/P3，不自动下载权重。")
        ttk.Label(frame, textvariable=self.status, wraplength=760).grid(row=8, column=0, columnspan=3, sticky="w")
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        self._buttons()
        root.after(80, self.poll)

    def package_key(self):
        return next(k for k, v in PACKAGES.items() if v[0] == self.package.get())

    def _buttons(self):
        editable = not self.busy and not self.closing
        for widget in (self.package_box, self.variant_box, self.thread_box):
            widget.configure(state="readonly" if editable else "disabled")
        self.voice_box.configure(state="readonly" if editable and self.pack else "disabled")
        self.import_button.configure(state="normal" if editable else "disabled")
        self.synth_button.configure(state="normal" if editable and self.pack else "disabled")
        for widget in (self.play_button, self.save_button):
            widget.configure(state="normal" if self.wav and not self.closing else "disabled")
        self.stop_button.configure(state="normal" if not self.closing and (self.busy or self.player.process) else "disabled")

    def _submit(self, action, **args):
        self.busy = True
        self.last_error = None
        self.progress.start(12)
        self._buttons()
        self.worker.submit(action, **args)

    def invalidate(self, event=None):
        self.pack = None
        self.voice.set("")
        self.voice_box.configure(values=[])
        self.variant.set("P3")
        self.variant_box.configure(values=["P3"] if self.package_key() == "Q4" else ["P3", "P5"])
        self._submit("release")
        self.status.set("版本已切换，请重新选择并校验模型目录。")

    def choose_directory(self):
        directory = filedialog.askdirectory(title="选择包含清单、native、voices 的完整模型目录", initialdir=self.directory.get() or str(Path.home()))
        if directory:
            self.import_directory(directory)

    def import_directory(self, directory):
        self.player.stop()
        self.pack = None
        self.voice.set("")
        self.directory.set(str(directory))
        self.status.set("正在校验全部文件的大小和 SHA256…")
        self._submit("import", directory=directory, package=self.package_key())

    def synthesize(self):
        if self.busy or not self.pack:
            return
        text = self.text.get("1.0", "end").strip()
        if not text or len(text) > 2000:
            messagebox.showwarning("文本长度", "请输入 1～2000 字，建议先测试短句。")
            return
        self.player.stop()
        voice = next(v for v in self.pack.voices if VOICE_NAMES[v] == self.voice.get())
        self.status.set("正在加载 / 合成…")
        self._submit("synthesize", text=text, variant=self.variant.get(), voice=voice, threads=int(self.threads.get()))

    def play(self):
        if self.wav:
            try:
                self.player.play(self.wav)
                self.status.set("播放中…")
            except Exception as exc:
                self.status.set(str(exc))
            self._buttons()

    def save(self):
        if self.wav:
            destination = filedialog.asksaveasfilename(title="保存语音", defaultextension=".wav", initialfile=self.wav.name, filetypes=[("WAV 音频", "*.wav")])
            if destination:
                try:
                    shutil.copyfile(self.wav, destination)
                    self.status.set(f"已保存：{destination}")
                except OSError as exc:
                    self.status.set(f"保存失败：{exc}")

    def stop(self):
        self.player.stop()
        if self.busy:
            self.worker.cancel()
            self.status.set("正在停止…离线计算可能需要等待当前推理返回。")
        else:
            self.status.set("播放已停止")
        self._buttons()

    def close(self):
        if self.closing:
            return
        self.closing = True
        self.player.stop()
        self.status.set("正在安全退出，等待运行时释放…")
        self._buttons()
        self.worker.shutdown()

    def poll(self):
        try:
            while True:
                event, value = self.worker.events.get_nowait()
                if event == "closed":
                    self.worker.thread.join()
                    self.root.destroy()
                    return
                if self.closing:
                    continue
                if event == "status":
                    self.status.set(value)
                elif event == "imported":
                    self.pack = value
                    self.voice_box.configure(values=[VOICE_NAMES[v] for v in value.voices])
                    self.voice.set(VOICE_NAMES[value.voices[0]])
                    self.variant_box.configure(values=value.variants)
                    self.variant.set("P3")
                    self.config_path.write_text(json.dumps({"directory": str(value.root)}, ensure_ascii=False))
                    self.status.set(f"模型校验通过 · {PACKAGES[value.package][0]} · {len(value.voices)} 个音色")
                elif event == "audio":
                    self.wav = value["path"]
                    self.last_audio = value
                    self.status.set(f"合成完成 · {value['seconds']:.2f} 秒音频 · 24 kHz / 单声道 · 模型句柄复用")
                    if self.autoplay.get():
                        self.play()
                elif event in ("error", "cancelled"):
                    self.last_error = value if event == "error" else None
                    self.status.set(value)
                elif event == "done":
                    self.busy = False
                    self.progress.stop()
                self._buttons()
        except queue.Empty:
            pass
        try:
            if self.player.poll():
                self.status.set("播放结束，可继续合成或保存 WAV。")
                self._buttons()
        except RuntimeError as exc:
            self.status.set(str(exc))
            self._buttons()
        self.root.after(80, self.poll)


def main():
    parser = argparse.ArgumentParser(description="OrTTS 最小桌面 Demo")
    parser.add_argument("--library", type=Path, help="本地 libortts.dylib（默认使用随包运行时）")
    parser.add_argument("--state-dir", type=Path, help="独立测试用用户数据目录")
    parser.add_argument("--smoke", type=Path, metavar="MODEL", help="无窗口执行运行时验收并退出")
    parser.add_argument("--ui-smoke", type=Path, metavar="MODEL", help="真实窗口自动验收后退出")
    parser.add_argument("--package", choices=PACKAGES, default="Q4")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.smoke:
        from desktop.smoke import run
        run(args)
        return
    root = tk.Tk()
    app = App(root, args.library, args.state_dir)
    report = None
    if args.ui_smoke:
        from desktop.smoke import ui_run
        report = ui_run(app, args)
    root.mainloop()
    if report is not None and report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
