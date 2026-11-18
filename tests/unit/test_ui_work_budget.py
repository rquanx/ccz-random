"""Visible content survives batched layout and idle task delivery."""
import json
from pathlib import Path
import threading
import time
import tkinter as tk
import unittest

from ccz_randomizer.ui.tasks import WindowTasks
from ccz_randomizer.ui.viewport_rows import ViewportRows


class WorkBudgetTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('500x300')
        self.addCleanup(self.root.destroy)
        self.errors = []
        self.root.report_callback_exception = lambda *error: self.errors.append(error)
        self.root.update()

    def wait(self, condition):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.root.update()
            if condition():
                self.assertEqual([], self.errors)
                return
            time.sleep(.002)
        self.fail('UI did not finish its pending work')

    def test_viewport_scroll_resize_and_replace_display_only_current_rows(self):
        canvas = tk.Canvas(self.root)
        canvas.pack(fill='both', expand=True)
        content = tk.Frame(canvas)
        canvas.create_window(0, 0, window=content, anchor='nw', width=500)
        rendered = {}
        viewport = ViewportRows(canvas, content,
            lambda index, y, height: rendered.update({index: (y, height, canvas.winfo_width())}),
            lambda index: rendered.pop(index), columns=4)
        viewport.replace([100]*10, 40)
        self.wait(lambda: viewport.ready)
        self.assertEqual(viewport.visible_indices, set(rendered))
        self.assertLess(len(rendered), 40)
        canvas.yview_moveto(1)
        self.wait(lambda: viewport.ready and 39 in rendered)
        self.assertEqual(viewport.visible_indices, set(rendered))
        self.root.geometry('700x350')
        self.wait(lambda: viewport.ready and all(value[2] == canvas.winfo_width() for value in rendered.values()))
        viewport.replace([120], 3)
        self.wait(lambda: viewport.ready)
        self.assertEqual({0, 1, 2}, set(rendered))
        self.assertTrue(all(value[1] == 120 for value in rendered.values()))
        viewport.schedule()
        viewport.clear()
        self.root.update()
        self.assertEqual({}, rendered)
        self.assertIsNone(viewport.timer)

    def test_idle_tasks_stop_polling_and_restart_for_requests_and_channels(self):
        tasks = WindowTasks(self.root)
        self.addCleanup(tasks.close)
        self.assertIsNone(tasks.timer)
        values = []
        tasks.request('read', lambda: 3, values.append, self.fail)
        self.wait(lambda: values == [3] and tasks.timer is None)
        tasks.request('read', lambda: 4, values.append, self.fail)
        self.wait(lambda: values == [3, 4] and tasks.timer is None)
        writer = tasks.channel('stream', values.append)
        worker = threading.Thread(target=lambda: writer(5))
        worker.start()
        worker.join()
        self.wait(lambda: values == [3, 4, 5])
        self.assertIsNotNone(tasks.timer)
        tasks.invalidate('stream')
        self.assertIsNone(tasks.timer)
        writer(6)  # A superseded stream cannot deliver its old response.
        tasks.request('latest', lambda: 7, values.append, self.fail)
        self.wait(lambda: values == [3, 4, 5, 7] and tasks.timer is None)

    def test_recorded_member_measurements_fit_at_multiple_widths_and_reopen(self):
        from ccz_randomizer.history_members import history_members
        from ccz_randomizer.ui.history import COLORS, FONT, _score, _skill_names
        from ccz_randomizer.ui.member_card import MemberCard
        fixture = Path(__file__).resolve().parents[1]/'fixtures/personnel_220_1104/randomized-result.json'
        members = history_members(json.loads(fixture.read_text(encoding='utf-8')))
        self.assertGreater(len(members), 100)
        for width in (268, 210, 268):
            heights = MemberCard.row_heights(self.root, members, 4, width,
                font=FONT, score=_score, skill_names=_skill_names)
            card = MemberCard(self.root, members[0], colors=COLORS, font=FONT,
                              score=_score, skill_names=_skill_names)
            for index, member in enumerate(members):
                card.member = member
                card._width = None
                card._draw(width)
                self.assertLessEqual(int(card.cget('height')), heights[index//4] - 6)
                self.assertIn(str(member.get('name') or '未知'),
                              [card.itemcget(item, 'text') for item in card.find_all()
                               if card.type(item) == 'text'])
            card.destroy()
        self.assertLessEqual(len(self.root._ccz_member_measurements), 4096)

    def test_progress_burst_yields_to_input_without_losing_or_reordering_updates(self):
        tasks = WindowTasks(self.root)
        self.addCleanup(tasks.close)
        values, heartbeat = [], []
        def receive(value):
            values.append(value)
            if value == 0:
                self.root.after(0, lambda: heartbeat.append(len(values)))
        writer = tasks.channel('progress', receive)
        # Same integer progress channel used by background diagnostic actions.
        for value in range(300):
            writer(value)
        self.wait(lambda: len(values) == 300 and bool(heartbeat))
        self.assertEqual(list(range(300)), values)
        self.assertLess(heartbeat[0], 300)
        tasks.invalidate('progress')
        self.assertIsNone(tasks.timer)

    def test_detail_close_before_deferred_layout_cancels_all_owned_timers(self):
        from ccz_randomizer.ui.history import _show_detail
        fixture = Path(__file__).resolve().parents[1]/'fixtures/personnel_220_1104/randomized-result.json'
        _show_detail(self.root, json.loads(fixture.read_text(encoding='utf-8')))
        dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
        timers = set(dialog._ccz_owned_timers)
        self.assertTrue(timers)
        dialog.destroy()
        self.root.update()
        self.assertFalse(timers.intersection(self.root.tk.call('after', 'info')))
        self.assertEqual([], self.errors)
