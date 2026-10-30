"""Shared initial placement for application dialogs."""
from __future__ import annotations

import tkinter as tk


def center_on_parent(window, parent) -> None:
    parent = parent.winfo_toplevel()
    window.update_idletasks()
    width, height = window.winfo_width(), window.winfo_height()
    # geometry positions the outer frame; rootx/rooty point inside the title
    # bar and borders and would shift the dialog right and down.
    x = parent.winfo_x() + (parent.winfo_width() - width) // 2
    y = parent.winfo_y() + (parent.winfo_height() - height) // 2
    # Clamp only to the desktop, not to the parent's upper-left corner:
    # a dialog larger than its parent still needs to be centered.
    left, top = window.winfo_vrootx(), window.winfo_vrooty()
    x = max(left, min(x, left + max(0, window.winfo_vrootwidth() - width)))
    y = max(top, min(y, top + max(0, window.winfo_vrootheight() - height)))
    window.geometry(f"+{x}+{y}")


def centered_toplevel(parent):
    window = tk.Toplevel(parent)
    # Tk needs to map the native window to resolve its final dimensions.
    # Keep it transparent until placement is complete, including when callers
    # explicitly withdraw/deiconify or run layout updates during construction.
    window.attributes("-alpha", 0.0)
    pending = None
    positioned = False

    def place() -> None:
        nonlocal pending
        pending = None
        if window.winfo_exists() and parent.winfo_exists():
            center_on_parent(window, parent)
            window.update_idletasks()
            window.attributes("-alpha", 1.0)

    def mapped(event) -> None:
        nonlocal pending, positioned
        if event.widget is window and not positioned:
            positioned = True
            pending = window.after(0, place)

    def destroyed(event) -> None:
        nonlocal pending
        if event.widget is window and pending is not None:
            window.after_cancel(pending)
            pending = None

    window.bind("<Map>", mapped, add="+")
    window.bind("<Destroy>", destroyed, add="+")
    return window
