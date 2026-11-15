"""Small modal text prompts using the same placement as other tool dialogs."""
from ccz_randomizer.ui.dialog_actions import add_dialog_actions
import tkinter as tk
from tkinter import ttk

from ccz_randomizer.ui.inputs import TextEntry
from ccz_randomizer.ui.window_position import centered_toplevel, show_centered


def ask_text(title, prompt, *, parent, initialvalue=""):
    previous = parent.grab_current()
    previous_mode = previous.grab_status() if previous is not None else None
    dialog = centered_toplevel(parent)
    dialog.title(title)
    dialog.transient(parent)
    dialog.resizable(False, False)
    body = ttk.Frame(dialog, padding=18)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text=prompt).pack(anchor="w")
    value = tk.StringVar(dialog, value=initialvalue)
    entry = TextEntry(body, textvariable=value, width=36)
    entry.pack(fill="x", pady=(8, 16))
    actions = ttk.Frame(body)
    actions.pack(fill="x")
    result = None

    def submit(_event=None):
        nonlocal result
        result = value.get()
        dialog.destroy()
        return "break"

    def cancel(_event=None):
        dialog.destroy()
        return "break"

    add_dialog_actions(actions, confirm=submit, cancel=cancel)
    dialog.bind("<Return>", submit)
    dialog.bind("<KP_Enter>", submit)
    dialog.bind("<Escape>", cancel)
    dialog.protocol("WM_DELETE_WINDOW", cancel)
    show_centered(dialog)
    dialog.grab_set()
    entry.focus_set()
    entry.selection_range(0, "end")
    try:
        dialog.wait_window()
    finally:
        try:
            if previous is not None and previous.winfo_exists():
                if previous_mode == "global":
                    previous.grab_set_global()
                else:
                    previous.grab_set()
            if parent.winfo_exists():
                parent.focus_set()
        except tk.TclError:
            pass  # The owning application may itself have closed.
    return result
