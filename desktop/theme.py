"""Shared desktop appearance; keep native macOS controls and use Clam on Linux."""
from pathlib import Path
import sys
import tkinter as tk
from tkinter import font, ttk


def configure(root):
    family = font.nametofont("TkDefaultFont").actual("family")
    if sys.platform.startswith("linux"):
        available = {name.casefold(): name for name in font.families(root)}
        family = available.get("noto sans cjk sc", available.get("helvetica", family))
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
            font.nametofont(name).configure(family=family, size=10)
    style = ttk.Style(root)
    if sys.platform.startswith("linux"):
        style.theme_use("clam")
    root.configure(background="#F4F6FA")
    style.configure("TFrame", background="#F4F6FA")
    style.configure("TLabel", background="#F4F6FA", foreground="#243047")
    style.configure("Card.TFrame", background="#FFFFFF")
    style.configure("Card.TLabel", background="#FFFFFF", foreground="#243047")
    style.configure("Muted.TLabel", foreground="#647189")
    style.configure("CardMuted.TLabel", background="#FFFFFF", foreground="#647189")
    style.configure("Title.TLabel", font=(family, 22, "bold"))
    style.configure("Section.TLabel", background="#FFFFFF", font=(family, 11, "bold"))
    style.configure("TButton", padding=(12, 7))
    style.configure("Primary.TButton", padding=(20, 8))
    style.configure("TCombobox", padding=5)
    style.configure("TEntry", padding=5)
    style.configure("TProgressbar", background="#5976C9", troughcolor="#E4E9F3", borderwidth=0)
    if sys.platform.startswith("linux"):
        style.configure("TButton", background="#FFFFFF", bordercolor="#D8DEEA")
        style.map("TButton", background=[("active", "#EAF0FF")])
        style.configure("Primary.TButton", background="#4265BC", foreground="#FFFFFF")
        style.map("Primary.TButton", background=[("disabled", "#DCE3EF"), ("active", "#3455A8")],
                  foreground=[("disabled", "#8794AB"), ("!disabled", "#FFFFFF")])
    return family


def brand(root):
    path = Path(__file__).resolve().parents[1] / "assets/brand/ortts-icon.png"
    if not path.is_file():
        return None
    icon = tk.PhotoImage(master=root, file=str(path))
    root.iconphoto(True, icon)
    scale = max(1, (icon.width() + 55) // 56)
    return icon.subsample(scale)
