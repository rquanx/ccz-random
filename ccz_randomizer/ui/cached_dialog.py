"""Retain expensive controls while restoring placement and modal ownership."""
import tkinter as tk
from ccz_randomizer.ui.window_position import show_centered


def hide_dialog(window):
    window._ccz_cached_closed = True
    if window.grab_current() is window:
        window.grab_release()
    def close_children(widget):
        for child in widget.winfo_children():
            if isinstance(child, tk.Toplevel):
                child.destroy()
            else:
                close_children(child)
    close_children(window)
    window.withdraw()


def restore_dialog(window, *, modal=False):
    window._ccz_cached_closed = False
    window._ccz_dialog_shown = False
    show_centered(window)
    window.lift()
    if modal:
        window.grab_set()
