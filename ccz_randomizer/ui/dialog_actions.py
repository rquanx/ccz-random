"""One action order for dialogs: cancel, alternatives, primary action."""
from tkinter import ttk

from ccz_randomizer.ui.theme import setup_theme


def add_dialog_actions(parent, *, confirm=None, confirm_text="确认", cancel=None,
                       cancel_text="取消", alternatives=(), danger=False):
    setup_theme(parent)
    buttons = {}
    if confirm is not None:
        button = ttk.Button(parent, text=confirm_text, command=confirm,
                            style="TButton" if confirm_text == "关闭" else "Danger.TButton" if danger else "Primary.TButton")
        button.pack(side="right")
        buttons["confirm"] = button
    for label, command in reversed(alternatives):
        button = ttk.Button(parent, text=label, command=command)
        button.pack(side="right", padx=(0, 8))
        buttons[label] = button
    if cancel is not None:
        button = ttk.Button(parent, text=cancel_text, command=cancel)
        button.pack(side="right", padx=(0, 8 if confirm is not None or alternatives else 0))
        buttons["cancel"] = button
    return buttons
