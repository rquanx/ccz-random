from __future__ import annotations
from ccz_randomizer.ui.dialog_actions import add_dialog_actions
from tkinter import ttk

from ccz_randomizer.ui.inputs import SearchEntry, TextEntry
from ccz_randomizer.ui.window_position import centered_toplevel, show_centered
from ccz_randomizer.ui.theme import setup_theme, style_dialog

import math
from pathlib import Path
from typing import Any, Callable

from ccz_randomizer.history import SUMMARY_MEMBER_LIMIT, HistoryRepository
from ccz_randomizer.history_members import history_members
from ccz_randomizer.history_filters import matching_summaries, parse_time_range
from ccz_randomizer.ui.history_loading import HistoryLoader, render_in_batches
from ccz_randomizer.ui.history_rounds import RoundCard


COLORS = {
    "page": "#F4F6FA",
    "surface": "#FFFFFF",
    "surface_alt": "#F8FAFC",
    "ink": "#182230",
    "muted": "#667085",
    "border": "#D9E0EA",
    "blue": "#2563EB",
    "blue_soft": "#EAF0FB",
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
ROUND_PAGE_SIZE = 10
DETAIL_EQUIPMENT_COLUMNS = 4
DETAIL_SPECIAL_MIN_WIDTH = 220


def _score(value: Any) -> str:
    try:
        return f"{float(value):.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return "-"


def _skill_names(items: list[dict[str, Any]]) -> str:
    names = [str(item.get("name") or "") for item in items]
    return "、".join(name for name in names if name) or "无"


def _display_time(value: Any, *, include_seconds: bool = False) -> str:
    text = str(value or "").replace("T", " ")
    length = 19 if include_seconds else 16
    return text[:length]


def _display_round_title(value: Any) -> str:
    title = str(value or "未命名")
    return title if len(title) <= 16 else title[:16] + "..."


def _metrics(snapshot: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    detail = snapshot.get("detail") or {}
    job = ((detail.get("job") or {}).get("metrics") or {})
    skill = ((detail.get("skill") or {}).get("metrics") or {})
    return job, skill


def _bind_mousewheel(widget, canvas) -> None:
    from ccz_randomizer.ui.window_events import bind_window_event
    owner = widget.winfo_toplevel()
    remainder = 0

    def scroll(event):
        nonlocal remainder
        current = event.widget
        while current is not None and current is not widget:
            current = getattr(current, "master", None)
        if current is not widget:
            return None
        remainder -= event.delta
        units = int(remainder / 120)
        if units:
            remainder -= units * 120
            canvas.yview_scroll(units, "units")
        return "break"

    binding = owner.bind("<MouseWheel>", scroll, add="+")
    bind_window_event(widget, "<Destroy>", lambda _event: owner.unbind("<MouseWheel>", binding))


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
    from ccz_randomizer.ui.member_card import MemberCard

    card = MemberCard(parent, member, colors=COLORS, font=FONT, score=_score, skill_names=_skill_names)
    card.grid(row=row, column=column, sticky="nsew", padx=3, pady=3)
    return card


def _show_detail(parent, snapshot: dict[str, Any]) -> None:
    import tkinter as tk

    detail_dialog = centered_toplevel(parent)
    detail_dialog.title(f"第 {snapshot.get('slot', '-')} 号存档详情")
    detail_dialog.minsize(960, 620)
    detail_dialog.transient(parent)
    detail_dialog.configure(bg=COLORS["page"])
    detail_dialog.geometry("1220x780")

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
        _score(job_metrics.get("qualificationAverage", job_metrics.get("average"))),
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
    from ccz_randomizer.ui.detail_actions import add_detail_actions
    # 宝物内容已直接展示在存档详情底部，避免再提供重复的独立入口。
    add_detail_actions(member_section, detail_dialog, snapshot, include_equipment=False)
    _section_heading(member_section, "武将与特技", color=COLORS["blue"])
    member_grid = tk.Frame(member_section, bg=COLORS["surface"])
    member_grid.pack(fill="x")
    members = history_members(snapshot)
    member_columns = 3 if len(members) <= 3 else 4
    from ccz_randomizer.ui.member_card import MemberCard
    from ccz_randomizer.ui.viewport_rows import ViewportRows
    member_grid.configure(width=member_columns*274)
    active_cards, free_cards = {}, []
    def render_member(index, y, height):
        card = active_cards.get(index)
        if card is None:
            if free_cards:
                card = free_cards.pop()
                card.member = members[index]
                card._width = None
            else:
                card = MemberCard(member_grid, members[index], colors=COLORS, font=FONT,
                                  score=_score, skill_names=_skill_names)
            active_cards[index] = card
        width = max(1, member_grid.winfo_width()/member_columns)
        card_width = max(1, int(width)-6)
        card._draw(card_width)
        card.place(x=int(index%member_columns*width)+3, y=y+3,
                   width=card_width, height=max(1, height-6))

    def release_member(index):
        card = active_cards.pop(index, None)
        if card is not None:
            card.place_forget()
            free_cards.append(card)

    viewport = ViewportRows(canvas, member_grid, render_member, release_member,
        columns=member_columns, manage_scrollregion=False,
        origin=lambda: member_section.winfo_y()+member_grid.winfo_y())
    detail_dialog._member_viewport = viewport
    measured_width = None
    reflow_timer = None
    def reflow_members(_event=None):
        nonlocal measured_width, reflow_timer
        reflow_timer = None
        if member_grid.winfo_width() <= 1:
            return
        width = max(1, int(member_grid.winfo_width()/member_columns)-6)
        if width == measured_width:
            return
        measured_width = width
        heights = MemberCard.row_heights(member_grid, members, member_columns, width,
                                        font=FONT, score=_score, skill_names=_skill_names)
        if viewport.count:
            viewport._set_heights(heights)
            viewport.width = None
            viewport.schedule()
        else:
            viewport.replace(heights, len(members))
    def schedule_reflow(_event=None):
        nonlocal reflow_timer
        if reflow_timer is None:
            from ccz_randomizer.ui.window_timer import window_after
            # Geometry negotiation can produce several intermediate widths in
            # one idle pass; measure the full roster only after that pass.
            reflow_timer = window_after(detail_dialog, 1, reflow_members)
    member_grid.bind('<Configure>', schedule_reflow)
    from ccz_randomizer.ui.render_state import track_render
    track_render(member_grid, lambda: reflow_timer is None and (not members or viewport.ready))

    from ccz_randomizer.ui.equipment_sections import render_equipment_sections
    render_equipment_sections(content, snapshot.get("equipment") or {})
    show_centered(detail_dialog)


def _summary_member_text(
    snapshot: dict[str, Any],
    *,
    limit: int = SUMMARY_MEMBER_LIMIT,
) -> str:
    lines = []
    members = history_members(snapshot)
    visible_members = members[:max(0, limit)]
    for member in visible_members:
        lines.append(
            f"{member.get('name', '')} · {member.get('job', '')}  "
            f"评分 {_score(member.get('jobScore'))}"
        )
    remaining = int(snapshot.get("memberCount", len(members))) - len(visible_members)
    if remaining > 0:
        lines.append(f"……其余 {remaining} 人请查看完整详情")
    return "\n\n".join(lines)


def _summary_card_view(snapshot, search_query=""):
    job_metrics, skill_metrics = _metrics(snapshot)
    metadata = snapshot.get("history") or {}
    preview = str(metadata.get("title") or metadata.get("note") or "")
    return dict(slot=f"存档 {snapshot.get('slot', '-')}",
                preview=preview[:80] + ("…" if len(preview) > 80 else ""),
                marked=False, hit="",
                job=f"兵种 {_score(job_metrics.get('average'))}",
                skill=f"特技 {_score(skill_metrics.get('skillScore'))}",
                members=_summary_member_text(snapshot), backed_up=bool(metadata.get("backed_up")))


def _render_summary_card(parent, snapshot, *, show_detail, edit_metadata=None, export_save=None, search_query=""):
    from ccz_randomizer.ui.history_cards import SummaryCard
    card = SummaryCard(parent, colors=COLORS, font=FONT)
    card.update_content(snapshot, _summary_card_view(snapshot, search_query), show_detail=show_detail,
                        edit_metadata=edit_metadata, export_save=export_save)
    return card


def _render_full_result_card(parent, snapshot: dict[str, Any]):
    from ccz_randomizer.ui.overview_card import result_card
    return result_card(parent, snapshot)


def _show_round_overview(
    parent,
    row: dict[str, Any],
    snapshots: list[dict[str, Any]],
) -> None:
    import tkinter as tk

    overview = centered_toplevel(parent)
    setup_theme(overview)
    style_dialog(overview)
    overview.title(f"第 {row['round_number']} 轮全部结果")
    overview.minsize(1100, 700)
    overview.transient(parent)
    overview.configure(bg=COLORS["page"])
    overview.geometry("1500x900")
    header = tk.Frame(overview, bg=COLORS["ink"], padx=18, pady=13)
    header.pack(fill="x")
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
            f"规则：{row['rule_name']}  "
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
    def render_card(index, snapshot):
        card = _render_full_result_card(grid, snapshot)
        card.grid(
            row=index // 5,
            column=index % 5,
            sticky="nsew",
            padx=6,
            pady=6,
        )
    render_in_batches(overview, snapshots, render_card, batch_size=4, time_budget_ms=6)
    show_centered(overview)


def show_history_window(parent, repository: HistoryRepository | Path) -> None:
    import tkinter as tk
    from tkinter import filedialog, ttk
    from ccz_randomizer.ui import messages as messagebox
    from itertools import count
    from pathlib import Path
    import datetime as dt
    from ccz_randomizer.ui.history_actions import edit_history_metadata

    existing = getattr(parent, "_history_window", None)
    if existing is not None and existing.winfo_exists():
        if getattr(existing, "_ccz_cached_closed", False):
            existing._reload_history()
            from ccz_randomizer.ui.cached_dialog import restore_dialog
            restore_dialog(existing)
        else:
            existing.lift()
        return
    dialog = centered_toplevel(parent)
    parent._history_window = dialog
    setup_theme(dialog)
    style_dialog(dialog)
    dialog.title("历史记录")
    dialog.minsize(1120, 680)
    dialog.transient(parent)
    dialog.configure(bg=COLORS["page"])
    dialog.geometry("1480x850")

    page = 1
    selected_round_id: int | None = None
    selected_snapshots: list[dict[str, Any]] = []
    round_rows: dict[str, dict[str, Any]] = {}
    total = 0
    render_generation = 0
    page_generation = 0
    selection_to_restore = None
    loader = HistoryLoader(dialog)
    operations = count()
    applied_filters = dict(query="", marked_only=False, started_after=None, started_before=None, rule_name=None)
    rule_names = []

    def resolve_repository():
        # Called only by the serialized worker, including initialization and
        # migration. Opening the window must never wait for a database lock.
        nonlocal repository
        if isinstance(repository, Path):
            repository = HistoryRepository(repository)
        return repository

    def request_action(action, done, failed):
        # Writes and exports must not be cancelled by a subsequent action.
        loader.request(f"action-{next(operations)}", action, done, failed, durable=True)

    toolbar = tk.Frame(dialog, bg=COLORS["page"], padx=14, pady=10)
    toolbar.pack(fill="x")
    title_var = tk.StringVar(value="历史记录")
    tk.Label(
        toolbar,
        textvariable=title_var,
        font=(FONT, 14, "bold"),
        fg=COLORS["ink"],
        bg=COLORS["page"],
    ).pack(side="left")

    filters = tk.Frame(dialog, bg=COLORS["page"], padx=14, pady=6)
    filters.pack(fill="x")
    query_var = tk.StringVar()
    tk.Label(filters, text="关键字", bg=COLORS["page"]).pack(side="left")
    query_entry = SearchEntry(filters, textvariable=query_var, width=28,
        hint="搜索轮次名称、备注和规则；回车应用筛选，Esc 清空输入")
    query_entry.pack(side="left", padx=8)

    tk.Label(filters, text="规则", bg=COLORS["page"]).pack(side="left", padx=(8, 4))
    rule_combo = ttk.Combobox(filters, state="readonly", width=18, values=("全部规则",))
    rule_combo.current(0)
    rule_combo.pack(side="left", padx=(0, 8))

    start_var, end_var = tk.StringVar(), tk.StringVar()
    tk.Label(filters, text="时间", bg=COLORS["page"]).pack(side="left", padx=(12, 4))
    start_entry = TextEntry(filters, textvariable=start_var, width=18)
    start_entry.pack(side="left", padx=8)
    tk.Label(filters, text="至", bg=COLORS["page"]).pack(side="left")
    end_entry = TextEntry(filters, textvariable=end_var, width=18)
    end_entry.pack(side="left", padx=8)

    def open_time_picker(target):
        picker = centered_toplevel(dialog)
        picker.title("选择日期与时间")
        picker.transient(dialog)
        body = tk.Frame(picker, padx=14, pady=12)
        body.pack(fill="both", expand=True)
        date_var = tk.StringVar()
        time_var = tk.StringVar(value="00:00:00")
        value = target.get().strip().replace("T", " ")
        if value:
            date_var.set(value[:10])
            if len(value) > 10:
                time_var.set(value[11:19])
        import datetime as dt
        today = dt.date.today()
        try:
            parsed_date = dt.date.fromisoformat(date_var.get()) if date_var.get() else today
        except ValueError:
            parsed_date = today
        try:
            parsed_time = dt.time.fromisoformat(time_var.get()) if time_var.get() else dt.time()
        except ValueError:
            parsed_time = dt.time()
        values = [
            tk.StringVar(value=str(parsed_date.year)), tk.StringVar(value=f"{parsed_date.month:02d}"),
            tk.StringVar(value=f"{parsed_date.day:02d}"), tk.StringVar(value=f"{parsed_time.hour:02d}"),
            tk.StringVar(value=f"{parsed_time.minute:02d}"), tk.StringVar(value=f"{parsed_time.second:02d}"),
        ]
        tk.Label(body, text="日期").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        for index, var in enumerate(values[:3], start=1):
            TextEntry(body, textvariable=var, width=6).grid(row=0, column=index, padx=2, pady=4)
        tk.Label(body, text="年 / 月 / 日", fg=COLORS["muted"]).grid(row=0, column=4, sticky="w", padx=(5, 0))
        tk.Label(body, text="时间").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        for index, var in enumerate(values[3:], start=1):
            TextEntry(body, textvariable=var, width=6).grid(row=1, column=index, padx=2, pady=4)
        tk.Label(body, text="时 / 分 / 秒", fg=COLORS["muted"]).grid(row=1, column=4, sticky="w", padx=(5, 0))
        def apply_picker():
            try:
                date_text = f"{int(values[0].get()):04d}-{int(values[1].get()):02d}-{int(values[2].get()):02d}"
                time_text = f"{int(values[3].get()):02d}:{int(values[4].get()):02d}:{int(values[5].get()):02d}"
                dt.datetime.fromisoformat(f"{date_text} {time_text}")
            except (TypeError, ValueError):
                messagebox.showerror("时间无效", "请选择有效的日期和时间。", parent=picker)
                return
            target.delete(0, "end")
            target.insert(0, f"{date_text} {time_text}")
            picker.destroy()
        def clear_picker():
            target.delete(0, "end")
            picker.destroy()
        picker_actions = ttk.Frame(body)
        picker_actions.grid(row=2, column=2, columnspan=3, sticky="ew", pady=(10, 0))
        add_dialog_actions(picker_actions, confirm=apply_picker, cancel=picker.destroy,
                           alternatives=(("清除", clear_picker),))
        show_centered(picker)

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

    # Keep a tiny compatibility Treeview for automation and old integrations.
    # The visible round picker below is made from ordinary Tk cards so the
    # editing affordance and selected state are obvious.
    columns = ("title", "time", "rule")
    rounds = ttk.Treeview(
        list_panel,
        columns=columns,
        show="headings",
        selectmode="browse",
    )
    headings = {
        "title": "轮次",
        "time": "时间",
        "rule": "规则",
    }
    widths = {"title": 150, "time": 132, "rule": 110}
    for column in columns:
        rounds.heading(column, text=headings[column])
        rounds.column(column, width=widths[column], stretch=column == "title")
    rounds.place(x=-2000, y=-2000, width=1, height=1)

    round_picker = tk.Frame(list_panel, bg=COLORS["surface"])
    round_picker.pack(fill="both", expand=True)
    round_canvas = tk.Canvas(round_picker, bg=COLORS["surface"], highlightthickness=0)
    round_scroll = ttk.Scrollbar(round_picker, orient="vertical", command=round_canvas.yview)
    round_canvas.configure(yscrollcommand=round_scroll.set)
    round_scroll.pack(side="right", fill="y")
    round_canvas.pack(side="left", fill="both", expand=True)
    round_content = tk.Frame(round_canvas, bg=COLORS["surface"])
    round_window = round_canvas.create_window((0, 0), window=round_content, anchor="nw")
    round_content.bind("<Configure>", lambda _e: round_canvas.configure(scrollregion=round_canvas.bbox("all")))
    round_canvas.bind("<Configure>", lambda e: round_canvas.itemconfigure(round_window, width=e.width))
    round_widgets: dict[int, RoundCard] = {}
    round_pool: list[RoundCard] = []
    active_edit_finish: Callable[[], None] | None = None

    def commit_edit_on_click(_event=None):
        if active_edit_finish is not None:
            active_edit_finish()

    def bind_edit_clicks(widget):
        # Bind to the existing widget tree instead of bind_all. Global
        # bindings accumulated one handler per edit and caused sluggishness.
        widget.bind("<Button-1>", commit_edit_on_click, add="+")
        for child in widget.winfo_children():
            bind_edit_clicks(child)

    bind_edit_clicks(round_picker)
    dialog.bind("<Button-1>", commit_edit_on_click, add="+")

    def scroll_round(event):
        delta = -1 if event.delta > 0 else 1
        round_canvas.yview_scroll(delta, "units")
        return "break"

    def bind_round_wheel(widget):
        widget.bind("<MouseWheel>", scroll_round, add="+")
        for child in widget.winfo_children():
            bind_round_wheel(child)

    bind_round_wheel(round_picker)

    def set_round_selected(round_id: int) -> None:
        for rid, widget in round_widgets.items():
            widget.set_selected(rid == round_id)

    def edit_round_inline(row: dict[str, Any], head: tk.Frame, name_label, edit_button) -> None:
        nonlocal active_edit_finish
        if active_edit_finish is not None:
            # Finish the previous editor first; never allow two rows to show
            # input fields at the same time.
            previous = active_edit_finish
            previous()
            return
        for child in list(head.winfo_children()):
            if getattr(child, "_round_editor", False):
                return
        name_label.pack_forget()
        edit_button.pack_forget()
        editor = tk.Frame(head, bg=COLORS["blue_soft"])
        editor._round_editor = True
        editor.pack(side="left", fill="x", expand=True)
        title_var = tk.StringVar(value=row.get("title") or "")
        entry = TextEntry(editor, textvariable=title_var, font=(FONT, 11, "bold"), width=18)
        entry.pack(side="left", fill="x", expand=True)
        finished = False
        def restore_editor():
            nonlocal active_edit_finish
            if editor.winfo_exists():
                editor.destroy()
                name_label.pack(side="left", fill="x", expand=True)
                edit_button.pack(side="right", anchor="center", padx=(12, 0), before=name_label)
            if active_edit_finish is finish_edit:
                active_edit_finish = None
        def finish_edit(_event=None):
            nonlocal finished
            if finished:
                return
            finished = True
            title_text = title_var.get().strip()[:100]
            if not title_text:
                restore_editor()
                return
            values = {"title": title_text, "note": row.get("note", "")}
            restore_editor()
            request_action(lambda: resolve_repository().annotate_round(int(row["id"]), **values),
                           lambda _: load_page(), action_error)
        # Defer one idle cycle so the Entry has committed the last keystroke
        # before the focus transition triggers persistence.
        entry.bind("<FocusOut>", lambda _event: dialog.after_idle(finish_edit))
        entry.bind("<Return>", finish_edit)
        entry.bind("<KP_Enter>", finish_edit)
        active_edit_finish = finish_edit
        entry.focus_set()
        entry.select_range(0, "end")

    def build_round_widget(row: dict[str, Any]) -> RoundCard:
        def choose(current_row):
            rid = int(current_row["id"])
            if active_edit_finish is not None:
                active_edit_finish()
            item = next((key for key, value in round_rows.items() if int(value["id"]) == rid), None)
            if item:
                rounds.selection_set(item)
                rounds.focus(item)
            set_round_selected(rid)
            render_results(current_row)
        card = RoundCard(round_content, colors=COLORS, font=FONT,
            display_title=_display_round_title, display_time=_display_time,
            select=choose, edit=edit_round_inline)
        card.update_content(row)
        bind_edit_clicks(card)
        bind_round_wheel(card)
        return card

    pager = tk.Frame(list_panel, bg=COLORS["surface"], pady=8)
    pager.pack(fill="x")
    previous_button = ttk.Button(pager, text="上一页")
    previous_button.pack(side="left", padx=(8, 0))
    page_var = tk.StringVar(value="第 1 页")
    tk.Label(
        pager,
        textvariable=page_var,
        fg=COLORS["muted"],
        bg=COLORS["surface"],
    ).pack(side="left", expand=True)
    next_button = ttk.Button(pager, text="下一页")
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

    holder, canvas, grid, grid_window = _scrollable_frame(
        result_panel,
        background=COLORS["page"],
    )
    holder.pack(fill="both", expand=True)
    # Result cards use a responsive four-column grid; horizontal scrolling
    # only creates an apparent empty strip when the last row is short.
    for child in holder.winfo_children():
        if isinstance(child, ttk.Scrollbar) and str(child.cget("orient")) == "horizontal":
            child.pack_forget()
    grid.configure(padx=8, pady=8)
    cards = []
    active_cards = {}
    result_views = []
    notice = tk.Label(grid, bg=COLORS["page"], fg=COLORS["muted"], pady=30)
    def commit_edit_on_result_click(_event=None):
        if active_edit_finish is not None:
            active_edit_finish()
    result_panel.bind("<Button-1>", commit_edit_on_result_click, add="+")
    canvas.bind("<Button-1>", commit_edit_on_result_click, add="+")
    for column in range(4):
        grid.columnconfigure(column, minsize=236, weight=1)

    def hide_cards(text=None):
        result_viewport.clear()
        for card in cards:
            card.suspend()
        if text:
            notice.configure(text=text)
            notice.grid(row=0, column=0, sticky="w")
        else:
            notice.grid_remove()

    def resize_grid(event) -> None:
        canvas.itemconfigure(grid_window, width=max(event.width, 1))

    canvas.bind("<Configure>", resize_grid)

    def release_visible_card(index):
        card = active_cards.pop(index, None)
        if card is not None:
            card.suspend()

    def render_visible_card(index, top, height):
        from ccz_randomizer.ui.history_cards import SummaryCard
        snapshot = selected_snapshots[index]
        card = active_cards.get(index) or next((card for card in cards if card not in active_cards.values()), None)
        if card is None:
            card = SummaryCard(grid, colors=COLORS, font=FONT)
            cards.append(card)
        card.update_content(snapshot, result_views[index],
                            show_detail=open_result_detail, export_save=export_result)
        card.place(x=8 + (index % 4) * max(236, (canvas.winfo_width() - 16) // 4),
                   y=top + 5, width=224, height=height - 10)
        active_cards[index] = card

    from ccz_randomizer.ui.viewport_rows import ViewportRows
    result_viewport = ViewportRows(canvas, grid, render_visible_card, release_visible_card)
    # Diagnostics inspect completed visible rows, rather than requiring hidden cards.
    dialog._result_viewport = result_viewport

    def render_results(row: dict[str, Any]) -> None:
        nonlocal selected_round_id, selected_snapshots, render_generation
        if selected_round_id == int(row["id"]):
            return
        selected_round_id = int(row["id"])
        selected_snapshots = []
        render_generation += 1
        loader.invalidate("detail")
        loader.invalidate("overview")
        generation = render_generation
        canvas.xview_moveto(0)
        canvas.yview_moveto(0)
        hide_cards("正在读取本轮记录…")
        round_header.set(
            f"{_display_time(row['started_at'], include_seconds=True)}  "
            f"第 {row['round_number']} 轮  "
            f"{row.get('title') or row['rule_name']}"
        )
        round_id = selected_round_id
        loader.request("results", lambda: resolve_repository().get_round_summaries(round_id),
                       lambda snapshots: show_results(row, snapshots, generation), show_error)

    def open_result_detail(snapshot):
        round_id, slot = selected_round_id, int(snapshot["slot"])
        loader.request("detail", lambda: resolve_repository().get_result(round_id, slot),
                       lambda full: _show_detail(dialog, full) if full is not None else show_error("该结果已被删除"),
                       show_error)

    def action_error(error):
        messagebox.showerror("历史记录操作失败", str(error), parent=dialog)

    def export_result(snapshot):
        round_id, slot = selected_round_id, int(snapshot["slot"])
        destination = filedialog.asksaveasfilename(parent=dialog, title="导出历史存档",
            initialfile=f"SV{slot:03}.E5S", defaultextension=".E5S", filetypes=[("游戏存档", "*.E5S")])
        if destination:
            request_action(lambda: resolve_repository().export_result_save(round_id, slot, Path(destination)),
                           lambda _: messagebox.showinfo("存档已导出", "存档已导出。将文件放入游戏 SV 目录的对应槽位后即可读取。", parent=dialog),
                           action_error)

    def show_error(error) -> None:
        hide_cards()
        round_header.set(f"历史记录读取失败：{error}")

    def show_results(row, snapshots, generation) -> None:
        nonlocal selected_snapshots, result_views
        if generation != render_generation:
            return
        notice.grid_remove()
        selected_snapshots = matching_summaries(row, snapshots, query=applied_filters["query"],
                                                marked_only=applied_filters["marked_only"])
        if any(applied_filters.values()):
            round_header.set(f"{_display_time(row['started_at'], include_seconds=True)}  "
                             f"{row.get('title') or row['rule_name']} · 第 {row['round_number']} 轮  "
                             f"匹配 {len(selected_snapshots)} / 共 {len(snapshots)} 个合格存档")
        if not selected_snapshots:
            hide_cards("本轮没有匹配的合格存档。" if any(applied_filters.values()) else "该轮次还没有已保存的合格结果。")
            return
        from ccz_randomizer.ui.history_cards import SummaryCard
        result_views = [_summary_card_view(snapshot, applied_filters["query"]) for snapshot in selected_snapshots]
        if not cards:
            cards.append(SummaryCard(grid, colors=COLORS, font=FONT))
        heights = SummaryCard.row_heights(canvas, result_views, cards[0].detail.winfo_reqheight(), FONT)
        result_viewport.replace(heights, len(selected_snapshots))

    def selected_row() -> dict[str, Any] | None:
        selection = rounds.selection()
        return round_rows.get(selection[0]) if selection else None

    def select_round(_event=None) -> None:
        row = selected_row()
        if row is not None:
            render_results(row)

    rounds.bind("<<TreeviewSelect>>", select_round)

    def load_page() -> None:
        nonlocal round_rows, selected_round_id, selected_snapshots, render_generation, selection_to_restore, page_generation
        if selected_round_id is not None:
            selection_to_restore = selected_round_id
        render_generation += 1
        page_generation += 1
        loader.invalidate("results")
        loader.invalidate("detail")
        loader.invalidate("overview")
        selected_round_id = None
        selected_snapshots = []
        previous_button.configure(state="disabled")
        next_button.configure(state="disabled")
        round_header.set("正在读取历史记录…")
        hide_cards()
        for item in rounds.get_children():
            rounds.delete(item)
        round_rows = {}
        # Keep the picker widgets alive across background reloads. This avoids
        # focus flicker and preserves the visual list while a result query is
        # being refreshed.
        requested_page = page
        filters = dict(applied_filters)

        def read_page():
            active_repository = resolve_repository()
            count = active_repository.count_rounds(**filters)
            resolved_page = min(requested_page, max(1, math.ceil(count / ROUND_PAGE_SIZE)))
            return resolved_page, active_repository.list_rounds(resolved_page, ROUND_PAGE_SIZE, **filters), count, active_repository.list_rule_names()

        loader.request("page", read_page, show_page, show_error)

    def show_page(result) -> None:
        nonlocal page, total, active_edit_finish, rule_names
        page, rows, total, rule_names = result
        # Selection uses the item index, so a real profile named “全部规则”
        # remains distinct from the all-rules option.
        selected_rule = applied_filters["rule_name"]
        if selected_rule is not None and selected_rule not in rule_names:
            rule_names.append(selected_rule)
        rule_combo.configure(values=("全部规则", *rule_names))
        rule_combo.current(0 if selected_rule is None else rule_names.index(selected_rule) + 1)
        # Reuse at most one page of cards; changing pages must not accumulate widgets.
        if active_edit_finish is not None:
            active_edit_finish()
            active_edit_finish = None
        round_widgets.clear()
        for widget in round_pool[len(rows):]:
            widget.pack_forget()
        for row in rows:
            item = rounds.insert(
                "",
                "end",
                values=(
                    row.get("title") or "未命名",
                    _display_time(row["started_at"]),
                    row["rule_name"],
                ),
            )
            round_rows[item] = row
        generation = page_generation
        def render_round(index, row):
            if index < len(round_pool):
                widget = round_pool[index]
                widget.update_content(row)
            else:
                widget = build_round_widget(row)
                round_pool.append(widget)
            round_widgets[int(row["id"])] = widget
            if not widget.winfo_manager():
                widget.pack(fill="x", padx=7, pady=4)
            widget.set_selected(selected_round_id == int(row["id"]))
        reused = min(len(rows), len(round_pool))
        for index, row in enumerate(rows[:reused]):
            render_round(index, row)
        render_in_batches(dialog, rows[reused:], lambda index, row: render_round(index + reused, row),
                           is_current=lambda: generation == page_generation,
                           batch_size=4, delay_ms=1, time_budget_ms=6)
        total_pages = max(1, math.ceil(total / ROUND_PAGE_SIZE))
        page_var.set(f"第 {page} / {total_pages} 页")
        previous_button.configure(state="normal" if page > 1 else "disabled")
        next_button.configure(
            state="normal" if page < total_pages else "disabled"
        )
        title_var.set(f"历史记录  {'命中' if any(applied_filters.values()) else '共'} {total} 轮")
        if rows:
            first = next((item for item, row in round_rows.items() if row["id"] == selection_to_restore), rounds.get_children()[0])
            rounds.selection_set(first)
            rounds.focus(first)
            set_round_selected(int(round_rows[first]["id"]))
            render_results(round_rows[first])
        else:
            round_header.set("没有匹配的历史记录，请调整筛选条件" if any(applied_filters.values()) else "暂无历史记录")
            hide_cards()

    def previous_page() -> None:
        nonlocal page
        if page > 1:
            page -= 1
            load_page()

    def next_page() -> None:
        nonlocal page
        if page * ROUND_PAGE_SIZE < total:
            page += 1
            load_page()

    def delete_selected() -> None:
        row = selected_row()
        if row is None:
            return
        if not messagebox.askyesno(
            "删除历史轮次",
            "将删除这轮历史记录及其独立存档副本。游戏 SV 目录中的存档和旧图片不受影响。确定继续吗？",
            parent=dialog,
        ):
            return
        round_id = int(row["id"])
        request_action(lambda: resolve_repository().delete_round(round_id), lambda _: load_page(), action_error)

    def clear_history() -> None:
        if not messagebox.askyesno(
            "清空历史记录",
            "将删除全部历史记录，包括被筛选隐藏的记录。\n"
            "独立存档副本也会删除；游戏 SV 目录中的存档和旧图片不受影响。确定继续吗？",
            parent=dialog,
        ):
            return
        request_action(lambda: resolve_repository().clear(), lambda _: load_page(), action_error)

    previous_button.configure(command=previous_page)
    next_button.configure(command=next_page)
    def apply_filters(_event=None):
        nonlocal page, applied_filters
        try:
            after, before = parse_time_range(start_var.get(), end_var.get())
        except ValueError as error:
            messagebox.showerror("筛选时间无效", str(error), parent=dialog)
            return
        applied_filters = dict(query=query_var.get().strip(), marked_only=False,
                               started_after=after, started_before=before,
                               rule_name=rule_names[rule_combo.current() - 1] if rule_combo.current() > 0 else None)
        page = 1
        load_page()

    def reset_filters():
        query_var.set("")
        start_var.set("")
        end_var.set("")
        rule_combo.current(0)
        apply_filters()

    def edit_round():
        row = selected_row()
        if row is not None:
            round_id = int(row["id"])
            edit_history_metadata(dialog, row, lambda values: request_action(
                lambda: resolve_repository().annotate_round(round_id, **values),
                lambda _: load_page(), action_error))

    def edit_round_icon(event):
        if rounds.identify_column(event.x) != "#1":
            return
        item = rounds.identify_row(event.y)
        if not item:
            return
        column_width = rounds.column("title", "width")
        if event.x < column_width - 24:
            return
        rounds.selection_set(item)
        rounds.focus(item)
        edit_round()
        return "break"

    query_entry.bind("<Return>", apply_filters)
    rule_combo.bind("<<ComboboxSelected>>", apply_filters)
    rounds.bind("<Button-1>", edit_round_icon, add="+")
    start_entry.bind("<Button-1>", lambda _event: open_time_picker(start_entry))
    end_entry.bind("<Button-1>", lambda _event: open_time_picker(end_entry))
    start_entry.bind("<Return>", apply_filters)
    end_entry.bind("<Return>", apply_filters)
    ttk.Button(filters, text="搜索", command=apply_filters).pack(side="left")
    ttk.Button(filters, text="重置筛选", command=reset_filters).pack(side="left")
    ttk.Button(toolbar, text="刷新", command=load_page).pack(
        side="right"
    )
    ttk.Button(toolbar, text="清空全部历史", command=clear_history).pack(
        side="right", padx=(0, 8)
    )
    ttk.Button(toolbar, text="删除本轮", command=delete_selected).pack(
        side="right", padx=(0, 8)
    )
    from ccz_randomizer.ui.window_events import bind_window_event
    remove_storage_listener = bind_window_event(dialog._root(), "<<StorageCleaned>>", lambda _: load_page()
        if "history" in getattr(dialog._root(), "_ccz_cleaned_categories", ()) else None)
    bind_window_event(dialog, "<Destroy>", lambda _: remove_storage_listener())
    dialog._reload_history = load_page
    from ccz_randomizer.ui.cached_dialog import hide_dialog
    dialog.protocol("WM_DELETE_WINDOW", lambda: (commit_edit_on_click(), hide_dialog(dialog)))
    load_page()
    show_centered(dialog)
