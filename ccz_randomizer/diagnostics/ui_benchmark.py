"""Opt-in packaged UI measurements; the launcher supplies an isolated data copy.

Exercise real Tk commands and asynchronous delivery without desktop input. The
launcher owns a private Windows desktop; normal application startup is unchanged.
"""
import json
from pathlib import Path
import sys
import time
import traceback
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class Measurements:
    def __init__(self, root):
        self.root = root
        self.samples = []
        self.errors = []
        self.root.report_callback_exception = self.callback_error

    def callback_error(self, *error):
        self.errors.append("".join(traceback.format_exception(*error)))

    def wait(self, condition, timeout=20):
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            self.root.update()
            if self.errors:
                raise RuntimeError(self.errors[-1])
            if condition():
                return
            time.sleep(.001)
        raise TimeoutError("UI did not reach its expected visible state")

    def measure(self, name, action, ready=lambda: True):
        from ccz_randomizer.ui.render_state import content_ready
        gaps = []
        started = last = time.perf_counter()
        timer = None

        def beat():
            nonlocal last, timer
            now = time.perf_counter()
            gaps.append((now-last)*1000)
            last = now
            timer = self.root.after(8, beat)

        timer = self.root.after(8, beat)
        try:
            action()
            returned = time.perf_counter()
            self.wait(lambda: ready() and content_ready(self.root))
            ready_at = time.perf_counter()
            # Include delayed Configure/draw callbacks in the responsiveness sample.
            self.wait(lambda: time.perf_counter()-ready_at >= .12)
            self.samples.append(dict(name=name, command_ms=(returned-started)*1000,
                ready_ms=(ready_at-started)*1000, within_300ms=(ready_at-started) <= .3,
                max_heartbeat_gap_ms=max(gaps, default=0)))
        finally:
            self.root.after_cancel(timer)

    def button(self, parent, text):
        return next(w for w in descendants(parent)
                    if isinstance(w, ttk.Button) and w.cget("text") == text)

    def window(self, title):
        return next(w for w in descendants(self.root)
                    if isinstance(w, tk.Toplevel) and w.title() == title)

    def texts(self, parent):
        return [str(w.cget("text")) for w in descendants(parent)
                if isinstance(w, (tk.Label, ttk.Label)) and w.winfo_manager()]

    def select(self, combo, value):
        combo.set(value)
        combo.event_generate("<<ComboboxSelected>>")


def exercise(root, base, results, actions=None):
    from ccz_randomizer.ui.statistics_charts import Chart
    from ccz_randomizer.ui.searchable_combo import SelectionCombobox
    from ccz_randomizer.ui.history_cards import SummaryCard
    from ccz_randomizer.ui.history_rounds import RoundCard
    from ccz_randomizer.statistics_store import StatisticsRepository
    from ccz_randomizer.history import HistoryRepository
    from ccz_randomizer.equipment_labels import merge_equipment_frequencies
    from ccz_randomizer.ui.member_pages import MemberPages

    run = Measurements(root)
    results["samples"] = run.samples
    results["callback_errors"] = run.errors

    def stats_ready():
        return any(text.startswith(("兵种 ", "暂无符合")) for text in run.texts(run.window("数据统计")))

    run.measure("statistics.open.first", lambda: run.button(root, "数据统计").invoke(), stats_ready)
    statistics = run.window("数据统计")
    notebook = next(w for w in descendants(statistics) if isinstance(w, ttk.Notebook))
    charts = [w for w in descendants(statistics) if isinstance(w, Chart)]
    equipment = next(w for w in charts if w.title.startswith("宝物效果"))
    skills = next(w for w in charts if w.title.startswith("特技频率"))
    # Query expected values only after the cold first opening has been measured.
    repository = StatisticsRepository(base)
    expected = repository.query()
    expected['equipment'] = merge_equipment_frequencies(expected['equipment'])
    rule_picker = next(w for w in descendants(statistics)
                       if isinstance(w, SelectionCombobox) and w.get() == "全部规则")
    popdown = rule_picker.tk.call("ttk::combobox::PopdownWindow", str(rule_picker))
    run.measure("statistics.native_dropdown.open",
                lambda: rule_picker.tk.call("ttk::combobox::Post", str(rule_picker)),
                lambda: bool(root.tk.call("winfo", "ismapped", popdown)))
    run.measure("statistics.native_dropdown.close",
                lambda: rule_picker.tk.call("ttk::combobox::Unpost", str(rule_picker)))
    searchable = next((w for w in descendants(statistics) if isinstance(w, SelectionCombobox)
                       and len(w.cget("values")) > w.search_threshold), None)
    if searchable:
        run.measure("statistics.search_dropdown.open", searchable.open_popup,
                    lambda: searchable.popup is not None and searchable.popup.winfo_ismapped())
        run.measure("statistics.search_dropdown.close", searchable.close_popup)
    run.measure("statistics.members.first", lambda: notebook.select(1),
                lambda: skills.rows == expected["skills"])
    if len(skills.rows) > 6:
        run.measure("statistics.skills.scroll", lambda: skills.yview_scroll(9, "units"),
                    lambda: skills._offset > 0)
    run.measure("statistics.equipment.first", lambda: notebook.select(2),
                lambda: equipment.rows == expected["equipment"])
    merge_check = next(w for w in descendants(statistics) if isinstance(w, ttk.Checkbutton)
                       and w.cget('text') == '合并同类特效')
    raw_equipment = repository.query(view='equipment')['equipment']
    run.measure('statistics.equipment.unmerge', merge_check.invoke,
                lambda: equipment.rows == raw_equipment)
    run.measure('statistics.equipment.merge', merge_check.invoke,
                lambda: equipment.rows == expected['equipment'])
    if len(equipment.rows) > 6:
        run.measure("statistics.equipment.scroll", lambda: equipment.yview_scroll(9, "units"),
                    lambda: equipment._offset > 0)
    picker = next(w for w in descendants(statistics)
                  if isinstance(w, SelectionCombobox) and w.get() == "全部结果")
    qualified = repository.query(result="qualified")
    qualified['equipment'] = merge_equipment_frequencies(qualified['equipment'])
    run.measure("statistics.filter.qualified", lambda: run.select(picker, "只看合格"),
                lambda: stats_ready() and equipment.rows == qualified["equipment"])
    run.measure("statistics.overview.cached", lambda: notebook.select(0), stats_ready)
    run.measure("statistics.equipment.cached", lambda: notebook.select(2), stats_ready)
    results["statistics"] = dict(attempts=expected["totals"][0],
        equipment_items=len(expected["equipment"]), skill_items=len(expected["skills"]))
    statistics.tk.call(statistics.protocol('WM_DELETE_WINDOW'))
    run.measure('statistics.open.cached', lambda: run.button(root, '数据统计').invoke(), stats_ready)
    statistics.destroy()
    for index in range(2):
        run.measure(f"statistics.open.repeat{index+1}",
                    lambda: run.button(root, "数据统计").invoke(), stats_ready)
        run.window("数据统计").destroy()

    # Repository is initialized after the first history click, on its real worker.
    def history_ready():
        window = run.window("历史记录")
        widgets = list(descendants(window))
        if hasattr(window, "_result_viewport") and not window._result_viewport.ready:
            return False
        tree = next(w for w in widgets if isinstance(w, ttk.Treeview))
        if len([w for w in widgets if isinstance(w, RoundCard) and w.winfo_manager()]) != len(tree.get_children()):
            return False
        return any(isinstance(w, RoundCard) and w.row for w in widgets) and not any(
            text.startswith("正在读取") for text in run.texts(window))

    run.measure("history.open.first", lambda: run.button(root, "历史记录").invoke(), history_ready)
    history = run.window("历史记录")
    tree = next(w for w in descendants(history) if isinstance(w, ttk.Treeview))
    history_repository = HistoryRepository(base)
    results["history_rounds"] = history_repository.count_rounds()

    def wait_cards():
        selected = tree.selection()
        if not selected:
            return False
        row = next((w.row for w in descendants(history)
                    if isinstance(w, RoundCard) and w.row and w._selected), None)
        if row is None:
            return False
        viewport = getattr(history, "_result_viewport", None)
        expected_count = row.get("result_count", 0)
        if viewport is not None:
            return viewport.count == expected_count and viewport.ready
        return len([w for w in descendants(history) if isinstance(w, SummaryCard)
                    and w.winfo_manager() and w.snapshot]) == expected_count

    run.measure("history.cards.first", lambda: None, wait_cards)
    viewport = getattr(history, "_result_viewport", None)
    if viewport is not None and viewport.count:
        def visible_slot(slot):
            return viewport.ready and any(isinstance(w, SummaryCard) and w.winfo_manager()
                                          and w.snapshot.get("slot") == slot for w in descendants(history))
        row = next(w.row for w in descendants(history) if isinstance(w, RoundCard) and w._selected)
        snapshots = history_repository.get_round_summaries(int(row["id"]))
        run.measure("history.scroll.end", lambda: viewport.canvas.yview_moveto(1),
                    lambda: visible_slot(snapshots[-1]["slot"]))
        run.measure("history.scroll.start", lambda: viewport.canvas.yview_moveto(0),
                    lambda: visible_slot(snapshots[0]["slot"]))
    next_page = run.button(history, "下一页")
    if not next_page.instate(("disabled",)):
        old_ids = tuple(tree.get_children())
        run.measure("history.page.next", next_page.invoke,
                    lambda: tuple(tree.get_children()) != old_ids and history_ready() and wait_cards())
        run.measure("history.page.previous", run.button(history, "上一页").invoke,
                    lambda: run.button(history, "上一页").instate(("disabled",)) and history_ready() and wait_cards())
    history_rule = next(w for w in descendants(history) if isinstance(w, ttk.Combobox))
    names = history_rule.cget("values")
    if len(names) > 1:
        run.measure("history.filter.rule", lambda: run.select(history_rule, names[1]),
                    lambda: history_ready() and wait_cards() and all(
                        tree.item(item, "values")[2] == names[1] for item in tree.get_children()))
        run.measure("history.filter.reset", run.button(history, "重置筛选").invoke,
                    lambda: history_ready() and wait_cards() and history_rule.current() == 0)
    summary = next((w for w in descendants(history) if isinstance(w, SummaryCard) and w.snapshot and w.winfo_manager()), None)
    if summary:
        before = {w for w in descendants(root) if isinstance(w, tk.Toplevel)}
        run.measure("history.detail.open", lambda: summary.detail.invoke(),
                    lambda: any(getattr(w, '_member_viewport', None) is None or w._member_viewport.ready
                                for w in {w for w in descendants(root) if isinstance(w, tk.Toplevel)}-before))
        for window in {w for w in descendants(root) if isinstance(w, tk.Toplevel)}-before:
            window.destroy()
    history.tk.call(history.protocol("WM_DELETE_WINDOW"))
    run.measure("history.open.cached", lambda: run.button(root, "历史记录").invoke(), history_ready)
    history.destroy()
    run.measure("history.open.repeat", lambda: run.button(root, "历史记录").invoke(), history_ready)
    run.window("历史记录").destroy()

    run.measure("rules.open.first", lambda: run.button(root, "规则设置").invoke())
    editor = run.window("规则设置")
    pages = [w for w in descendants(editor) if isinstance(w, ttk.Notebook)]
    for index in range(len(pages[0].tabs()) if pages else 0):
        run.measure(f"rules.tab.{index}", lambda index=index: pages[0].select(index))
    if len(pages) > 1:
        for index in range(len(pages[1].tabs())):
            run.measure(f"rules.advanced.tab.{index}", lambda index=index: pages[1].select(index))
    members = [w for w in descendants(editor) if isinstance(w, MemberPages)]
    if members and not members[0].next.instate(("disabled",)):
        run.measure("rules.members.next", members[0].next.invoke)
        run.measure("rules.members.previous", members[0].previous.invoke)
    editor.tk.call(editor.protocol("WM_DELETE_WINDOW"))
    run.measure("rules.open.repeat", lambda: run.button(root, "规则设置").invoke())
    run.window("规则设置").destroy()

    run.measure("effects.open.first", lambda: run.button(root, "特效手册").invoke())
    effects = run.window("特效手册")
    table = next(w for w in descendants(effects) if isinstance(w, ttk.Treeview))
    count = len(table.get_children())
    if count > 1:
        target = table.get_children()[-1]
        run.measure("effects.select.last", lambda: table.selection_set(target))
        from ccz_randomizer.ui.inputs import SearchEntry
        search = next(w for w in descendants(effects) if isinstance(w, SearchEntry))
        term = table.item(target, "text")
        run.measure("effects.search", lambda: search.insert(0, term),
                    lambda: 0 < len(table.get_children()) < count)
    results["effect_items"] = count
    effects.destroy()
    run.measure("effects.open.repeat", lambda: run.button(root, "特效手册").invoke())
    run.window("特效手册").destroy()

    run.measure("support.open", lambda: run.button(root, "常见问题").invoke())
    support = run.window("常见问题")
    run.measure("guide.open.first", lambda: run.button(support, "不会用？").invoke())
    guide = next(w for w in descendants(root) if isinstance(w, tk.Toplevel)
                 and w not in (support,) and w.title() != root.title())
    book = next(w for w in descendants(guide) if isinstance(w, ttk.Notebook))
    for index in range(len(book.tabs())):
        run.measure(f"guide.tab.{index}", lambda index=index: book.select(index))
    guide.destroy()
    run.measure("cleanup.open.scan", lambda: run.button(support, "空间清理").invoke(),
                lambda: any(text.startswith("统计完成") for text in run.texts(run.window("空间清理"))))
    run.window("空间清理").destroy()
    support.destroy()

    from ccz_randomizer.ui import messages
    def close_question():
        question = run.window("后台性能测试")
        results["confirmation_mapped"] = bool(question.winfo_ismapped())
        run.button(question, "取消").invoke()
    def question():
        # wait_window runs a nested Tk loop; dismiss through its actual cancel button.
        root.after(80, close_question)
        answer = messages.askyesno("后台性能测试", "仅验证弹窗布局和取消操作。", parent=root)
        if answer is not False:
            raise AssertionError("Cancel did not return False")
    run.measure("confirmation.open.cancel", question)

    from ccz_randomizer.diagnostics.dialog_benchmark import exercise_dialogs
    exercise_dialogs(run, base, results, actions)


def run_request(request_path):
    from ccz_randomizer import app
    from ccz_randomizer.profile_session import ProfileUpdateSession

    request = json.loads(Path(request_path).read_text(encoding="utf-8"))
    base, output = Path(request["base"]), Path(request["output"])
    results = dict(frozen=bool(getattr(sys, "frozen", False)), executable=sys.executable,
                   desktop=request.get("desktop"), status="failed")
    mainloop = tk.Tk.mainloop

    def measured_loop(root, *args, **kwargs):
        actions = sys._getframe(1).f_locals
        if request.get('trace_tk'):
            from ccz_randomizer.diagnostics.tk_timing import TkTiming
            timer = TkTiming(root.tk)
            for widget in (root, *descendants(root)):
                widget.tk = timer
            results['tk_timings'] = timer.timings
        def run():
            try:
                exercise(root, base, results, actions)
                results['performance'] = dict(budget_ms=300,
                    operation_count=len(results['samples']),
                    within_budget_count=sum(s['within_300ms'] for s in results['samples']),
                    basis='action to content ready after Tk event/paint processing; excludes DWM presentation',
                    status='passed' if all(s['within_300ms'] for s in results['samples']) else 'over_budget',
                    over_budget=[s['name'] for s in results['samples'] if not s['within_300ms']])
                results["status"] = "passed"
            except Exception:
                results["error"] = traceback.format_exc()
            finally:
                root.after(0, root.destroy)
        root.after(300, run)
        return mainloop(root, *args, **kwargs)

    try:
        with patch.object(app, "app_dir", return_value=base), \
                patch.object(app, "first_use_notice_acknowledged", return_value=True), \
                patch.object(app, "locate_game_executable", side_effect=FileNotFoundError), \
                patch.object(ProfileUpdateSession, "start"), \
                patch.object(tk.Tk, "mainloop", measured_loop):
            app.gui_main()
    except Exception:
        results["error"] = traceback.format_exc()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if results["status"] == "passed" else 1
