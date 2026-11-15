import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch
import io
from contextlib import redirect_stdout

from ccz_randomizer.app import result_detail_for_runner, build_history_result_snapshot, collect_accepted_equipment_and_publish
from ccz_randomizer.ui.result_details import show_score_detail, encode_result_detail, decode_result_detail
from ccz_randomizer.ui.equipment import show_equipment_window
from ccz_randomizer.search_history import SearchHistory
from ccz_randomizer.ui.recent_searches import RecentSearchesBar


FIXTURE = Path(__file__).resolve().parents[1] / 'fixtures/personnel_22/randomized-equipment.json'


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class EquipmentTests(unittest.TestCase):
    def setUp(self):
        self.equipment = json.loads(FIXTURE.read_text(encoding='utf-8'))
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.history_path = Path(directory.name) / 'equipment_searches.json'
        mocked_path = patch('ccz_randomizer.ui.equipment.default_search_history_path', return_value=self.history_path)
        mocked_path.start()
        self.addCleanup(mocked_path.stop)

    def test_live_transport_and_history_preserve_same_equipment(self):
        runner = SimpleNamespace(_result_outcome='accepted', _three_person_mode=True,
            _equip_info=[([(i['name'], i['effect']) for i in c['items']], c['name'])
                         for c in self.equipment['categories']],
            _equip_specials=[(s['title'], s['items']) for s in self.equipment['specials']])
        detail = decode_result_detail(encode_result_detail(result_detail_for_runner(runner, 1, 1)))
        self.assertEqual(self.equipment, detail['equipment'])
        with tempfile.TemporaryDirectory() as directory:
            history = build_history_result_snapshot(runner, result_slot=1, accepted_attempt=1,
                round_number=1, equip_info=None, save_path=Path(directory) / 'missing.E5S')
        self.assertEqual(self.equipment, history['equipment'])
        runner._equip_info = None
        runner._equip_specials = ()
        runner._result_outcome = 'job_failed'
        self.assertIsNone(result_detail_for_runner(runner, 1, 2)['equipment'])
        self.assertEqual(self.equipment, detail['equipment'])

    def test_accepted_detail_is_published_after_equipment_collection(self):
        runner = SimpleNamespace(_result_outcome='accepted', _three_person_mode=True,
                                 _equip_info=None, _equip_specials=())
        def collect():
            runner._equip_info = [([(item['name'], item['effect']) for item in category['items']], category['name'])
                                  for category in self.equipment['categories']]
            runner._equip_specials = [(s['title'], s['items']) for s in self.equipment['specials']]
            return runner._equip_info
        runner.collect_equipment = collect
        output = io.StringIO()
        with redirect_stdout(output):
            equipment = collect_accepted_equipment_and_publish(runner, 3, 2)
        lines = output.getvalue().splitlines()
        self.assertEqual(1, len(lines))
        detail = decode_result_detail(lines[0])
        self.assertEqual(self.equipment, detail['equipment'])
        self.assertEqual(70, sum(len(c['items']) for c in detail['equipment']['categories']))
        with tempfile.TemporaryDirectory() as folder:
            history = build_history_result_snapshot(runner, result_slot=3, accepted_attempt=2,
                round_number=1, equip_info=equipment, save_path=Path(folder) / 'SV003.E5S')
        self.assertEqual(history['equipment'], detail['equipment'])

    def make_root(self):
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        return root

    def settle(self, root):
        root.update()
        done = tk.BooleanVar(root)
        root.after(180, lambda: done.set(True))
        root.wait_variable(done)
        root.update()

    def texts(self, canvas):
        return [w.cget('text') for w in descendants(canvas) if isinstance(w, tk.Label)]

    def test_score_button_displays_equipment_and_filters(self):
        root = self.make_root()
        show_score_detail(root, dict(label='合格', mode='three', equipment=self.equipment))
        button = next(w for w in descendants(root) if isinstance(w, ttk.Button) and w.cget('text') == '宝物信息')
        button.invoke()
        self.settle(root)
        dialog = next(w for w in descendants(root) if isinstance(w, tk.Toplevel) and w.title() == '宝物信息')
        canvas = next(w for w in descendants(dialog) if isinstance(w, tk.Canvas))
        texts = self.texts(canvas)
        headings = {w.cget('text'): w for w in descendants(canvas) if isinstance(w, tk.Label)
                    and w.cget('text') in ('宝物特殊组合', '宝物列表')}
        self.assertLess(headings['宝物特殊组合'].winfo_rootx(), headings['宝物列表'].winfo_rootx())
        self.assertEqual(headings['宝物特殊组合'].winfo_rooty(), headings['宝物列表'].winfo_rooty())
        for category in self.equipment['categories']:
            for item in category['items']:
                self.assertIn(f"{item['name']}  {item['effect']}",
                              [line for text in texts for line in text.splitlines()])
                if item['effect']:
                    self.assertTrue(any(item['effect'] in text for text in texts))
        for special in self.equipment['specials']:
            self.assertIn(special['title'], texts)
        search = next(w for w in descendants(dialog) if isinstance(w, ttk.Entry))
        name = self.equipment['categories'][0]['items'][0]['name']
        search.insert(0, name)
        self.settle(root)
        self.assertTrue(any(name in text for text in self.texts(canvas)))
        self.assertFalse(any(self.equipment['categories'][0]['items'][1]['name'] in text for text in self.texts(canvas)))
        search.delete(0, 'end')
        search.insert(0, '不存在的宝物')
        self.settle(root)
        self.assertEqual(['没有符合条件的宝物信息。'], self.texts(canvas))
        search.delete(0, 'end')
        dialog.destroy()
        self.settle(root)

    def test_score_detail_closes_with_escape(self):
        root = self.make_root()
        show_score_detail(root, dict(label="合格", mode="three"))
        dialog = next(
            w for w in descendants(root)
            if isinstance(w, tk.Toplevel) and w.title() == "评分详情"
        )
        self.assertTrue(dialog.bind("<Escape>"))
        dialog.destroy()
        self.settle(root)

    def test_full_equipment_preserves_every_item_with_bounded_widget_count(self):
        root = self.make_root()
        show_equipment_window(root, snapshot={"equipment": self.equipment})
        root.update()
        labels = [w for w in descendants(root) if isinstance(w, tk.Label)]
        text = "\n".join(str(w.cget("text")) for w in labels)
        for category in self.equipment["categories"]:
            self.assertIn(category["name"], text)
            for item in category["items"]:
                self.assertIn(f"{item['name']}  {item['effect']}", text)
        # A real 70-item snapshot must not require one native widget per item.
        self.assertLess(len(labels), sum(len(c["items"]) for c in self.equipment["categories"]))

    def test_equivalent_search_keeps_widgets_and_scroll_position(self):
        root = self.make_root()
        show_equipment_window(root, snapshot={"equipment": self.equipment})
        self.settle(root)
        dialog = next(w for w in descendants(root) if isinstance(w, tk.Toplevel))
        search = next(w for w in descendants(dialog) if isinstance(w, ttk.Entry))
        canvas = next(w for w in descendants(dialog) if isinstance(w, tk.Canvas))
        before = tuple(str(w) for w in descendants(canvas))
        canvas.yview_moveto(.5)
        position = canvas.yview()
        search.insert(0, "  ")
        self.settle(root)
        self.assertEqual(before, tuple(str(w) for w in descendants(canvas)))
        self.assertEqual(position, canvas.yview())

    def test_empty_equipment_distinguishes_no_records_from_no_search_matches(self):
        root = self.make_root()
        show_equipment_window(root, snapshot={"equipment": {"categories": [], "specials": []}})
        self.settle(root)
        dialog = next(w for w in descendants(root) if isinstance(w, tk.Toplevel))
        search = next(w for w in descendants(dialog) if isinstance(w, ttk.Entry))
        canvas = next(w for w in descendants(dialog) if isinstance(w, tk.Canvas))
        self.assertEqual(["本次结果没有宝物记录。"], self.texts(canvas))
        search.insert(0, "不存在的宝物")
        self.settle(root)
        self.assertEqual(["没有符合条件的宝物信息。"], self.texts(canvas))
        search.delete(0, "end")
        self.settle(root)
        self.assertEqual(["本次结果没有宝物记录。"], self.texts(canvas))

    def test_score_detail_focuses_itself_after_open(self):
        root = self.make_root()
        # 只有已映射的主窗口才有可验证的窗口焦点；实际应用主窗口本身一直可见。
        root.deiconify()
        show_score_detail(root, dict(label="合格", mode="three"))
        self.settle(root)
        dialog = next(
            w for w in descendants(root)
            if isinstance(w, tk.Toplevel) and w.title() == "评分详情"
        )
        self.assertEqual(dialog, dialog.focus_get())
        dialog.destroy()
        self.settle(root)

    def test_uncollected_equipment_is_explicit(self):
        root = self.make_root()
        show_equipment_window(root, snapshot={})
        self.settle(root)
        canvas = next(w for w in descendants(root) if isinstance(w, tk.Canvas))
        self.assertEqual(['本次尝试未采集宝物信息，请查看合格结果。'], self.texts(canvas))

    def test_recent_searches_record_automatically_merge_and_reuse(self):
        root = self.make_root()
        root.deiconify()
        with patch('ccz_randomizer.ui.equipment.SEARCH_HISTORY_IDLE_MS', 50):
            show_equipment_window(root, snapshot={'equipment': self.equipment})
            self.settle(root)
            dialog = next(w for w in descendants(root) if isinstance(w, tk.Toplevel))
            search = next(w for w in descendants(dialog) if isinstance(w, ttk.Entry))
            self.assertFalse(any(isinstance(w, ttk.Button) and w.cget('text') == '清空'
                                 for w in descendants(dialog)))
            search.focus_force()
            deadline = time.monotonic() + 2
            while dialog.focus_get() != search and time.monotonic() < deadline:
                root.update()
                time.sleep(.005)
            self.assertEqual(search, dialog.focus_get(), "输入前搜索框必须先获得焦点")
            search.insert(0, '雌雄')
            self.settle(root)
            self.assertEqual(['雌雄'], SearchHistory(self.history_path).items)
            self.assertEqual(search, dialog.focus_get())
            search.insert('end', '双剑')
            self.settle(root)
            self.assertEqual(['雌雄双剑'], SearchHistory(self.history_path).items)
            search.delete(0, 'end')
            search.insert(0, '不存在的宝物')
            self.settle(root)
            self.assertEqual(['雌雄双剑'], SearchHistory(self.history_path).items)
            recent = next(w for w in descendants(dialog) if isinstance(w, RecentSearchesBar))
            recent.buttons[0].invoke()
            self.settle(root)
            self.assertEqual('雌雄双剑', search.get())
            canvas = next(w for w in descendants(dialog) if isinstance(w, tk.Canvas))
            self.assertIn('雌雄双剑  反击成双', self.texts(canvas))
            search.delete(0, 'end')
            self.settle(root)
            self.assertEqual(['雌雄双剑'], SearchHistory(self.history_path).items)
            dialog.destroy()
            show_equipment_window(root, snapshot={'equipment': self.equipment})
            self.settle(root)
            recent = next(w for w in descendants(root) if isinstance(w, RecentSearchesBar))
            self.assertEqual(['雌雄双剑'], [button._keyword for button in recent.buttons])

    def test_destroy_saves_pending_search_and_cancels_callbacks(self):
        root = self.make_root()
        errors = []
        root.report_callback_exception = lambda *args: errors.append(args)
        with patch('ccz_randomizer.ui.equipment.SEARCH_HISTORY_IDLE_MS', 50):
            show_equipment_window(root, snapshot={'equipment': self.equipment})
            self.settle(root)
            dialog = next(w for w in descendants(root) if isinstance(w, tk.Toplevel))
            search = next(w for w in descendants(dialog) if isinstance(w, ttk.Entry))
            search.insert(0, '倚天剑')
            dialog.destroy()
            self.settle(root)
        self.assertEqual(['倚天剑'], SearchHistory(self.history_path).items)
        self.assertEqual([], errors)
