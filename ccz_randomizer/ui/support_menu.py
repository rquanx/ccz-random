"""Grouped entry points for help, troubleshooting and maintenance."""
import tkinter as tk
from tkinter import ttk

from ccz_randomizer.ui.window_position import centered_toplevel, show_centered
from ccz_randomizer.ui.theme import FONT


def show_support_menu(parent, actions, package_version):
    dialog = centered_toplevel(parent)
    dialog.title("常见问题")
    dialog.resizable(False, False)
    dialog.transient(parent)
    body = tk.Frame(dialog, padx=18, pady=16)
    body.pack(fill="both", expand=True)
    groups = (
        ("使用帮助", (("guide", "不会用？"), ("effects", "特效手册"))),
        ("故障排查", (("diagnostics", "随机用不了？"), ("sound", "游戏没声音"),
                     ("logs", "上传最新日志"))),
        ("数据与维护", (("update", f"手动更新数据（{package_version}）"), ("cleanup", "空间清理"))),
    )
    for index, (heading, entries) in enumerate(groups):
        section = tk.Frame(body)
        section.pack(fill="x", pady=(14 if index else 0, 0))
        title = tk.Frame(section)
        title.pack(fill="x", pady=(0, 7))
        tk.Label(title, text=heading, fg="#667085", font=(FONT, 9)).pack(side="left")
        ttk.Separator(title).pack(side="left", fill="x", expand=True, padx=(10, 0))
        buttons = tk.Frame(section)
        buttons.pack(fill="x")
        for column in range(2):
            buttons.columnconfigure(column, weight=1, uniform="support-actions")
        for position, (key, text) in enumerate(entries):
            last_wide = position == len(entries)-1 and len(entries) % 2
            button = ttk.Button(buttons, text=text, command=lambda action=actions[key]: action(dialog))
            button.grid(row=position//2, column=position % 2, columnspan=2 if last_wide else 1,
                sticky="ew", padx=(0 if last_wide or position % 2 == 0 else 4,
                                   0 if last_wide or position % 2 else 4), pady=(0, 6))
    ttk.Button(body, text="关闭", width=10, command=dialog.destroy).pack(anchor="e", pady=(12, 0))
    dialog.update_idletasks()
    width, height = max(400, dialog.winfo_reqwidth()), dialog.winfo_reqheight()
    dialog.geometry(f"{width}x{height}")
    show_centered(dialog)
    dialog.grab_set()
    return dialog
