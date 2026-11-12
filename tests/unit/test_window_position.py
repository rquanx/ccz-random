import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ccz_randomizer.ui.window_native import native_placement
from ccz_randomizer.ui.window_position import _center_native, centered_origin, centered_toplevel, show_centered


class CenterGeometryTests(unittest.TestCase):
    def test_dpi_size_change_is_recentered_on_negative_origin_monitor(self):
        class Monitor:
            frame = (0, 0, 316, 239)
            moves = 0
            def work_area(self, parent):
                return (-2560, 40, 0, 1440)
            def bounds(self, window):
                return self.frame
            def move(self, window, x, y):
                self.moves += 1
                # Model the one WM_DPICHANGED resize during a monitor move.
                width, height = 474, 358
                self.frame = (x, y, x+width, y+height)
        backend = Monitor()
        window = Mock()
        window.winfo_width.return_value = 300
        window.winfo_height.return_value = 200
        _center_native(window, Mock(), backend)
        left, top, right, bottom = backend.frame
        self.assertEqual(-2560, left+right)
        self.assertEqual(1480, top+bottom)
        self.assertEqual(2, backend.moves)

    def test_monitor_origins_taskbars_and_oversize_windows(self):
        # Win32 work rectangles may be offset or negative; they are not sizes.
        cases = [
            ((0, 0, 1920, 1040), 800, 600, (560, 220)),
            ((48, 0, 1920, 1080), 800, 600, (584, 240)),
            ((0, 40, 1920, 1080), 800, 600, (560, 260)),
            ((-1920, 0, 0, 1040), 800, 600, (-1360, 220)),
            ((-1280, -1024, 0, 0), 800, 600, (-1040, -812)),
            ((100, 40, 500, 340), 800, 600, (100, 40)),
        ]
        for work, width, height, expected in cases:
            with self.subTest(work=work):
                self.assertEqual(expected, centered_origin(work, width, height))


class WindowPositionTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry("500x350+50+50")
        self.root.update()
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.addCleanup(self.root.destroy)
        self.backend = native_placement()

    def assert_native_centered(self, window, work=None):
        if self.backend is None:
            self.skipTest("Windows native placement")
        left, top, right, bottom = self.backend.bounds(window)
        work = work or self.backend.work_area(self.root)
        # Compare outer-frame midpoints, independently of Tk client geometry.
        self.assertLessEqual(abs(left+right-work[0]-work[2]), 1)
        self.assertLessEqual(abs(top+bottom-work[1]-work[3]), 1)
        self.assertGreaterEqual(left, work[0])
        self.assertGreaterEqual(top, work[1])
        self.assertLessEqual(right, work[2])
        self.assertLessEqual(bottom, work[3])
        self.assertEqual(1.0, window.attributes("-alpha"))

    def test_building_and_intermediate_layout_do_not_reveal_window(self):
        dialog = centered_toplevel(self.root)
        dialog.geometry("300x200")
        self.root.update()
        self.assertEqual("withdrawn", dialog.state())
        self.assertEqual(0.0, dialog.attributes("-alpha"))
        # Reproduce builders doing layout before changing to their final size.
        dialog.geometry("720x560")
        dialog.update_idletasks()
        self.assertEqual("withdrawn", dialog.state())
        show_centered(dialog)
        self.root.update()
        self.assertEqual((720, 560), (dialog.winfo_width(), dialog.winfo_height()))
        self.assert_native_centered(dialog)

    def test_only_reveal_after_final_outer_frame_is_centered(self):
        dialog = centered_toplevel(self.root)
        dialog.geometry("320x220+0+0")
        original = dialog.attributes
        revealed = []
        def attributes(*args):
            if args == ("-alpha", 1.0):
                self.assert_native_centered_geometry(dialog)
                revealed.append(True)
            return original(*args)
        with patch.object(dialog, "attributes", side_effect=attributes):
            show_centered(dialog)
        self.root.update()
        self.assertEqual([True], revealed)
        self.assert_native_centered(dialog)

    def assert_native_centered_geometry(self, dialog):
        if self.backend is not None:
            left, top, right, bottom = self.backend.bounds(dialog)
            work = self.backend.work_area(self.root)
            self.assertLessEqual(abs(left+right-work[0]-work[2]), 1)
            self.assertLessEqual(abs(top+bottom-work[1]-work[3]), 1)

    def test_move_resize_and_restore_do_not_recenter(self):
        dialog = centered_toplevel(self.root)
        dialog.geometry("300x200")
        show_centered(dialog)
        self.root.update()
        dialog.geometry("320x220+100+100")
        self.root.update()
        dialog.withdraw()
        show_centered(dialog)
        self.root.update()
        self.assertTrue(dialog.geometry().endswith("+100+100"), dialog.geometry())
        self.assertEqual([], self.errors)

    def test_large_minimum_and_fixed_dialog_fit_work_area(self):
        if self.backend is None:
            self.skipTest("Windows native placement")
        dialog = centered_toplevel(self.root)
        dialog.geometry("1180x850")
        dialog.minsize(1000, 700)
        dialog.resizable(False, False)
        work = (100, 100, 850, 650)
        with patch.object(self.backend, "work_area", return_value=work):
            show_centered(dialog)
            self.root.update()
            self.assert_native_centered(dialog, work)
        self.assertLess(dialog.winfo_width(), 750)
        self.assertLess(dialog.winfo_height(), 550)
        self.assertEqual((0, 0), dialog.resizable())

    def test_native_failure_falls_back_without_leaving_invisible_dialog(self):
        dialog = centered_toplevel(self.root)
        dialog.geometry("300x200")
        with patch("ccz_randomizer.ui.window_position.native_placement", side_effect=OSError("unavailable")):
            show_centered(dialog)
        self.root.update()
        self.assertTrue(dialog.winfo_ismapped())
        self.assertEqual(1.0, dialog.attributes("-alpha"))
        self.assertEqual([], self.errors)

    def test_both_positioning_paths_fail_but_dialog_remains_visible(self):
        dialog = centered_toplevel(self.root)
        dialog.geometry("300x200")
        with patch("ccz_randomizer.ui.window_position.native_placement", side_effect=OSError("unavailable")), \
             patch("ccz_randomizer.ui.window_position._center_fallback", side_effect=tk.TclError("position failed")):
            show_centered(dialog)
        self.root.update()
        self.assertTrue(dialog.winfo_ismapped())
        self.assertEqual(1.0, dialog.attributes("-alpha"))

    def test_destroy_before_or_during_initial_layout_has_no_late_callback(self):
        dialog = centered_toplevel(self.root)
        dialog.destroy()
        show_centered(dialog)
        dialog = centered_toplevel(self.root)
        dialog.after_idle(dialog.destroy)
        show_centered(dialog)
        self.root.update()
        self.assertEqual([], self.errors)

    def test_real_dialog_builders_share_work_area_center(self):
        from ccz_randomizer.app import TEAM_MEMBERS, show_changelog_window
        from ccz_randomizer.history import HistoryRepository
        from ccz_randomizer.jobs import JOB_MAP
        from ccz_randomizer.profile_updates import show_profile_update_dialog
        from ccz_randomizer.rules.config import default_rule_config
        from ccz_randomizer.rules.editor import show_rule_editor, show_advanced_help
        from ccz_randomizer.ui.equipment import show_equipment_window
        from ccz_randomizer.ui.effect_dictionary import show_effect_dictionary
        from ccz_randomizer.ui.history import show_history_window
        from ccz_randomizer.ui.recruitment import show_recruit_window
        from ccz_randomizer.ui.result_details import show_score_detail
        from ccz_randomizer.ui.support_menu import show_support_menu
        from ccz_randomizer.ui.usage_guide import show_usage_guide
        fixture = Path(__file__).parents[1]/"fixtures/personnel_220_1104/randomized-result.json"
        snapshot = json.loads(fixture.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            factories = [
                lambda: show_history_window(self.root, HistoryRepository(base)),
                lambda: show_recruit_window(self.root, snapshot=snapshot, history_path=base/"recruit.json"),
                lambda: show_equipment_window(self.root, snapshot={}, history_path=base/"equipment.json"),
                lambda: show_score_detail(self.root, dict(label="qualified", mode="three")),
                lambda: show_support_menu(self.root, {}, "3"),
                lambda: show_profile_update_dialog(self.root, base),
                lambda: show_usage_guide(self.root),
                lambda: show_advanced_help(self.root, 0),
                lambda: show_rule_editor(self.root, base, default_rule_config(), JOB_MAP, TEAM_MEMBERS, (), lambda _: None),
                lambda: show_changelog_window(self.root),
                lambda: show_effect_dictionary(self.root),
            ]
            actions = {key: lambda parent: None for key in ("guide", "effects", "diagnostics", "sound", "logs", "update", "cleanup")}
            factories[4] = lambda: show_support_menu(self.root, actions, "3")
            for index, factory in enumerate(factories):
                with self.subTest(dialog=index):
                    factory()
                    self.root.update()
                    dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
                    self.assert_native_centered(dialog)
                    dialog.destroy()
                    self.root.update()
        self.assertEqual([], self.errors)

    def test_centered_text_prompt_submits_cancels_and_restores_modal_grab(self):
        from ccz_randomizer.ui.inputs import TextEntry
        from ccz_randomizer.ui.text_prompt import ask_text
        self.root.grab_set()
        for key, expected in (("<Return>", "新名称"), ("<Escape>", None)):
            failures = []
            def exercise():
                dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
                try:
                    self.assert_native_centered(dialog)
                    entry = next(w for w in dialog.winfo_children()[0].winfo_children() if isinstance(w, TextEntry))
                    self.assertEqual("原名称", entry.get())
                    entry.delete(0, "end")
                    entry.insert(0, "新名称")
                    entry.focus_force()
                    dialog.update()
                    self.assertIs(entry, dialog.focus_get())
                    entry.event_generate(key)
                except Exception as error:
                    failures.append(error)
                finally:
                    if dialog.winfo_exists():
                        dialog.destroy()
            self.root.after(30, exercise)
            result = ask_text("重命名规则", "输入新的规则名称：", initialvalue="原名称", parent=self.root)
            if failures:
                raise failures[0]
            self.assertEqual(expected, result)
            self.assertIs(self.root, self.root.grab_current())
        self.assertEqual([], self.errors)
