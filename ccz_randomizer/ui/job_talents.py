from __future__ import annotations

import json
import sys
from pathlib import Path


def load_job_talents() -> tuple[dict, ...]:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    path = root / "resources" / "data" / "recruitment" / "job_talents_2.2.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != 1 or payload.get("gameVersion") != "2.2":
        raise ValueError("兵种天赋目录版本不匹配")
    jobs = payload.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise ValueError("兵种天赋目录为空")
    for job in jobs:
        if type(job.get("jobId")) is not int or not isinstance(job.get("name"), str) or not isinstance(job.get("talents"), list):
            raise ValueError("兵种天赋目录格式错误")
        if not all(isinstance(item, str) for item in job["talents"]):
            raise ValueError("兵种天赋名称格式错误")
    return tuple(jobs)


def show_job_talents_window(parent) -> None:
    import tkinter as tk
    from tkinter import messagebox, ttk

    try:
        jobs = load_job_talents()
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
    ttk.Label(outer, text="这是 2.2 规则目录中的完整兵种天赋，不受本次随机结果影响。", foreground=colors["muted"]).pack(anchor="w", pady=(4, 12))
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
    canvas.create_window((0, 0), window=content, anchor="nw")
    count = ttk.Label(outer, foreground=colors["muted"])
    count.pack(anchor="w", pady=(10, 0))

    def refresh(*_args):
        for child in content.winfo_children():
            child.destroy()
        term = query.get().casefold().strip()
        visible = [job for job in jobs if not term or term in (job["name"] + " " + " ".join(job["talents"])).casefold()]
        for position, job in enumerate(visible):
            card = tk.Frame(content, bg=colors["surface"], highlightbackground="#D9DEE7", highlightthickness=1, padx=12, pady=10)
            card.grid(row=position // 3, column=position % 3, sticky="nsew", padx=6, pady=6)
            tk.Label(card, text=job["name"], bg=colors["surface"], fg=colors["ink"], font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")
            tk.Label(card, text="\n".join(job["talents"]) if job["talents"] else "无特殊兵种天赋", bg=colors["surface"], fg=colors["ink"], justify="left", wraplength=230).pack(anchor="w", pady=(8, 0))
        count.configure(text=f"显示 {len(visible)} / {len(jobs)} 个兵种")
        content.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

    content.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
    query.trace_add("write", refresh)
    refresh()
