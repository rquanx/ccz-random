import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest

from ccz_randomizer.app import result_detail_for_runner, build_history_result_snapshot
from ccz_randomizer.ui.result_details import show_score_detail, encode_result_detail, decode_result_detail
from ccz_randomizer.ui.equipment import show_equipment_window


FIXTURE = Path(__file__).resolve().parents[1] / 'fixtures/personnel_22/randomized-equipment.json'


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class EquipmentTests(unittest.TestCase):
    def setUp(self):
        self.equipment = json.loads(FIXTURE.read_text(encoding='utf-8'))

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
        return [canvas.itemcget(i, 'text') for i in canvas.find_all() if canvas.type(i) == 'text']

    def test_score_button_displays_equipment_and_filters(self):
        root = self.make_root()
        show_score_detail(root, dict(label='合格', mode='three', equipment=self.equipment))
        button = next(w for w in descendants(root) if isinstance(w, tk.Button) and w.cget('text') == '宝物信息')
        button.invoke()
        self.settle(root)
        dialog = next(w for w in descendants(root) if isinstance(w, tk.Toplevel) and w.title() == '宝物信息')
        canvas = next(w for w in descendants(dialog) if isinstance(w, tk.Canvas))
        texts = self.texts(canvas)
        for category in self.equipment['categories']:
            for item in category['items']:
                self.assertIn(item['name'], texts)
                if item['effect']:
                    self.assertIn(item['effect'], texts)
        for special in self.equipment['specials']:
            self.assertIn(special['title'], texts)
        search = next(w for w in descendants(dialog) if isinstance(w, ttk.Entry))
        name = self.equipment['categories'][0]['items'][0]['name']
        search.insert(0, name)
        self.settle(root)
        self.assertIn(name, self.texts(canvas))
        self.assertNotIn(self.equipment['categories'][0]['items'][1]['name'], self.texts(canvas))
        search.delete(0, 'end')
        search.insert(0, '不存在的宝物')
        self.settle(root)
        self.assertEqual(['没有符合条件的宝物信息。'], self.texts(canvas))
        search.delete(0, 'end')
        dialog.destroy()
        self.settle(root)

    def test_uncollected_equipment_is_explicit(self):
        root = self.make_root()
        show_equipment_window(root, snapshot={})
        self.settle(root)
        canvas = next(w for w in descendants(root) if isinstance(w, tk.Canvas))
        self.assertEqual(['本次尝试未采集宝物信息，请查看合格结果。'], self.texts(canvas))
