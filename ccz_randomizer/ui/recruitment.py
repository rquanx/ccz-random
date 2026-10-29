from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path

from ccz_randomizer.recruitment import Recruit, filter_recruits, parse_recruits


def show_recruit_window(parent, catalog_path: Path | None = None, *, snapshot: dict | None = None) -> None:
    """Display recruitment candidates as lightweight canvas cards."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    if catalog_path is None and snapshot is None:
        filename = filedialog.askopenfilename(parent=parent, title="打开 2.2 人员快照", filetypes=[("人员快照", "*.json")])
        if not filename: return
        catalog_path = Path(filename)
    try:
        payload = snapshot if snapshot is not None else json.loads(catalog_path.read_text(encoding="utf-8"))
        recruits = parse_recruits(payload)
    except (OSError, ValueError) as exc:
        messagebox.showerror("无法读取人员快照", str(exc), parent=parent); return
    dialog = tk.Toplevel(parent); dialog.title("2.2 招募人物"); dialog.geometry("1180x760"); dialog.minsize(820, 560); dialog.transient(parent)
    colors = {"ink":"#182230", "muted":"#667085", "surface":"#FFFFFF", "alt":"#F4F6FA", "line":"#D9E0EA", "accent":"#2563EB"}
    outer = ttk.Frame(dialog, padding=20); outer.pack(fill="both", expand=True)
    ttk.Label(outer, text="2.2 招募人物", font=("Microsoft YaHei UI",17,"bold")).pack(anchor="w")
    source = {"title":"标题界面基础数据，非随机结果", "randomized":"本次随机结果"}.get(payload.get("phase"), "读取时机待验证")
    label = catalog_path.name if catalog_path else f"第 {payload.get('slot','-')} 号存档"
    ttk.Label(outer, text=f"{label} · {source}", foreground=colors["muted"]).pack(anchor="w", pady=(4,8))
    ttk.Label(outer, text=("每行是一个关卡，卡片展示该关卡的招募人物。初始三人参与合格判断；招募候选受路线、15 次额度和特殊人物规则影响。" if all(row.availability_verified for row in recruits) else "招募关系未确认的记录可能包括敌军和占位人物，不参与合格判断。"), foreground=colors["muted"], wraplength=1080).pack(anchor="w")
    filters = ttk.Frame(outer); filters.pack(fill="x", pady=12)
    query, stage = tk.StringVar(), tk.StringVar(value="全部关卡"); only_selected = tk.BooleanVar(value=False)
    ttk.Label(filters, text="搜索人物、兵种或天赋", foreground=colors["muted"]).pack(side="left")
    entry = ttk.Entry(filters, textvariable=query, width=28); entry.pack(side="left", padx=(8,12))
    stage_values = tuple(OrderedDict.fromkeys(value for row in recruits for value in (row.stages or (row.stage,))))
    ttk.Combobox(filters, textvariable=stage, state="readonly", width=24, values=("全部关卡", *stage_values)).pack(side="left", padx=(0,12))
    ttk.Checkbutton(filters, text="只看关注人物", variable=only_selected).pack(side="left")
    body = ttk.Frame(outer); body.pack(fill="both", expand=True); body.rowconfigure(0,weight=1); body.columnconfigure(0,weight=1)
    canvas = tk.Canvas(body, background=colors["alt"], highlightthickness=0); canvas.grid(row=0,column=0,sticky="nsew")
    vertical = ttk.Scrollbar(body, orient="vertical", command=canvas.yview); vertical.grid(row=0,column=1,sticky="ns")
    horizontal = ttk.Scrollbar(body, orient="horizontal", command=canvas.xview); horizontal.grid(row=1,column=0,sticky="ew")
    canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    details = tk.StringVar(value="点击人物卡片查看完整信息；关注状态只作用于本次查看。")
    detail_label = ttk.Label(outer, textvariable=details, foreground=colors["muted"], wraplength=1080, justify="left"); detail_label.pack(fill="x", pady=(10,4))
    count = ttk.Label(outer, foreground=colors["muted"]); count.pack(anchor="w")
    selected: set[int] = set(); stage_people: OrderedDict[str,list[Recruit]] = OrderedDict()
    for row in recruits:
        for stage_name in row.stages or (row.stage,): stage_people.setdefault(stage_name, []).append(row)
    refresh_after = None
    def show_details(row: Recruit) -> None:
        note = ""
        if row.job_choices: note += "\n招募兵种选项：" + "、".join(row.job_choices) + "。这是招募前预览，选择兵种后天赋可能变化。"
        if row.fixed_configuration: note += "\n固定配置人物：招募时可能另有装备或天赋调整；彩蛋女武将之间互斥。"
        details.set(f"{row.name} · {row.job} · 招募消耗 {row.cost}\n兵种天赋：{'、'.join(row.job_talents) or '无'}\n人物天赋：{'、'.join(row.personal_talents) or '无'}{note}")
    def refresh() -> None:
        nonlocal refresh_after
        refresh_after = None; canvas.delete("all")
        selected_stage = "" if stage.get()=="全部关卡" else stage.get()
        visible = filter_recruits(recruits, query.get(), stage=selected_stage, selected=frozenset(selected) if only_selected.get() else None)
        visible_ids = {row.record_index for row in visible}; y=12; shown_stages=0
        for stage_name, people_all in stage_people.items():
            if selected_stage and stage_name != selected_stage: continue
            people = [row for row in people_all if row.record_index in visible_ids]
            if not people: continue
            shown_stages += 1; canvas.create_text(14,y,anchor="nw",text=stage_name,fill=colors["ink"],font=("Microsoft YaHei UI",11,"bold")); y += 31
            for i,row in enumerate(people):
                x=14+i*246; top=y; right=x+236; bottom=y+154; tag=f"card:{row.record_index}"
                canvas.create_rectangle(x,top,right,bottom,fill=colors["surface"],outline=colors["line"],tags=(tag,))
                canvas.create_text(x+10,top+10,anchor="nw",text=row.name,fill=colors["ink"],font=("Microsoft YaHei UI",10,"bold"),tags=(tag,))
                canvas.create_text(right-10,top+11,anchor="ne",text=f"{row.cost}次",fill=colors["muted"],font=("Microsoft YaHei UI",9),tags=(tag,))
                job_text=row.job+(" · 可选兵种" if row.job_choices else " · 固定配置" if row.fixed_configuration else "")
                canvas.create_text(x+10,top+35,anchor="nw",text=job_text,fill=colors["ink"],font=("Microsoft YaHei UI",9),tags=(tag,))
                canvas.create_text(x+10,top+58,anchor="nw",text="兵种天赋："+("、".join(row.job_talents) or "无"),fill=colors["muted"],width=216,font=("Microsoft YaHei UI",8),tags=(tag,))
                canvas.create_text(x+10,top+84,anchor="nw",text="人物天赋："+("、".join(row.personal_talents) or "无"),fill=colors["muted"],width=216,font=("Microsoft YaHei UI",8),tags=(tag,))
                watch_tag=f"watch:{row.record_index}"; canvas.create_rectangle(right-72,bottom-29,right-10,bottom-8,fill=colors["accent"] if row.record_index in selected else colors["surface"],outline=colors["accent"],tags=(watch_tag,)); canvas.create_text(right-41,bottom-18,text="已关注" if row.record_index in selected else "关注",fill="white" if row.record_index in selected else colors["accent"],font=("Microsoft YaHei UI",8),tags=(watch_tag,))
            y += 170
        if not shown_stages: canvas.create_text(20,y,anchor="nw",text="没有符合条件的招募人物",fill=colors["muted"],font=("Microsoft YaHei UI",10)); y += 40
        max_cards=max((len(p) for s,p in stage_people.items() if not selected_stage or s==selected_stage), default=1)
        canvas.configure(scrollregion=(0,0,max(canvas.winfo_width(),14+max_cards*246),y)); count.configure(text=f"显示 {len(visible)} / {len(recruits)} 人 · {shown_stages} 个关卡 · 已关注 {len(selected)} 人")
    def schedule_query(*_args) -> None:
        nonlocal refresh_after
        if not dialog.winfo_exists():
            return
        if refresh_after: dialog.after_cancel(refresh_after)
        refresh_after=dialog.after(120,refresh)
    def click(event) -> None:
        hits = canvas.find_overlapping(canvas.canvasx(event.x), canvas.canvasy(event.y), canvas.canvasx(event.x), canvas.canvasy(event.y))
        tags = canvas.gettags(hits[-1]) if hits else ()
        for tag in tags:
            kind,_,value=tag.partition(":")
            if kind=="watch": selected.symmetric_difference_update((int(value),)); refresh(); return
            if kind=="card":
                row=next((item for item in recruits if item.record_index==int(value)),None)
                if row: show_details(row)
                return
    canvas.bind("<Button-1>",click); canvas.bind("<MouseWheel>",lambda e: canvas.yview_scroll(-int(e.delta/120),"units")); canvas.bind("<Button-4>",lambda e:canvas.yview_scroll(-1,"units")); canvas.bind("<Button-5>",lambda e:canvas.yview_scroll(1,"units"))
    query.trace_add("write",schedule_query); stage.trace_add("write",lambda *_:refresh()); only_selected.trace_add("write",lambda *_:refresh())
    dialog.bind("<Configure>",lambda _e:detail_label.configure(wraplength=max(400,outer.winfo_width()-40)))
    def close() -> None:
        if refresh_after: dialog.after_cancel(refresh_after)
        dialog.destroy()
    def on_destroy(event) -> None:
        nonlocal refresh_after
        if event.widget is dialog and refresh_after:
            try:
                dialog.after_cancel(refresh_after)
            except tk.TclError:
                pass
            refresh_after = None
    dialog.bind("<Destroy>", on_destroy)
    dialog.protocol("WM_DELETE_WINDOW",close); refresh(); entry.focus_set()
