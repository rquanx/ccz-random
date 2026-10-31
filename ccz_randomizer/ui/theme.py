"""Shared Tk/ttk visual defaults for the desktop application."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

FONT = "Microsoft YaHei UI"
COLORS = {
    "page": "#F4F6FA",
    "surface": "#FFFFFF",
    "surface_alt": "#F8FAFC",
    "ink": "#182230",
    "muted": "#667085",
    "border": "#D9E0EA",
    "accent": "#2563EB",
    "accent_soft": "#EAF0FB",
    "danger": "#B42318",
    "success": "#18794E",
}


def setup_theme(root: tk.Misc) -> None:
    """Apply the same fonts, colors, and spacing to Tk and ttk controls."""
    root.option_add("*Font", f"{{{FONT}}} 10")
    root.option_add("*Button.Font", f"{{{FONT}}} 10")
    root.option_add("*Label.Font", f"{{{FONT}}} 10")
    root.option_add("*Entry.Font", f"{{{FONT}}} 10")
    style = ttk.Style(root)
    style.configure("TButton", font=(FONT, 10), padding=(10, 6))
    style.configure("TLabel", font=(FONT, 10))
    style.configure("TEntry", padding=(6, 4))
    style.configure("TCombobox", padding=(6, 3))
    style.configure("Treeview", font=(FONT, 10), rowheight=28)
    style.configure("Treeview.Heading", font=(FONT, 10, "bold"))


def style_dialog(dialog: tk.Misc) -> None:
    """Set the common dialog background; child frames may override it."""
    dialog.configure(bg=COLORS["page"])

