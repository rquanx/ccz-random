from __future__ import annotations

from ccz_randomizer.jobs import JOB_MAP


def load_job_talents(snapshot: dict) -> tuple[dict, ...]:
    """Never substitute a different random result for missing historical data."""
    rows = snapshot.get("jobTalents")
    if rows is None:
        return tuple({"jobId": i, "name": value[0], "talents": None} for i, value in JOB_MAP.items())
    if not isinstance(rows, list):
        raise ValueError("兵种天赋快照格式错误")
    by_id = {}
    for row in rows:
        if not isinstance(row, dict) or type(row.get("jobId")) is not int or row["jobId"] not in JOB_MAP:
            raise ValueError("兵种天赋快照编号无效")
        if row["jobId"] in by_id or not isinstance(row.get("talents"), list) or not all(isinstance(s, str) for s in row["talents"]):
            raise ValueError("兵种天赋快照数据无效")
        by_id[row["jobId"]] = row["talents"]
    return tuple({"jobId": i, "name": value[0], "talents": by_id.get(i)} for i, value in JOB_MAP.items())


def show_job_talents_window(parent, *, snapshot: dict) -> None:
    import tkinter as tk
    from tkinter import messagebox, ttk

    try:
        jobs = load_job_talents(snapshot)
    except (OSError, ValueError) as exc:
        messagebox.showerror("无法读取兵种天赋", str(exc), parent=parent)
        return
    dialog = tk.Toplevel(parent)
    dialog.title("2.2 兵种天赋")
    dialog.geometry("900x680")
    dialog.minsize(680, 480)
    dialog.transient(parent)
    colors = {"ink": "#182230", "muted": "#667085", "surface": "#FFFFFF", "page": "#F4F6FA"}
    outer = ttk.Frame(dialog, padding=20)
    outer.pack(fill="both", expand=True)
    ttk.Label(outer, text="全部兵种天赋", font=("Microsoft YaHei UI", 17, "bold")).pack(anchor="w")
    ttk.Label(outer, text="本次随机的 40 类兵种天赋；未采集的历史数据标为未采集，不代表无天赋。", foreground=colors["muted"]).pack(anchor="w", pady=(4, 12))
    query = tk.StringVar()
    ttk.Entry(outer, textvariable=query, width=32).pack(anchor="w", pady=(0, 12))
    body = ttk.Frame(outer)
    body.pack(fill="both", expand=True)
    body.rowconfigure(0, weight=1)
    body.columnconfigure(0, weight=1)
    canvas = tk.Canvas(body, background=colors["page"], highlightthickness=0)
    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
    scrollbar.grid(row=0, column=1, sticky="ns")
    canvas.configure(yscrollcommand=scrollbar.set)
    content = ttk.Frame(canvas)
    window = canvas.create_window((0, 0), window=content, anchor="nw")
    for column in range(3):
        content.columnconfigure(column, weight=1, uniform="job")
    canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
    count = ttk.Label(outer, foreground=colors["muted"])
    count.pack(anchor="w", pady=(10, 0))

    def refresh(*_args):
        for child in content.winfo_children():
            child.destroy()
        term = query.get().casefold().strip()
        visible = [job for job in jobs if not term or term in (job["name"] + " " + " ".join(job["talents"] or [])).casefold()]
        for position, job in enumerate(visible):
            card = tk.Frame(content, bg=colors["surface"], highlightbackground="#D9DEE7", highlightthickness=1, padx=12, pady=10)
            card.grid(row=position // 3, column=position % 3, sticky="nsew", padx=6, pady=6)
            tk.Label(card, text=job["name"], bg=colors["surface"], fg=colors["ink"], font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")
            tk.Label(card, text=("未采集（请查看新生成的结果）" if job["talents"] is None else "\n".join(job["talents"]) or "无兵种天赋"), bg=colors["surface"], fg=colors["ink"], justify="left", wraplength=230).pack(anchor="w", pady=(8, 0))
        count.configure(text=f"显示 {len(visible)} / {len(jobs)} 个兵种")
        content.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

    content.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
    def wheel(event):
        canvas.yview_scroll(-int(event.delta / 120), "units")
    dialog.bind("<MouseWheel>", wheel)
    query.trace_add("write", refresh)
    refresh()
