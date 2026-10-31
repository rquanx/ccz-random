"""Shared entry points for live scoring and saved result details."""


def add_detail_actions(parent, dialog, snapshot, *, include_equipment=True):
    import tkinter as tk
    from tkinter import messagebox
    from ccz_randomizer.ui.job_talents import show_job_talents_window
    from ccz_randomizer.ui.recruitment import show_recruit_window
    from ccz_randomizer.ui.equipment import show_equipment_window

    background = parent.cget("background")
    bar = tk.Frame(parent, bg=background)
    bar.pack(fill="x", pady=(2, 14))

    def recruitment():
        if not snapshot.get("personnel") and not snapshot.get("fixedPersonnel"):
            messagebox.showinfo("入队人员信息", "本次尝试没有采集入队人员信息，请查看新生成的合格结果。", parent=dialog)
            return
        show_recruit_window(dialog, snapshot=snapshot)

    actions = []
    if include_equipment:
        actions.append(("宝物信息", lambda: show_equipment_window(dialog, snapshot=snapshot)))
    actions.extend([
        ("入队人员信息", recruitment),
        ("兵种天赋", lambda: show_job_talents_window(dialog, snapshot=snapshot)),
    ])
    action_count = len(actions)
    for column, (label, command) in enumerate(actions):
        bar.columnconfigure(column, weight=1, uniform="detail-action")
        outline = tk.Frame(bar, bg="#DCE3EC", padx=1, pady=1)
        outline.grid(row=0, column=column, sticky="ew",
                     padx=(0 if column == 0 else 5, 0 if column == action_count - 1 else 5))
        button = tk.Button(
            outline, text=label, command=command,
            font=("Microsoft YaHei UI", 10),
            bg="#F5F7FA", fg="#334E73",
            activebackground="#E7EFFB", activeforeground="#2457C5",
            relief="flat", overrelief="flat", borderwidth=0,
            highlightthickness=0, cursor="hand2", takefocus=True,
            padx=12, pady=10,
        )
        button.pack(fill="x")

        def update_style(_event=None, *, target=button, border=outline):
            focused = target.focus_get() is target
            hovered = target.winfo_containing(target.winfo_pointerx(), target.winfo_pointery()) is target
            active = focused or hovered
            target.configure(bg="#EAF0FB" if active else "#F5F7FA",
                             fg="#2457C5" if active else "#334E73")
            border.configure(bg="#7297D5" if active else "#DCE3EC")

        for event in ("<Enter>", "<Leave>", "<FocusIn>", "<FocusOut>"):
            button.bind(event, update_style)
    return bar
