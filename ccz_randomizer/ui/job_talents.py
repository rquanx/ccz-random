from __future__ import annotations

from ccz_randomizer.ui.window_position import centered_toplevel, show_centered
from ccz_randomizer.ui.inputs import SearchEntry
from ccz_randomizer.ui.theme import setup_theme, style_dialog
from ccz_randomizer.ui.window_events import bind_window_event

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


def show_job_talents_window(parent, *, snapshot: dict, rule: dict | None = None) -> None:
    import tkinter as tk
    from tkinter import ttk, font
    from ccz_randomizer.ui import messages as messagebox
    from ccz_randomizer.ui.recruitment import high_job_names, special_talent_names
    from ccz_randomizer.runtime.skill_memory import normalize_skill_name

    try:
        jobs = load_job_talents(snapshot)
    except (OSError, ValueError) as exc:
        messagebox.showerror("无法读取兵种天赋", str(exc), parent=parent)
        return
    dialog = centered_toplevel(parent)
    setup_theme(dialog)
    style_dialog(dialog)
    dialog.title("兵种天赋")
    dialog.geometry("900x680")
    dialog.minsize(680, 480)
    dialog.transient(parent)
    colors = {"ink": "#182230", "muted": "#667085", "surface": "#FFFFFF", "page": "#F4F6FA"}
    outer = ttk.Frame(dialog, padding=20)
    outer.pack(fill="both", expand=True)
    ttk.Label(outer, text="全部兵种天赋", font=("Microsoft YaHei UI", 17, "bold")).pack(anchor="w")
    ttk.Label(outer, text="本次随机的 40 类兵种天赋；未采集的历史数据标为未采集，不代表无天赋。", foreground=colors["muted"]).pack(anchor="w", pady=(4, 12))
    query = tk.StringVar()
    special_only = tk.BooleanVar(value=False)
    high_only = tk.BooleanVar(value=False)
    filters = ttk.Frame(outer)
    filters.pack(fill='x', pady=(0, 12))
    SearchEntry(filters, textvariable=query, width=32,
        hint="即时搜索兵种或天赋；Esc 清空，Ctrl+A 全选").pack(side='left', fill='x', expand=True, padx=(0, 12))
    ttk.Checkbutton(filters, text='只看特殊技能', variable=special_only).pack(side='left')
    ttk.Checkbutton(filters, text='只看高阶兵种', variable=high_only).pack(side='left', padx=(10, 0))
    body = ttk.Frame(outer)
    body.pack(fill="both", expand=True)
    body.rowconfigure(0, weight=1)
    body.columnconfigure(0, weight=1)
    canvas = tk.Canvas(body, background=colors["page"], highlightthickness=0)
    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
    scrollbar.grid(row=0, column=1, sticky="ns")
    canvas.configure(yscrollcommand=scrollbar.set)
    title_font = font.Font(dialog, family="Microsoft YaHei UI", size=11, weight="bold")
    text_font = font.nametofont("TkDefaultFont", root=dialog)
    count = ttk.Label(outer, foreground=colors["muted"])
    count.pack(anchor="w", pady=(10, 0))
    # Prepare searchable text once; filtering never creates native child windows.
    cards = [(job["name"],
              "未采集（请查看新生成的结果）" if job["talents"] is None
              else "\n".join(job["talents"]) or "无兵种天赋",
              (job["name"] + " " + " ".join(job["talents"] or [])).casefold(),
              frozenset(normalize_skill_name(talent) for talent in job['talents'] or []))
             for job in jobs]
    pending = None
    last_layout = None
    cached_filters = None

    def rule_filters():
        nonlocal cached_filters
        if cached_filters is None:
            provider = getattr(parent._root(), '_current_rule_profile', None)
            selected = rule if rule is not None else provider() if callable(provider) else snapshot.get('rule')
            cached_filters = special_talent_names(selected), high_job_names(selected)
        return cached_filters

    def refresh():
        nonlocal pending, last_layout
        pending = None
        width = canvas.winfo_width()
        if width <= 1:
            width = 840  # Initial layout; Configure adapts to the mapped window.
        term = query.get().casefold().strip()
        special_names, high_names = rule_filters()
        layout = (width, term, special_only.get(), high_only.get(), special_names, high_names)
        if layout == last_layout:
            return
        if last_layout is None or layout[1:] != last_layout[1:]:
            canvas.yview_moveto(0)
        last_layout = layout
        visible = [card for card in cards if all(word in card[2] for word in term.split())
                   and (not special_only.get() or card[3] & special_names)
                   and (not high_only.get() or card[0] in high_names)]
        canvas.delete("all")
        columns = max(1, min(3, width // 250))
        card_width = (width - 12 * (columns + 1)) / columns
        y = 6
        for start in range(0, len(visible), columns):
            backgrounds, bottoms = [], []
            for column, (name, talents, *_metadata) in enumerate(visible[start:start + columns]):
                x = 12 + column * (card_width + 12)
                backgrounds.append(canvas.create_rectangle(x, y, x + card_width, y + 1,
                    fill=colors["surface"], outline="#D9DEE7"))
                title = canvas.create_text(x + 12, y + 10, anchor="nw", text=name,
                    font=title_font, fill=colors["ink"], width=card_width - 24)
                text = canvas.create_text(x + 12, canvas.bbox(title)[3] + 8, anchor="nw",
                    text=talents, font=text_font, fill=colors["ink"], width=card_width - 24)
                bottoms.append(canvas.bbox(text)[3] + 12)
            bottom = max(bottoms)
            for background in backgrounds:
                left, top, right, _ = canvas.coords(background)
                canvas.coords(background, left, top, right, bottom)
            y = bottom + 12
        if not visible:
            canvas.create_text(12, 12, anchor="nw", text="没有符合条件的兵种。",
                font=text_font, fill=colors["muted"])
            y = 48
        count.configure(text=f"显示 {len(visible)} / {len(jobs)} 个兵种")
        canvas.configure(scrollregion=(0, 0, width, y))

    def schedule(*_args):
        nonlocal pending
        if pending is None:
            pending = dialog.after_idle(refresh)

    def destroyed(event):
        nonlocal pending
        if event.widget is not dialog:
            return
        remove_rule_listener()
        if pending is not None:
            dialog.after_cancel(pending)
            pending = None

    canvas.bind("<Configure>", schedule)
    bind_window_event(dialog, "<Destroy>", destroyed)
    dialog.bind("<MouseWheel>", lambda event: canvas.yview_scroll(-int(event.delta / 120), "units"))
    query.trace_add("write", schedule)
    special_only.trace_add('write', schedule)
    high_only.trace_add('write', schedule)
    def rules_updated(*_args):
        nonlocal cached_filters
        cached_filters = None
        schedule()
    remove_rule_listener = bind_window_event(parent._root(), '<<RulesUpdated>>', rules_updated)
    schedule()
    show_centered(dialog)
