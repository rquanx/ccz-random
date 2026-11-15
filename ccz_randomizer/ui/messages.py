"""Application messages use the same themed controls and action order as editors."""
import tkinter as tk
from tkinter import scrolledtext

from ccz_randomizer.ui.dialog_actions import add_dialog_actions
from ccz_randomizer.ui.theme import COLORS, FONT, setup_theme
from ccz_randomizer.ui.window_position import centered_toplevel, show_centered


def _show(title, message, *, parent=None, question=False, choices=False, danger=False, **_options):
    parent = parent or tk._default_root
    owned = parent is None
    if owned:
        parent = tk.Tk()
        parent.withdraw()
    previous = parent.grab_current()
    previous_mode = previous.grab_status() if previous is not None else None
    dialog = centered_toplevel(parent)
    setup_theme(dialog)
    dialog.title(title or "提示")
    dialog.transient(parent)
    dialog.resizable(False, False)
    dialog.configure(bg=COLORS["surface"])
    result = [None if choices else False if question else "ok"]
    def choose(value):
        result[0] = value
        dialog.destroy()
    actions = tk.Frame(dialog, bg=COLORS["surface_alt"], padx=20, pady=16)
    actions.pack(fill="x", side="bottom")
    body = tk.Frame(dialog, bg=COLORS["surface"], padx=24, pady=22)
    body.pack(fill="both", expand=True)
    tk.Label(body, text=title or "提示", bg=COLORS["surface"], fg=COLORS["ink"],
             font=(FONT, 13, "bold"), anchor="w").pack(fill="x")
    message = str(message or "")
    if len(message) > 700 or message.count("\n") > 12:
        content = scrolledtext.ScrolledText(body, width=58, height=12, wrap="word", font=(FONT, 10),
                                            bg=COLORS["surface"], fg=COLORS["ink"], relief="flat")
        content.insert("1.0", message)
        content.configure(state="disabled")
        content.pack(fill="both", expand=True, pady=(12, 0))
    else:
        tk.Label(body, text=message, bg=COLORS["surface"], fg=COLORS["ink"],
                 wraplength=500, justify="left", anchor="w").pack(fill="x", pady=(12, 0))
    buttons = add_dialog_actions(actions, confirm=lambda: choose(True if question else "ok"),
        confirm_text="三人规则" if choices else "确认" if question else "关闭",
        cancel=(lambda: choose(None if choices else False)) if question else None,
        alternatives=(("七人规则", lambda: choose(False)),) if choices else (), danger=danger)
    dialog.protocol("WM_DELETE_WINDOW", lambda: choose(None if choices else False if question else "ok"))
    dialog.bind("<Escape>", lambda _: choose(None if choices else False if question else "ok"))
    show_centered(dialog)
    dialog.grab_set()
    buttons.get("cancel", buttons["confirm"]).focus_set()
    try:
        parent.wait_window(dialog)
    finally:
        if owned:
            parent.destroy()
        elif previous is not None:
            try:
                if previous.winfo_exists():
                    previous.grab_set_global() if previous_mode == "global" else previous.grab_set()
            except tk.TclError:
                pass
    return result[0]


def askyesno(title=None, message=None, **options):
    options.setdefault("danger", options.get("icon") == "warning" or
                       any(word in (title or "") for word in ("删除", "清空", "清理", "放弃", "退出")))
    return _show(title, message, question=True, **options)


def askyesnocancel(title=None, message=None, **options):
    return _show(title, message, question=True, choices=True, **options)


def showinfo(title=None, message=None, **options):
    return _show(title, message, **options)


def showwarning(title=None, message=None, **options):
    return _show(title, message, **options)


def showerror(title=None, message=None, **options):
    return _show(title, message, **options)
