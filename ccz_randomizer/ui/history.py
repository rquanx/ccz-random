from __future__ import annotations

import math
from typing import Any, Callable

from ccz_randomizer.history import DEFAULT_PAGE_SIZE, HistoryRepository


COLORS = {
    "page": "#EEECE7",
    "surface": "#FFFFFF",
    "surface_alt": "#F7F6F2",
    "ink": "#1F2937",
    "muted": "#667085",
    "border": "#D6D3CD",
    "blue": "#2457C5",
    "blue_soft": "#EAF0FF",
    "red": "#B42318",
    "red_soft": "#FDECEA",
    "green": "#18794E",
    "green_soft": "#E8F5EE",
    "amber": "#A15C00",
    "amber_soft": "#FFF3D8",
    "purple": "#7C3AED",
}
SPECIAL_COLORS = (
    "#2457C5",
    "#B42318",
    "#7C3AED",
    "#18794E",
    "#A15C00",
    "#0E7490",
)
FONT = "Microsoft YaHei UI"
DETAIL_EQUIPMENT_COLUMNS = 4
DETAIL_SPECIAL_MIN_WIDTH = 220


def _center_window(window, parent, width: int, height: int) -> None:
    window.update_idletasks()
    parent.update_idletasks()
    parent_width = max(parent.winfo_width(), parent.winfo_reqwidth())
    parent_height = max(parent.winfo_height(), parent.winfo_reqheight())
    x = parent.winfo_rootx() + (parent_width - width) // 2
    y = parent.winfo_rooty() + (parent_height - height) // 2
    screen_x = window.winfo_vrootx()
    screen_y = window.winfo_vrooty()
    screen_width = window.winfo_vrootwidth()
    screen_height = window.winfo_vrootheight()
    x = max(screen_x, min(x, screen_x + max(0, screen_width - width)))
    y = max(screen_y, min(y, screen_y + max(0, screen_height - height)))
    window.geometry(f"{width}x{height}+{x}+{y}")


def _score(value: Any) -> str:
    try:
        return f"{float(value):.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return "-"


def _skill_names(items: list[dict[str, Any]]) -> str:
    names = [str(item.get("name") or "") for item in items]
    return "、".join(name for name in names if name) or "无"


def _status_text(status: str) -> str:
    return {
        "running": "进行中",
        "completed": "已完成",
        "stopped": "已停止",
        "failed": "异常",
    }.get(status, status)


def _display_time(value: Any, *, include_seconds: bool = False) -> str:
    text = str(value or "").replace("T", " ")
    length = 19 if include_seconds else 16
    return text[:length]


def _metrics(snapshot: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    detail = snapshot.get("detail") or {}
    job = ((detail.get("job") or {}).get("metrics") or {})
    skill = ((detail.get("skill") or {}).get("metrics") or {})
    return job, skill


def _bind_mousewheel(widget, canvas) -> None:
    def scroll(event) -> None:
        canvas.yview_scroll(int(-event.delta / 120), "units")

    widget.bind(
        "<Enter>",
        lambda _event: canvas.bind_all("<MouseWheel>", scroll),
    )
    widget.bind(
        "<Leave>",
        lambda _event: canvas.unbind_all("<MouseWheel>"),
    )


def _scrollable_frame(parent, *, background: str):
    import tkinter as tk
    from tkinter import ttk

    holder = tk.Frame(parent, bg=background)
    canvas = tk.Canvas(holder, highlightthickness=0, bg=background)
    vertical = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview)
    horizontal = ttk.Scrollbar(
        holder,
        orient="horizontal",
        command=canvas.xview,
    )
    canvas.configure(
        yscrollcommand=vertical.set,
        xscrollcommand=horizontal.set,
    )
    vertical.pack(side="right", fill="y")
    horizontal.pack(side="bottom", fill="x")
    canvas.pack(side="left", fill="both", expand=True)
    content = tk.Frame(canvas, bg=background)
    window = canvas.create_window((0, 0), window=content, anchor="nw")
    content.bind(
        "<Configure>",
        lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
    )
    _bind_mousewheel(holder, canvas)
    return holder, canvas, content, window


def _section_heading(parent, text: str, *, color: str):
    import tkinter as tk

    row = tk.Frame(parent, bg=COLORS["surface"])
    row.pack(fill="x", pady=(0, 5))
    tk.Frame(row, width=3, height=17, bg=color).pack(side="left")
    tk.Label(
        row,
        text=text,
        font=(FONT, 10, "bold"),
        bg=COLORS["surface"],
        fg=COLORS["ink"],
        padx=6,
    ).pack(side="left")
    return row


def _stat_box(parent, label: str, value: str, *, color: str, background: str):
    import tkinter as tk

    box = tk.Frame(
        parent,
        bg=background,
        highlightbackground=color,
        highlightthickness=1,
        padx=11,
        pady=7,
    )
    tk.Label(
        box,
        text=label,
        font=(FONT, 9),
        fg=COLORS["muted"],
        bg=background,
    ).pack(anchor="w")
    tk.Label(
        box,
        text=value,
        font=(FONT, 15, "bold"),
        fg=color,
        bg=background,
    ).pack(anchor="w", pady=(2, 0))
    return box


def _render_member_card(parent, member: dict[str, Any], column: int, row: int):
    import tkinter as tk

    card = tk.Frame(
        parent,
        bg=COLORS["surface_alt"],
        highlightbackground=COLORS["border"],
        highlightthickness=1,
        padx=7,
        pady=5,
    )
    card.grid(row=row, column=column, sticky="nsew", padx=3, pady=3)
    title = tk.Frame(card, bg=COLORS["surface_alt"])
    title.pack(fill="x")
    tk.Label(
        title,
        text=str(member.get("name") or "未知"),
        font=(FONT, 10, "bold"),
        fg=COLORS["ink"],
        bg=COLORS["surface_alt"],
    ).pack(side="left")
    tk.Label(
        title,
        text=(
            f"{member.get('job') or '未知兵种'}  "
            f"{_score(member.get('jobScore'))}"
        ),
        font=(FONT, 8, "bold"),
        fg=COLORS["red"],
        bg=COLORS["red_soft"],
        padx=5,
        pady=1,
    ).pack(side="right")
    for label, value, color in (
        (
            "个人",
            _skill_names(member.get("personalSkills") or []),
            COLORS["blue"],
        ),
        (
            "兵种",
            _skill_names(member.get("jobSkills") or []),
            COLORS["purple"],
        ),
    ):
        line = tk.Frame(card, bg=COLORS["surface_alt"])
        line.pack(fill="x", pady=(3, 0))
        tk.Label(
            line,
            text=label,
            font=(FONT, 8, "bold"),
            fg=color,
            bg=COLORS["surface_alt"],
            width=4,
            anchor="w",
        ).pack(side="left")
        tk.Label(
            line,
            text=value,
            font=(FONT, 8),
            fg=COLORS["ink"],
            bg=COLORS["surface_alt"],
            justify="left",
            wraplength=205,
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
    return card


def _show_detail(parent, snapshot: dict[str, Any]) -> None:
    import tkinter as tk

    detail_dialog = tk.Toplevel(parent)
    detail_dialog.title(f"第 {snapshot.get('slot', '-')} 号存档详情")
    detail_dialog.minsize(960, 620)
    detail_dialog.transient(parent)
    detail_dialog.configure(bg=COLORS["page"])
    _center_window(detail_dialog, parent, 1220, 780)

    holder, canvas, content, content_window = _scrollable_frame(
        detail_dialog,
        background=COLORS["page"],
    )
    holder.pack(fill="both", expand=True)
    content.configure(padx=12, pady=12)

    def fit_content(event) -> None:
        requested = content.winfo_reqwidth()
        canvas.itemconfigure(content_window, width=max(event.width, requested))

    canvas.bind("<Configure>", fit_content)

    job_metrics, skill_metrics = _metrics(snapshot)

    stats = tk.Frame(content, bg=COLORS["page"])
    stats.pack(fill="x", pady=(0, 7))
    for column in range(3):
        stats.columnconfigure(column, weight=1, uniform="detail-stat")
    _stat_box(
        stats,
        "兵种平均分",
        _score(job_metrics.get("average")),
        color=COLORS["blue"],
        background=COLORS["blue_soft"],
    ).grid(row=0, column=0, sticky="nsew", padx=(0, 5))
    _stat_box(
        stats,
        "特技总分",
        _score(skill_metrics.get("skillScore")),
        color=COLORS["purple"],
        background="#F2ECFF",
    ).grid(row=0, column=1, sticky="nsew", padx=5)
    _stat_box(
        stats,
        "保存时间",
        _display_time(snapshot.get("createdAt")),
        color=COLORS["amber"],
        background=COLORS["amber_soft"],
    ).grid(row=0, column=2, sticky="nsew", padx=(5, 0))

    member_section = tk.Frame(
        content,
        bg=COLORS["surface"],
        highlightbackground=COLORS["border"],
        highlightthickness=1,
        padx=7,
        pady=7,
    )
    member_section.pack(fill="x", pady=(0, 7))
    _section_heading(member_section, "武将与特技", color=COLORS["blue"])
    member_grid = tk.Frame(member_section, bg=COLORS["surface"])
    member_grid.pack(fill="x")
    members = snapshot.get("members") or []
    member_columns = 3 if len(members) <= 3 else 4
    for column in range(member_columns):
        member_grid.columnconfigure(column, weight=1, uniform="member")
    for index, member in enumerate(members):
        _render_member_card(
            member_grid,
            member,
            index % member_columns,
            index // member_columns,
        )

    lower = tk.Frame(content, bg=COLORS["page"])
    lower.pack(fill="x")
    lower.columnconfigure(0, weight=0, minsize=DETAIL_SPECIAL_MIN_WIDTH)
    lower.columnconfigure(1, weight=1, minsize=850)
    equipment = snapshot.get("equipment") or {}

    special_panel = tk.Frame(
        lower,
        bg=COLORS["surface"],
        highlightbackground=COLORS["border"],
        highlightthickness=1,
        padx=7,
        pady=7,
    )
    special_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
    _section_heading(special_panel, "宝物特殊组合", color=COLORS["red"])
    specials = equipment.get("specials") or []
    if not specials:
        tk.Label(
            special_panel,
            text="本存档没有特殊组合",
            font=(FONT, 10),
            fg=COLORS["muted"],
            bg=COLORS["surface"],
        ).pack(anchor="w", pady=6)
    for index, special in enumerate(specials):
        color = SPECIAL_COLORS[index % len(SPECIAL_COLORS)]
        block = tk.Frame(
            special_panel,
            bg=COLORS["surface_alt"],
            highlightbackground=color,
            highlightthickness=1,
            padx=7,
            pady=5,
        )
        block.pack(fill="x", pady=(0, 5))
        tk.Label(
            block,
            text=str(special.get("title") or "特殊组合"),
            font=(FONT, 9, "bold"),
            fg=color,
            bg=COLORS["surface_alt"],
        ).pack(anchor="w")
        tk.Label(
            block,
            text="\n".join(str(value) for value in special.get("items") or []),
            font=(FONT, 8),
            fg=COLORS["ink"],
            bg=COLORS["surface_alt"],
            justify="left",
            wraplength=190,
        ).pack(anchor="w", fill="x", pady=(2, 0))

    equipment_panel = tk.Frame(
        lower,
        bg=COLORS["surface"],
        highlightbackground=COLORS["border"],
        highlightthickness=1,
        padx=7,
        pady=7,
    )
    equipment_panel.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
    _section_heading(equipment_panel, "宝物列表", color=COLORS["green"])
    equipment_grid = tk.Frame(equipment_panel, bg=COLORS["surface"])
    equipment_grid.pack(fill="x")
    for column in range(DETAIL_EQUIPMENT_COLUMNS):
        equipment_grid.columnconfigure(column, weight=1, uniform="equipment")
    for index, category in enumerate(equipment.get("categories") or []):
        category_frame = tk.Frame(
            equipment_grid,
            bg=COLORS["surface_alt"],
            padx=6,
            pady=4,
        )
        category_frame.grid(
            row=index // DETAIL_EQUIPMENT_COLUMNS,
            column=index % DETAIL_EQUIPMENT_COLUMNS,
            sticky="nsew",
            padx=3,
            pady=3,
        )
        tk.Label(
            category_frame,
            text=str(category.get("name") or "其他"),
            font=(FONT, 9, "bold"),
            fg=COLORS["green"],
            bg=COLORS["surface_alt"],
        ).pack(anchor="w", pady=(0, 2))
        for item in category.get("items") or []:
            tk.Label(
                category_frame,
                text=f"{item.get('name', '')}  {item.get('effect', '')}",
                font=(FONT, 8),
                fg=COLORS["ink"],
                bg=COLORS["surface_alt"],
                justify="left",
                wraplength=165,
            ).pack(anchor="w", fill="x")

def _summary_member_text(snapshot: dict[str, Any]) -> str:
    lines = []
    for member in snapshot.get("members") or []:
        personal = _skill_names(member.get("personalSkills") or [])
        job = _skill_names(member.get("jobSkills") or [])
        lines.append(
            f"{member.get('name', '')} · {member.get('job', '')}\n"
            f"个人 {personal}\n兵种 {job}"
        )
    return "\n\n".join(lines)


def _render_summary_card(
    parent,
    snapshot: dict[str, Any],
    *,
    show_detail: Callable[[dict[str, Any]], None],
):
    import tkinter as tk

    job_metrics, skill_metrics = _metrics(snapshot)
    card = tk.Frame(
        parent,
        width=260,
        height=360,
        bg=COLORS["surface"],
        highlightbackground=COLORS["border"],
        highlightthickness=1,
    )
    card.grid_propagate(False)
    header = tk.Frame(card, bg=COLORS["ink"], padx=9, pady=6)
    header.pack(fill="x")
    tk.Label(
        header,
        text=f"存档 {snapshot.get('slot', '-')}",
        font=(FONT, 10, "bold"),
        fg="#FFFFFF",
        bg=COLORS["ink"],
    ).pack(side="left")
    score_bar = tk.Frame(card, bg=COLORS["surface"], padx=9, pady=5)
    score_bar.pack(fill="x")
    tk.Label(
        score_bar,
        text=f"兵种 {_score(job_metrics.get('average'))}",
        font=(FONT, 9, "bold"),
        fg=COLORS["blue"],
        bg=COLORS["surface"],
    ).pack(side="left")
    tk.Label(
        score_bar,
        text=f"特技 {_score(skill_metrics.get('skillScore'))}",
        font=(FONT, 9, "bold"),
        fg=COLORS["purple"],
        bg=COLORS["surface"],
    ).pack(side="right")
    tk.Frame(card, height=1, bg=COLORS["border"]).pack(fill="x")
    tk.Label(
        card,
        text=_summary_member_text(snapshot),
        font=(FONT, 8),
        fg=COLORS["ink"],
        bg=COLORS["surface"],
        justify="left",
        anchor="nw",
        wraplength=238,
        padx=9,
        pady=6,
    ).pack(fill="both", expand=True)
    tk.Button(
        card,
        text="查看完整详情",
        command=lambda: show_detail(snapshot),
        font=(FONT, 9),
        fg="#FFFFFF",
        bg=COLORS["blue"],
        activebackground="#1946A3",
        activeforeground="#FFFFFF",
        relief="flat",
        padx=8,
        pady=4,
        cursor="hand2",
    ).pack(fill="x", padx=9, pady=7)
    return card


def _render_full_result_card(parent, snapshot: dict[str, Any]):
    import tkinter as tk

    job_metrics, skill_metrics = _metrics(snapshot)
    card = tk.Frame(
        parent,
        width=360,
        bg=COLORS["surface"],
        highlightbackground=COLORS["border"],
        highlightthickness=1,
    )

    header = tk.Frame(card, bg=COLORS["ink"], padx=10, pady=7)
    header.pack(fill="x")
    tk.Label(
        header,
        text=f"存档 {snapshot.get('slot', '-')}",
        font=(FONT, 10, "bold"),
        fg="#FFFFFF",
        bg=COLORS["ink"],
    ).pack(side="left")
    tk.Label(
        header,
        text=f"第 {snapshot.get('acceptedAttempt', '-')} 次尝试",
        font=(FONT, 8),
        fg="#D1D5DB",
        bg=COLORS["ink"],
    ).pack(side="right")

    score_bar = tk.Frame(card, bg=COLORS["surface"], padx=10, pady=6)
    score_bar.pack(fill="x")
    tk.Label(
        score_bar,
        text=f"兵种 {_score(job_metrics.get('average'))}",
        font=(FONT, 9, "bold"),
        fg=COLORS["blue"],
        bg=COLORS["surface"],
    ).pack(side="left")
    tk.Label(
        score_bar,
        text=f"特技 {_score(skill_metrics.get('skillScore'))}",
        font=(FONT, 9, "bold"),
        fg=COLORS["purple"],
        bg=COLORS["surface"],
    ).pack(side="right")

    members_panel = tk.Frame(card, bg=COLORS["surface"], padx=8, pady=3)
    members_panel.pack(fill="x")
    for member in snapshot.get("members") or []:
        block = tk.Frame(
            members_panel,
            bg=COLORS["surface_alt"],
            padx=7,
            pady=5,
        )
        block.pack(fill="x", pady=2)
        title = tk.Frame(block, bg=COLORS["surface_alt"])
        title.pack(fill="x")
        tk.Label(
            title,
            text=str(member.get("name") or "未知"),
            font=(FONT, 9, "bold"),
            fg=COLORS["ink"],
            bg=COLORS["surface_alt"],
        ).pack(side="left")
        tk.Label(
            title,
            text=(
                f"{member.get('job', '未知兵种')}  "
                f"{_score(member.get('jobScore'))}"
            ),
            font=(FONT, 8, "bold"),
            fg=COLORS["red"],
            bg=COLORS["surface_alt"],
        ).pack(side="right")
        tk.Label(
            block,
            text=(
                "个人  "
                + _skill_names(member.get("personalSkills") or [])
                + "\n兵种  "
                + _skill_names(member.get("jobSkills") or [])
            ),
            font=(FONT, 8),
            fg=COLORS["ink"],
            bg=COLORS["surface_alt"],
            justify="left",
            anchor="w",
            wraplength=324,
        ).pack(fill="x", pady=(2, 0))

    equipment = snapshot.get("equipment") or {}
    specials = equipment.get("specials") or []
    section = tk.Frame(card, bg=COLORS["surface"], padx=8, pady=5)
    section.pack(fill="x")
    tk.Label(
        section,
        text="宝物特殊组合",
        font=(FONT, 9, "bold"),
        fg=COLORS["red"],
        bg=COLORS["surface"],
    ).pack(anchor="w", pady=(0, 3))
    if not specials:
        tk.Label(
            section,
            text="无",
            font=(FONT, 8),
            fg=COLORS["muted"],
            bg=COLORS["surface"],
        ).pack(anchor="w")
    for index, special in enumerate(specials):
        color = SPECIAL_COLORS[index % len(SPECIAL_COLORS)]
        tk.Label(
            section,
            text=(
                f"{special.get('title', '')}\n"
                + "\n".join(
                    f"  {value}" for value in special.get("items") or []
                )
            ),
            font=(FONT, 8),
            fg=color,
            bg=COLORS["surface"],
            justify="left",
            anchor="w",
            wraplength=334,
        ).pack(fill="x", pady=2)

    equipment_section = tk.Frame(
        card,
        bg=COLORS["surface"],
        padx=8,
        pady=0,
    )
    equipment_section.pack(fill="x", pady=(0, 8))
    tk.Label(
        equipment_section,
        text="宝物列表",
        font=(FONT, 9, "bold"),
        fg=COLORS["green"],
        bg=COLORS["surface"],
    ).pack(anchor="w", pady=(0, 3))
    for category in equipment.get("categories") or []:
        rows = [
            f"{item.get('name', '')}  {item.get('effect', '')}"
            for item in category.get("items") or []
        ]
        tk.Label(
            equipment_section,
            text=(
                f"{category.get('name', '其他')}\n"
                + "\n".join(f"  {item}" for item in rows)
            ),
            font=(FONT, 8),
            fg=COLORS["ink"],
            bg=COLORS["surface"],
            justify="left",
            anchor="w",
            wraplength=334,
        ).pack(fill="x", pady=2)
    return card


def _show_round_overview(
    parent,
    row: dict[str, Any],
    snapshots: list[dict[str, Any]],
) -> None:
    import tkinter as tk

    overview = tk.Toplevel(parent)
    overview.title(f"第 {row['round_number']} 轮全部结果")
    overview.minsize(1100, 700)
    overview.transient(parent)
    overview.configure(bg=COLORS["page"])
    _center_window(overview, parent, 1500, 900)
    header = tk.Frame(overview, bg=COLORS["ink"], padx=18, pady=13)
    header.pack(fill="x")
    mode = "3人" if row["mode"] == "three" else "7人"
    tk.Label(
        header,
        text=f"第 {row['round_number']} 轮 · 全部存档详情",
        font=(FONT, 15, "bold"),
        fg="#FFFFFF",
        bg=COLORS["ink"],
    ).pack(side="left")
    tk.Label(
        header,
        text=(
            f"{_display_time(row['started_at'], include_seconds=True)}  "
            f"{mode}  规则：{row['rule_name']}  "
            f"共 {len(snapshots)} 个结果"
        ),
        font=(FONT, 9),
        fg="#D1D5DB",
        bg=COLORS["ink"],
        padx=16,
    ).pack(side="left")
    holder, _canvas, grid, _window = _scrollable_frame(
        overview,
        background=COLORS["page"],
    )
    holder.pack(fill="both", expand=True)
    grid.configure(padx=12, pady=12)
    for column in range(5):
        grid.columnconfigure(column, minsize=370)
    for index, snapshot in enumerate(snapshots):
        card = _render_full_result_card(grid, snapshot)
        card.grid(
            row=index // 5,
            column=index % 5,
            sticky="nsew",
            padx=6,
            pady=6,
        )


def show_history_window(parent, repository: HistoryRepository) -> None:
    import tkinter as tk
    from tkinter import messagebox, ttk

    dialog = tk.Toplevel(parent)
    dialog.title("历史结果")
    dialog.minsize(1120, 680)
    dialog.transient(parent)
    dialog.configure(bg=COLORS["page"])
    _center_window(dialog, parent, 1480, 850)

    page = 1
    selected_round_id: int | None = None
    selected_snapshots: list[dict[str, Any]] = []
    round_rows: dict[str, dict[str, Any]] = {}

    toolbar = tk.Frame(dialog, bg=COLORS["page"], padx=14, pady=10)
    toolbar.pack(fill="x")
    title_var = tk.StringVar(value="历史结果")
    tk.Label(
        toolbar,
        textvariable=title_var,
        font=(FONT, 14, "bold"),
        fg=COLORS["ink"],
        bg=COLORS["page"],
    ).pack(side="left")

    body = tk.PanedWindow(
        dialog,
        orient="horizontal",
        sashwidth=5,
        bg=COLORS["border"],
    )
    body.pack(fill="both", expand=True, padx=14, pady=(0, 10))
    list_panel = tk.Frame(body, width=390, bg=COLORS["surface"])
    result_panel = tk.Frame(body, bg=COLORS["page"])
    body.add(list_panel, minsize=340)
    body.add(result_panel, minsize=680)

    columns = ("time", "mode", "rule", "count", "status")
    rounds = ttk.Treeview(
        list_panel,
        columns=columns,
        show="headings",
        selectmode="browse",
    )
    headings = {
        "time": "时间",
        "mode": "模式",
        "rule": "规则",
        "count": "结果",
        "status": "状态",
    }
    widths = {"time": 132, "mode": 64, "rule": 116, "count": 52, "status": 68}
    for column in columns:
        rounds.heading(column, text=headings[column])
        rounds.column(column, width=widths[column], stretch=column == "rule")
    rounds.pack(fill="both", expand=True)

    pager = tk.Frame(list_panel, bg=COLORS["surface"], pady=8)
    pager.pack(fill="x")
    previous_button = tk.Button(pager, text="上一页", width=8)
    previous_button.pack(side="left", padx=(8, 0))
    page_var = tk.StringVar(value="第 1 页")
    tk.Label(
        pager,
        textvariable=page_var,
        fg=COLORS["muted"],
        bg=COLORS["surface"],
    ).pack(side="left", expand=True)
    next_button = tk.Button(pager, text="下一页", width=8)
    next_button.pack(side="right", padx=(0, 8))

    result_header = tk.Frame(result_panel, bg=COLORS["surface"], padx=12, pady=9)
    result_header.pack(fill="x")
    round_header = tk.StringVar(value="请选择一个历史轮次")
    tk.Label(
        result_header,
        textvariable=round_header,
        font=(FONT, 12, "bold"),
        fg=COLORS["ink"],
        bg=COLORS["surface"],
        anchor="w",
    ).pack(side="left", fill="x", expand=True)
    overview_button = tk.Button(
        result_header,
        text="本轮全部结果",
        state="disabled",
        font=(FONT, 9, "bold"),
        fg="#FFFFFF",
        bg=COLORS["blue"],
        activebackground="#1946A3",
        activeforeground="#FFFFFF",
        relief="flat",
        padx=12,
        pady=5,
        cursor="hand2",
    )
    overview_button.pack(side="right")

    holder, canvas, grid, grid_window = _scrollable_frame(
        result_panel,
        background=COLORS["page"],
    )
    holder.pack(fill="both", expand=True)
    grid.configure(padx=8, pady=8)

    def resize_grid(event) -> None:
        canvas.itemconfigure(grid_window, width=max(event.width, 1360))

    canvas.bind("<Configure>", resize_grid)

    def render_results(row: dict[str, Any]) -> None:
        nonlocal selected_round_id, selected_snapshots
        selected_round_id = int(row["id"])
        for child in grid.winfo_children():
            child.destroy()
        mode = "3人" if row["mode"] == "three" else "7人"
        round_header.set(
            f"{_display_time(row['started_at'], include_seconds=True)}  "
            f"第 {row['round_number']} 轮  {mode}  "
            f"规则：{row['rule_name']}"
        )
        selected_snapshots = repository.get_round_results(selected_round_id)
        overview_button.configure(
            state="normal" if selected_snapshots else "disabled",
            command=lambda: _show_round_overview(
                dialog,
                row,
                selected_snapshots,
            ),
        )
        if not selected_snapshots:
            tk.Label(
                grid,
                text="该轮次还没有已保存的合格结果。",
                bg=COLORS["page"],
                fg=COLORS["muted"],
                pady=30,
            ).grid(row=0, column=0, sticky="w")
            return
        for column in range(5):
            grid.columnconfigure(column, minsize=270)
        for index, snapshot in enumerate(selected_snapshots):
            card = _render_summary_card(
                grid,
                snapshot,
                show_detail=lambda value: _show_detail(dialog, value),
            )
            card.grid(
                row=index // 5,
                column=index % 5,
                sticky="nsew",
                padx=5,
                pady=5,
            )

    def selected_row() -> dict[str, Any] | None:
        selection = rounds.selection()
        return round_rows.get(selection[0]) if selection else None

    def select_round(_event=None) -> None:
        row = selected_row()
        if row is not None:
            render_results(row)

    rounds.bind("<<TreeviewSelect>>", select_round)

    def load_page() -> None:
        nonlocal round_rows
        for item in rounds.get_children():
            rounds.delete(item)
        rows = repository.list_rounds(page, DEFAULT_PAGE_SIZE)
        round_rows = {}
        for row in rows:
            item = rounds.insert(
                "",
                "end",
                values=(
                    _display_time(row["started_at"]),
                    "3人" if row["mode"] == "three" else "7人",
                    row["rule_name"],
                    row["result_count"],
                    _status_text(str(row["status"])),
                ),
            )
            round_rows[item] = row
        total = repository.count_rounds()
        total_pages = max(1, math.ceil(total / DEFAULT_PAGE_SIZE))
        page_var.set(f"第 {page} / {total_pages} 页")
        previous_button.configure(state="normal" if page > 1 else "disabled")
        next_button.configure(
            state="normal" if page < total_pages else "disabled"
        )
        title_var.set(f"历史结果  共 {total} 轮")
        if rows:
            first = rounds.get_children()[0]
            rounds.selection_set(first)
            rounds.focus(first)
            render_results(rows[0])
        else:
            round_header.set("暂无历史结果")
            overview_button.configure(state="disabled")
            for child in grid.winfo_children():
                child.destroy()

    def previous_page() -> None:
        nonlocal page
        if page > 1:
            page -= 1
            load_page()

    def next_page() -> None:
        nonlocal page
        if page * DEFAULT_PAGE_SIZE < repository.count_rounds():
            page += 1
            load_page()

    def delete_selected() -> None:
        row = selected_row()
        if row is None:
            return
        if not messagebox.askyesno(
            "删除历史轮次",
            "只删除这轮的历史记录，不会删除游戏存档或旧图片。确定继续吗？",
            parent=dialog,
        ):
            return
        repository.delete_round(int(row["id"]))
        load_page()

    def clear_history() -> None:
        total = repository.count_rounds()
        if not total:
            return
        if not messagebox.askyesno(
            "清空历史记录",
            f"将删除全部 {total} 轮历史记录。\n"
            "游戏存档和旧图片不会被删除。确定继续吗？",
            parent=dialog,
        ):
            return
        repository.clear()
        load_page()

    previous_button.configure(command=previous_page)
    next_button.configure(command=next_page)
    tk.Button(toolbar, text="刷新", width=8, command=load_page).pack(
        side="right"
    )
    tk.Button(toolbar, text="清空历史", width=10, command=clear_history).pack(
        side="right", padx=(0, 8)
    )
    tk.Button(toolbar, text="删除本轮", width=10, command=delete_selected).pack(
        side="right", padx=(0, 8)
    )
    load_page()
