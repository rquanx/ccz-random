"""Shared entry points for live scoring and saved result details."""


def add_detail_actions(parent, dialog, snapshot):
    import tkinter as tk
    from tkinter import messagebox
    from ccz_randomizer.ui.job_talents import show_job_talents_window
    from ccz_randomizer.ui.recruitment import show_recruit_window

    bar = tk.Frame(parent)
    bar.pack(fill="x", pady=(0, 10))

    def recruitment():
        if not snapshot.get("personnel"):
            messagebox.showinfo("招募人员信息", "本次尝试没有采集招募信息，请查看新生成的合格结果。", parent=dialog)
            return
        show_recruit_window(dialog, snapshot=snapshot)

    tk.Button(bar, text="兵种天赋", command=lambda: show_job_talents_window(
        dialog, snapshot=snapshot)).pack(side="left", padx=(0, 8))
    tk.Button(bar, text="招募人员信息", command=recruitment).pack(side="left")
    return bar
