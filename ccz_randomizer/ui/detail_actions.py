"""Shared entry points for live scoring and saved result details."""
from tkinter import ttk


def add_detail_actions(parent, dialog, snapshot, *, include_equipment=True):
    import tkinter as tk
    from ccz_randomizer.ui import messages as messagebox
    from ccz_randomizer.ui.job_talents import show_job_talents_window
    from ccz_randomizer.ui.recruitment import show_recruit_window
    from ccz_randomizer.ui.equipment import show_equipment_window

    background = parent.cget("background")
    bar = tk.Frame(parent, bg=background)
    bar.pack(fill="x", pady=(2, 14))

    def recruitment():
        if not snapshot.get("personnel") and not snapshot.get("fixedPersonnel"):
            messagebox.showinfo(
                "入队人员信息",
                "本次结果未采集入队人员信息。\n\n"
        "请在规则设置 → 高级模式 → 实验功能中，开启“采集入队人员信息”，"
                "然后重新运行并查看新的合格结果。",
                parent=dialog,
            )
            return
        show_recruit_window(dialog, snapshot=snapshot)

    def job_talents():
        if snapshot.get("jobTalents") is None:
            messagebox.showinfo(
                "兵种天赋",
                "本次结果未采集兵种天赋。\n\n"
        "请在规则设置 → 高级模式 → 实验功能中，开启“采集兵种天赋”，"
                "然后重新运行并查看新的合格结果。",
                parent=dialog,
            )
            return
        show_job_talents_window(dialog, snapshot=snapshot)

    actions = []
    if include_equipment:
        actions.append(("宝物信息", lambda: show_equipment_window(dialog, snapshot=snapshot)))
    actions.extend([
        ("入队人员信息", recruitment),
        ("兵种天赋", job_talents),
    ])
    for column, (label, command) in enumerate(actions):
        bar.columnconfigure(column, weight=1, uniform="detail-action")
        ttk.Button(bar, text=label, command=command).grid(
            row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))
    return bar
