from collections import Counter
from contextlib import ExitStack
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ccz_randomizer.ui.statistics_frequency import FrequencyChart
from tests.unit.test_statistics_equipment import equipment_fixture


class FrequencyChartTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.chart = FrequencyChart(self.root, "宝物效果频率")
        stack = self.enterContext(ExitStack())
        stack.enter_context(patch.object(self.chart, "winfo_width", return_value=500))
        stack.enter_context(patch.object(self.chart, "winfo_height", return_value=260))
        counts = Counter(effect for items, _ in equipment_fixture() for _, effect in items)
        self.rows = sorted(counts.items(), key=lambda row: (-row[1], row[0]))

    def test_all_positive_rows_are_accessible_without_drawing_whole_list(self):
        self.assertGreater(len(self.rows), 12)
        self.chart.set(self.rows)
        self.assertEqual(self.chart.rows, self.rows)
        self.assertLess(len(self.chart.find_withtag("bar-label")), 12)
        self.assertLess(self.chart.yview()[1], 1)
        self.chart.yview_moveto(1)
        self.assertEqual(self.chart.yview()[1], 1)
        self.assertIn(f"{self.rows[-1][0]}：{self.rows[-1][1]:,}", [value for _, value in self.chart.regions])
        self.assertLess(len(self.chart.find_all()), 40)
        # Scrolling leaves a shared item's relative bar length unchanged.
        before = [bounds[2]-bounds[0] for _, kind, bounds, _ in self.chart.graphics.commands if kind == "rectangle"]
        self.chart.yview_scroll(-1, "units")
        after = [bounds[2]-bounds[0] for _, kind, bounds, _ in self.chart.graphics.commands if kind == "rectangle"]
        self.assertEqual(before[0], after[1])

    def test_wheel_is_local_and_accumulates_small_deltas(self):
        other = FrequencyChart(self.root, "特技频率")
        self.chart.set(self.rows)
        initial = self.chart.yview()
        self.chart._wheel(SimpleNamespace(delta=-60))
        self.assertEqual(self.chart.yview(), initial)
        self.chart._wheel(SimpleNamespace(delta=-60))
        self.assertGreater(self.chart.yview()[0], initial[0])
        self.assertEqual(other.yview()[0], 0)
        self.chart.yview_moveto(0)
        self.assertEqual(self.chart.yview()[0], 0)

    def test_search_and_refresh_reset_scroll_and_exclude_zero_counts(self):
        self.chart.set([*self.rows[1:], (self.rows[0][0], 0)])
        self.assertEqual(len(self.chart.rows), len(self.rows)-1)
        self.chart.yview_moveto(1)
        target = self.rows[-1][0]
        self.chart.search_entry.insert(0, target)
        self.assertEqual(self.chart.yview()[0], 0)
        self.assertTrue(all(target in name for name, _ in self.chart.rows))
        self.chart.search_entry.delete(0, "end")
        self.chart.set(self.rows[:1])
        self.assertEqual(self.chart.rows, self.rows[:1])
        self.assertEqual(self.chart.yview(), (0, 1))
        self.chart.set([])
        self.assertFalse(self.chart.find_withtag("bar-label"))
        self.assertEqual(self.chart.regions, [])
