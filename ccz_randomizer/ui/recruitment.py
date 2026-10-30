from __future__ import annotations

from ccz_randomizer.ui.window_position import centered_toplevel

import json
from collections import OrderedDict
from pathlib import Path

from ccz_randomizer.recruitment import Recruit, filter_recruits, parse_recruits
from ccz_randomizer.entry_catalog import entry_stage_order, missing_fixed_entries


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
        fixed = payload.get("fixedPersonnel")
        if fixed is None:
            fixed = missing_fixed_entries()
        recruits = parse_recruits(dict(payload, personnel=[*(payload.get("personnel") or []), *fixed]))
    except (OSError, ValueError) as exc:
        messagebox.showerror("无法读取人员快照", str(exc), parent=parent); return
    dialog = centered_toplevel(parent); dialog.title("入队人员"); dialog.geometry("1180x760"); dialog.minsize(820, 560); dialog.transient(parent)
    colors = {"ink":"#182230", "muted":"#667085", "surface":"#FFFFFF", "alt":"#F4F6FA", "line":"#D9E0EA", "accent":"#2563EB"}
    outer = ttk.Frame(dialog, padding=20); outer.pack(fill="both", expand=True)
    filters = ttk.Frame(outer); filters.pack(fill="x", pady=12)
    query, stage = tk.StringVar(), tk.StringVar(value="全部关卡")
    ttk.Label(filters, text="搜索人物、兵种或天赋", foreground=colors["muted"]).pack(side="left")
    entry = ttk.Entry(filters, textvariable=query, width=28); entry.pack(side="left", padx=(8,12))
    stage_order = entry_stage_order()
    stage_values = tuple(sorted(dict.fromkeys(value for row in recruits for value in (row.stages or (row.stage,))),
                                key=lambda label: stage_order.get(label, 999)))
    ttk.Combobox(filters, textvariable=stage, state="readonly", width=24, values=("全部关卡", *(value.removeprefix("共通 · ") for value in stage_values))).pack(side="left", padx=(0,12))
    body = ttk.Frame(outer); body.pack(fill="both", expand=True); body.rowconfigure(0,weight=1); body.columnconfigure(0,weight=1)
    canvas = tk.Canvas(body, background=colors["alt"], highlightthickness=0); canvas.grid(row=0,column=0,sticky="nsew")
    vertical = ttk.Scrollbar(body, orient="vertical", command=canvas.yview); vertical.grid(row=0,column=1,sticky="ns")
    canvas.configure(yscrollcommand=vertical.set)
    stage_people: OrderedDict[str, list[Recruit]] = OrderedDict()
    for row in recruits:
        for stage_name in row.stages or (row.stage,): stage_people.setdefault(stage_name, []).append(row)
    refresh_after = None
    def refresh() -> None:
        nonlocal refresh_after
        refresh_after = None
        canvas.delete("all")
        selected_stage = next((value for value in stage_values
                               if value.removeprefix("共通 · ") == stage.get()), "")
        visible = filter_recruits(recruits, query.get(), stage=selected_stage)
        visible_ids = {row.record_index for row in visible}
        width = max(1, canvas.winfo_width())
        columns = max(1, (width - 28 + 12) // 258)
        card_width = max(100, (width - 28 - (columns - 1) * 12) // columns)
        y = 12
        shown_stages = 0

        def draw_card(row: Recruit, x: int, top: int) -> tuple[int, int]:
            tag = f"card:{row.record_index}"
            background = canvas.create_rectangle(
                x, top, x + card_width, top + 1,
                fill=colors["surface"], outline=colors["line"], tags=(tag,))
            cursor = top + 12

            def line(text: str, *, indent: int = 0, bold: bool = False, reserve: int = 0) -> None:
                nonlocal cursor
                item = canvas.create_text(
                    x + 12 + indent, cursor, anchor="nw", text=text,
                    fill=colors["ink"] if bold else colors["muted"],
                    width=max(1, card_width - 24 - indent - reserve),
                    font=("Microsoft YaHei UI", 10, "bold" if bold else "normal"),
                    tags=(tag,))
                cursor = canvas.bbox(item)[3] + 5

            cost = canvas.create_text(
                x + card_width - 12, cursor, anchor="ne", text="固定" if row.entry_kind == "fixed" else f"{row.cost}次",
                fill=colors["muted"], font=("Microsoft YaHei UI", 9), tags=(tag,))
            cost_bounds = canvas.bbox(cost)
            line(f"{row.name} · {row.job}", bold=True,
                 reserve=cost_bounds[2] - cost_bounds[0] + 12)
            for title, talents in (("兵种天赋", row.job_talents),
                                   ("人物天赋", row.personal_talents)):
                cursor += 5
                line(title, bold=True)
                for talent in talents or ("无",):
                    line(talent, indent=14)
            bottom = cursor + 7
            canvas.coords(background, x, top, x + card_width, bottom)
            return background, bottom

        for stage_name in stage_values:
            people_all = stage_people[stage_name]
            if selected_stage and stage_name != selected_stage:
                continue
            people = [row for row in people_all if row.record_index in visible_ids]
            if not people:
                continue
            shown_stages += 1
            canvas.create_text(14, y, anchor="nw",
                               text=stage_name.removeprefix("共通 · "),
                               fill=colors["ink"], font=("Microsoft YaHei UI", 11, "bold"))
            y += 31
            for kind, label in (("fixed", "固定入队 · 战前（随机预览）"), ("recruit", "可招募 · 战后")):
                group = [row for row in people if row.entry_kind == kind]
                if not group:
                    continue
                canvas.create_text(14, y, anchor="nw", text=label, fill=colors["muted"],
                                   font=("Microsoft YaHei UI", 9))
                y += 26
                for start in range(0, len(group), columns):
                    cards = [draw_card(row, 14 + i * (card_width + 12), y)
                               for i, row in enumerate(group[start:start + columns])]
                    bottom = max(height for _background, height in cards)
                    for background, _height in cards:
                        left, top, right, _ = canvas.coords(background)
                        canvas.coords(background, left, top, right, bottom)
                    y = bottom + 12
            y += 8
        if not shown_stages:
            canvas.create_text(20, y, anchor="nw", text="没有符合条件的入队人员",
                               fill=colors["muted"], font=("Microsoft YaHei UI", 10))
            y += 40
        canvas.configure(scrollregion=(0, 0, width, y))
    def schedule_query(*_args) -> None:
        nonlocal refresh_after
        if not dialog.winfo_exists():
            return
        if refresh_after: dialog.after_cancel(refresh_after)
        refresh_after=dialog.after(120,refresh)
    canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(-int(e.delta / 120), "units"))
    canvas.bind("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
    canvas.bind("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))
    canvas.bind("<Configure>", schedule_query)
    query.trace_add("write", schedule_query)
    stage.trace_add("write", schedule_query)
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
