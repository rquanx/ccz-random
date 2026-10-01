from __future__ import annotations

import datetime as dt
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from typing import Any, Callable

from ccz_randomizer.statistics import StatisticsFilters, StatisticsRepository
from ccz_randomizer.ui.history import show_result_snapshot_detail


COLORS = {
    "page": "#EEECE7",
    "surface": "#FFFFFF",
    "ink": "#1F2937",
    "muted": "#667085",
    "border": "#D6D3CD",
    "blue": "#2457C5",
    "red": "#B42318",
}
FONT = "Microsoft YaHei UI"


def _center(window: tk.Toplevel, parent: tk.Misc, width: int, height: int):
    window.update_idletasks()
    parent.update_idletasks()
    width = min(width, max(720, window.winfo_screenwidth() - 32))
    height = min(height, max(600, window.winfo_screenheight() - 64))
    x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
    window.geometry(f"{width}x{height}+{max(8, x)}+{max(8, y)}")


def _scrollable_tab(notebook: ttk.Notebook, title: str) -> tk.Frame:
    container = tk.Frame(notebook, bg=COLORS["page"])
    notebook.add(container, text=title)
    canvas = tk.Canvas(
        container,
        bg=COLORS["page"],
        highlightthickness=0,
    )
    scrollbar = ttk.Scrollbar(
        container,
        orient="vertical",
        command=canvas.yview,
    )
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    content = tk.Frame(canvas, bg=COLORS["page"])
    window_id = canvas.create_window((0, 0), window=content, anchor="nw")
    content.bind(
        "<Configure>",
        lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
    )
    canvas.bind(
        "<Configure>",
        lambda event: canvas.itemconfigure(window_id, width=event.width),
    )
    return content


def _bar_chart(
    parent: tk.Misc,
    rows: list[dict[str, Any]],
    *,
    title: str,
    on_click: Callable[[dict[str, Any]], None] | None = None,
) -> tk.Frame:
    holder = tk.Frame(
        parent,
        bg=COLORS["surface"],
        highlightbackground=COLORS["border"],
        highlightthickness=1,
    )
    tk.Label(
        holder,
        text=title,
        font=(FONT, 12, "bold"),
        fg=COLORS["ink"],
        bg=COLORS["surface"],
        anchor="w",
    ).pack(fill="x", padx=12, pady=(10, 4))
    search_var = tk.StringVar()
    sort_var = tk.StringVar(value="次数")
    if len(rows) > 12:
        tools = tk.Frame(holder, bg=COLORS["surface"])
        tools.pack(fill="x", padx=12, pady=(0, 6))
        tk.Label(
            tools,
            text="搜索",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=(FONT, 9),
        ).pack(side="left")
        search_entry = tk.Entry(
            tools,
            textvariable=search_var,
            width=22,
        )
        search_entry.pack(side="left", padx=(6, 12))
        tk.Label(
            tools,
            text="排序",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=(FONT, 9),
        ).pack(side="left")
        sort_combo = ttk.Combobox(
            tools,
            textvariable=sort_var,
            values=("次数", "名称"),
            state="readonly",
            width=8,
        )
        sort_combo.pack(side="left", padx=(6, 0))
    canvas = tk.Canvas(
        holder,
        height=130,
        bg=COLORS["surface"],
        highlightthickness=0,
    )
    canvas.pack(fill="both", expand=True, padx=12, pady=(0, 10))

    def draw(_event=None) -> None:
        canvas.delete("all")
        query = search_var.get().strip().casefold()
        visible = [
            row
            for row in rows
            if not query
            or query in str(row.get("label") or "").casefold()
        ]
        if sort_var.get() == "名称":
            visible.sort(key=lambda row: str(row.get("label") or ""))
        else:
            visible.sort(
                key=lambda row: (
                    -int(row.get("count") or 0),
                    str(row.get("label") or ""),
                )
            )
        canvas.configure(
            height=max(130, 34 * max(1, len(visible)) + 20)
        )
        if not visible:
            canvas.create_text(
                12,
                24,
                text="暂无符合条件的数据",
                anchor="w",
                fill=COLORS["muted"],
                font=(FONT, 10),
            )
            return
        max_count = max(int(row.get("count") or 0) for row in visible) or 1
        width = max(320, canvas.winfo_width())
        label_width = min(220, max(120, width // 3))
        for index, row in enumerate(visible):
            y = 22 + index * 32
            label = str(row.get("label") or "未知")
            if row.get("rule_snapshot_hash"):
                label = f"{str(row['rule_snapshot_hash'])[:10]} · {label}"
            count = int(row.get("count") or 0)
            ratio = float(row.get("ratio") or 0)
            tag = f"bar-{index}"
            canvas.create_text(
                0,
                y,
                text=label[:36],
                anchor="w",
                fill=COLORS["ink"],
                font=(FONT, 9),
                tags=(tag,),
            )
            left = label_width
            right = left + int((width - left - 100) * count / max_count)
            canvas.create_rectangle(
                left,
                y - 8,
                max(left + 2, right),
                y + 8,
                fill=COLORS["blue"],
                outline="",
                tags=(tag,),
            )
            canvas.create_text(
                width - 4,
                y,
                text=(
                    f"{count}  {ratio:.1%}"
                    + (
                        f"  存档{int(row.get('save_count') or 0)}"
                        if row.get("save_count") is not None
                        else ""
                    )
                    + (
                        f"  武将{int(row.get('member_count') or 0)}"
                        if row.get("member_count") is not None
                        else ""
                    )
                ),
                anchor="e",
                fill=COLORS["muted"],
                font=(FONT, 9),
                tags=(tag,),
            )
            if on_click is not None:
                canvas.tag_bind(
                    tag,
                    "<Button-1>",
                    lambda _event, value=row: on_click(value),
                )
                canvas.tag_bind(
                    tag,
                    "<Enter>",
                    lambda _event: canvas.configure(cursor="hand2"),
                )
                canvas.tag_bind(
                    tag,
                    "<Leave>",
                    lambda _event: canvas.configure(cursor=""),
                )

    if len(rows) > 12:
        search_entry.bind("<KeyRelease>", lambda _event: draw())
        sort_combo.bind("<<ComboboxSelected>>", lambda _event: draw())
    canvas.bind("<Configure>", draw)
    draw()
    return holder


def _line_chart(
    parent: tk.Misc,
    rows: list[dict[str, Any]],
    *,
    title: str,
    value_field: str = "accepted",
    value_label: str = "合格",
    on_click: Callable[[dict[str, Any]], None] | None = None,
) -> tk.Frame:
    holder = tk.Frame(
        parent,
        bg=COLORS["surface"],
        highlightbackground=COLORS["border"],
        highlightthickness=1,
    )
    tk.Label(
        holder,
        text=title,
        font=(FONT, 12, "bold"),
        fg=COLORS["ink"],
        bg=COLORS["surface"],
        anchor="w",
    ).pack(fill="x", padx=12, pady=(10, 4))
    canvas = tk.Canvas(
        holder,
        height=180,
        bg=COLORS["surface"],
        highlightthickness=0,
    )
    canvas.pack(fill="x", padx=12, pady=(0, 10))
    def draw(_event=None) -> None:
        canvas.delete("all")
        if not rows:
            canvas.create_text(
                12,
                24,
                text="暂无趋势数据",
                anchor="w",
                fill=COLORS["muted"],
                font=(FONT, 10),
            )
            return
        values = [float(row.get(value_field) or 0) for row in rows]
        maximum = max(values + [1])
        left, top = 30, 15
        width = max(320, canvas.winfo_width())
        height = max(130, canvas.winfo_height() - 20)
        usable_width = width - left - 10
        usable_height = height - top - 20
        points = []
        for index, value in enumerate(values):
            x = left if len(values) == 1 else (
                left + usable_width * index / (len(values) - 1)
            )
            y = top + usable_height * (1 - value / maximum)
            points.append((x, y))
        if len(points) > 1:
            canvas.create_line(
                *[value for point in points for value in point],
                fill=COLORS["blue"],
                width=2,
            )
        for index, (x, y) in enumerate(points):
            canvas.create_oval(
                x - 4,
                y - 4,
                x + 4,
                y + 4,
                fill=COLORS["blue"],
                outline="",
                tags=(f"point-{index}",),
            )
            canvas.create_text(
                x,
                height - 4,
                text=str(rows[index].get("date") or ""),
                angle=45,
                anchor="e",
                fill=COLORS["muted"],
                font=(FONT, 8),
            )
            if on_click is not None:
                canvas.tag_bind(
                    f"point-{index}",
                    "<Button-1>",
                    lambda _event, value=rows[index]: on_click(value),
                )
        canvas.create_text(
            width - 4,
            top,
            text=(
                f"{value_label} "
                f"{sum(values):.1f}".rstrip("0").rstrip(".")
            ),
            anchor="e",
            fill=COLORS["muted"],
            font=(FONT, 9),
        )

    canvas.bind("<Configure>", draw)
    draw()
    return holder


def _pie_chart(
    parent: tk.Misc,
    rows: list[dict[str, Any]],
    *,
    title: str,
    on_click: Callable[[dict[str, Any]], None] | None = None,
) -> tk.Frame:
    holder = tk.Frame(
        parent,
        bg=COLORS["surface"],
        highlightbackground=COLORS["border"],
        highlightthickness=1,
    )
    tk.Label(
        holder,
        text=title,
        font=(FONT, 12, "bold"),
        fg=COLORS["ink"],
        bg=COLORS["surface"],
        anchor="w",
    ).pack(fill="x", padx=12, pady=(10, 4))
    canvas = tk.Canvas(
        holder,
        width=360,
        height=220,
        bg=COLORS["surface"],
        highlightthickness=0,
    )
    canvas.pack(fill="both", expand=True, padx=12, pady=(0, 10))
    def draw(_event=None) -> None:
        canvas.delete("all")
        total = sum(int(row.get("count") or 0) for row in rows)
        if not total:
            canvas.create_text(
                12,
                24,
                text="暂无符合条件的数据",
                anchor="w",
                fill=COLORS["muted"],
                font=(FONT, 10),
            )
            return
        palette = ("#2457C5", "#4A7BD0", "#7E9DDF", "#B42318", "#D67A72")
        width = max(320, canvas.winfo_width())
        diameter = min(180, max(120, width // 2 - 30))
        label_x = diameter + 40
        start = 0.0
        for index, row in enumerate(rows):
            count = int(row.get("count") or 0)
            extent = 360.0 * count / total
            tag = f"slice-{index}"
            canvas.create_arc(
                20,
                20,
                20 + diameter,
                20 + diameter,
                start=start,
                extent=extent,
                fill=palette[index % len(palette)],
                outline=COLORS["surface"],
                width=1,
                tags=(tag,),
            )
            label = str(row.get("label") or "")
            canvas.create_text(
                label_x,
                38 + index * 25,
                text=f"{label}  {count} ({count / total:.1%})",
                anchor="w",
                fill=COLORS["ink"],
                font=(FONT, 9),
                tags=(tag,),
            )
            if on_click is not None:
                canvas.tag_bind(
                    tag,
                    "<Button-1>",
                    lambda _event, value=row: on_click(value),
                )
            start += extent

    canvas.bind("<Configure>", draw)
    draw()
    return holder


def _metric_card(parent, label: str, value: Any, column: int):
    card = tk.Frame(
        parent,
        bg=COLORS["surface"],
        highlightbackground=COLORS["border"],
        highlightthickness=1,
    )
    card.grid(row=0, column=column, sticky="nsew", padx=4)
    tk.Label(
        card,
        text=label,
        bg=COLORS["surface"],
        fg=COLORS["muted"],
        font=(FONT, 9),
    ).pack(anchor="w", padx=10, pady=(8, 2))
    tk.Label(
        card,
        text=str(value),
        bg=COLORS["surface"],
        fg=COLORS["ink"],
        font=(FONT, 16, "bold"),
    ).pack(anchor="w", padx=10, pady=(0, 8))
    return card


def _snapshot_text(snapshot: dict[str, Any], key: str) -> str:
    values: list[str] = []
    for member in snapshot.get("members") or []:
        if not isinstance(member, dict):
            continue
        if key == "job":
            value = member.get("jobName") or member.get("job")
            if value:
                values.append(f"{member.get('name', '未知')}:{value}")
        elif key == "member":
            value = member.get("name") or member.get("memberName")
            if value:
                values.append(str(value))
        elif key in {"personalSkills", "jobSkills"}:
            names = []
            for skill in member.get(key) or []:
                if isinstance(skill, dict):
                    names.append(
                        str(skill.get("name") or skill.get("skillName") or "未知")
                    )
            if names:
                values.append(f"{member.get('name', '未知')}:{'、'.join(names)}")
    return "；".join(values) or "无"


def _treasure_text(snapshot: dict[str, Any]) -> str:
    names = []
    for item in snapshot.get("treasures") or []:
        if isinstance(item, dict):
            names.append(str(item.get("treasureName") or item.get("name") or "未知"))
            for value in item.get("setNames") or item.get("setIds") or []:
                names.append(str(value))
    return "、".join(names) or "无"


def _treasure_property_text(snapshot: dict[str, Any]) -> str:
    values: list[str] = []
    for item in snapshot.get("treasures") or []:
        if not isinstance(item, dict):
            continue
        for prop in item.get("properties") or []:
            if isinstance(prop, dict):
                name = prop.get("propertyName") or prop.get("name")
            else:
                name = prop
            if name:
                values.append(str(name))
    return "、".join(values) or "无"


def show_statistics_window(
    parent: tk.Misc,
    repository: StatisticsRepository,
    *,
    current_run_id: str | None = None,
    current_round_id: int | None = None,
    current_rule_hash: str | None = None,
) -> None:
    if current_round_id is None:
        current_round_id = repository.latest_round_id(current_run_id)
    dialog = tk.Toplevel(parent)
    dialog.title("统计")
    dialog.minsize(1000, 680)
    dialog.transient(parent)
    dialog.configure(bg=COLORS["page"])
    _center(dialog, parent, 1280, 840)

    scope_values = ["全部历史", "指定运行", "指定轮次"]
    if current_run_id:
        scope_values.insert(0, "当前运行")
    if current_round_id is not None:
        scope_values.insert(1 if current_run_id else 0, "当前轮次")
    scope_var = tk.StringVar(value="全部历史")
    metric_var = tk.StringVar(value="最终结果")
    mode_var = tk.StringVar(value="全部")
    rule_var = tk.StringVar(value="全部规则汇总")
    slot_var = tk.StringVar(value="全部")
    member_var = tk.StringVar(value="全部")
    time_var = tk.StringVar(value="全部时间")
    custom_after_var = tk.StringVar()
    custom_before_var = tk.StringVar()
    status_var = tk.StringVar(value="")
    trend_metric_var = tk.StringVar(value="合格数")
    treasure_chart_var = tk.StringVar(value="柱状图")
    selected_run_id: str | None = None
    selected_round_id: int | None = None
    selected_scope_label = tk.StringVar(value="未选择运行或轮次")
    detail_filter: dict[str, str] = {}
    selected_rule_hashes: set[str] = set()
    selected_slots: tuple[int, ...] = ()
    detail_page = 0
    detail_page_size = 100

    controls = tk.Frame(dialog, bg=COLORS["page"], padx=12, pady=10)
    controls.pack(fill="x")
    filter_grid = tk.Frame(controls, bg=COLORS["page"])
    filter_grid.pack(fill="x")
    for column in range(2):
        filter_grid.columnconfigure(
            column,
            weight=1,
            uniform="statistics_filters",
        )
    context_bar = tk.Frame(controls, bg=COLORS["page"])
    context_bar.pack(fill="x", pady=(8, 0))
    rule_options = repository.list_rule_options()
    rule_display_to_hash = {
        (
            f"{item['rule_name']} · "
            f"{str(item['rule_snapshot_hash'])[:15]}"
        ): str(item["rule_snapshot_hash"])
        for item in rule_options
    }
    hash_to_rule_display = {
        value: key for key, value in rule_display_to_hash.items()
    }

    def open_rule_selector() -> None:
        chooser = tk.Toplevel(dialog)
        chooser.title("选择规则配置")
        chooser.transient(dialog)
        chooser.configure(bg=COLORS["page"])
        _center(chooser, dialog, 620, 460)
        tk.Label(
            chooser,
            text="可多选规则配置。相同名称但不同指纹视为不同规则。",
            bg=COLORS["page"],
            fg=COLORS["muted"],
            anchor="w",
        ).pack(fill="x", padx=16, pady=(14, 8))
        listbox = tk.Listbox(
            chooser,
            selectmode="extended",
            activestyle="none",
            font=(FONT, 10),
            relief="solid",
            borderwidth=1,
        )
        listbox.pack(fill="both", expand=True, padx=16, pady=8)
        values = list(rule_display_to_hash.items())
        for display, _hash in values:
            listbox.insert("end", display)
        for index, (_display, value) in enumerate(values):
            if value in selected_rule_hashes:
                listbox.selection_set(index)

        def accept() -> None:
            selected_rule_hashes.clear()
            selected_rule_hashes.update(
                value
                for index, (_display, value) in enumerate(values)
                if index in listbox.curselection()
            )
            chooser.destroy()
            render()

        actions = tk.Frame(chooser, bg=COLORS["page"])
        actions.pack(fill="x", padx=16, pady=(0, 14))
        tk.Button(actions, text="取消", command=chooser.destroy).pack(
            side="right", padx=(8, 0)
        )
        tk.Button(
            actions,
            text="应用",
            command=accept,
            bg=COLORS["blue"],
            fg="#FFFFFF",
            relief="flat",
        ).pack(side="right")

    def open_custom_time() -> None:
        chooser = tk.Toplevel(dialog)
        chooser.title("自定义时间范围")
        chooser.transient(dialog)
        chooser.configure(bg=COLORS["page"])
        _center(chooser, dialog, 430, 190)
        tk.Label(
            chooser,
            text="请输入日期，格式：YYYY-MM-DD；结束日期不包含当天。",
            bg=COLORS["page"],
            fg=COLORS["muted"],
        ).pack(anchor="w", padx=16, pady=(14, 8))
        form = tk.Frame(chooser, bg=COLORS["page"])
        form.pack(fill="x", padx=16)
        tk.Label(form, text="开始", bg=COLORS["page"]).grid(row=0, column=0)
        tk.Entry(form, textvariable=custom_after_var, width=18).grid(
            row=0, column=1, padx=(8, 18)
        )
        tk.Label(form, text="结束", bg=COLORS["page"]).grid(row=0, column=2)
        tk.Entry(form, textvariable=custom_before_var, width=18).grid(
            row=0, column=3, padx=(8, 0)
        )

        def apply() -> None:
            try:
                for value in (
                    custom_after_var.get().strip(),
                    custom_before_var.get().strip(),
                ):
                    if value:
                        dt.date.fromisoformat(value)
                if (
                    custom_after_var.get().strip()
                    and custom_before_var.get().strip()
                    and custom_after_var.get().strip()
                    >= custom_before_var.get().strip()
                ):
                    raise ValueError
            except ValueError:
                messagebox.showerror(
                    "时间格式错误",
                    "请输入有效日期，并确保开始日期早于结束日期。",
                    parent=chooser,
                )
                return
            chooser.destroy()
            render()

        actions = tk.Frame(chooser, bg=COLORS["page"])
        actions.pack(fill="x", padx=16, pady=18)
        tk.Button(actions, text="取消", command=chooser.destroy).pack(
            side="right", padx=(8, 0)
        )
        tk.Button(
            actions,
            text="应用",
            command=apply,
            bg=COLORS["blue"],
            fg="#FFFFFF",
            relief="flat",
        ).pack(side="right")

    def open_slot_selector() -> None:
        nonlocal selected_slots
        chooser = tk.Toplevel(dialog)
        chooser.title("选择存档范围")
        chooser.transient(dialog)
        chooser.configure(bg=COLORS["page"])
        _center(chooser, dialog, 420, 210)
        available = repository.list_slot_options()
        minimum = min(available) if available else 1
        maximum = max(available) if available else 15
        start_var = tk.IntVar(
            value=min(selected_slots) if selected_slots else minimum
        )
        end_var = tk.IntVar(
            value=max(selected_slots) if selected_slots else maximum
        )
        form = tk.Frame(chooser, bg=COLORS["page"])
        form.pack(fill="x", padx=18, pady=(24, 10))
        tk.Label(form, text="起始存档", bg=COLORS["page"]).grid(
            row=0,
            column=0,
            sticky="w",
        )
        tk.Spinbox(
            form,
            from_=minimum,
            to=maximum,
            textvariable=start_var,
            width=8,
        ).grid(row=0, column=1, padx=(8, 24))
        tk.Label(form, text="结束存档", bg=COLORS["page"]).grid(
            row=0,
            column=2,
            sticky="w",
        )
        tk.Spinbox(
            form,
            from_=minimum,
            to=maximum,
            textvariable=end_var,
            width=8,
        ).grid(row=0, column=3, padx=(8, 0))

        def accept() -> None:
            nonlocal selected_slots
            start = int(start_var.get())
            end = int(end_var.get())
            if start > end:
                messagebox.showerror(
                    "存档范围错误",
                    "起始存档不能大于结束存档。",
                    parent=chooser,
                )
                return
            selected_slots = tuple(
                slot for slot in available if start <= slot <= end
            )
            if not selected_slots:
                selected_slots = tuple(range(start, end + 1))
            slot_var.set(f"存档{start}-{end}")
            chooser.destroy()
            reset_page_and_render()

        actions = tk.Frame(chooser, bg=COLORS["page"])
        actions.pack(fill="x", padx=18, pady=(12, 16))
        tk.Button(actions, text="取消", command=chooser.destroy).pack(
            side="right",
            padx=(8, 0),
        )
        tk.Button(
            actions,
            text="应用",
            command=accept,
            bg=COLORS["blue"],
            fg="#FFFFFF",
            relief="flat",
        ).pack(side="right")

    def open_scope_selector(kind: str) -> None:
        nonlocal selected_run_id, selected_round_id
        chooser = tk.Toplevel(dialog)
        chooser.title("选择历史范围")
        chooser.transient(dialog)
        chooser.configure(bg=COLORS["page"])
        _center(chooser, dialog, 860, 520)
        listbox = tk.Listbox(
            chooser,
            selectmode="browse",
            activestyle="none",
            font=(FONT, 9),
            relief="solid",
            borderwidth=1,
        )
        listbox.pack(fill="both", expand=True, padx=16, pady=16)
        if kind == "run":
            values = repository.list_run_options()
            for item in values:
                listbox.insert(
                    "end",
                    f"{item['started_at']} · {item['rule_name']} · "
                    f"{item['mode']} · {item['id']}",
                )
            selected = selected_run_id
        else:
            values = repository.list_round_options()
            for item in values:
                listbox.insert(
                    "end",
                    f"{item['started_at']} · 第{item['round_number']}轮 · "
                    f"{item['mode']} · {item['run_id']}",
                )
            selected = selected_round_id
        for index, item in enumerate(values):
            item_id = item["id"]
            if item_id == selected:
                listbox.selection_set(index)
                listbox.see(index)

        def accept() -> None:
            nonlocal selected_run_id, selected_round_id
            selection = listbox.curselection()
            if not selection:
                return
            value = values[selection[0]]
            if kind == "run":
                selected_run_id = str(value["id"])
                selected_scope_label.set(f"运行 {selected_run_id[:12]}")
            else:
                selected_round_id = int(value["id"])
                selected_scope_label.set(
                    f"轮次 {selected_round_id} · 第{value['round_number']}轮"
                )
            chooser.destroy()
            render()

        actions = tk.Frame(chooser, bg=COLORS["page"])
        actions.pack(fill="x", padx=16, pady=(0, 14))
        tk.Button(actions, text="取消", command=chooser.destroy).pack(
            side="right", padx=(8, 0)
        )
        tk.Button(
            actions,
            text="应用",
            command=accept,
            bg=COLORS["blue"],
            fg="#FFFFFF",
            relief="flat",
        ).pack(side="right")

    options = (
        ("统计范围", scope_var, tuple(scope_values)),
        ("数据口径", metric_var, ("最终结果", "全部已完成", "全部尝试")),
        ("随机模式", mode_var, ("全部", "3人", "7人")),
        (
            "规则配置",
            rule_var,
            ("当前规则", "指定规则", "全部规则汇总", "全部规则分组"),
        ),
        (
            "存档范围",
            slot_var,
            ("全部",)
            + tuple(f"存档{slot}" for slot in repository.list_slot_options())
            + ("自定义范围",),
        ),
        (
            "武将",
            member_var,
            ("全部",)
            + tuple(
                item["member_name"]
                for item in repository.list_member_options()
            ),
        ),
        ("时间", time_var, ("全部时间", "今天", "本周", "本月", "自定义")),
    )
    combos: list[ttk.Combobox] = []
    for index, (label, variable, values) in enumerate(options):
        field = tk.Frame(filter_grid, bg=COLORS["page"])
        field.grid(
            row=index // 2,
            column=index % 2,
            sticky="ew",
            padx=(0 if index % 2 == 0 else 8, 0),
            pady=(0, 8 if index < 6 else 0),
        )
        tk.Label(
            field,
            text=label,
            bg=COLORS["page"],
            fg=COLORS["muted"],
            font=(FONT, 9),
        ).pack(anchor="w")
        combo = ttk.Combobox(
            field,
            textvariable=variable,
            values=values,
            state="readonly",
            width=20,
        )
        combo.pack(fill="x", pady=(3, 0))
        combos.append(combo)
    select_rule_button = tk.Button(
        context_bar,
        text="选择规则",
        command=open_rule_selector,
        relief="flat",
        state="disabled",
    )
    select_rule_button.pack(side="left")
    select_run_button = tk.Button(
        context_bar,
        text="选择运行",
        command=lambda: open_scope_selector("run"),
        relief="flat",
        state="disabled",
    )
    select_run_button.pack(side="left", padx=(6, 0))
    select_round_button = tk.Button(
        context_bar,
        text="选择轮次",
        command=lambda: open_scope_selector("round"),
        relief="flat",
        state="disabled",
    )
    select_round_button.pack(side="left", padx=(6, 0))
    select_slot_button = tk.Button(
        context_bar,
        text="选择存档范围",
        command=open_slot_selector,
        relief="flat",
        state="disabled",
    )
    select_slot_button.pack(side="left", padx=(6, 0))
    tk.Label(
        context_bar,
        textvariable=selected_scope_label,
        bg=COLORS["page"],
        fg=COLORS["muted"],
        anchor="w",
    ).pack(side="left", padx=(10, 0))
    tk.Label(
        context_bar,
        textvariable=status_var,
        bg=COLORS["page"],
        fg=COLORS["muted"],
        anchor="w",
        justify="left",
        wraplength=620,
    ).pack(side="left", fill="x", expand=True, padx=(12, 8))
    clear_filter_button = tk.Button(
        context_bar,
        text="清除图表筛选",
        relief="flat",
        state="disabled",
    )
    clear_filter_button.pack(side="right")

    notebook = ttk.Notebook(dialog)
    notebook.pack(fill="both", expand=True, padx=12, pady=(0, 12))
    overview = _scrollable_tab(notebook, "总览")
    jobs = _scrollable_tab(notebook, "兵种分布")
    skills = _scrollable_tab(notebook, "特技分布")
    treasures = _scrollable_tab(notebook, "宝物分布")

    def build_filters() -> StatisticsFilters:
        mode = {"3人": "three", "7人": "seven"}.get(mode_var.get(), "all")
        metric = {
            "最终结果": "final",
            "全部已完成": "completed",
            "全部尝试": "attempts",
        }[metric_var.get()]
        scope = {
            "当前运行": "current_run",
            "当前轮次": "current_round",
            "指定运行": "current_run",
            "指定轮次": "current_round",
            "全部历史": "history",
        }[scope_var.get()]
        rule_mode = {
            "当前规则": "current",
            "指定规则": "selected",
            "全部规则汇总": "all_summary",
            "全部规则分组": "all_grouped",
        }[rule_var.get()]
        active_slots: tuple[int, ...] = ()
        if slot_var.get() == "自定义范围" or "-" in slot_var.get():
            active_slots = selected_slots
        elif slot_var.get() != "全部":
            active_slots = (int(slot_var.get().replace("存档", "")),)
        selected_member_id = None
        for item in repository.list_member_options():
            if item["member_name"] == member_var.get():
                selected_member_id = item["member_id"]
                break
        started_after = None
        started_before = None
        if time_var.get() != "全部时间":
            today = dt.datetime.now().astimezone().date()
            if time_var.get() == "自定义":
                started_after = (
                    dt.datetime.fromisoformat(custom_after_var.get())
                    .astimezone()
                    .isoformat(timespec="seconds")
                    if custom_after_var.get().strip()
                    else None
                )
                started_before = (
                    dt.datetime.fromisoformat(custom_before_var.get())
                    .astimezone()
                    .isoformat(timespec="seconds")
                    if custom_before_var.get().strip()
                    else None
                )
            elif time_var.get() == "今天":
                first = today
            elif time_var.get() == "本周":
                first = today - dt.timedelta(days=today.weekday())
            else:
                first = today.replace(day=1)
            if time_var.get() != "自定义":
                started_after = dt.datetime.combine(
                    first,
                    dt.time.min,
                ).astimezone().isoformat(timespec="seconds")
                started_before_date = today + dt.timedelta(days=1)
                started_before = dt.datetime.combine(
                    started_before_date,
                    dt.time.min,
                ).astimezone().isoformat(timespec="seconds")
        if detail_filter.get("kind") == "date":
            chart_date = dt.date.fromisoformat(detail_filter["value"])
            started_after = dt.datetime.combine(
                chart_date,
                dt.time.min,
            ).astimezone().isoformat(timespec="seconds")
            started_before = dt.datetime.combine(
                chart_date + dt.timedelta(days=1),
                dt.time.min,
            ).astimezone().isoformat(timespec="seconds")
        return StatisticsFilters(
            scope=scope,
            metric=metric,
            mode=mode,
            rule_mode=rule_mode,
            rule_hashes=tuple(sorted(selected_rule_hashes)),
            current_rule_hash=current_rule_hash,
            run_id=(
                selected_run_id
                if scope_var.get() == "指定运行"
                else current_run_id
            ),
            round_id=(
                selected_round_id
                if scope_var.get() == "指定轮次"
                else current_round_id
            ),
            slots=active_slots,
            member_id=(
                detail_filter.get("member_id")
                or selected_member_id
            ),
            started_after=started_after,
            started_before=started_before,
            status=detail_filter.get("status"),
            failure_reason=detail_filter.get("failure_reason"),
            attempt_id=(
                int(detail_filter["attempt_id"])
                if detail_filter.get("attempt_id")
                else None
            ),
            content_kind=detail_filter.get("content_kind"),
            content_value=detail_filter.get("content_value"),
        )

    def clear(frame: tk.Misc) -> None:
        for child in frame.winfo_children():
            child.destroy()

    def filtered_details(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return rows

    def set_detail_filter(kind: str, row: dict[str, Any]) -> None:
        value = str(
            row.get("value")
            if row.get("value") not in {None, ""}
            else row.get("label") or ""
        )
        if value:
            detail_filter.clear()
            detail_filter.update(kind=kind, value=value)
            if kind == "status":
                detail_filter["status"] = value
            elif kind == "failure":
                detail_filter["failure_reason"] = value
            elif kind == "attempt":
                detail_filter["attempt_id"] = value
            elif kind == "member":
                detail_filter["member_id"] = value
            elif kind not in {"date"}:
                detail_filter["content_kind"] = kind
                detail_filter["content_value"] = value
            reset_page_and_render()

    def clear_detail_filter() -> None:
        detail_filter.clear()
        reset_page_and_render()

    def reset_page_and_render() -> None:
        nonlocal detail_page
        detail_page = 0
        render()

    def change_detail_page(delta: int) -> None:
        nonlocal detail_page
        detail_page = max(0, detail_page + delta)
        render()

    def open_snapshot_image(snapshot: dict[str, Any]) -> None:
        for key in ("resultImagePath", "resultGridPath"):
            value = snapshot.get(key)
            if value and Path(value).is_file():
                os.startfile(value)
                return
        messagebox.showinfo("结果图", "当前记录没有可用的结果图文件。", parent=dialog)

    def render_tree(
        frame: tk.Misc,
        rows: list[dict[str, Any]],
        *,
        total: int,
        page: int,
    ) -> None:
        holder = tk.Frame(frame, bg=COLORS["surface"])
        holder.pack(fill="both", expand=True)
        columns = (
            "time", "round", "slot", "member", "job", "personal",
            "job_skill", "treasure", "property", "status", "attempts",
        )
        tree = ttk.Treeview(holder, columns=columns, show="headings")
        headings = {
            "time": "运行时间", "round": "轮次", "slot": "存档",
            "member": "武将", "job": "兵种", "personal": "个人天赋",
            "job_skill": "兵种技能", "treasure": "宝物",
            "property": "宝物特性", "status": "最终状态",
            "attempts": "尝试",
        }
        widths = {
            "time": 145, "round": 55, "slot": 55, "member": 220,
            "job": 220, "personal": 240, "job_skill": 240,
            "treasure": 180, "property": 200, "status": 90,
            "attempts": 55,
        }
        vertical = ttk.Scrollbar(holder, orient="vertical", command=tree.yview)
        horizontal = ttk.Scrollbar(
            holder,
            orient="horizontal",
            command=tree.xview,
        )
        tree.configure(
            yscrollcommand=vertical.set,
            xscrollcommand=horizontal.set,
        )
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        for column in columns:
            tree.heading(column, text=headings[column])
            tree.column(column, width=widths[column], stretch=False)
        for row in rows:
            snapshot = row.get("snapshot") or {}
            item_id = tree.insert(
                "",
                "end",
                values=(
                    str(row.get("run_started_at") or "")[:19],
                    row.get("round_number", ""),
                    row.get("slot", ""),
                    _snapshot_text(snapshot, "member"),
                    _snapshot_text(snapshot, "job"),
                    _snapshot_text(snapshot, "personalSkills"),
                    _snapshot_text(snapshot, "jobSkills"),
                    _treasure_text(snapshot),
                    _treasure_property_text(snapshot),
                    row.get("status", ""),
                    row.get("attempt_number", ""),
                ),
            )
            tree.item(item_id, tags=(str(row.get("attempt_id", "")),))

        def open_selected(_event=None) -> None:
            selection = tree.selection()
            if not selection:
                return
            tags = tree.item(selection[0], "tags")
            for row in rows:
                if tags and str(row.get("attempt_id")) == tags[0]:
                    show_result_snapshot_detail(dialog, row.get("snapshot") or {})
                    return

        def image_selected() -> None:
            selection = tree.selection()
            if not selection:
                return
            tags = tree.item(selection[0], "tags")
            for row in rows:
                if tags and str(row.get("attempt_id")) == tags[0]:
                    open_snapshot_image(row.get("snapshot") or {})
                    return

        tree.bind("<Double-1>", open_selected)
        tk.Button(
            frame,
            text="打开结果图",
            command=image_selected,
            relief="flat",
        ).pack(side="right", pady=(6, 0))
        page_count = max(1, (total + detail_page_size - 1) // detail_page_size)
        pager = tk.Frame(frame, bg=COLORS["surface"])
        pager.pack(side="left", fill="x", pady=(6, 0))
        tk.Button(
            pager,
            text="上一页",
            command=lambda: change_detail_page(-1),
            state="normal" if page > 0 else "disabled",
            relief="flat",
        ).pack(side="left")
        tk.Label(
            pager,
            text=f"第 {page + 1}/{page_count} 页，共 {total} 条",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
        ).pack(side="left", padx=8)
        tk.Button(
            pager,
            text="下一页",
            command=lambda: change_detail_page(1),
            state="normal" if page + 1 < page_count else "disabled",
            relief="flat",
        ).pack(side="left")

    def render_grouped(
        frame: tk.Misc,
        rows: list[dict[str, Any]],
        *,
        title: str,
        kind: str,
    ) -> None:
        if not rows:
            _bar_chart(frame, [], title=title).pack(fill="x", padx=12, pady=12)
            return
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(str(row.get("rule_snapshot_hash") or ""), []).append(row)
        for rule_hash, group_rows in grouped.items():
            group_title = title
            if rule_hash:
                group_title += f" · {hash_to_rule_display.get(rule_hash, rule_hash)}"
            _bar_chart(
                frame,
                group_rows,
                title=group_title,
                on_click=lambda row, value=kind: set_detail_filter(value, row),
            ).pack(fill="x", padx=12, pady=6)

    def render() -> None:
        nonlocal detail_page
        select_rule_button.configure(
            state="normal" if rule_var.get() == "指定规则" else "disabled"
        )
        select_run_button.configure(
            state="normal" if scope_var.get() == "指定运行" else "disabled"
        )
        select_round_button.configure(
            state="normal" if scope_var.get() == "指定轮次" else "disabled"
        )
        select_slot_button.configure(
            state=(
                "normal"
                if slot_var.get() == "自定义范围"
                or "-" in slot_var.get()
                else "disabled"
            )
        )
        clear_filter_button.configure(
            state="normal" if detail_filter else "disabled"
        )
        filters = build_filters()
        summary = repository.get_summary(filters)
        clear(overview)
        clear(jobs)
        clear(skills)
        clear(treasures)
        metric_grid = tk.Frame(overview, bg=COLORS["page"])
        metric_grid.pack(fill="x", padx=12, pady=12)
        for column in range(3):
            metric_grid.columnconfigure(
                column,
                weight=1,
                uniform="statistics_metrics",
            )
        cards = (
            ("统计存档", summary.get("save_count", 0)),
            ("已完成", summary.get("completed_count", 0)),
            ("合格", summary.get("accepted", 0)),
            ("不合格", summary.get("rejected", 0)),
            ("异常", summary.get("failed", 0)),
            ("已停止", summary.get("stopped", 0)),
            ("未完成", summary.get("unfinished", 0)),
            ("总尝试", summary.get("attempt_count", 0)),
            ("平均尝试", f"{summary.get('average_attempts', 0):.2f}"),
            (
                "合格率",
                (
                    f"{summary['qualification_rate']:.1%}"
                    if summary.get("qualification_rate") is not None
                    else "-"
                ),
            ),
        )
        for index, (label, value) in enumerate(cards):
            card = _metric_card(metric_grid, label, value, index % 3)
            if index >= 3:
                card.grid_configure(
                    row=index // 3,
                    pady=(8, 0),
                )
        if filters.rule_mode == "all_grouped":
            grouped_holder = tk.Frame(overview, bg=COLORS["surface"])
            grouped_holder.pack(fill="x", padx=12, pady=(0, 10))
            tk.Label(
                grouped_holder,
                text="规则分组汇总",
                bg=COLORS["surface"],
                fg=COLORS["ink"],
                font=(FONT, 11, "bold"),
                anchor="w",
            ).pack(fill="x", padx=10, pady=(8, 4))
            grouped_rows = repository.get_grouped_summary(filters)
            for grouped in grouped_rows:
                rate = grouped.get("qualification_rate")
                rate_text = f"{rate:.1%}" if rate is not None else "-"
                label = (
                    f"{grouped.get('rule_name') or '未知规则'} · "
                    f"{str(grouped.get('rule_snapshot_hash') or '')[:12]}"
                )
                tk.Label(
                    grouped_holder,
                    text=(
                        f"{label}  存档 {grouped.get('save_count', 0)}  "
                        f"合格 {grouped.get('accepted', 0)}  "
                        f"不合格 {grouped.get('rejected', 0)}  "
                        f"合格率 {rate_text}"
                    ),
                    bg=COLORS["surface"],
                    fg=COLORS["muted"],
                    anchor="w",
                    font=(FONT, 9),
                ).pack(fill="x", padx=10, pady=2)
        chart_row = tk.Frame(overview, bg=COLORS["page"])
        chart_row.pack(fill="x", padx=12)
        chart_row.columnconfigure(0, weight=1, uniform="statistics_charts")
        chart_row.columnconfigure(1, weight=1, uniform="statistics_charts")
        _pie_chart(
            chart_row,
            [
                {"label": "合格", "value": "accepted", "count": summary.get("accepted", 0)},
                {"label": "不合格", "value": "rejected", "count": summary.get("rejected", 0)},
                {"label": "异常", "value": "failed", "count": summary.get("failed", 0)},
                {"label": "已停止", "value": "stopped", "count": summary.get("stopped", 0)},
                {"label": "未完成", "value": "unfinished", "count": summary.get("unfinished", 0)},
            ],
            title="状态分布",
            on_click=lambda row: set_detail_filter("status", row),
        ).grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        _bar_chart(
            chart_row,
            repository.get_failure_distribution(filters),
            title="失败原因",
            on_click=lambda row: set_detail_filter("failure", row),
        ).grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        trend = tk.Frame(overview, bg=COLORS["page"])
        trend.pack(fill="x", padx=12, pady=(10, 0))
        trend_controls = tk.Frame(trend, bg=COLORS["page"])
        trend_controls.pack(fill="x", pady=(0, 4))
        tk.Label(
            trend_controls,
            text="趋势指标",
            bg=COLORS["page"],
            fg=COLORS["muted"],
            font=(FONT, 9),
        ).pack(side="left")
        trend_options = {
            "运行数": ("runs", "运行"),
            "完成存档数": ("completed", "完成"),
            "合格数": ("accepted", "合格"),
            "合格率": ("qualification_rate", "合格率"),
            "平均尝试次数": ("average_attempts", "平均尝试"),
            "不同最终结果数": ("different_results", "不同结果"),
            "不同兵种数": ("different_jobs", "不同兵种"),
            "不同个人天赋数": (
                "different_personal_skills",
                "不同个人天赋",
            ),
            "不同兵种技能数": (
                "different_job_skills",
                "不同兵种技能",
            ),
            "不同宝物数": ("different_treasures", "不同宝物"),
            "不同宝物特性数": (
                "different_properties",
                "不同宝物特性",
            ),
        }
        trend_combo = ttk.Combobox(
            trend_controls,
            textvariable=trend_metric_var,
            values=tuple(trend_options),
            state="readonly",
            width=16,
        )
        trend_combo.pack(side="left", padx=(8, 0))
        trend_rows = repository.get_trend(filters)
        trend_field, trend_label = trend_options.get(
            trend_metric_var.get(),
            ("accepted", "合格"),
        )
        _line_chart(
            trend,
            trend_rows,
            title=(
                f"历史趋势：每日{trend_label}"
                if filters.scope == "history"
                else f"本次累计趋势：{trend_label}"
            ),
            value_field=trend_field,
            value_label=trend_label,
            on_click=lambda row: set_detail_filter(
                (
                    "date"
                    if filters.scope == "history"
                    else "attempt"
                ),
                {
                    "value": str(
                        row.get("date")
                        if filters.scope == "history"
                        else row.get("attempt_id")
                        or ""
                    )
                },
            ),
        ).pack(fill="x")
        trend_combo.bind("<<ComboboxSelected>>", lambda _event: render())
        details = tk.Frame(overview, bg=COLORS["surface"])
        details.pack(fill="both", expand=True, padx=12, pady=12)
        detail_total = repository.count_detail_rows(filters)
        page_count = max(
            1,
            (detail_total + detail_page_size - 1) // detail_page_size,
        )
        detail_page = min(detail_page, page_count - 1)
        render_tree(
            details,
            repository.get_detail_rows(
                filters,
                limit=detail_page_size,
                offset=detail_page * detail_page_size,
            ),
            total=detail_total,
            page=detail_page,
        )
        render_grouped(
            jobs,
            repository.get_member_distribution(filters),
            title="武将分布",
            kind="member",
        )
        render_grouped(
            jobs,
            repository.get_job_distribution(filters),
            title="兵种分布",
            kind="job",
        )
        skill_notebook = ttk.Notebook(skills)
        skill_notebook.pack(fill="both", expand=True, padx=12, pady=8)
        personal_skills = tk.Frame(skill_notebook, bg=COLORS["page"])
        job_skills = tk.Frame(skill_notebook, bg=COLORS["page"])
        skill_notebook.add(personal_skills, text="个人天赋")
        skill_notebook.add(job_skills, text="兵种技能")
        render_grouped(
            personal_skills,
            repository.get_personal_skill_distribution(filters),
            title="个人天赋",
            kind="personal",
        )
        render_grouped(
            personal_skills,
            repository.get_personal_skill_combination_distribution(filters),
            title="个人天赋组合",
            kind="personal_combo",
        )
        render_grouped(
            job_skills,
            repository.get_job_skill_distribution(filters),
            title="兵种技能",
            kind="job_skill",
        )
        render_grouped(
            job_skills,
            repository.get_job_skill_combination_distribution(filters),
            title="兵种技能组合",
            kind="job_skill_combo",
        )
        render_grouped(
            treasures,
            repository.get_treasure_distribution(filters),
            title="宝物",
            kind="treasure",
        )
        property_rows = repository.get_treasure_property_distribution(filters)
        property_controls = tk.Frame(treasures, bg=COLORS["page"])
        property_controls.pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(
            property_controls,
            text="宝物特性图表",
            bg=COLORS["page"],
            fg=COLORS["muted"],
            font=(FONT, 9),
        ).pack(side="left")
        property_combo = ttk.Combobox(
            property_controls,
            textvariable=treasure_chart_var,
            values=("柱状图", "环形图"),
            state="readonly",
            width=10,
        )
        property_combo.pack(side="left", padx=(8, 0))
        property_holder = tk.Frame(treasures, bg=COLORS["page"])
        property_holder.pack(fill="x")
        if treasure_chart_var.get() == "环形图":
            _pie_chart(
                property_holder,
                property_rows,
                title="宝物特性",
                on_click=lambda row: set_detail_filter("property", row),
            ).pack(fill="x", padx=12, pady=6)
        else:
            render_grouped(
                property_holder,
                property_rows,
                title="宝物特性",
                kind="property",
            )
        property_combo.bind("<<ComboboxSelected>>", lambda _event: render())
        combinations = repository.get_combination_distribution(filters)
        if combinations:
            render_grouped(
                treasures,
                combinations,
                title="宝物套装与组合",
                kind="combination",
            )
        else:
            tk.Label(
                treasures,
                text="本次没有识别到套装组合",
                bg=COLORS["page"],
                fg=COLORS["muted"],
                anchor="w",
            ).pack(fill="x", padx=12, pady=12)
        presence = repository.get_skill_presence_distribution(filters)
        if presence:
            for scope, target, title in (
                ("personal", personal_skills, "个人天赋有无分布"),
                ("job", job_skills, "兵种技能有无分布"),
            ):
                _bar_chart(
                    target,
                    [
                        row
                        for row in presence
                        if row["skill_scope"] == scope
                    ],
                    title=title,
                ).pack(fill="x", padx=12, pady=8)
        report = repository.validate_statistics(filters)
        recognition = repository.get_recognition_summary(filters)
        rule_notice = {
            "current": "当前规则",
            "selected": "指定规则",
            "all_grouped": "全部规则分组",
            "all_summary": "跨规则汇总",
        }[filters.rule_mode]
        status_var.set(
            f"{rule_notice} · {summary.get('rule_count', 0)}规则 · "
            f"{summary.get('save_count', 0)}存档 · "
            f"平均{summary.get('average_attempts', 0):.2f}次 · "
            f"识别{recognition['known_positions']}/"
            f"{recognition['total_positions']}"
            + (" · 已筛选图表明细" if detail_filter else "")
            + (
                " · 数据不完整：" + "；".join(report.issues)
                if not report.valid
                else ""
            )
        )

    def export_csv() -> None:
        target = filedialog.asksaveasfilename(
            parent=dialog,
            title="导出统计 CSV",
            defaultextension=".csv",
            filetypes=(("CSV 文件", "*.csv"),),
        )
        if target:
            repository.export_csv(build_filters(), Path(target))
            messagebox.showinfo("导出完成", "CSV 已导出。", parent=dialog)

    def export_json() -> None:
        target = filedialog.asksaveasfilename(
            parent=dialog,
            title="导出统计 JSON",
            defaultextension=".json",
            filetypes=(("JSON 文件", "*.json"),),
        )
        if target:
            repository.export_json(build_filters(), Path(target))
            messagebox.showinfo("导出完成", "JSON 已导出。", parent=dialog)

    def export_png() -> None:
        target = filedialog.asksaveasfilename(
            parent=dialog,
            title="导出统计 PNG",
            defaultextension=".png",
            filetypes=(("PNG 文件", "*.png"),),
        )
        if not target:
            return
        try:
            from PIL import ImageGrab

            dialog.update_idletasks()
            box = (
                dialog.winfo_rootx(),
                dialog.winfo_rooty(),
                dialog.winfo_rootx() + dialog.winfo_width(),
                dialog.winfo_rooty() + dialog.winfo_height(),
            )
            ImageGrab.grab(bbox=box).save(target)
        except Exception as exc:
            messagebox.showerror("导出失败", f"当前系统无法导出窗口图像：{exc}", parent=dialog)
            return
        messagebox.showinfo("导出完成", "PNG 已导出。", parent=dialog)

    def clear_statistics() -> None:
        if not messagebox.askyesno(
            "清空统计",
            "只隐藏统计历史，不删除存档、结果图或日志。确定继续吗？",
            parent=dialog,
        ):
            return
        repository.clear_statistics()
        render()

    def rebuild_statistics() -> None:
        repository.rebuild_statistics()
        render()

    def delete_run() -> None:
        runs = repository.history.list_runs(page_size=100)
        if not runs:
            messagebox.showinfo("删除运行", "没有可删除的运行记录。", parent=dialog)
            return
        chooser = tk.Toplevel(dialog)
        chooser.title("删除运行记录")
        chooser.transient(dialog)
        _center(chooser, dialog, 760, 430)
        listbox = tk.Listbox(chooser, selectmode="browse", font=(FONT, 9))
        listbox.pack(fill="both", expand=True, padx=14, pady=14)
        for item in runs:
            listbox.insert(
                "end",
                f"{item['started_at']} · {item['rule_name']} · "
                f"{item['mode']} · {item['id']}",
            )

        def confirm_delete() -> None:
            selection = listbox.curselection()
            if not selection:
                return
            run = runs[selection[0]]
            if not messagebox.askyesno(
                "确认删除",
                "只删除该运行的统计事实和历史快照，不删除游戏存档、结果图或日志。\n"
                "确定继续吗？",
                parent=chooser,
            ):
                return
            repository.delete_run(str(run["id"]))
            chooser.destroy()
            render()

        actions = tk.Frame(chooser)
        actions.pack(fill="x", padx=14, pady=(0, 14))
        tk.Button(actions, text="取消", command=chooser.destroy).pack(
            side="right", padx=(8, 0)
        )
        tk.Button(actions, text="删除", command=confirm_delete, fg=COLORS["red"]).pack(
            side="right"
        )

    buttons = tk.Frame(controls, bg=COLORS["page"])
    buttons.pack(fill="x", pady=(8, 0))
    for text, command in (
        ("刷新", render),
        ("导出 PNG", export_png),
        ("导出 CSV", export_csv),
        ("导出 JSON", export_json),
        ("清空统计", clear_statistics),
        ("重建统计", rebuild_statistics),
        ("删除运行", delete_run),
    ):
        tk.Button(buttons, text=text, command=command, relief="flat").pack(
            side="left",
            padx=2,
        )
    for combo in combos:
        combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: reset_page_and_render(),
        )
    clear_filter_button.configure(command=clear_detail_filter)
    time_combo = combos[-1]
    time_combo.bind(
        "<<ComboboxSelected>>",
        lambda _event: (
            open_custom_time()
            if time_var.get() == "自定义"
            else reset_page_and_render()
        ),
    )
    render()
