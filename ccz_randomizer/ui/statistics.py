"""Independent asynchronous statistical dashboard with native canvas charts."""
import datetime as dt
import tkinter as tk
from tkinter import ttk

from ccz_randomizer.history_filters import parse_time_range
from ccz_randomizer.statistics_store import StatisticsRepository
from ccz_randomizer.ui.searchable_combo import SelectionCombobox
from ccz_randomizer.ui.statistics_charts import Chart, REASON_LABELS
from ccz_randomizer.ui.statistics_frequency import FrequencyChart
from ccz_randomizer.ui.tasks import WindowTasks
from ccz_randomizer.ui.tooltip import HoverTooltip
from ccz_randomizer.ui.theme import COLORS, FONT, setup_theme, style_dialog
from ccz_randomizer.ui.window_position import centered_toplevel, show_centered


def show_statistics_window(parent, base):
    existing = getattr(parent, "_statistics_window", None)
    if existing is not None and existing.winfo_exists():
        existing.lift()
        return existing
    setup_theme(parent)
    window = centered_toplevel(parent)
    parent._statistics_window = window
    window.title("数据统计")
    window.geometry("1180x820")
    window.minsize(980, 700)
    style_dialog(window)
    repository = StatisticsRepository(base)
    tasks = WindowTasks(window)
    filters = tk.Frame(window, bg=COLORS["page"])
    filters.pack(fill="x", padx=24, pady=(20, 12))
    for column, weight, minimum in ((1, 1, 90), (3, 1, 90), (5, 2, 135), (7, 1, 75)):
        filters.columnconfigure(column, weight=weight, minsize=minimum)
    start, end = tk.StringVar(), tk.StringVar()
    rule, person = tk.StringVar(value="全部规则"), tk.StringVar(value="全部人物")
    result = tk.StringVar(value="全部结果")
    result_filters = {"全部结果": "all", "只看合格": "qualified", "只看不合格": "rejected"}
    date_entries = []
    for column, label, var in ((0, "开始时间", start), (2, "结束时间", end)):
        tk.Label(filters, text=label, bg=COLORS["page"]).grid(row=0, column=column, padx=(0, 6))
        entry = ttk.Entry(filters, textvariable=var, width=18)
        entry.grid(row=0, column=column+1, sticky="ew", padx=(0, 12))
        HoverTooltip(entry, "日期格式：YYYY-MM-DD，可附加 HH:MM:SS")
        date_entries.append(entry)
    tk.Label(filters, text="规则", bg=COLORS["page"]).grid(row=0, column=4, padx=(0, 6))
    rule_combo = SelectionCombobox(filters, textvariable=rule, values=("全部规则",),
                                  state="readonly", width=22, search_label="搜索规则")
    rule_combo.grid(row=0, column=5, sticky="ew", padx=(0, 12))
    HoverTooltip(rule_combo, "按随机时使用的规则筛选")
    tk.Label(filters, text="人物", bg=COLORS["page"]).grid(row=0, column=6, padx=(0, 6))
    people_combo = SelectionCombobox(filters, textvariable=person, values=("全部人物",),
                                    state="readonly", width=10, search_label="搜索人物")
    people_combo.grid(row=0, column=7, sticky="ew", padx=(0, 12))
    HoverTooltip(people_combo, "兵种、特技按人物统计；总览与宝物按该人物参与的随机统计")
    tk.Label(filters, text="结果", bg=COLORS["page"]).grid(row=0, column=8, padx=(0, 6))
    result_combo = SelectionCombobox(filters, textvariable=result, values=tuple(result_filters),
                                    state="readonly", width=10, search_label="筛选结果")
    result_combo.grid(row=0, column=9, padx=(0, 12))
    HoverTooltip(result_combo, "合格以规则检查通过为准；不合格仅包含兵种和特技淘汰")
    status = tk.StringVar(value="正在读取统计…")
    tk.Label(window, textvariable=status, anchor="w", bg=COLORS["page"],
             fg=COLORS["muted"]).pack(fill="x", padx=24, pady=(0, 8))
    kpis = tk.Frame(window, bg=COLORS["page"])
    kpis.pack(fill="x", padx=24, pady=(0, 12))
    values = []
    for column, title in enumerate(("执行次数", "规则合格", "保存成功", "合格比例", "平均执行耗时")):
        kpis.columnconfigure(column, weight=1)
        card = tk.Frame(kpis, bg="white", padx=16, pady=10)
        card.grid(row=0, column=column, sticky="ew", padx=(0, 8))
        tk.Label(card, text=title, bg="white", fg=COLORS["muted"]).pack(anchor="w")
        var = tk.StringVar(value="—")
        values.append(var)
        tk.Label(card, textvariable=var, bg="white", fg=COLORS["ink"],
                 font=(FONT, 19, "bold")).pack(anchor="w")
    notebook = ttk.Notebook(window)
    notebook.pack(fill="both", expand=True, padx=24, pady=(0, 20))
    charts = {}
    for title, specs in (
        ("过程总览", (("statuses", "执行结果构成", "donut", ""),
                      ("trend", "每日执行趋势", "line", "上下分图使用独立刻度 · 悬停查看每日数量"),
                      ("reasons", "不合格原因 · 前 12 项", "bars", ""),
                      ("comparisons", "规则保存比例", "percent", ""))),
        ("分数与人物", (("job", "兵种分数分布", "histogram", ""),
                        ("skill", "特技分数分布", "histogram", ""),
                        ("jobs", "兵种频率", "bars", ""),
                        ("skills", "特技频率", "bars", ""))),
    ):
        page = tk.Frame(notebook, bg=COLORS["page"])
        notebook.add(page, text=title)
        for i, (key, label, kind, subtitle) in enumerate(specs):
            page.columnconfigure(i % 2, weight=1, uniform="chart")
            page.rowconfigure(i // 2, weight=1, uniform="chart")
            chart = (FrequencyChart(page, label) if key in ("jobs", "skills") else
                     Chart(page, label, kind, subtitle=subtitle,
                           label_aliases=REASON_LABELS if key == "reasons" else None))
            chart.grid(row=i//2, column=i%2, sticky="nsew", padx=5, pady=5)
            charts[key] = chart
    equipment_page = tk.Frame(notebook, bg=COLORS["page"])
    notebook.add(equipment_page, text="宝物效果")
    equipment_filters = tk.Frame(equipment_page, bg=COLORS["page"])
    equipment_filters.pack(fill="x", padx=8, pady=12)
    tk.Label(equipment_filters, text="宝物", bg=COLORS["page"]).pack(side="left", padx=(0, 8))
    equipment_name = tk.StringVar(value="全部宝物")
    equipment_combo = SelectionCombobox(equipment_filters, textvariable=equipment_name,
        values=("全部宝物",), state="readonly", width=26, search_label="搜索宝物")
    equipment_combo.pack(side="left")
    charts["equipment"] = FrequencyChart(equipment_page, "宝物效果频率")
    charts["equipment"].pack(fill="both", expand=True, padx=5, pady=(0, 5))
    rule_ids = {}

    def failed(error):
        status.set(f"筛选未更新，图表保留上次结果：{error}")

    def display(data):
        total, qualified, saved, jobs, skills, elapsed = data["totals"]
        rate = qualified / total if total else 0
        for variable, value in zip(values, (f"{total:,}", f"{qualified:,}", f"{saved:,}",
                                           f"{rate:.1%}" if total else "—",
                                           f"{elapsed/total:.2f} 秒" if total else "—")):
            variable.set(value)
        status.set((f"兵种 {jobs:,} 次 · 特技 {skills:,} 次"
                    if total else "暂无符合条件的数据") +
                   (f" · 注意：曾有 {data['lost']:,} 次采集缺失，统计不完整" if data["lost"] else ""))
        for key in ("statuses", "trend", "reasons", "jobs", "skills"):
            charts[key].set(data[key])
        charts["comparisons"].set([(name, 100*saved/count) for name, count, saved in data["comparisons"]])
        charts["equipment"].set(data["equipment"], f"{data['equipment_samples']:,} 次采集")
        for stage in ("job", "skill"):
            rows = data["histograms"][stage]
            count = sum(row[1] for row in rows)
            if rows and rows[-1][0] - rows[0][0] < 120:
                counts = dict(rows)
                rows = [(score, counts.get(score, 0)) for score in range(rows[0][0], rows[-1][0]+1)]
            charts[stage].set([(f"{score:g}–{score+1:g}", value) for score, value in rows],
                              f"{count:,} 人次")

    def refresh():
        try:
            after, before = parse_time_range(start.get(), end.get())
            options = dict(start=dt.datetime.fromisoformat(after).timestamp() if after else None,
                           end=dt.datetime.fromisoformat(before).timestamp() if before else None,
                           revision=rule_ids.get(rule.get()),
                           person=None if person.get() == "全部人物" else person.get(),
                           result=result_filters[result.get()],
                           equipment_name=None if equipment_name.get() == "全部宝物" else equipment_name.get())
        except (ValueError, OverflowError, OSError) as error:
            tasks.invalidate("query")
            failed(error)
            return
        status.set("正在汇总统计…")
        tasks.request("query", lambda: repository.query(**options), display, failed)

    def choices(data):
        selected_revision = rule_ids.get(rule.get())
        rule_ids.clear()
        rule_ids.update({name: revision for revision, name in data["rules"]})
        rule_combo.configure(values=("全部规则", *rule_ids))
        rule.set(next((name for name, revision in rule_ids.items() if revision == selected_revision), "全部规则"))
        people_combo.configure(values=("全部人物", *data["people"]))
        equipment_combo.configure(values=("全部宝物", *data["equipment"]))
        refresh()

    def reload_all():
        tasks.invalidate("query")
        tasks.request("choices", repository.choices, choices, failed)

    rule_update_binding = parent.bind("<<RulesUpdated>>", lambda _: reload_all(), add="+")
    from ccz_randomizer.ui.window_events import bind_window_event
    remove_storage_listener = bind_window_event(window._root(), "<<StorageCleaned>>", lambda _: reload_all()
        if "statistics" in getattr(window._root(), "_ccz_cleaned_categories", ()) else None)

    def cleanup(event):
        if event.widget is window:
            remove_storage_listener()
            parent.unbind("<<RulesUpdated>>", rule_update_binding)

    window.bind("<Destroy>", cleanup, add="+")

    ttk.Button(filters, text="刷新", command=reload_all).grid(row=0, column=10)
    for combo in (rule_combo, people_combo, result_combo, equipment_combo):
        combo.bind("<<ComboboxSelected>>", lambda _: refresh(), add="+")
    for entry in date_entries:
        entry.bind("<Return>", lambda _: refresh())
    reload_all()
    show_centered(window)
    return window
