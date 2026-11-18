"""First-use choice, real control guidance and non-destructive navigation."""
import tempfile
import os
import tkinter as tk
from tkinter import ttk
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from ccz_randomizer.ui.first_use import show_first_use_prompt
from ccz_randomizer.ui.onboarding import STEPS, show_onboarding
from ccz_randomizer.ui.theme import setup_theme


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('1000x720')
        setup_theme(self.root)
        self.errors = []
        self.root.report_callback_exception = lambda *exc: self.errors.append(exc)
        self.addCleanup(self.root.destroy)
        self.root.update()

    def button(self, parent, text):
        return next(w for w in descendants(parent) if isinstance(w, ttk.Button) and w.cget('text') == text)

    def make_prompt(self, saved=True):
        self.ack = Mock(return_value=saved)
        self.beginner, self.failed, self.exit = Mock(), Mock(), Mock()
        return show_first_use_prompt(self.root, acknowledge=self.ack, on_beginner=self.beginner,
            on_save_failed=self.failed, on_exit=self.exit)

    def test_choice_is_available_during_countdown_but_cannot_bypass_reading(self):
        callbacks = []
        with patch('ccz_randomizer.ui.first_use.window_after', side_effect=lambda w, ms, fn: callbacks.append((ms, fn))):
            dialog = self.make_prompt()
            radio = next(w for w in descendants(dialog) if isinstance(w, ttk.Radiobutton)
                         and w.cget('value') == 'beginner')
            radio.invoke()
            confirm = self.button(dialog, '开始新手引导')
            self.assertTrue(confirm.instate(('disabled',)))
            confirm.invoke()
            self.ack.assert_not_called()
            for index in range(5):
                delay, callback = callbacks.pop(0)
                self.assertEqual(1000, delay)
                callback()
                self.assertEqual(index < 4, confirm.instate(('disabled',)))
            confirm.invoke()
            self.ack.assert_called_once_with()
            self.beginner.assert_called_once_with()
            self.failed.assert_not_called()
            self.assertFalse(dialog.winfo_exists())
            self.assertIsNone(self.root.grab_current())
            self.assertEqual([], callbacks)

    def test_after_five_seconds_requires_choice_and_experienced_user_skips_guide(self):
        callbacks = []
        with patch('ccz_randomizer.ui.first_use.window_after', side_effect=lambda w, ms, fn: callbacks.append(fn)):
            dialog = self.make_prompt(saved=False)
            for _ in range(5):
                callbacks.pop(0)()
            confirm = self.button(dialog, '进入工具')
            self.assertTrue(confirm.instate(('disabled',)))
            radio = next(w for w in descendants(dialog) if isinstance(w, ttk.Radiobutton)
                         and w.cget('value') == 'experienced')
            radio.invoke()
            self.assertFalse(confirm.instate(('disabled',)))
            confirm.invoke()
            self.ack.assert_called_once_with()
            self.failed.assert_called_once_with()
            self.beginner.assert_not_called()

    def test_early_close_does_not_acknowledge_and_cancels_countdown(self):
        dialog = self.make_prompt()
        timers = set(dialog._ccz_owned_timers)
        dialog.tk.call(dialog.protocol('WM_DELETE_WINDOW'))
        self.exit.assert_called_once_with()
        self.ack.assert_not_called()
        dialog.destroy()
        self.root.update()
        self.assertFalse(timers.intersection(self.root.tk.call('after', 'info')))
        self.assertEqual([], self.errors)

    def test_all_steps_highlight_real_controls_preserve_values_and_cleanup_on_replay(self):
        body = ttk.Frame(self.root)
        body.pack(fill='both', expand=True)
        toolbar = ttk.Frame(body)
        toolbar.pack(fill='x')
        selected = tk.StringVar(value='默认规则')
        combo = ttk.Combobox(toolbar, textvariable=selected, values=('默认规则', '其他规则'))
        combo.pack(side='left')
        launch = Mock()
        start = ttk.Button(toolbar, text='开始随机', command=launch)
        start.pack(side='right')
        help_action = Mock()
        targets = {key: combo if key == 'rules' else start for _, _, keys in STEPS for key in keys}
        guide = show_onboarding(body, before=toolbar, targets=targets, open_help=help_action)
        baseline = self.root.bindtags()
        self.root.update()
        self.assertTrue(self.button(guide, '上一步').instate(('disabled',)))
        for index, (title, description, _) in enumerate(STEPS):
            self.root.update()
            self.assertIn(title, guide.heading.cget('text'))
            self.assertEqual(description, guide.description.cget('text'))
            self.assertEqual(len(set(targets[key] for key in STEPS[index][2])),
                             len(guide.spotlight.holes), title)
            self.assertTrue(guide.spotlight.winfo_ismapped())
            self.assertIs(guide, self.root.grab_current())
            self.assertEqual('wm', guide.winfo_manager())
            self.button(guide, '完成引导' if index == len(STEPS)-1 else '下一步').invoke()
        self.assertFalse(guide.winfo_exists())
        self.assertEqual('默认规则', selected.get())
        launch.assert_not_called()
        self.assertIsNone(self.root.grab_current())
        guide = show_onboarding(body, before=toolbar, targets=targets, open_help=help_action)
        self.button(guide, '下一步').invoke()
        self.button(guide, '上一步').invoke()
        self.assertEqual(0, guide.index)
        self.button(guide, '查看使用说明').invoke()
        help_action.assert_called_once_with(self.root)
        self.assertFalse(guide.winfo_exists())
        guide = show_onboarding(body, before=toolbar, targets=targets, open_help=help_action)
        overlay = guide.spotlight
        replacement = show_onboarding(body, before=toolbar, targets=targets, open_help=help_action)
        self.assertFalse(guide.winfo_exists())
        self.assertFalse(overlay.winfo_exists())
        self.button(replacement, '跳过引导').invoke()
        self.root.update()
        self.assertEqual([], self.errors)
        self.assertEqual(baseline, self.root.bindtags())

    def test_floating_card_tracks_window_without_covering_target_and_escape_cleans_up(self):
        body = ttk.Frame(self.root)
        body.pack(fill='both', expand=True)
        target = ttk.Button(body, text='开始随机')
        target.pack(anchor='nw', padx=24, pady=24)
        self.root.update()
        original = (target.winfo_x(), target.winfo_y(), target.winfo_width(), target.winfo_height())
        guide = show_onboarding(body, before=target, targets={'source': target}, open_help=Mock())
        overlay = guide.spotlight
        for geometry in ('1000x720+100+100', '760x520+150+130'):
            self.root.geometry(geometry)
            self.root.update()
            self.assertEqual(original, (target.winfo_x(), target.winfo_y(), target.winfo_width(), target.winfo_height()))
            self.assertEqual(self.root.winfo_rootx(), overlay.winfo_rootx())
            self.assertEqual(self.root.winfo_rooty(), overlay.winfo_rooty())
            self.assertEqual(self.root.winfo_width(), overlay.winfo_width())
            self.assertEqual(self.root.winfo_height(), overlay.winfo_height())
            x, y = guide.winfo_rootx()-self.root.winfo_rootx(), guide.winfo_rooty()-self.root.winfo_rooty()
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(x+guide.winfo_width(), self.root.winfo_width())
            self.assertLessEqual(y+guide.winfo_height(), self.root.winfo_height())
            left, top, right, bottom = overlay.holes[0]
            self.assertTrue(x >= right or x+guide.winfo_width() <= left or
                            y >= bottom or y+guide.winfo_height() <= top)
        self.root.withdraw()
        self.root.update()
        self.assertFalse(guide.winfo_ismapped())
        self.assertFalse(overlay.winfo_ismapped())
        self.root.deiconify()
        self.root.update()
        self.assertTrue(guide.winfo_ismapped())
        guide.focus_force()
        self.root.update()
        guide.event_generate('<Escape>')
        self.root.update()
        self.assertFalse(guide.winfo_exists())
        self.assertFalse(overlay.winfo_exists())
        self.assertIsNone(self.root.grab_current())
        self.assertEqual([], self.errors)

    @unittest.skipUnless(os.name == 'nt', 'Windows monitor coordinates')
    def test_spotlight_and_card_follow_negative_monitor_coordinates(self):
        from ccz_randomizer.ui.window_native import native_placement
        target = ttk.Button(self.root, text='开始随机')
        target.pack(anchor='nw', padx=20, pady=20)
        self.root.update()
        native_placement().move(self.root, -200, -50)
        self.root.update()
        guide = show_onboarding(self.root, before=target, targets={'source': target}, open_help=Mock())
        self.root.update()
        self.assertEqual(self.root.winfo_rootx(), guide.spotlight.winfo_rootx())
        self.assertEqual(self.root.winfo_rooty(), guide.spotlight.winfo_rooty())
        self.assertGreaterEqual(guide.winfo_rootx(), self.root.winfo_rootx())
        self.assertLessEqual(guide.winfo_rootx()+guide.winfo_width(), self.root.winfo_rootx()+self.root.winfo_width())
        guide.destroy()
        self.root.update()
        self.assertEqual([], self.errors)

    def test_actual_main_window_wires_first_use_and_replay_without_starting_random(self):
        from ccz_randomizer import app
        observed = []
        def exercise(root):
            import sys
            state = sys._getframe(1).f_locals
            state['show_first_use_notice']()
            dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel)
                          and w.title() == '首次使用提示')
            radio = next(w for w in descendants(dialog) if isinstance(w, ttk.Radiobutton)
                         and w.cget('value') == 'beginner')
            radio.invoke()
            for _ in range(5):
                ticks.pop(0)()
            self.button(dialog, '开始新手引导').invoke()
            guide = root._ccz_onboarding
            self.assertTrue(guide.winfo_exists())
            self.assertIs(state['action_button'], guide.targets['start'])
            self.assertIs(state['rule_profile_combo'], guide.targets['rules'])
            self.assertIs(state['runtime_settings_bar'], guide.targets['runtime'])
            self.assertIsNone(state['worker'])
            root.geometry('760x520')
            root.update()
            button = state['action_button']
            self.assertGreaterEqual(button.winfo_width(), button.winfo_reqwidth())
            self.assertLessEqual(button.winfo_rootx()+button.winfo_width(), root.winfo_rootx()+root.winfo_width())
            self.button(guide, '跳过引导').invoke()
            state['open_repair_dialog']()
            menu = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel)
                        and w.title() == '常见问题')
            self.button(menu, '新手引导').invoke()
            self.assertFalse(menu.winfo_exists())
            self.assertTrue(root._ccz_onboarding.winfo_exists())
            root.update()
            self.assertIs(root._ccz_onboarding, root.grab_current())
            self.assertIsNone(state['worker'])
            observed.append(True)
            for child in list(root.winfo_children()):
                if child.winfo_exists():
                    child.destroy()
            for callback in root.tk.call('after', 'info'):
                root.after_cancel(callback)
            root.destroy()
        ticks = []
        with tempfile.TemporaryDirectory() as folder, \
             patch.dict(os.environ), \
             patch.object(tk.Tk, 'mainloop', exercise), \
             patch.object(app, 'app_dir', return_value=Path(folder)), \
             patch.object(app, 'first_use_notice_acknowledged', return_value=False), \
             patch.object(app, 'acknowledge_first_use_notice', return_value=True) as ack, \
             patch.object(app, 'skill_score_catalog', return_value={}), \
             patch.object(app, 'activate_game_version', return_value='2.2'), \
             patch.object(app.threading.Thread, 'start'), \
             patch('ccz_randomizer.ui.first_use.window_after', side_effect=lambda w, ms, fn: ticks.append(fn)), \
             patch('ccz_randomizer.profile_session.ProfileUpdateSession.start'), \
             patch.object(app.subprocess, 'Popen') as launch:
            app.gui_main()
            ack.assert_called_once_with(Path(folder))
            launch.assert_not_called()
        self.assertEqual([True], observed)

    def test_destroy_main_window_with_active_walkthrough_cleans_pending_layout(self):
        owner = tk.Toplevel(self.root)
        body = ttk.Frame(owner)
        body.pack(fill='both', expand=True)
        target = ttk.Button(body, text='开始随机')
        target.pack()
        guide = show_onboarding(body, before=target, targets={'source': target}, open_help=Mock())
        owner.destroy()
        self.root.update()
        self.assertFalse(guide.winfo_exists())
        self.assertFalse(guide.spotlight.winfo_exists())
        self.assertEqual([], self.errors)
