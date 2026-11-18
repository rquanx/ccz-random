"""Start-time dependency failures must not launch a random worker or touch saves."""
import io
import os
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ccz_randomizer import app
from ccz_randomizer.diagnostics.dependencies import dependency_guidance, VC_DOWNLOADS
from ccz_randomizer.ui.start_dependencies import StartDependencyCheck
from tests.unit.test_dependency_diagnostics import FAILURE, SYSTEM


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class StartDependenciesTests(unittest.TestCase):
    def test_start_requires_dependencies_and_keeps_one_worker_in_sandbox_scheduler(self):
        targets = []
        failed = [dict(label="win32ui", ok=False, **dependency_guidance(FAILURE, SYSTEM))]
        passed = [dict(label="win32ui", ok=True, message="组件正常。")]
        def capture(thread):
            if thread.name == "window-task":
                targets.append(thread._target)
        def exercise(root):
            state = sys._getframe(1).f_locals
            button = state["action_button"]
            def wait_until(predicate):
                deadline = time.monotonic() + 3
                while not predicate() and time.monotonic() < deadline:
                    root.update()
                    time.sleep(.002)
                self.assertTrue(predicate())
            try:
                button.invoke()
                self.assertTrue(button.instate(("disabled",)))
                self.assertIn("检测", button.cget("text"))
                state["start"]()  # Direct duplicate requests must also be ignored.
                self.assertEqual(1, len(targets))
                targets.pop(0)()
                wait_until(lambda: any(isinstance(w, tk.Toplevel) and w.title() == "无法开始随机" for w in root.winfo_children()))
                dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
                text = next(w for w in descendants(dialog) if isinstance(w, tk.Text)).get("1.0", "end")
                self.assertIn(VC_DOWNLOADS["x64"], text)
                self.assertIn("win32ui", text)
                self.launch.assert_not_called()
                self.cleanup.assert_not_called()
                self.validate.assert_not_called()
                next(w for w in descendants(dialog) if isinstance(w, ttk.Button) and w.cget("text") == "复制下载地址").invoke()
                self.assertEqual(VC_DOWNLOADS["x64"], root.clipboard_get())
                next(w for w in descendants(dialog) if isinstance(w, ttk.Button) and w.cget("text") == "重新检测").invoke()
                self.assertTrue(button.instate(("disabled",)))
                targets.pop(0)()
                wait_until(lambda: button.cget("text") == "停止随机")
                self.assertFalse(button.instate(("disabled",)))
                self.launch.assert_called_once()
                self.cleanup.assert_called_once()
                self.validate.assert_called_once()
                self.assertIn("--worker", self.launch.call_args.args[0])
                # Replace the old source-string check with actual launch parameters.
                self.assertEqual("1", self.launch.call_args.kwargs["env"]["CCZ_CONCURRENT_MODE"])
                self.assertEqual("1", self.launch.call_args.kwargs["env"]["CCZ_CONCURRENT_COUNT"])
                self.assertIsNone(state["concurrent_console_state"])
                self.assertIn("开始随机：", state["output"].get("1.0", "end"))
                self.check.assert_called_with([sys.executable, str(app.source_entry_path())], app.bundle_root())
                worker.returncode = 0
                state["poll_worker_once"]()
                worker.returncode = None
                button.invoke()
                self.assertTrue(button.instate(("disabled",)))
                self.assertEqual(1, self.launch.call_count)
                targets.pop(0)()
                wait_until(lambda: self.launch.call_count == 2)
                self.assertEqual(3, self.check.call_count)
            finally:
                for child in list(root.winfo_children()):
                    child.destroy()
                for timer in root.tk.call("after", "info"):
                    root.after_cancel(timer)
                root.destroy()
        worker = SimpleNamespace(stdout=io.StringIO(""), returncode=None, pid=12345)
        worker.poll = lambda: worker.returncode
        with tempfile.TemporaryDirectory() as folder, \
             patch.dict(os.environ), \
             patch.object(tk.Tk, "mainloop", exercise), \
             patch.object(app, "app_dir", return_value=Path(folder)), \
             patch.object(app, "locate_game_executable", return_value=Path(folder) / "Ekd5.exe"), \
             patch.object(app, "activate_game_version", return_value="2.2"), \
             patch.object(app, "validate_start_environment") as validate, \
             patch.object(app, "cleanup_random_runtime") as cleanup, \
             patch.object(app, "skill_score_catalog", return_value={}), \
             patch("ccz_randomizer.profile_session.startup_profile_check"), \
             patch.object(app.threading.Thread, "start", capture), \
             patch("ccz_randomizer.ui.start_dependencies.inspect_runtime_dependencies", side_effect=[failed, passed, passed]) as check, \
             patch.object(app.subprocess, "Popen", return_value=worker) as launch:
            self.launch, self.cleanup, self.validate, self.check = launch, cleanup, validate, check
            app.gui_main()

    def test_check_does_not_block_ui_and_close_prevents_late_start(self):
        root = tk.Tk()
        button = ttk.Button(root, text="开始随机")
        button.pack()
        targets, starts, responsive = [], [], []
        with patch("ccz_randomizer.ui.tasks.threading.Thread.start", lambda thread: targets.append(thread._target)), \
             patch("ccz_randomizer.ui.start_dependencies.inspect_runtime_dependencies", return_value=[dict(label="runtime", ok=True, message="正常")]):
            gate = StartDependencyCheck(root, button, lambda: starts.append(True), ["tool.exe"], Path("."))
            gate.request()
            root.after_idle(lambda: responsive.append(True))
            root.update()
            self.assertEqual([True], responsive)
            self.assertEqual([], starts)
            root.destroy()
            targets.pop(0)()
            self.assertEqual([], starts)

    def test_check_exception_restores_start_action_and_can_retry(self):
        root = tk.Tk()
        self.addCleanup(root.destroy)
        button = ttk.Button(root, text="开始随机")
        targets, errors = [], []
        with patch("ccz_randomizer.ui.tasks.threading.Thread.start", lambda thread: targets.append(thread._target)), \
             patch("ccz_randomizer.ui.start_dependencies.inspect_runtime_dependencies", side_effect=RuntimeError("检测超时")), \
             patch("ccz_randomizer.ui.start_dependencies.show_dependency_issues", side_effect=lambda parent, checks, retry: errors.extend(checks)):
            gate = StartDependencyCheck(root, button, lambda: self.fail("must not start"), ["tool.exe"], Path("."))
            gate.request()
            targets.pop(0)()
            deadline = time.monotonic() + 3
            while gate.pending and time.monotonic() < deadline:
                root.update()
                time.sleep(.002)
            self.assertFalse(gate.pending)
            self.assertTrue(gate.tasks.closed)
            self.assertFalse(button.instate(("disabled",)))
            self.assertEqual("开始随机", button.cget("text"))
            self.assertIn("检测超时", errors[0]["message"])
            gate.request()
            self.assertTrue(gate.pending)
