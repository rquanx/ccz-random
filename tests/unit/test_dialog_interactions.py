"""Regression coverage for the complete-data and lifecycle paths of child dialogs."""
import json
from pathlib import Path
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ccz_randomizer.ui.theme import setup_theme

FIXTURES = Path(__file__).resolve().parents[1]/'fixtures/personnel_22'


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class DialogInteractionTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('1000x720')
        setup_theme(self.root)
        self.errors = []
        self.root.report_callback_exception = lambda *exc: self.errors.append(exc)
        self.addCleanup(self.root.destroy)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root.update()

    def wait(self, ready):
        deadline = time.monotonic()+5
        while time.monotonic() < deadline:
            self.root.update()
            if ready():
                self.assertEqual([], self.errors)
                return
            time.sleep(.002)
        self.fail('子弹窗未达到预期状态')

    def test_destroying_a_window_cancels_its_delayed_callbacks(self):
        from ccz_randomizer.ui.window_timer import window_after
        dialog = tk.Toplevel(self.root)
        calls = []
        timer = window_after(dialog, 1000, lambda: calls.append(True))
        self.assertIn(timer, self.root.tk.call('after', 'info'))
        dialog.destroy()
        self.assertNotIn(timer, self.root.tk.call('after', 'info'))
        self.assertEqual([], calls)

    def test_recruitment_scroll_reaches_every_record_with_bounded_canvas_items(self):
        from ccz_randomizer.ui.recruitment import show_recruit_window
        from ccz_randomizer.recruitment import parse_recruits
        snapshot = dict(schemaVersion=1, gameVersion='2.2', personnel=json.loads((FIXTURES/'randomized-personnel.json').read_text(encoding='utf-8')),
                        fixedPersonnel=json.loads((FIXTURES/'randomized-fixed-personnel.json').read_text(encoding='utf-8')))
        people = parse_recruits(dict(snapshot, personnel=snapshot['personnel']+snapshot['fixedPersonnel']))
        show_recruit_window(self.root, snapshot=snapshot, history_path=Path(self.folder.name)/'searches.json')
        dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
        cards = dialog._recruitment_cards
        self.wait(lambda: cards.ready)
        canvas = cards.canvas
        seen = set()
        maximum = 0
        for step in range(101):
            canvas.yview_moveto(step/100)
            self.root.update()
            maximum = max(maximum, len(canvas.find_all()))
            for item in canvas.find_all():
                for tag in canvas.gettags(item):
                    if tag.startswith('card:'):
                        seen.add(int(tag.split(':')[1]))
        self.assertEqual({person.record_index for person in people}, seen)
        self.assertLess(maximum, 350)
        dialog.destroy()
        self.root.update()
        self.assertEqual([], self.errors)

    def test_equipment_filters_reuse_cards_without_hiding_any_restored_item(self):
        from ccz_randomizer.ui.equipment import show_equipment_window
        from ccz_randomizer.ui.equipment_sections import EquipmentSections
        equipment = json.loads((FIXTURES/'randomized-equipment.json').read_text(encoding='utf-8'))
        show_equipment_window(self.root, snapshot={'equipment':equipment}, history_path=Path(self.folder.name)/'searches.json')
        dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
        sections = next(w for w in descendants(dialog) if isinstance(w, EquipmentSections))
        before = tuple(sections.categories+sections.specials)
        search = next(w for w in descendants(dialog) if isinstance(w, ttk.Entry))
        search.insert(0, '不存在的宝物')
        self.wait(lambda: not sections.winfo_manager())
        search.delete(0, 'end')
        self.wait(lambda: bool(sections.winfo_manager()))
        self.assertEqual(before, tuple(sections.categories+sections.specials))
        texts = '\n'.join(block.itemcget(item, 'text') for block in sections.categories for item in block.items)
        for category in equipment['categories']:
            for item in category['items']:
                self.assertIn(f"{item['name']}  {item['effect']}", texts)

    def test_affinity_reopen_resets_cancelled_edits_and_uses_latest_callback(self):
        from ccz_randomizer.rules.editor import show_member_affinity_editor
        from ccz_randomizer.ui.searchable_combo import SelectionCombobox
        calls = []
        original = {'曹操':('ALL_ROUNDER', 'NONE')}
        show_member_affinity_editor(self.root, ('曹操',), original, True, lambda value: calls.append(('old',value)))
        dialog = self.root._ccz_affinity_editor
        combo = next(w for w in descendants(dialog) if isinstance(w, SelectionCombobox))
        combo.set('武将型')
        next(w for w in descendants(dialog) if isinstance(w, ttk.Button) and w.cget('text') == '取消').invoke()
        self.assertIsNone(self.root.grab_current())
        latest = {'曹操':('MASTER', 'NONE')}
        show_member_affinity_editor(self.root, ('曹操',), latest, True, lambda value: calls.append(('new',value)))
        self.assertIs(dialog, self.root._ccz_affinity_editor)
        self.assertEqual('文官型', combo.get())
        next(w for w in descendants(dialog) if isinstance(w, ttk.Button) and w.cget('text') == '确认').invoke()
        self.assertEqual([('new',latest)], calls)
        self.assertTrue(dialog._ccz_cached_closed)
        self.assertIsNone(self.root.grab_current())

    def test_diagnostic_environment_check_never_runs_on_ui_thread(self):
        from ccz_randomizer import app
        from ccz_randomizer.ui.support_controller import create_support_actions
        keys = ('UploadCancelled', 'app_dir', 'application_build_info', 'build_version_text',
                'centered_toplevel', 'create_log_archive', 'show_centered', 'show_toast',
                'upload_log_archive', 'bundle_root', 'current_game_version', 'inspect_environment',
                'locate_game_executable', 'native_dir', 'source_entry_path')
        api = SimpleNamespace(**{key:getattr(app,key) for key in keys})
        api.app_dir = lambda: Path(self.folder.name)
        checked = []
        def locate():
            checked.append(threading.get_ident())
            raise FileNotFoundError('isolated test')
        api.locate_game_executable = locate
        _, _, diagnose = create_support_actions(self.root, api)
        with patch('ccz_randomizer.ui.support_controller.inspect_runtime_dependencies', return_value=[]):
            diagnose()
            self.wait(lambda: bool(checked))
            self.assertNotEqual(threading.get_ident(), checked[0])
            dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
            report = next(w for w in descendants(dialog) if isinstance(w, tk.Text))
            self.wait(lambda: '游戏定位失败' in report.get('1.0','end'))

    def test_storage_scan_can_be_closed_while_worker_is_still_waiting(self):
        from ccz_randomizer.ui.storage_cleanup import show_storage_cleanup
        from ccz_randomizer.runtime.storage_cleanup import CATEGORIES, StorageUsage
        release, started = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def scan(_):
            started.set()
            release.wait(3)
            return {key:StorageUsage() for key in CATEGORIES}
        with patch('ccz_randomizer.ui.storage_cleanup.scan_storage', side_effect=scan):
            show_storage_cleanup(self.root, Path(self.folder.name))
            self.wait(started.is_set)
            dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
            dialog.tk.call(dialog.protocol('WM_DELETE_WINDOW'))
            self.assertFalse(dialog.winfo_exists())
            release.set()
            self.root.update()
            self.assertEqual([], self.errors)

    def test_unchanged_frequency_data_retains_scrolled_view_and_render(self):
        from ccz_randomizer.ui.statistics_frequency import FrequencyChart
        equipment = json.loads((FIXTURES/'randomized-equipment.json').read_text(encoding='utf-8'))
        rows = [(item['name'], index+1) for index, item in enumerate(
            item for category in equipment['categories'] for item in category['items'])]
        chart = FrequencyChart(self.root, '宝物频率')
        chart.pack(fill='both', expand=True)
        self.root.update()
        chart.set(rows)
        chart.yview_moveto(1)
        self.root.update()
        before = chart.yview(), chart.find_all()
        chart.set(list(rows))
        self.root.update()
        self.assertEqual(before, (chart.yview(), chart.find_all()))

    def test_statistics_reopen_reuses_widgets_and_reloads_current_data(self):
        from ccz_randomizer.ui.statistics import show_statistics_window
        from ccz_randomizer.statistics_store import StatisticsRepository
        base = Path(self.folder.name)
        StatisticsRepository(base)
        window = show_statistics_window(self.root, base)
        self.wait(lambda: any(isinstance(w, tk.Label) and str(w.cget('text')).startswith('暂无符合')
                              for w in descendants(window)))

        widgets = tuple(descendants(window))
        window.tk.call(window.protocol('WM_DELETE_WINDOW'))
        self.assertTrue(window._ccz_cached_closed)
        self.assertIsNone(self.root.grab_current())
        with patch.object(window, '_reload_statistics', wraps=window._reload_statistics) as reload:
            self.assertIs(window, show_statistics_window(self.root, base))
            reload.assert_called_once()
        self.assertFalse(window._ccz_cached_closed)
        self.assertEqual(widgets, tuple(descendants(window)))
        self.wait(lambda: any(isinstance(w, tk.Label) and str(w.cget('text')).startswith('暂无符合')
                              for w in descendants(window)))

    def test_sound_repair_is_asynchronous_and_rejects_duplicate_requests(self):
        from ccz_randomizer.ui.sound_repair import create_sound_repair
        from ccz_randomizer.runtime.manual_repair import ManualRepairResult
        from unittest.mock import Mock
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        calls = []
        def audio(*_args, **_kwargs):
            calls.append(threading.get_ident())
            entered.set()
            release.wait(3)
            return ManualRepairResult('not_needed', '无需修复')
        api = SimpleNamespace(show_toast=Mock(), locate_game_executable=lambda: Path(self.folder.name)/'Ekd5.exe',
                              repair_normal_game_audio=audio, find_process_ids=None, process_executable=None,
                              restore_process_audio_sessions=None)
        repair = create_sound_repair(self.root, api)
        with patch('ccz_randomizer.ui.sound_repair.messages.askyesno', return_value=True) as question:
            repair()
            self.wait(entered.is_set)
            repair()
            question.assert_called_once()
            self.assertNotEqual(threading.get_ident(), calls[0])
            beats = []
            self.root.after(0, lambda: beats.append(True))
            self.wait(lambda: bool(beats))
            release.set()
            self.wait(lambda: api.show_toast.call_count == 2)
            self.assertEqual('无需修复', api.show_toast.call_args.args[1])
