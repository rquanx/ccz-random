from __future__ import annotations

import json
from pathlib import Path

from ccz_randomizer.recruitment import filter_recruits, parse_recruits


def show_recruit_window(parent, catalog_path: Path | None = None, *, snapshot: dict | None = None) -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    if catalog_path is None and snapshot is None:
        filename = filedialog.askopenfilename(parent=parent, title="打开 2.2 人员快照",
            filetypes=[("人员快照", "*.json")])
        if not filename:
            return
        catalog_path = Path(filename)
    try:
        payload = snapshot if snapshot is not None else json.loads(catalog_path.read_text(encoding="utf-8"))
        recruits = parse_recruits(payload)
    except (OSError, ValueError) as exc:
        messagebox.showerror("无法读取人员快照", str(exc), parent=parent)
        return
    dialog = tk.Toplevel(parent)
    dialog.title("2.2 招募总览")
    dialog.geometry("1060x640")
    dialog.minsize(720, 460)
    dialog.transient(parent)
    style = ttk.Style(dialog)
    style.configure("Recruit.Treeview", rowheight=34, font=("Microsoft YaHei UI", 10),
                    background="#FFFFFF", fieldbackground="#FFFFFF", foreground="#1F2937")
    style.configure("Recruit.Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"))
    style.map("Recruit.Treeview", background=[("selected", "#2457C5")],
              foreground=[("selected", "#FFFFFF")])
    outer = ttk.Frame(dialog, padding=20)
    outer.pack(fill="both", expand=True)
    ttk.Label(outer, text="2.2 招募总览", font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w")
    source = {"title": "标题界面基础数据，非随机结果", "randomized": "本次随机结果 · 已开启招募模式"}.get(payload.get("phase"), "读取时机待验证")
    label = catalog_path.name if catalog_path else f"第 {payload.get('slot', '-')} 号存档"
    ttk.Label(outer, text=f"{label} · {source}").pack(anchor="w", pady=(4, 8))
    guidance = ttk.Label(outer, wraplength=960, text="关卡结束后的招募候选 · 仅初始三人参与合格判断。共 15 次招募额度；彩蛋女武将只能选一名。" if all(row.availability_verified for row in recruits) else "招募关系未确认的记录可能包括敌军和占位人物，不参与合格判断。")
    guidance.pack(anchor="w")
    filters = ttk.Frame(outer)
    filters.pack(fill="x", pady=12)
    query, stage = tk.StringVar(), tk.StringVar(value="全部关卡")
    only_selected = tk.BooleanVar(value=False)
    selected: set[int] = set()
    ttk.Label(filters, text="搜索").pack(side="left")
    entry = ttk.Entry(filters, textvariable=query, width=24)
    entry.pack(side="left", padx=8)
    ttk.Combobox(filters, textvariable=stage, state="readonly", width=18,
        values=("全部关卡", *dict.fromkeys(value for row in recruits for value in (row.stages or (row.stage,))))).pack(side="left", padx=(0, 8))
    ttk.Checkbutton(filters, text="只看关注人物", variable=only_selected).pack(side="left")
    body = ttk.Frame(outer)
    body.pack(fill="both", expand=True)
    body.rowconfigure(0, weight=1)
    body.columnconfigure(0, weight=1)
    columns = ("selected", "name", "stage", "cost", "job", "job_talents", "personal_talents")
    tree = ttk.Treeview(body, columns=columns, show="headings", selectmode="extended", style="Recruit.Treeview")
    tree.tag_configure("alternate", background="#F7F6F2")
    for column, label, width in zip(columns,
            ("关注", "人物", "招募关卡", "消耗", "兵种 / 预览", "兵种天赋", "人物天赋"),
            (50, 90, 170, 50, 140, 240, 240)):
        tree.heading(column, text=label)
        tree.column(column, width=width, minwidth=width, anchor="w")
    tree.grid(row=0, column=0, sticky="nsew")
    vertical = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
    vertical.grid(row=0, column=1, sticky="ns")
    horizontal = ttk.Scrollbar(body, orient="horizontal", command=tree.xview)
    horizontal.grid(row=1, column=0, sticky="ew")
    tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    details = tk.StringVar(value="选择人物查看完整天赋；可用 Ctrl / Shift 多选后关注。")
    detail_label = ttk.Label(outer, textvariable=details, wraplength=970, justify="left")
    detail_label.pack(fill="x", pady=10)
    def resize_details(event):
        width = max(300, event.width - 40)
        detail_label.configure(wraplength=width)
        guidance.configure(wraplength=width)
    outer.bind("<Configure>", resize_details)
    footer = ttk.Frame(outer)
    footer.pack(fill="x")
    count = ttk.Label(footer)
    count.pack(side="left")
    by_id = {str(row.record_index): row for row in recruits}

    def refresh(*_args):
        children = tree.get_children()
        if children:
            tree.delete(*children)
        visible = filter_recruits(recruits, query.get(),
            stage="" if stage.get() == "全部关卡" else stage.get(),
            selected=frozenset(selected) if only_selected.get() else None)
        for position, row in enumerate(visible):
            tree.insert("", "end", iid=str(row.record_index), tags=("alternate",) if position % 2 else (), values=(
                "是" if row.record_index in selected else "", row.name, row.stage, row.cost, row.job + ("（招募时可选）" if row.job_choices else "（固定配置）" if row.fixed_configuration else ""),
                "、".join(row.job_talents) or "无", "、".join(row.personal_talents) or "无"))
        count.configure(text=f"显示 {len(visible)} / {len(recruits)} 人 · 已关注 {len(selected)} 人")

    def toggle_selection():
        for item in tree.selection():
            index = int(item)
            if index in selected:
                selected.remove(index)
            else:
                selected.add(index)
        refresh()

    def show_details(_event):
        if tree.selection():
            row = by_id[tree.selection()[0]]
            note = ""
            if row.job_choices:
                note += "\n招募兵种选项：" + "、".join(row.job_choices) + "。上表为招募前预览，选择兵种后天赋可能变化。"
            if row.fixed_configuration:
                note += "\n彩蛋人物使用固定配置，招募时可能另有装备或天赋调整；与其他彩蛋女武将互斥。"
            details.set(f"{row.name} · {row.stage} · {row.job}\n兵种天赋：{'、'.join(row.job_talents) or '无'}\n人物天赋：{'、'.join(row.personal_talents) or '无'}" + note)

    ttk.Button(footer, text="关注 / 取消关注所选", command=toggle_selection).pack(side="right")
    tree.bind("<<TreeviewSelect>>", show_details)
    for variable in (query, stage, only_selected):
        variable.trace_add("write", refresh)
    refresh()
    entry.focus_set()
