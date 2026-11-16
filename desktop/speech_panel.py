"""Task-specific desktop pages using the same catalog and speech ABI as iOS."""
from pathlib import Path
import queue
import shutil
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from desktop.audio import Player
from desktop.models import Cancelled
from desktop.speech import SpeechTask, catalog, prepare
from desktop.theme import PALETTE


class SpeechPanel(ttk.Frame):
    def __init__(self, parent, task, home, library=None):
        super().__init__(parent, padding=24)
        self.task, self.home, self.library = task, Path(home), library
        try:
            self.models = [m for m in catalog(library) if m["task"] == task]
        except (OSError, ValueError, AttributeError):
            self.models = []
        self.model_root = self.home / "speech-models"
        self.events = queue.Queue()
        self.cancelled = threading.Event()
        self.native = None
        self.thread = None
        self.busy = False
        self.closing = False
        self.last_error = None
        self.last_audio = None
        self.player = Player()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        title = "其他语音合成" if task == "tts" else "语音识别"
        purpose = "输入文字，合成语音。" if task == "tts" else "导入音频，转换为文字。"
        header = ttk.Frame(self)
        header.grid(row=0, sticky="ew", pady=(0, 16))
        ttk.Label(header, text=title, style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text=purpose, style="Muted.TLabel").pack(anchor="w", pady=(3, 0))

        model_card = ttk.Frame(self, padding=18, style="Card.TFrame")
        model_card.grid(row=1, sticky="ew", pady=(0, 14))
        model_card.columnconfigure(0, weight=1)
        model_head = ttk.Frame(model_card, style="CardInner.TFrame")
        model_head.grid(row=0, sticky="ew", pady=(0, 10))
        ttk.Label(model_head, text="模型与音色" if task == "tts" else "识别模型", style="Section.TLabel").pack(side="left")
        ttk.Button(model_head, text="模型详情", command=self.details).pack(side="right")
        self.model = ttk.Combobox(model_card, state="readonly", values=[m["display_name"] for m in self.models])
        if self.models:
            self.model.current(0)
        self.model.grid(row=1, sticky="ew")
        self.model.bind("<<ComboboxSelected>>", self.changed)
        self.info = tk.StringVar()
        ttk.Label(model_card, textvariable=self.info, style="CardMuted.TLabel", wraplength=850).grid(row=2, sticky="w", pady=(8, 12))
        actions = ttk.Frame(model_card, style="CardInner.TFrame")
        actions.grid(row=3, sticky="ew")
        self.download = ttk.Button(actions, text="下载 / 检查模型", command=lambda: self.start("download"))
        self.download.pack(side="left")
        self.import_button = ttk.Button(actions, text="导入模型文件夹…", command=self.import_model)
        self.import_button.pack(side="left", padx=8)
        self.voice = ttk.Combobox(actions, width=18, state="readonly")
        if task == "tts":
            self.voice.pack(side="right")

        editor_card = ttk.Frame(self, padding=18, style="Card.TFrame")
        editor_card.grid(row=2, sticky="nsew")
        editor_card.columnconfigure(0, weight=1)
        editor_card.rowconfigure(1, weight=1)
        ttk.Label(editor_card, text="合成文本" if task == "tts" else "识别结果", style="Section.TLabel").grid(row=0, sticky="w", pady=(0, 10))
        text_wrap = ttk.Frame(editor_card, style="CardInner.TFrame")
        text_wrap.grid(row=1, sticky="nsew")
        self.text = tk.Text(
            text_wrap, wrap="word", font=("SF Pro Text" if sys.platform == "darwin" else "TkDefaultFont", 13),
            height=8, padx=12, pady=12, relief="flat", highlightthickness=1,
            highlightbackground=PALETTE["border"], highlightcolor=PALETTE["accent"],
            background=PALETTE["card"], foreground=PALETTE["text"], insertbackground=PALETTE["accent"],
        )
        scrollbar = ttk.Scrollbar(text_wrap, command=self.text.yview)
        scrollbar.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.pack(fill="both", expand=True)
        if task == "tts":
            self.text.insert("1.0", "Hello, welcome to local speech synthesis.")
        else:
            self.text.configure(state="disabled")

        controls = ttk.Frame(self)
        controls.grid(row=3, sticky="ew", pady=14)
        self.run_button = ttk.Button(controls, text="合成并播放" if task == "tts" else "导入音频识别…", style="Primary.TButton", command=self.run)
        self.run_button.pack(side="left")
        self.stop_button = ttk.Button(controls, text="停止", command=self.stop)
        self.stop_button.pack(side="left", padx=8)
        self.save_button = ttk.Button(controls, text="保存 WAV…" if task == "tts" else "保存文字…", command=self.save)
        self.save_button.pack(side="left")
        if task == "tts":
            ttk.Button(controls, text="重播", command=self.replay).pack(side="left", padx=8)
        self.status = tk.StringVar(value="选择模型，下载或导入后即可离线使用。")
        ttk.Label(self, textvariable=self.status, style="Muted.TLabel", wraplength=850).grid(row=4, sticky="w")
        self.changed()
        self.after(80, self.poll)

    def selected(self):
        return self.models[self.model.current()] if self.models else None

    def details(self):
        model = self.selected()
        if not model:
            return
        review = model.get("license_review", {})
        lines = [model["display_name"], review.get("weights_license", ""), review.get("source", ""), review.get("notes", "")]
        if model["family"] == "streaming_paraformer":
            lines.append("实验模型：英语与混合语言质量尚未达到项目验收标准。")
        lines.append("下载与导入使用固定版本和 SHA256 校验。")
        messagebox.showinfo("模型详情", "\n\n".join(line for line in lines if line))

    def changed(self, event=None):
        model = self.selected()
        if not model:
            self.info.set("当前运行时不支持此功能")
            for button in (self.download, self.import_button, self.run_button):
                button.configure(state="disabled")
            return
        voices = model.get("voice_sample", [])
        self.voice.configure(values=voices)
        self.voice.set(voices[0] if voices else "")
        size = sum(a["bytes"] for a in model["assets"]) / 1e6
        description = "合成后播放 · 可保存 WAV" if self.task == "tts" else "音频最长 60 秒"
        self.info.set(f"{description} · 模型 {size:.0f} MB")

    def import_model(self):
        if not self.busy:
            folder = filedialog.askdirectory(title="选择模型目录或包含模型的资源根目录")
            if folder:
                self.start("import", source=folder)

    def run(self):
        if self.busy:
            return
        if self.task == "asr":
            audio = filedialog.askopenfilename(title="选择音频（最多60秒）", filetypes=[("音频", "*.wav *.caf *.mp3 *.m4a *.aiff"), ("所有文件", "*")])
            if audio:
                self.start("run", audio=audio)
        else:
            self.start("run")

    def start(self, action, source=None, audio=None):
        if self.busy or self.closing or not self.models:
            return
        model = self.selected()
        text, voice = self.text.get("1.0", "end").strip(), self.voice.get()
        if action == "run" and self.task == "tts" and not 0 < len(text) <= 2000:
            self.status.set("请输入 1–2000 字")
            return
        self.busy, self.last_error = True, None
        self.cancelled.clear()
        self.player.stop()
        if action == "run" and self.task == "asr":
            self.set_text("")
        self.model.configure(state="disabled")
        self.voice.configure(state="disabled")
        for button in (self.download, self.import_button, self.run_button):
            button.configure(state="disabled")
        self.status.set("正在准备…")
        def notify(event, value):
            self.events.put((event, value))
        def work():
            try:
                prepare(model, self.model_root, self.cancelled, notify, source, action == "download")
                if action == "run":
                    native = SpeechTask(self.library, self.cancelled, notify)
                    self.native = native
                    output = self.home / "outputs" / (model["id"] + ".wav")
                    output.parent.mkdir(parents=True, exist_ok=True)
                    native.run(model, self.model_root, output, text, voice, audio)
                notify("status", "识别完成" if action == "run" and self.task == "asr" else "合成完成" if action == "run" else "模型已校验，可离线使用")
            except Cancelled:
                notify("status", "已停止，可重新开始")
            except Exception as exc:
                notify("error", str(exc))
            finally:
                self.native = None
                notify("done", None)
        self.thread = threading.Thread(target=work, name="ortts-"+self.task)
        self.thread.start()

    def stop(self):
        self.cancelled.set()
        native = self.native
        if native:
            native.cancel()
        self.player.stop()
        self.status.set("正在停止，等待当前计算安全返回…" if self.busy else "播放已停止")

    def set_text(self, value):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value)
        self.text.configure(state="disabled")

    def replay(self):
        if self.last_audio and not self.busy:
            try:
                self.player.play(self.last_audio)
            except Exception as exc:
                self.status.set(str(exc))

    def save(self):
        if self.busy:
            return
        if self.task == "tts" and not self.last_audio:
            self.status.set("请先合成音频")
            return
        path = filedialog.asksaveasfilename(defaultextension=".wav" if self.task == "tts" else ".txt")
        if path:
            try:
                if self.task == "tts":
                    shutil.copyfile(self.last_audio, path)
                else:
                    Path(path).write_text(self.text.get("1.0", "end"), encoding="utf-8")
                self.status.set("已保存：" + path)
            except OSError as exc:
                self.status.set(str(exc))

    def close(self):
        self.closing = True
        self.stop()

    def poll(self):
        try:
            while True:
                event, value = self.events.get_nowait()
                if event == "done":
                    self.busy = False
                    if self.thread:
                        self.thread.join()
                    self.model.configure(state="readonly")
                    self.voice.configure(state="readonly")
                    for button in (self.download, self.import_button, self.run_button):
                        button.configure(state="normal")
                elif event == "error":
                    self.last_error = value
                    self.status.set(value)
                elif not self.closing:
                    if event == "text" and not self.cancelled.is_set():
                        self.set_text(value)
                    elif event == "audio" and not self.cancelled.is_set():
                        self.last_audio = value
                        try:
                            self.player.play(value)
                        except Exception as exc:
                            self.status.set(str(exc))
                    elif event == "status":
                        self.status.set(value)
        except queue.Empty:
            pass
        try:
            self.player.poll()
        except RuntimeError as exc:
            self.status.set(str(exc))
        if not self.closing or self.busy:
            self.after(80, self.poll)
