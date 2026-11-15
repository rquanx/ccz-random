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
    owner = root._root()
    if getattr(owner, "_ccz_theme_initialized", False):
        return
    root.option_add("*Font", f"{{{FONT}}} 10")
    root.option_add("*Label.Font", f"{{{FONT}}} 10")
    root.option_add("*Entry.Font", f"{{{FONT}}} 10")
    root.option_add("*TCombobox*Listbox.font", f"{{{FONT}}} 10")
    style = ttk.Style(root)
    style.configure("TButton", font=(FONT, 10), padding=(8, 2))
    style.configure("Primary.TButton", font=(FONT, 10, "bold"), foreground=COLORS["accent"])
    style.configure("Danger.TButton", foreground=COLORS["danger"])
    style.configure("Compact.TButton", padding=(4, 1))
    style.configure("Icon.TButton", padding=2)
    for button_style in ("Primary.TButton", "Danger.TButton", "Compact.TButton", "Icon.TButton"):
        style.map(button_style, foreground=[("disabled", COLORS["muted"])])
    style.configure("TLabel", font=(FONT, 10))
    style.configure("TEntry", padding=(6, 4))
    style.configure("TCombobox", padding=(6, 4))
    for control in ("TEntry", "TCombobox"):
        style.configure(control, foreground=COLORS["ink"], fieldbackground=COLORS["surface"])
        style.map(control, fieldbackground=[("disabled", COLORS["surface_alt"]),
                                           ("readonly", COLORS["surface"])],
                  foreground=[("disabled", COLORS["muted"])])
    # Card editors have a fixed height; standard form padding would clip text.
    style.configure("Inline.TEntry", padding=(3, 0))
    style.configure("Inline.TCombobox", padding=(2, 0))
    style.configure("Treeview", font=(FONT, 10), rowheight=28)
    style.configure("Treeview.Heading", font=(FONT, 10, "bold"))
    owner._ccz_theme_initialized = True


def style_dialog(dialog: tk.Misc) -> None:
    """Set the common dialog background; child frames may override it."""
    dialog.configure(bg=COLORS["page"])

