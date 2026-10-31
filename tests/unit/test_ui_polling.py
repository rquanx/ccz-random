import tempfile
import unittest
import sys
import io
import tkinter as tk
from unittest.mock import patch
from pathlib import Path

from ccz_randomizer.ui.polling import poll_and_reschedule, report_poll_error


class ProgressPollingTests(unittest.TestCase):
    def test_gui_can_finish_and_start_again_with_progress(self):
        from ccz_randomizer import app

        class Worker:
            stdout = io.StringIO("")
            returncode = None
            pid = 12345
            def poll(self):
                return self.returncode

        with tempfile.TemporaryDirectory() as folder:
            workers = []
            def launch(*args, **kwargs):
                worker = Worker()
                workers.append(worker)
                return worker

            def exercise(root):
                state = sys._getframe(1).f_locals
                try:
                    for number in (1, 2):
                        state["start"]()
                        self.assertEqual("停止随机", state["action_button"].cget("text"))
                        state["output_queue"].put("R0 三人兵种筛选: 张宝:弓兵; 结果=不通过")
                        state["poll_worker_once"]()
                        self.assertEqual(number, state["output"].get("1.0", "end").count("张宝:弓兵"))
                        workers[-1].returncode = 0
                        state["poll_worker_once"]()
                        self.assertEqual("开始随机", state["action_button"].cget("text"))
                    self.assertEqual(2, len(workers))
                finally:
                    for callback in root.tk.call('after', 'info'):
                        root.after_cancel(callback)
                    root.destroy()

            with patch.object(tk.Tk, "mainloop", exercise), \
                 patch.object(app, "app_dir", return_value=Path(folder)), \
                 patch.object(app, "locate_game_executable", return_value=Path(folder) / "Ekd5.exe"), \
                 patch.object(app, "validate_start_environment"), \
                 patch.object(app, "cleanup_random_runtime"), \
                 patch.object(app.subprocess, "Popen", side_effect=launch), \
                 patch.object(app.threading.Thread, "start"):
                app.gui_main()

    def test_failed_refresh_does_not_stop_subsequent_progress(self):
        # Tk does not reschedule a callback that raises before its after() call.
        # Model one failed UI update followed by the next completed result.
        pending = [RuntimeError("render failed"), "第 4 号存档已保存"]
        displayed, scheduled, errors = [], [], []

        def poll():
            value = pending.pop(0)
            if isinstance(value, Exception):
                raise value
            displayed.append(value)
            return 1

        poll_and_reschedule(poll, scheduled.append, errors.append)
        self.assertEqual([100], scheduled)
        self.assertEqual(1, len(errors))
        poll_and_reschedule(poll, scheduled.append, errors.append)
        self.assertEqual(["第 4 号存档已保存"], displayed)
        self.assertEqual([100, 1], scheduled)

    def test_log_failure_still_reschedules(self):
        scheduled = []
        def fail():
            raise RuntimeError("refresh failed")
        def log_failure(error):
            raise OSError("disk unavailable")
        poll_and_reschedule(fail, scheduled.append, log_failure)
        self.assertEqual([100], scheduled)

    def test_diagnostics_include_traceback(self):
        with tempfile.TemporaryDirectory() as folder:
            try:
                raise ValueError("invalid progress")
            except ValueError as error:
                report_poll_error(Path(folder), error)
            text = (Path(folder) / "ccz_fast_logs/gui-progress.log").read_text(encoding="utf-8")
            self.assertIn("ValueError: invalid progress", text)
            self.assertIn("Traceback", text)
