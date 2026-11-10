from __future__ import annotations

from ccz_randomizer.ui.window_position import centered_toplevel, show_centered
from ccz_randomizer.ui.theme import COLORS, setup_theme, style_dialog
from ccz_randomizer.ui.window_events import bind_window_event

import json
from collections import OrderedDict
from pathlib import Path

from ccz_randomizer.recruitment import Recruit, display_job_options, filter_recruits, parse_recruits
from ccz_randomizer.runtime.skill_memory import normalize_skill_name
from ccz_randomizer.rules import skill_scores
from ccz_randomizer.entry_catalog import entry_stage_order, missing_fixed_entries
from ccz_randomizer.search_history import default_search_history_path
from ccz_randomizer.ui.inputs import SearchEntry
from ccz_randomizer.ui.search_memory import SearchMemory
from ccz_randomizer.ui.searchable_combo import SearchableCombobox

SEARCH_HISTORY_IDLE_MS = 1000


def special_talent_names(rule: dict | None) -> frozenset[str]:
    """Return names that the selected rule currently treats as special."""
    profile = rule or {}
    if "profiles" in profile:
        profile = profile.get("profiles", {}).get(profile.get("activeProfile"), {})
    seven = profile.get("sevenPerson", {}) if isinstance(profile, dict) else {}
    threshold = seven.get("specialSkillWeight", 5.0)
    overrides = seven.get("skillBaseScores", {})
    normalized_overrides = {normalize_skill_name(name): value for name, value in overrides.items()}
    result = set()
    names = {normalize_skill_name(name): (name, default)
             for name, default in skill_scores.DEFAULT_SCORES.items()}
    for name in overrides:
        names.setdefault(normalize_skill_name(name), (name, 0.0))
    for normalized, (name, default) in names.items():
        score = overrides.get(name, normalized_overrides.get(normalized, default))
        if skill_scores.special_score_category(score, threshold):
            result.add(normalized)
    return frozenset(result)


def show_recruit_window(parent, catalog_path: Path | None = None, *, snapshot: dict | None = None, history_path: Path | None = None, rule: dict | None = None) -> None:
    """Display recruitment candidates as lightweight canvas cards."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    if catalog_path is None and snapshot is None:
        filename = filedialog.askopenfilename(parent=parent, title="打开人员快照", filetypes=[("人员快照", "*.json")])
        if not filename: return
        catalog_path = Path(filename)
    try:
        payload = snapshot if snapshot is not None else json.loads(catalog_path.read_text(encoding="utf-8"))
        fixed = payload.get("fixedPersonnel")
        if fixed is None:
            fixed = missing_fixed_entries(payload.get("gameVersion"))
        recruits = parse_recruits(dict(payload, personnel=[*(payload.get("personnel") or []), *fixed]))
    except (OSError, ValueError) as exc:
        messagebox.showerror("无法读取人员快照", str(exc), parent=parent); return
    def current_rule():
        if rule is not None:
            return rule
        provider = getattr(parent._root(), "_current_rule_profile", None)
        return provider() if callable(provider) else payload.get("rule")
    dialog = centered_toplevel(parent); dialog.title("入队人员"); dialog.geometry("1180x760"); dialog.minsize(820, 560); dialog.transient(parent)
    setup_theme(dialog)
    style_dialog(dialog)
    colors = {"ink":"#182230", "muted":"#667085", "surface":"#FFFFFF", "alt":"#F4F6FA", "line":"#D9E0EA", "accent":"#2563EB"}
    outer = ttk.Frame(dialog, padding=20); outer.pack(fill="both", expand=True)
    filters = ttk.Frame(outer); filters.pack(fill="x", pady=12)
    query, stage = tk.StringVar(), tk.StringVar(value="全部关卡")
    special_only = tk.BooleanVar(value=False)
    ttk.Label(filters, text="搜索人物、兵种或天赋", foreground=colors["muted"]).pack(side="left")
    entry = SearchEntry(filters, textvariable=query, width=28,
        hint="即时搜索人物、兵种或天赋；Esc 清空，Ctrl+A 全选"); entry.pack(side="left", padx=(8,12))
    stage_order = entry_stage_order(payload.get("gameVersion"))
    stage_values = tuple(sorted(dict.fromkeys(value for row in recruits for value in (row.stages or (row.stage,))),
                                key=lambda label: stage_order.get(label, 999)))
    stage_combo = SearchableCombobox(filters, textvariable=stage, width=24,
        search_label="搜索关卡", empty_text="没有匹配的关卡",
        values=("全部关卡", *(value.removeprefix("共通 · ") for value in stage_values)))
    stage_combo.pack(side="left", padx=(0,12))
    ttk.Checkbutton(filters, text="只看特殊技能", variable=special_only).pack(side="left")
    def selected_stage():
        return next((value for value in stage_values if value.removeprefix("共通 · ") == stage.get()), "")

    cached_special_names = None
    normalized_talents = {row.record_index: frozenset(normalize_skill_name(talent)
                         for talent in (*row.job_talents, *row.personal_talents)) for row in recruits}
    def current_special_names():
        nonlocal cached_special_names
        if cached_special_names is None:
            cached_special_names = special_talent_names(current_rule())
        return cached_special_names

    def matching_recruits(word: str, special_names: frozenset[str]) -> tuple[Recruit, ...]:
        rows = filter_recruits(recruits, word, stage=selected_stage())
        if not special_only.get():
            return rows
        return tuple(row for row in rows if normalized_talents[row.record_index] & special_names)

    body = ttk.Frame(outer); body.pack(fill="both", expand=True); body.rowconfigure(0,weight=1); body.columnconfigure(0,weight=1)
    memory = SearchMemory(entry, query,
        history_path if history_path is not None else default_search_history_path(),
        has_matches=lambda word: bool(matching_recruits(word, current_special_names())),
        parent=outer, before=body, idle_ms=SEARCH_HISTORY_IDLE_MS)
    canvas = tk.Canvas(body, background=colors["alt"], highlightthickness=0); canvas.grid(row=0,column=0,sticky="nsew")
    vertical = ttk.Scrollbar(body, orient="vertical", command=canvas.yview); vertical.grid(row=0,column=1,sticky="ns")
    canvas.configure(yscrollcommand=vertical.set)
    stage_people: OrderedDict[str, list[Recruit]] = OrderedDict()
    for row in recruits:
        for stage_name in row.stages or (row.stage,): stage_people.setdefault(stage_name, []).append(row)
    refresh_after = None
    last_layout = None
    render_generation = 0
    def refresh() -> None:
        nonlocal refresh_after, last_layout, render_generation
        refresh_after = None
        special_names = current_special_names()
        stage_filter = selected_stage()
        width = max(1, canvas.winfo_width())
        layout = (width, query.get(), stage_filter, special_only.get(), special_names)
        if layout == last_layout:
            return
        last_layout = layout
        render_generation += 1
        generation = render_generation
        canvas.delete("all")
        visible = matching_recruits(query.get(), special_names)
        visible_ids = {row.record_index for row in visible}
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

            def line(text: str, *, indent: int = 0, bold: bool = False, reserve: int = 0, special: bool = False) -> None:
                nonlocal cursor
                item = canvas.create_text(
                    x + 12 + indent, cursor, anchor="nw", text=text,
                    fill=COLORS["danger"] if special else (colors["ink"] if bold else colors["muted"]),
                    width=max(1, card_width - 24 - indent - reserve),
                    font=("Microsoft YaHei UI", 10, "bold" if bold else "normal"),
                    tags=(tag,))
                cursor = canvas.bbox(item)[3] + 5

            cost = canvas.create_text(
                x + card_width - 12, cursor, anchor="ne", text="固定" if row.entry_kind == "fixed" else f"{row.cost}次",
                fill=colors["muted"], font=("Microsoft YaHei UI", 9), tags=(tag,))
            cost_bounds = canvas.bbox(cost)
            line(f"{row.name} · {display_job_options(row)}", bold=True,
                 reserve=cost_bounds[2] - cost_bounds[0] + 12)
            for title, talents in (("兵种天赋", row.job_talents),
                                   ("人物天赋", row.personal_talents)):
                cursor += 5
                line(title, bold=True)
                for talent in talents or ("无",):
                    line(talent, indent=14, special=normalize_skill_name(talent) in special_names)
            bottom = cursor + 7
            canvas.coords(background, x, top, x + card_width, bottom)
            return background, bottom

        def draw_rows():
            nonlocal y, shown_stages
            for stage_name in stage_values:
                people_all = stage_people[stage_name]
                if stage_filter and stage_name != stage_filter:
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
                        canvas.configure(scrollregion=(0, 0, width, y))
                        yield None
                y += 8
            if not shown_stages:
                canvas.create_text(20, y, anchor="nw", text="没有符合条件的入队人员",
                                   fill=colors["muted"], font=("Microsoft YaHei UI", 10))
                y += 40
            canvas.configure(scrollregion=(0, 0, width, y))
        from ccz_randomizer.ui.history_loading import render_in_batches
        render_in_batches(dialog, draw_rows(), lambda _index, _item: None,
                          is_current=lambda: generation == render_generation, batch_size=3)

    def schedule_query(*_args) -> None:
        nonlocal refresh_after
        if not dialog.winfo_exists():
            return
        if refresh_after: dialog.after_cancel(refresh_after)
        refresh_after=dialog.after(50,refresh)
    canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(-int(e.delta / 120), "units"))
    canvas.bind("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
    canvas.bind("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))
    canvas.bind("<Configure>", schedule_query)
    query.trace_add("write", schedule_query)
    stage.trace_add("write", schedule_query)
    special_only.trace_add("write", schedule_query)
    def rules_updated(*_args):
        nonlocal cached_special_names
        cached_special_names = None
        schedule_query()
    remove_rule_listener = bind_window_event(parent._root(), "<<RulesUpdated>>", rules_updated)
    def close() -> None:
        memory.remember()
        if refresh_after: dialog.after_cancel(refresh_after)
        dialog.destroy()
    def on_destroy(event) -> None:
        nonlocal refresh_after
        if event.widget is not dialog:
            return
        remove_rule_listener()
        if refresh_after:
            try:
                dialog.after_cancel(refresh_after)
            except tk.TclError:
                pass
            refresh_after = None
    dialog.bind("<Destroy>", on_destroy)
    dialog.protocol("WM_DELETE_WINDOW", close)
    show_centered(dialog)
    if refresh_after:
        dialog.after_cancel(refresh_after)
    refresh()
    entry.focus_set()
