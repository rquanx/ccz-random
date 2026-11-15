"""Hidden Tk integration: chart rendering, asynchronous filters and close cleanup."""
from tkinter import ttk
import tempfile
import time
import tkinter as tk
from pathlib import Path
import unittest
from unittest.mock import patch

from ccz_randomizer.statistics import StatisticsRecorder
from ccz_randomizer.ui.statistics import show_statistics_window
from ccz_randomizer.ui.statistics_charts import Chart
from ccz_randomizer.ui.searchable_combo import SelectionCombobox
from ccz_randomizer.ui.inputs import SearchEntry
from ccz_randomizer.ui.statistics_ranking import show_ranking_window
from ccz_randomizer.statistics_store import StatisticsRepository
from ccz_randomizer.statistics_equipment import capture_equipment_statistics
from tests.unit.test_statistics_equipment import equipment_fixture
from tests.unit.test_statistics import runner_fixture


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class StatisticsUiTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.errors = []
        self.root.report_callback_exception = lambda *error: self.errors.append(error)

    def tearDown(self):
        self.root.destroy()
        self.tmp.cleanup()
        self.assertEqual([], self.errors)

    def wait_until(self, condition):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.root.update()
            if condition():
                return
            time.sleep(0.01)
        self.fail("统计窗口未在期限内加载")

    def test_filtering_and_close_during_reload(self):
        recorder = StatisticsRecorder(self.base, run_id="ui", rule_name="规则", rule={}, mode="three")
        with recorder.attempt(runner_fixture(), round_number=1, slot=1, attempt=1) as result:
            result["saved"] = True
        with recorder.attempt(runner_fixture(reject=True), round_number=1, slot=1, attempt=2):
            pass
        recorder.close()
        # Never map this test window or steal focus from the user's desktop.
        with patch("ccz_randomizer.ui.statistics.show_centered"):
            window = show_statistics_window(self.root, self.base)
        charts = [item for item in descendants(window) if isinstance(item, Chart)]
        people = next(item for item in descendants(window) if isinstance(item, SelectionCombobox)
                      and item.get() == "全部人物")
        skills = next(chart for chart in charts if chart.title.startswith("特技频率"))
        self.wait_until(lambda: bool(skills.rows))
        self.assertEqual([("能力辅助 防→攻精", 1)], skills.rows)
        people.set("曹操")
        people.event_generate("<<ComboboxSelected>>")
        self.wait_until(lambda: not skills.rows)
        jobs = next(chart for chart in charts if chart.title.startswith("兵种频率"))
        self.assertEqual([("群雄", 2)], jobs.rows)
        result_combo = next(item for item in descendants(window) if isinstance(item, SelectionCombobox)
                            and item.get() == "全部结果")
        result_combo.set("只看合格")
        result_combo.event_generate("<<ComboboxSelected>>")
        self.wait_until(lambda: jobs.rows == [("群雄", 1)])
        statuses = next(chart for chart in charts if chart.kind == "donut")
        self.assertEqual([("saved", 1)], statuses.rows)
        result_combo.set("只看不合格")
        result_combo.event_generate("<<ComboboxSelected>>")
        self.wait_until(lambda: statuses.rows == [("job_failed", 1)])
        people.set("全部人物")
        people.event_generate("<<ComboboxSelected>>")
        window.destroy()
        self.root.update()

    def test_all_chart_forms_render_with_bounded_items_and_small_dimensions(self):
        for kind in ("donut", "bars", "percent", "histogram", "line"):
            chart = Chart(self.root, "测试图表", kind)
            rows = ([(f"2026-11-{i:02}", i+1, i//2) for i in range(500)] if kind == "line"
                    else [(str(i), i+1) for i in range(7)])
            with patch.object(chart, "winfo_width", return_value=400), patch.object(chart, "winfo_height", return_value=240):
                chart.set(rows)
            self.assertGreater(len(chart.find_all()), 5)
            self.assertLess(len(chart.find_all()), 300)
            chart.destroy()

    def test_trend_keeps_small_saved_counts_visible_and_reports_exact_values(self):
        from types import SimpleNamespace
        chart = Chart(self.root, "每日执行趋势", "line")
        # Same (day, execution count, saved count) rows returned by the repository.
        with patch.object(chart, "winfo_width", return_value=500), patch.object(chart, "winfo_height", return_value=280):
            chart.set([("2026-11-13", 1, 0), ("2026-11-15", 3825, 5)])
            dots = [bounds for _, kind, bounds, _ in chart.graphics.commands if kind == "oval"]
            self.assertEqual(len(dots), 4)
            # Five saves must span the lower panel, rather than a fraction of a pixel.
            self.assertGreater(abs(dots[2][1]-dots[3][1]), 30)
            totals = [chart.itemcget(item, "text") for item in chart.find_withtag("trend-total")]
            self.assertEqual(totals, ["合计 3,826 次", "合计 5 次"])
            region, _ = chart.regions[-1]
            left, top, right, bottom = region.bounds
            chart._motion(SimpleNamespace(x=(left+right)/2, y=(top+bottom)/2))
            self.assertEqual(chart._hovered, "2026-11-15：执行 3,825 / 保存 5")
            self.assertFalse(chart.find_withtag("trend-zero"))
        chart.destroy()

    def test_trend_distinguishes_zero_saved_counts_and_supports_a_single_day(self):
        chart = Chart(self.root, "每日执行趋势", "line")
        with patch.object(chart, "winfo_width", return_value=400), patch.object(chart, "winfo_height", return_value=240):
            chart.set([("2026-11-15", 3825, 0)])
            zeros = [chart.itemcget(item, "text") for item in chart.find_withtag("trend-zero")]
            self.assertEqual(zeros, ["该时段为 0 次"])
            self.assertEqual([chart.itemcget(item, "text") for item in chart.find_withtag("trend-total")],
                             ["合计 3,825 次", "合计 0 次"])
            self.assertEqual(len(chart.regions), 2)
        chart.destroy()

    def test_reason_labels_are_short_and_hover_retains_full_explanation(self):
        from types import SimpleNamespace
        from ccz_randomizer.ui.statistics_charts import REASON_LABELS
        self.root.tk.call("tk", "scaling", 1.333)
        chart = Chart(self.root, "不合格原因", "bars", label_aliases=REASON_LABELS)
        rows = [("兵种综合评价未达到当前规则要求", 3494), ("特技综合评价未达到当前规则要求", 246)]
        with patch.object(chart, "winfo_width", return_value=600), patch.object(chart, "winfo_height", return_value=260):
            chart.set(rows)
            labels = chart.find_withtag("bar-label")
            self.assertEqual([chart.itemcget(item, "text") for item in labels], ["兵种评价未达标", "特技评价未达标"])
            x1, y1, x2, y2 = chart.bbox(labels[0])
            chart._motion(SimpleNamespace(x=(x1+x2)/2, y=(y1+y2)/2))
            hover_text = [chart.itemcget(item, "text") for item in chart.find_withtag("hover") if chart.type(item) == "text"]
            self.assertEqual(hover_text, ["兵种综合评价未达到当前规则要求：3,494"])
            self.assertEqual(chart.rows, rows)
        chart.destroy()

    def test_bar_labels_fit_before_bars_at_different_widths_and_display_scaling(self):
        for scaling in (1.333, 2.667):
            self.root.tk.call("tk", "scaling", scaling)
            for width in (300, 600):
                with self.subTest(scaling=scaling, width=width):
                    chart = Chart(self.root, "兵种频率", "bars")
                    with patch.object(chart, "winfo_width", return_value=width), patch.object(chart, "winfo_height", return_value=260):
                        chart.set([("长名称兵种与额外描述用于验证显示区域不会覆盖统计条形", 3494)])
                        bounds = chart.bbox(chart.find_withtag("bar-label")[0])
                        self.assertLess(bounds[2], min(160, width*.38))
                    chart.destroy()

    def test_raster_chart_preserves_hover_and_reuses_unchanged_render(self):
        from types import SimpleNamespace
        chart = Chart(self.root, "兵种频率", "bars")
        with patch.object(chart, "winfo_width", return_value=400), patch.object(chart, "winfo_height", return_value=240):
            chart.set([("群雄", 10)])
            photo = chart._photo
            chart.draw()
            self.assertIs(photo, chart._photo)
            chart._motion(SimpleNamespace(x=200, y=90))
            self.assertTrue(chart.find_withtag("hover"))
            chart._motion(SimpleNamespace(x=5, y=5))
            self.assertFalse(chart.find_withtag("hover"))
            chart._schedule_draw(None)
            chart._schedule_draw(None)
            timer = chart._redraw_timer
            chart.destroy()
            self.assertNotIn(timer, self.root.tk.call("after", "info"))

    def test_equipment_scroll_list_preserves_result_filters_without_expand(self):
        recorder = StatisticsRecorder(self.base, run_id="ui", rule_name="规则", rule={}, mode="three")
        for rejected in (False, True):
            runner = runner_fixture(reject=rejected)
            capture_equipment_statistics(runner, equipment_fixture, self.fail)
            with recorder.attempt(runner, round_number=1, slot=1, attempt=1) as result:
                result["saved"] = not rejected
        recorder.close()
        with patch("ccz_randomizer.ui.statistics.show_centered"):
            window = show_statistics_window(self.root, self.base)
        chart = next(widget for widget in descendants(window)
                     if isinstance(widget, Chart) and widget.title.startswith("宝物效果"))
        self.wait_until(lambda: bool(chart.rows))
        self.assertEqual(chart.rows, StatisticsRepository(self.base).query()["equipment"])
        self.assertGreater(len(chart.rows), 12)
        item, effect = equipment_fixture()[0][0][0]
        picker = next(widget for widget in descendants(window)
                      if isinstance(widget, SelectionCombobox) and widget.get() == "全部宝物")
        picker.set(item)
        picker.event_generate("<<ComboboxSelected>>")
        self.wait_until(lambda: chart.rows == [(effect, 2)])
        result_picker = next(widget for widget in descendants(window)
                            if isinstance(widget, SelectionCombobox) and widget.get() == "全部结果")
        result_picker.set("只看不合格")
        result_picker.event_generate("<<ComboboxSelected>>")
        self.wait_until(lambda: chart.rows == [(effect, 1)])
        self.assertIsNone(chart._expand_button)
        self.assertFalse(any(isinstance(widget, ttk.Button) and widget.cget("text") == "查看全部"
                             for widget in descendants(window)))
        window.destroy()

    def test_full_ranking_search_pagination_and_close_with_pending_search(self):
        recorder = StatisticsRecorder(self.base, run_id="ui", rule_name="规则", rule={}, mode="three")
        runner = runner_fixture(reject=True)
        capture_equipment_statistics(runner, equipment_fixture, self.fail)
        with recorder.attempt(runner, round_number=1, slot=1, attempt=1):
            pass
        recorder.close()
        repo = StatisticsRepository(self.base)
        expected = repo.ranking("equipment", page_size=200)["rows"]
        self.assertGreater(len(expected), 50)
        with patch("ccz_randomizer.ui.statistics_ranking.show_centered"):
            window = show_ranking_window(self.root, repo, "equipment", {})
        tree = next(widget for widget in descendants(window) if isinstance(widget, ttk.Treeview))
        self.wait_until(lambda: len(tree.get_children()) == 50)
        following = next(widget for widget in descendants(window)
                         if isinstance(widget, ttk.Button) and widget.cget("text") == "下一页")
        following.invoke()
        self.wait_until(lambda: len(tree.get_children()) == len(expected)-50)
        self.assertEqual(expected[50][0], tree.item(tree.get_children()[0], "values")[0])
        entry = next(widget for widget in descendants(window) if isinstance(widget, SearchEntry))
        entry.insert(0, expected[-1][0])
        self.wait_until(lambda: all(expected[-1][0] in tree.item(row, "values")[0]
                                   for row in tree.get_children()))
        entry.delete(0, "end")
        entry.insert(0, "关闭前的搜索")
        window.destroy()
        self.root.update()
