"""Unified iOS-inspired desktop theme shared across macOS and Linux."""
from pathlib import Path
import sys
import tkinter as tk
from tkinter import font, ttk

PALETTE = {
    "bg": "#F2F2F7",          # iOS systemGroupedBackground
    "card": "#FFFFFF",        # iOS secondarySystemGroupedBackground
    "border": "#E5E5EA",      # iOS separator
    "text": "#1C1C1E",        # iOS label
    "muted": "#6C6C70",       # iOS secondaryLabel
    "accent": "#007AFF",      # iOS systemBlue
    "accent_hover": "#0062CC",
    "accent_soft": "#E5F1FF",
    "accent_disabled": "#C7C7CC",
    "tab_idle": "#E5E5EA",
    "tab_hover": "#EBEBF0",
    "trough": "#E5E5EA",
}


def _pick_font(root):
    family = font.nametofont("TkDefaultFont").actual("family")
    available = {name.casefold(): name for name in font.families(root)}
    if sys.platform == "darwin":
        candidates = ("sf pro text", "pingfang sc", "helvetica neue", "helvetica")
    else:
        candidates = (
            "noto sans cjk sc",
            "source han sans sc",
            "wenquanyi micro hei",
            "noto sans",
            "dejavu sans",
            "nimbus sans l",
            "helvetica",
        )
    for candidate in candidates:
        if candidate in available:
            family = available[candidate]
            break
    size = 12 if sys.platform == "darwin" else 11
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        try:
            font.nametofont(name).configure(family=family, size=size)
        except tk.TclError:
            pass
    return family


def configure(root):
    family = _pick_font(root)
    style = ttk.Style(root)
    style.theme_use("clam")

    bg = PALETTE["bg"]
    card = PALETTE["card"]
    border = PALETTE["border"]
    text = PALETTE["text"]
    muted = PALETTE["muted"]
    accent = PALETTE["accent"]

    root.configure(background=bg)
    style.configure("TFrame", background=bg)
    style.configure("TLabel", background=bg, foreground=text)
    style.configure("Muted.TLabel", background=bg, foreground=muted)
    style.configure("Title.TLabel", background=bg, foreground=text, font=(family, 20, "bold"))

    style.configure("Card.TFrame", background=card, relief="solid", borderwidth=1, bordercolor=border)
    style.configure("CardInner.TFrame", background=card)
    style.configure("Card.TLabel", background=card, foreground=text)
    style.configure("CardMuted.TLabel", background=card, foreground=muted)
    style.configure("Section.TLabel", background=card, foreground=text, font=(family, 13, "bold"))

    style.configure(
        "TNotebook",
        background=bg,
        borderwidth=0,
        tabmargins=(16, 10, 16, 0),
    )
    style.configure(
        "TNotebook.Tab",
        background=PALETTE["tab_idle"],
        foreground=muted,
        padding=(18, 9),
        font=(family, 11, "bold"),
        borderwidth=0,
        focuscolor=bg,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", card), ("active", PALETTE["tab_hover"])],
        foreground=[("selected", accent), ("active", text)],
    )

    style.configure(
        "TButton",
        background=card,
        foreground=accent,
        bordercolor=border,
        lightcolor=card,
        darkcolor=card,
        relief="solid",
        borderwidth=1,
        padding=(14, 8),
        font=(family, 11),
        focuscolor=border,
    )
    style.map(
        "TButton",
        background=[("disabled", bg), ("active", PALETTE["accent_soft"])],
        foreground=[("disabled", PALETTE["accent_disabled"]), ("active", PALETTE["accent_hover"])],
    )

    style.configure(
        "Primary.TButton",
        background=accent,
        foreground="#FFFFFF",
        bordercolor=accent,
        lightcolor=accent,
        darkcolor=accent,
        relief="flat",
        borderwidth=0,
        padding=(22, 9),
        font=(family, 11, "bold"),
        focuscolor=accent,
    )
    style.map(
        "Primary.TButton",
        background=[("disabled", PALETTE["accent_disabled"]), ("active", PALETTE["accent_hover"])],
        foreground=[("disabled", "#FFFFFF"), ("!disabled", "#FFFFFF")],
    )

    style.configure(
        "TCombobox",
        fieldbackground=card,
        background=card,
        foreground=text,
        bordercolor=border,
        arrowcolor=muted,
        padding=6,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", card), ("disabled", bg)],
        foreground=[("disabled", muted)],
    )
    style.configure("TEntry", fieldbackground=card, foreground=text, bordercolor=border, padding=6)
    style.configure("TCheckbutton", background=card, foreground=text)
    style.configure(
        "TProgressbar",
        background=accent,
        troughcolor=PALETTE["trough"],
        borderwidth=0,
        thickness=6,
    )
    return family


def brand(root):
    path = Path(__file__).resolve().parents[1] / "assets/brand/ortts-icon.png"
    if not path.is_file():
        return None
    icon = tk.PhotoImage(master=root, file=str(path))
    root.iconphoto(True, icon)
    scale = max(1, (icon.width() + 55) // 56)
    return icon.subsample(scale)
