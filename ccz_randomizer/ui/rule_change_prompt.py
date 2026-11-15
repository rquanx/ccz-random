"""Focused, consistent confirmation for saving or discarding filter edits."""
from tkinter import ttk
import tkinter as tk

from ccz_randomizer.ui.window_position import centered_toplevel, show_centered
from ccz_randomizer.ui.theme import COLORS, FONT, setup_theme


def ask_rule_change(parent, *, closing=False, has_statistics=False):
    previous = parent.grab_current()
    previous_mode = previous.grab_status() if previous is not None else None
    dialog = centered_toplevel(parent)
    dialog.title("放弃修改" if closing else "保存修改")
    dialog.transient(parent)
    dialog.resizable(False, False)
    setup_theme(dialog)
    dialog.configure(bg=COLORS["surface"])
    result = ["cancel"]

    def choose(value):
        result[0] = value
        dialog.destroy()

    body = tk.Frame(dialog, bg=COLORS["surface"], padx=28, pady=26)
    body.pack(fill="both", expand=True)
    tk.Label(body, text="放弃本次修改？" if closing else "保存规则修改？",
             font=(FONT, 16, "bold"), fg=COLORS["ink"], bg=COLORS["surface"]).pack(anchor="w")
    text = ("尚有未保存的过滤条件修改，关闭后将放弃这些修改。" if closing else
            "过滤条件已修改，确认保存并覆盖当前规则？")
    tk.Label(body, text=text, justify="left", wraplength=460,
             fg=COLORS["muted"], bg=COLORS["surface"]).pack(anchor="w", pady=(12, 0))
    if has_statistics is not False:
        note = tk.Frame(body, bg=COLORS["accent_soft"], padx=16, pady=14)
        note.pack(fill="x", pady=(20, 0))
        note_title = "已有统计数据" if has_statistics else "统计关联暂未核实"
        if closing:
            detail = "放弃修改后，原规则及已有统计关联保持不变。"
        elif has_statistics:
            detail = "覆盖后，旧数据仍保留在全部统计中，但不再归入当前规则筛选。\n选择“保存为新规则”可保留原规则及其统计关联。"
        else:
            detail = "暂时无法读取统计数据，覆盖可能改变现有统计关联。\n选择“保存为新规则”可保留原规则。"
        tk.Label(note, text=note_title, font=(FONT, 10, "bold"), anchor="w",
                 fg=COLORS["accent"], bg=COLORS["accent_soft"]).pack(fill="x")
        tk.Label(note, text=detail, wraplength=428, justify="left", anchor="w",
                 fg=COLORS["ink"], bg=COLORS["accent_soft"]).pack(fill="x", pady=(6, 0))

    tk.Frame(dialog, height=1, bg=COLORS["border"]).pack(fill="x")
    actions = tk.Frame(dialog, bg=COLORS["surface_alt"], padx=24, pady=18)
    actions.pack(fill="x")

    from ccz_randomizer.ui.dialog_actions import add_dialog_actions
    buttons = add_dialog_actions(actions,
        confirm=lambda: choose("confirm"), confirm_text="放弃修改" if closing else "确认覆盖",
        cancel=lambda: choose("cancel"),
        alternatives=(("保存为新规则", lambda: choose("new")),), danger=closing)
    cancel = buttons["cancel"]
    dialog.protocol("WM_DELETE_WINDOW", lambda: choose("cancel"))
    dialog.bind("<Escape>", lambda _: choose("cancel"))
    show_centered(dialog)
    dialog.grab_set()
    cancel.focus_set()
    try:
        parent.wait_window(dialog)
    finally:
        try:
            if previous is not None and previous.winfo_exists():
                previous.grab_set_global() if previous_mode == "global" else previous.grab_set()
            if parent.winfo_exists():
                parent.focus_set()
        except tk.TclError:
            pass
    return result[0]
