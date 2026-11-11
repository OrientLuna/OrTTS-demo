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
from desktop.download import CHANNELS
from desktop.theme import brand, configure


def user_directory():
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/OrTTS Desktop"
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "OrTTS Desktop"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "ortts-desktop"


def format_bytes(value):
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024


class App:
    def __init__(self, root, library=None, state_dir=None, stream_player=None):
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
        known = config.get("verified_directories", [])
        self.verified_directories = [p for p in known if isinstance(p, str)][:8] if isinstance(known, list) else []
        self.streaming = stream_player is not None
        self.player = stream_player or Player()
        self.worker = Worker(self.home / "outputs", library,
                             pcm_sink=self.player.feed if self.streaming else None)
        self.busy = False
        self.closing = False
        self.pack = None
        self.wav = None
        self.last_audio = None
        self.last_error = None
        self.action = None
        self.cancelling = False
        self.download_parent = config.get("download_parent", "")
        self.transfer = tk.StringVar(value="模型仅在你确认后下载；推理在本机完成。")
        self.model_status = tk.StringVar(value="尚未加载模型")
        family = configure(root)
        root.title("OrTTS 语音合成")
        root.geometry("1000x820")
        root.minsize(900, 760)
        root.protocol("WM_DELETE_WINDOW", self.close)
        frame = ttk.Frame(root, padding=24)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)
        header = ttk.Frame(frame)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        self.icon = brand(root)
        if self.icon:
            ttk.Label(header, image=self.icon).pack(side="left", padx=(0, 14))
        heading = ttk.Frame(header)
        heading.pack(side="left")
        ttk.Label(heading, text="OrTTS 语音合成", style="Title.TLabel").pack(anchor="w")
        ttk.Label(heading, text="本地 CPU 推理 · " + ("边合成边播放" if self.streaming else "合成后播放"), style="Muted.TLabel").pack(anchor="w", pady=(3, 0))
        model = ttk.Frame(frame, padding=18, style="Card.TFrame")
        model.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        model.columnconfigure(1, weight=1)
        ttk.Label(model, text="模型与音色", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 12))
        ttk.Label(model, textvariable=self.model_status, style="CardMuted.TLabel").grid(row=0, column=1, columnspan=3, sticky="e", pady=(0, 12))
        ttk.Label(model, text="模型版本", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 12))
        package = config.get("package", "Q4")
        package = package if isinstance(package, str) and package in PACKAGES else "Q4"
        self.package = tk.StringVar(value=PACKAGES[package][0])
        self.package_box = ttk.Combobox(model, textvariable=self.package, values=[p[0] for p in PACKAGES.values()], state="readonly")
        self.package_box.grid(row=1, column=1, columnspan=3, sticky="ew")
        self.package_box.bind("<<ComboboxSelected>>", self.invalidate)
        ttk.Label(model, text="本地目录", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=10)
        self.directory = tk.StringVar(value=config.get("directory", ""))
        self.directory_entry = ttk.Entry(model, textvariable=self.directory, state="readonly")
        self.directory_entry.grid(row=2, column=1, sticky="ew", padx=(0, 8))
        self.import_button = ttk.Button(model, text="导入本地模型…", command=self.choose_directory)
        self.import_button.grid(row=2, column=2, padx=(0, 8))
        self.revalidate_button = ttk.Button(model, text="校验此目录", command=lambda: self.import_directory(self.directory.get()))
        self.revalidate_button.grid(row=2, column=3)
        ttk.Label(model, text="在线获取", style="Card.TLabel").grid(row=3, column=0, sticky="w")
        downloads = ttk.Frame(model, style="Card.TFrame")
        downloads.grid(row=3, column=1, columnspan=3, sticky="ew")
        saved_channel = config.get("channel", "ModelScope")
        self.channel = tk.StringVar(value=saved_channel if isinstance(saved_channel, str) and saved_channel in CHANNELS else "ModelScope")
        self.channel_box = ttk.Combobox(downloads, textvariable=self.channel, values=list(CHANNELS), width=16, state="readonly")
        self.channel_box.pack(side="left", padx=(0, 8))
        self.download_button = ttk.Button(downloads, text="下载 / 继续…", command=self.download)
        self.download_button.pack(side="left")
        ttk.Label(downloads, text="固定版本 · SHA256 校验 · 可取消", style="CardMuted.TLabel").pack(side="left", padx=12)
        options = ttk.Frame(model, style="Card.TFrame")
        options.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(14, 0))
        ttk.Label(options, text="推理版本", style="Card.TLabel").pack(side="left")
        self.variant = tk.StringVar(value="P3")
        self.variant_box = ttk.Combobox(options, textvariable=self.variant, values=["P3"] if package == "Q4" else ["P3", "P5"], width=7, state="readonly")
        self.variant_box.pack(side="left", padx=(8, 20))
        ttk.Label(options, text="音色", style="Card.TLabel").pack(side="left")
        self.voice = tk.StringVar(value="")
        self.voice_box = ttk.Combobox(options, textvariable=self.voice, values=[], width=9, state="disabled")
        self.voice_box.pack(side="left", padx=(8, 20))
        ttk.Label(options, text="CPU 线程", style="Card.TLabel").pack(side="left")
        self.threads = tk.StringVar(value="4")
        self.thread_box = ttk.Combobox(options, textvariable=self.threads, values=list(map(str, range(1, 9))), width=4, state="readonly")
        self.thread_box.pack(side="left", padx=8)
        self.release_button = ttk.Button(options, text="释放模型", command=self.release)
        self.release_button.pack(side="right")
        editor = ttk.Frame(frame, padding=18, style="Card.TFrame")
        editor.grid(row=2, column=0, sticky="nsew")
        editor.columnconfigure(0, weight=1)
        editor.rowconfigure(1, weight=1)
        title = ttk.Frame(editor, style="Card.TFrame")
        title.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(title, text="合成文本", style="Section.TLabel").pack(side="left")
        self.text_count = tk.StringVar(value="")
        ttk.Label(title, textvariable=self.text_count, style="CardMuted.TLabel").pack(side="right")
        text_frame = ttk.Frame(editor, style="Card.TFrame")
        text_frame.grid(row=1, column=0, sticky="nsew")
        self.text = tk.Text(text_frame, wrap="word", font=(family, 13), padx=12, pady=12, height=5, undo=True,
                            relief="flat", highlightthickness=1, highlightbackground="#D8DEEA",
                            background="#FFFFFF", foreground="#243047", insertbackground="#243047")
        scrollbar = ttk.Scrollbar(text_frame, command=self.text.yview)
        scrollbar.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.pack(fill="both", expand=True)
        self.text.insert("1.0", "你好，欢迎使用 OrTTS 本地语音合成。")
        self.text.bind("<<Modified>>", self.update_text_count)
        self.update_text_count()
        ttk.Label(editor, text="支持中英文，建议先输入一至三句。音频完全在本机生成。", style="CardMuted.TLabel").grid(row=2, column=0, sticky="w", pady=(8, 0))
        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, sticky="ew", pady=14)
        self.synth_button = ttk.Button(buttons, text="合成语音", style="Primary.TButton", command=self.synthesize)
        self.synth_button.pack(side="left")
        self.play_button = ttk.Button(buttons, text="重播", command=self.play)
        self.play_button.pack(side="left", padx=8)
        self.save_button = ttk.Button(buttons, text="保存 WAV…", command=self.save)
        self.save_button.pack(side="left")
        self.stop_button = ttk.Button(buttons, text="停止", command=self.stop)
        self.stop_button.pack(side="left", padx=8)
        self.autoplay = tk.BooleanVar(value=True)
        self.autoplay_button = ttk.Checkbutton(buttons, text="边合成边播放" if self.streaming else "合成后自动播放", variable=self.autoplay)
        self.autoplay_button.pack(side="right")
        self.status = tk.StringVar(value="导入已有模型，或选择通道下载模型，即可开始。")
        self.status_label = ttk.Label(frame, textvariable=self.status, wraplength=900)
        self.status_label.grid(row=4, column=0, sticky="w")
        self.progress = ttk.Progressbar(frame, mode="determinate", value=0, maximum=100)
        self.progress.grid(row=5, column=0, sticky="ew", pady=(8, 6))
        self.transfer_label = ttk.Label(frame, textvariable=self.transfer, style="Muted.TLabel", wraplength=900)
        self.transfer_label.grid(row=6, column=0, sticky="w")
        root.bind("<Configure>", lambda event: self.resize(event), add=True)
        self._buttons()
        root.after(80, self.poll)

    def package_key(self):
        return next(k for k, v in PACKAGES.items() if v[0] == self.package.get())

    def resize(self, event):
        if event.widget is self.root:
            width = max(600, event.width - 50)
            self.status_label.configure(wraplength=width)
            self.transfer_label.configure(wraplength=width)

    def update_text_count(self, event=None):
        count = len(self.text.get("1.0", "end").strip())
        self.text_count.set(f"{count} / 2000 字")
        self.text.edit_modified(False)

    def save_settings(self):
        try:
            self.config_path.write_text(json.dumps({"directory": self.directory.get(), "package": self.package_key(),
                                                   "channel": self.channel.get(), "download_parent": self.download_parent,
                                                   "verified_directories": self.verified_directories}, ensure_ascii=False))
        except OSError:
            self.transfer.set("设置未能保存；本次操作不受影响，下次启动需重新选择目录。")

    def _buttons(self):
        editable = not self.busy and not self.closing
        for widget in (self.package_box, self.variant_box, self.thread_box):
            widget.configure(state="readonly" if editable else "disabled")
        self.voice_box.configure(state="readonly" if editable and self.pack else "disabled")
        self.import_button.configure(state="normal" if editable else "disabled")
        self.synth_button.configure(state="normal" if editable and self.pack else "disabled")
        for widget in (self.play_button, self.save_button):
            widget.configure(state="normal" if self.wav and editable else "disabled")
        self.stop_button.configure(state="normal" if not self.closing and not self.cancelling and (self.busy or self.player.process) else "disabled",
                                   text="取消下载" if self.action == "download" else "取消校验" if self.action == "import" else "停止")
        self.release_button.configure(state="normal" if editable and self.pack else "disabled")
        self.download_button.configure(state="normal" if editable else "disabled")
        self.channel_box.configure(state="readonly" if editable else "disabled")
        self.revalidate_button.configure(state="normal" if editable and self.directory.get() else "disabled")
        self.autoplay_button.configure(state="normal" if editable else "disabled")

    def download(self):
        if self.busy or self.closing:
            return
        package = self.package_key()
        if not messagebox.askyesno("下载模型", f"将通过 {self.channel.get()} 下载 {PACKAGES[package][0]}。\n完整包可能需要数 GB；当前网络是否计费未知。\n已有文件仅校验通过后复用，不覆盖旧文件。\n\n确认继续联网并选择存放目录？"):
            return
        initial = Path(self.download_parent) if isinstance(self.download_parent, str) and self.download_parent else self.home
        parent = filedialog.askdirectory(title="选择模型存放位置（按版本创建子目录）",
                                         initialdir=str(initial if initial.is_dir() else self.home))
        if not parent:
            return
        directory = Path(parent) / PACKAGES[package][1]
        reuse = list(self.verified_directories)
        if self.pack and str(self.pack.root) not in reuse:
            reuse.append(str(self.pack.root))
        self.player.stop()
        self.pack = None
        self.voice.set("")
        self.directory.set(str(directory))
        self.download_parent = str(parent)
        self.save_settings()
        self.model_status.set("正在下载 · 完整校验后可用")
        self.status.set("准备下载并校验模型…")
        self._submit("download", directory=directory, package=package,
                     channel=self.channel.get(), reuse_roots=reuse)

    def release(self):
        if self.busy or self.closing:
            return
        self.player.stop()
        self._submit("unload")
        self.status.set("正在释放模型，保留已校验目录…")

    def _submit(self, action, **args):
        self.busy = True
        self.last_error = None
        self.action = action
        self.cancelling = False
        self.status_label.configure(foreground="#243047")
        self.progress.stop()
        self.progress.configure(mode="indeterminate", value=0, maximum=100)
        self.progress.start(12)
        if action in ("download", "import"):
            self.transfer.set("正在验证固定清单与文件；校验通过前不会加载模型。")
        self._buttons()
        self.worker.submit(action, **args)

    def invalidate(self, event=None):
        if self.busy or self.closing:
            return
        self.pack = None
        self.voice.set("")
        self.voice_box.configure(values=[])
        self.variant.set("P3")
        self.variant_box.configure(values=["P3"] if self.package_key() == "Q4" else ["P3", "P5"])
        self.model_status.set("尚未校验此版本")
        self._submit("release")
        self.status.set("版本已切换，请重新选择并校验模型目录。")

    def choose_directory(self):
        directory = filedialog.askdirectory(title="选择包含清单、native、voices 的完整模型目录", initialdir=self.directory.get() or str(Path.home()))
        if directory:
            self.import_directory(directory)

    def import_directory(self, directory):
        if self.busy or self.closing or not directory:
            return
        self.player.stop()
        self.pack = None
        self.voice.set("")
        self.directory.set(str(directory))
        self.status.set("正在校验全部文件的大小和 SHA256…")
        self.model_status.set("校验中 · 不复制、不修改模型")
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
        if self.streaming and self.autoplay.get():
            self.player.start_stream()
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
            self.cancelling = True
            self.worker.cancel()
            if self.action == "download":
                self.status.set("正在取消下载…等待当前网络读取返回（最多约 20 秒）。")
            elif self.action == "import":
                self.status.set("正在取消校验…原模型文件不会修改。")
            else:
                self.status.set("正在停止…等待下一个 PCM 边界。" if self.streaming else "正在停止…离线计算可能需要等待当前推理返回。")
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
                elif event == "transfer":
                    self.progress.stop()
                    self.progress.configure(mode="determinate", value=100 * value["completed"] / max(1, value["total"]))
                    speed = f" · 平均 {format_bytes(value['speed'])}/s" if value["speed"] else ""
                    self.transfer.set(f"{format_bytes(value['completed'])} / {format_bytes(value['total'])}{speed} · {value['phase']}\n{value['file']}")
                    if value["phase"] == "完整性复核":
                        self.model_status.set("下载已完成 · 完整性复核中")
                elif event == "unloaded":
                    self.model_status.set("模型已释放 · 下次合成自动加载")
                elif event == "imported":
                    self.pack = value
                    self.voice_box.configure(values=[VOICE_NAMES[v] for v in value.voices])
                    self.voice.set(VOICE_NAMES[value.voices[0]])
                    self.variant_box.configure(values=value.variants)
                    self.variant.set("P3")
                    self.verified_directories = [str(value.root)] + [p for p in self.verified_directories if p != str(value.root)][:7]
                    self.save_settings()
                    self.model_status.set(f"已校验 · {len(value.voices)} 个音色")
                    self.status.set(f"模型校验通过 · {PACKAGES[value.package][0]} · {len(value.voices)} 个音色")
                    self.transfer.set("可开始合成。P3 为轻量版本；P5 仅在模型包支持时开放。")
                elif event == "audio":
                    self.wav = value["path"]
                    self.last_audio = value
                    self.status.set(f"合成完成 · {value['seconds']:.2f} 秒音频 · 24 kHz / 单声道 · 模型句柄复用")
                    if self.streaming:
                        self.player.finish()
                        first = value['first_pcm_ms']
                        self.status.set(f"语音已生成 · {value['seconds']:.2f} 秒 · 可重播或保存 WAV")
                        timing = f"{first:.0f} ms" if first >= 0 else "未知"
                        self.transfer.set(f"首 PCM 就绪 {timing} · {value['chunks']} 个音频块 · 非扬声器发声时间")
                    elif self.autoplay.get():
                        self.play()
                    self.model_status.set(f"已加载 · {self.variant.get()} · {self.voice.get()}")
                elif event in ("error", "cancelled"):
                    if self.streaming:
                        self.player.stop()
                    self.last_error = value if event == "error" else None
                    self.status.set(value)
                    if event == "error":
                        self.status_label.configure(foreground="#B33A3A")
                    if self.action in ("download", "import"):
                        self.model_status.set("未就绪 · 可重新导入或继续下载")
                    if self.action == "download":
                        self.transfer.set("已验证文件和未完成下载均保留。继续时选择相同位置；不会覆盖原文件。")
                elif event == "done":
                    self.busy = False
                    self.action = None
                    self.cancelling = False
                    if str(self.progress.cget("mode")) == "indeterminate":
                        self.progress.stop()
                        self.progress.configure(mode="determinate", value=0)
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
