import io
import os
import json
from pathlib import Path
import sys
import tempfile
import threading
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from ccz_randomizer.sleep_guard import SleepGuard, ES_CONTINUOUS, ES_SYSTEM_REQUIRED, execution_state
from ccz_randomizer.preferences import (
    load_prevent_sleep, save_random_runtime_settings, preferences_path,
)


class SleepGuardTests(unittest.TestCase):
    def test_acquire_once_restore_previous_state_and_restart(self):
        setter = Mock(return_value=ES_CONTINUOUS | 2)
        guard = SleepGuard(setter)
        guard.close()
        setter.assert_not_called()
        guard.start()
        guard.start()
        setter.assert_called_once_with(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        guard.close()
        guard.close()
        self.assertEqual([ES_CONTINUOUS | 1, ES_CONTINUOUS | 2],
                         [call.args[0] for call in setter.call_args_list])
        guard.start()
        guard.close()
        self.assertEqual(4, setter.call_count)

    def test_failed_acquire_does_not_claim_sleep_is_blocked(self):
        setter = Mock(side_effect=OSError('failed'))
        guard = SleepGuard(setter)
        with self.assertRaises(OSError):
            guard.start()
        guard.close()
        self.assertEqual(1, setter.call_count)

    def test_native_request_is_thread_local_and_cleared_without_display_requirement(self):
        errors = []
        def exercise():
            try:
                guard = SleepGuard()
                try:
                    guard.start()
                    previous = execution_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
                    self.assertTrue(previous & ES_SYSTEM_REQUIRED)
                    self.assertFalse(previous & 2)  # ES_DISPLAY_REQUIRED
                finally:
                    guard.close()
                previous = execution_state(ES_CONTINUOUS)
                self.assertFalse(previous & ES_SYSTEM_REQUIRED)
            except BaseException as error:
                errors.append(error)
        thread = threading.Thread(target=exercise)
        thread.start()
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        if errors:
            raise errors[0]

    def test_preferences_default_validation_persistence_and_existing_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            self.assertFalse(load_prevent_sleep(base))
            for invalid in ('yes', 1, None):
                preferences_path(base).write_text(json.dumps({'preventSleep': invalid, 'custom': 'keep'}), encoding='utf8')
                self.assertFalse(load_prevent_sleep(base))
            save_random_runtime_settings(base, loop_random=True, concurrency=8, prevent_sleep=True)
            self.assertTrue(load_prevent_sleep(base))
            data = json.loads(preferences_path(base).read_text('utf8'))
            self.assertEqual(('keep', True, 8), (data['custom'], data['loopRandom'], data['concurrency']))
            with self.assertRaises(ValueError):
                save_random_runtime_settings(base, loop_random=False, concurrency=1, prevent_sleep='yes')
            self.assertTrue(load_prevent_sleep(base))


class SleepGuardGuiTests(unittest.TestCase):
    def run_gui(self, exercise, *, launch_error=False, sleep_error=False):
        from ccz_randomizer import app
        from contextlib import ExitStack
        class Worker:
            stdout = io.StringIO('')
            returncode = None
            pid = 12345
            def poll(self):
                return self.returncode
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ))
            base = Path(folder)
            calls = []
            def setter(flags):
                calls.append(flags)
                if sleep_error:
                    raise OSError('Windows拒绝防睡眠请求')
                return ES_CONTINUOUS
            workers = []
            def launch(*args, **kwargs):
                if launch_error:
                    raise OSError('启动失败')
                worker = Worker()
                workers.append(worker)
                return worker
            def mainloop(root):
                state = sys._getframe(1).f_locals
                try:
                    exercise(state, calls, workers, base)
                finally:
                    for child in list(root.winfo_children()):
                        child.destroy()
                    for callback in root.tk.call('after', 'info'):
                        root.after_cancel(callback)
                    root.destroy()
            for target, kwargs in [
                ('ccz_randomizer.sleep_guard.execution_state', {'side_effect': setter}),
                ('ccz_randomizer.ui.start_dependencies.StartDependencyCheck.request', {'new': lambda c: c.on_ready()}),
                ('ccz_randomizer.ui.messages.showerror', {}),
            ]:
                stack.enter_context(patch(target, **kwargs))
            stack.enter_context(patch.object(tk.Tk, 'mainloop', mainloop))
            for name, kwargs in [
                ('app_dir', {'return_value': base}),
                ('locate_game_executable', {'return_value': base / 'Ekd5.exe'}),
                ('activate_game_version', {'return_value': '2.2'}),
                ('validate_start_environment', {}), ('cleanup_random_runtime', {}),
            ]:
                stack.enter_context(patch.object(app, name, **kwargs))
            stack.enter_context(patch.object(app.subprocess, 'Popen', side_effect=launch))
            stack.enter_context(patch.object(app.threading.Thread, 'start'))
            app.gui_main()
            return calls, workers

    def test_loop_concurrent_stop_completion_failure_and_restart_release_request(self):
        def exercise(s, calls, workers, base):
            self.assertFalse(s['prevent_sleep_var'].get())
            for key in ('prevent_sleep_check', 'statistics_button'):
                control = s[key]
                self.assertFalse(hasattr(control, '_experimental_badge'))
                self.assertIn('尚未充分测试', control._tooltip.text)
            s['prevent_sleep_check'].invoke()
            self.assertTrue(load_prevent_sleep(base))
            s['loop_var'].set(True)
            s['concurrency_var'].set(4)
            for result in (0, 130, 1):
                s['start']()
                self.assertEqual(ES_CONTINUOUS | 1, calls[-1])
                self.assertTrue(s['prevent_sleep_check'].instate(['disabled']))
                before = len(calls)
                s['poll_worker_once']()
                self.assertEqual(before, len(calls))
                if result == 130:
                    s['stop']()
                    self.assertEqual(before, len(calls))  # keep awake during cleanup
                workers[-1].returncode = result
                s['poll_worker_once']()
                self.assertEqual(ES_CONTINUOUS, calls[-1])
                self.assertFalse(s['prevent_sleep_check'].instate(['disabled']))
            s['prevent_sleep_check'].invoke()
            self.assertFalse(load_prevent_sleep(base))
            before = len(calls)
            s['start']()
            workers[-1].returncode = 0
            s['poll_worker_once']()
            self.assertEqual(before, len(calls))
        calls, _ = self.run_gui(exercise)
        self.assertEqual([ES_CONTINUOUS | 1, ES_CONTINUOUS] * 3, calls)

    def test_window_exit_releases_active_request(self):
        def exercise(s, calls, workers, base):
            s['prevent_sleep_check'].invoke()
            s['start']()
            self.assertEqual([ES_CONTINUOUS | 1], calls)
        calls, _ = self.run_gui(exercise)
        self.assertEqual([ES_CONTINUOUS | 1, ES_CONTINUOUS], calls)

    def test_launch_failure_restores_sleep_and_keeps_start_available(self):
        def exercise(s, calls, workers, base):
            s['prevent_sleep_check'].invoke()
            s['start']()
            self.assertEqual([ES_CONTINUOUS | 1, ES_CONTINUOUS], calls)
            self.assertEqual('开始随机', s['action_button'].cget('text'))
        self.run_gui(exercise, launch_error=True)

    def test_native_failure_does_not_launch_unprotected_randomization(self):
        def exercise(s, calls, workers, base):
            s['prevent_sleep_check'].invoke()
            s['start']()
            self.assertEqual([], workers)
            self.assertEqual('开始随机', s['action_button'].cget('text'))
        self.run_gui(exercise, sleep_error=True)
