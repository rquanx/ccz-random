from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path

from ccz_randomizer.recruitment import Recruit, filter_recruits, parse_recruits


def show_recruit_window(parent, catalog_path: Path | None = None, *, snapshot: dict | None = None) -> None:
    """Show result-bound recruitment data as one horizontal card row per stage."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    if catalog_path is None and snapshot is None:
        filename = filedialog.askopenfilename(parent=parent, title="打开 2.2 人员快照", filetypes=[("人员快照", "*.json")])
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
    dialog.title("2.2 招募人物")
    dialog.geometry("1180x760")
    dialog.minsize(820, 560)
    dialog.transient(parent)
    colors = {"ink": "#182230", "muted": "#667085", "surface": "#FFFFFF", "surface_alt": "#F4F6FA"}
    style = ttk.Style(dialog)
    style.configure("Recruit.TFrame", background=colors["surface"])
    style.configure("Recruit.Card.TFrame", background=colors["surface"], relief="solid", borderwidth=1)
    style.configure("Recruit.Stage.TFrame", background=colors["surface_alt"])
    style.configure("Recruit.CardTitle.TLabel", background=colors["surface"], foreground=colors["ink"], font=("Microsoft YaHei UI", 11, "bold"))
    style.configure("Recruit.Body.TLabel", background=colors["surface"], foreground=colors["ink"], font=("Microsoft YaHei UI", 9))
    style.configure("Recruit.Muted.TLabel", background=colors["surface"], foreground=colors["muted"], font=("Microsoft YaHei UI", 9))
    style.configure("Recruit.Stage.TLabel", background=colors["surface_alt"], foreground=colors["ink"], font=("Microsoft YaHei UI", 11, "bold"))

    outer = ttk.Frame(dialog, padding=20, style="Recruit.TFrame")
    outer.pack(fill="both", expand=True)
    ttk.Label(outer, text="2.2 招募人物", style="Recruit.CardTitle.TLabel", font=("Microsoft YaHei UI", 17, "bold")).pack(anchor="w")
    source = {"title": "标题界面基础数据，非随机结果", "randomized": "本次随机结果"}.get(payload.get("phase"), "读取时机待验证")
    label = catalog_path.name if catalog_path else f"第 {payload.get('slot', '-')} 号存档"
    ttk.Label(outer, text=f"{label} · {source}", style="Recruit.Muted.TLabel").pack(anchor="w", pady=(4, 8))
    guidance = ttk.Label(outer, text=("每行是一个关卡，卡片展示该关卡的招募人物。初始三人参与合格判断；招募候选受路线、15 次额度和特殊人物规则影响。" if all(row.availability_verified for row in recruits) else "招募关系未确认的记录可能包括敌军和占位人物，不参与合格判断。"), wraplength=1080, style="Recruit.Muted.TLabel")
    guidance.pack(anchor="w")

    filters = ttk.Frame(outer, style="Recruit.TFrame")
    filters.pack(fill="x", pady=12)
    query, stage = tk.StringVar(), tk.StringVar(value="全部关卡")
    only_selected = tk.BooleanVar(value=False)
    ttk.Label(filters, text="搜索人物、兵种或天赋", style="Recruit.Muted.TLabel").pack(side="left")
    entry = ttk.Entry(filters, textvariable=query, width=28)
    entry.pack(side="left", padx=(8, 12))
    stage_values = tuple(OrderedDict.fromkeys(value for row in recruits for value in (row.stages or (row.stage,))))
    ttk.Combobox(filters, textvariable=stage, state="readonly", width=24, values=("全部关卡", *stage_values)).pack(side="left", padx=(0, 12))
    ttk.Checkbutton(filters, text="只看关注人物", variable=only_selected).pack(side="left")

    body = ttk.Frame(outer, style="Recruit.TFrame")
    body.pack(fill="both", expand=True)
    body.rowconfigure(0, weight=1)
    body.columnconfigure(0, weight=1)
    canvas = tk.Canvas(body, background=colors["surface_alt"], highlightthickness=0)
    canvas.grid(row=0, column=0, sticky="nsew")
    vertical = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
    vertical.grid(row=0, column=1, sticky="ns")
    horizontal = ttk.Scrollbar(body, orient="horizontal", command=canvas.xview)
    horizontal.grid(row=1, column=0, sticky="ew")
    canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    content = ttk.Frame(canvas, style="Recruit.TFrame")
    content_window = canvas.create_window((0, 0), window=content, anchor="nw")

    details = tk.StringVar(value="点击人物卡片查看完整信息；关注状态只作用于本次查看。")
    detail_label = ttk.Label(outer, textvariable=details, wraplength=1080, justify="left", style="Recruit.Muted.TLabel")
    detail_label.pack(fill="x", pady=(10, 4))
    footer = ttk.Frame(outer, style="Recruit.TFrame")
    footer.pack(fill="x")
    count = ttk.Label(footer, style="Recruit.Muted.TLabel")
    count.pack(side="left")

    selected: set[int] = set()
    stage_people: OrderedDict[str, list[Recruit]] = OrderedDict()
    for row in recruits:
        for stage_name in row.stages or (row.stage,):
            stage_people.setdefault(stage_name, []).append(row)

    def show_details(row: Recruit) -> None:
        note = ""
        if row.job_choices:
            note += "\n招募兵种选项：" + "、".join(row.job_choices) + "。这是招募前预览，选择兵种后天赋可能变化。"
        if row.fixed_configuration:
            note += "\n固定配置人物：招募时可能另有装备或天赋调整；彩蛋女武将之间互斥。"
        details.set(f"{row.name} · {row.job} · 招募消耗 {row.cost}\n兵种天赋：{'、'.join(row.job_talents) or '无'}\n人物天赋：{'、'.join(row.personal_talents) or '无'}{note}")

    def toggle(row: Recruit) -> None:
        if row.record_index in selected:
            selected.remove(row.record_index)
        else:
            selected.add(row.record_index)
        refresh()

    def card(parent_frame, row: Recruit) -> None:
        card_frame = ttk.Frame(parent_frame, style="Recruit.Card.TFrame", padding=10, width=226, height=166)
        card_frame.pack(side="left", anchor="n", padx=(0, 10), pady=(0, 8))
        card_frame.pack_propagate(False)
        title_row = ttk.Frame(card_frame, style="Recruit.Card.TFrame")
        title_row.pack(fill="x")
        ttk.Label(title_row, text=row.name, style="Recruit.CardTitle.TLabel").pack(side="left")
        ttk.Label(title_row, text=f"{row.cost}次", style="Recruit.Muted.TLabel").pack(side="right")
        job_text = row.job + (" · 可选兵种" if row.job_choices else " · 固定配置" if row.fixed_configuration else "")
        ttk.Label(card_frame, text=job_text, style="Recruit.Body.TLabel").pack(anchor="w", pady=(5, 0))
        ttk.Label(card_frame, text="兵种天赋：" + ("、".join(row.job_talents) or "无"), style="Recruit.Muted.TLabel", wraplength=204, justify="left").pack(anchor="w", pady=(3, 0))
        ttk.Label(card_frame, text="人物天赋：" + ("、".join(row.personal_talents) or "无"), style="Recruit.Muted.TLabel", wraplength=204, justify="left").pack(anchor="w", pady=(3, 0))
        ttk.Button(card_frame, text="取消关注" if row.record_index in selected else "关注", command=lambda: toggle(row)).pack(anchor="e", side="bottom")
        for widget in (card_frame, title_row):
            widget.bind("<Button-1>", lambda _event, item=row: show_details(item))

    def refresh(*_args) -> None:
        for child in content.winfo_children():
            child.destroy()
        visible = filter_recruits(recruits, query.get(), stage="" if stage.get() == "全部关卡" else stage.get(), selected=frozenset(selected) if only_selected.get() else None)
        visible_ids = {row.record_index for row in visible}
        shown_stages = 0
        for stage_name, people in stage_people.items():
            people = [row for row in people if row.record_index in visible_ids]
            if not people:
                continue
            shown_stages += 1
            stage_frame = ttk.Frame(content, style="Recruit.Stage.TFrame", padding=(12, 10, 12, 2))
            stage_frame.pack(fill="x", pady=(0, 10))
            ttk.Label(stage_frame, text=stage_name, style="Recruit.Stage.TLabel").pack(anchor="w", pady=(0, 8))
            cards = ttk.Frame(stage_frame, style="Recruit.Stage.TFrame")
            cards.pack(anchor="w", fill="x")
            for row in people:
                card(cards, row)
        count.configure(text=f"显示 {len(visible)} / {len(recruits)} 人 · {shown_stages} 个关卡 · 已关注 {len(selected)} 人")
        content.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

    def resize(_event=None) -> None:
        width = max(400, outer.winfo_width() - 40)
        detail_label.configure(wraplength=width)
        guidance.configure(wraplength=width)
        canvas.itemconfigure(content_window, width=max(content.winfo_reqwidth(), canvas.winfo_width()))

    content.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
    outer.bind("<Configure>", resize)
    canvas.bind("<MouseWheel>", lambda event: canvas.yview_scroll(-int(event.delta / 120), "units"))
    for variable in (query, stage, only_selected):
        variable.trace_add("write", refresh)
    refresh()
    entry.focus_set()
