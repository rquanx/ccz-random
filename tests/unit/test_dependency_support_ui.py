"""Real FAQ controls with recorded DLL failures and no game execution/network."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from ccz_randomizer import app
from ccz_randomizer.diagnostics.dependencies import dependency_guidance, VC_DOWNLOADS
from tests.unit.test_dependency_diagnostics import FAILURE, SYSTEM


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class DependencySupportUiTests(unittest.TestCase):
    def exercise_diagnostics(self, verify, results, worker_result):
        targets = []
        def capture(thread):
            if thread.name == "window-task":
                targets.append(thread._target)

        def exercise(root):
            state = sys._getframe(1).f_locals
            try:
                state["open_unusable_diagnostics"]()
                dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
                report = next(w for w in descendants(dialog) if isinstance(w, tk.Text))
                def wait_until(predicate):
                    deadline = time.monotonic() + 3
                    while not predicate() and time.monotonic() < deadline:
                        root.update()
                        time.sleep(.002)
                    self.assertTrue(predicate())
                def finish_pending():
                    wait_until(lambda: bool(targets))
                    targets.pop(0)()
                    wait_until(lambda: any(isinstance(w, ttk.Button) and w.cget("text") == "再次测试" and not w.instate(("disabled",)) for w in descendants(dialog)))
                verify(root, dialog, report, finish_pending)
            finally:
                for child in list(root.winfo_children()):
                    child.destroy()
                for timer in root.tk.call("after", "info"):
                    root.after_cancel(timer)
                root.destroy()

        with tempfile.TemporaryDirectory() as folder, \
             patch.dict(os.environ), \
             patch.object(tk.Tk, "mainloop", exercise), \
             patch.object(app, "app_dir", return_value=Path(folder)), \
             patch.object(app, "locate_game_executable", return_value=Path(folder) / "Ekd5.exe"), \
             patch.object(app, "activate_game_version", return_value="2.2"), \
             patch.object(app, "inspect_environment", return_value=[dict(label="环境", ok=True, message="环境正常")]), \
             patch.object(app, "skill_score_catalog", return_value={}), \
             patch("ccz_randomizer.profile_session.startup_profile_check"), \
             patch.object(app.threading.Thread, "start", capture), \
             patch("ccz_randomizer.ui.support_controller.inspect_runtime_dependencies", side_effect=results), \
             patch("ccz_randomizer.ui.support_controller.system_information", return_value=SYSTEM), \
             patch("ccz_randomizer.ui.support_controller.subprocess.run", return_value=worker_result) as worker, \
             patch("ccz_randomizer.ui.support_controller.os.startfile") as opened:
            self.worker = worker
            self.opened = opened
            app.gui_main()

    def test_missing_dependency_blocks_random_exposes_official_link_and_can_retry(self):
        failed = dict(label="win32ui", ok=False, **dependency_guidance(FAILURE, SYSTEM))
        passed = dict(label="win32ui", ok=True, message="组件可以正常加载。")
        def verify(root, dialog, report, finish):
            finish()
            text = report.get("1.0", "end")
            self.assertIn("本次未启动游戏", text)
            self.assertIn(VC_DOWNLOADS["x64"], text)
            self.worker.assert_not_called()
            next(w for w in descendants(dialog) if isinstance(w, ttk.Button) and str(w.cget("text")).startswith("打开微软 VC++")).invoke()
            self.opened.assert_called_once_with(VC_DOWNLOADS["x64"])
            next(w for w in descendants(dialog) if isinstance(w, ttk.Button) and w.cget("text") == "复制下载地址").invoke()
            self.assertEqual(VC_DOWNLOADS["x64"], root.clipboard_get())
            next(w for w in descendants(dialog) if isinstance(w, ttk.Button) and w.cget("text") == "再次测试").invoke()
            finish()
            self.assertIn("兼容模式测试成功", report.get("1.0", "end"))
            self.assertNotIn(VC_DOWNLOADS["x64"], report.get("1.0", "end"))
            self.worker.assert_called_once()
            self.assertIn("--worker", self.worker.call_args.args[0])
            self.assertEqual("1", self.worker.call_args.kwargs["env"]["CCZ_COMPATIBILITY_MODE"])
        self.exercise_diagnostics(verify, [[failed], [passed]], subprocess.CompletedProcess([], 0, "成功", ""))

    def test_loader_error_on_stderr_is_explained_instead_of_generic_failure(self):
        def verify(root, dialog, report, finish):
            finish()
            text = report.get("1.0", "end")
            self.assertIn("MFC", text)
            self.assertIn("DLL load failed", text)
            self.assertIn(VC_DOWNLOADS["x64"], text)
            self.assertNotIn("暂时无法明确定位原因", text)
        self.exercise_diagnostics(verify, [[dict(label="win32ui", ok=True, message="组件正常")]],
                                  subprocess.CompletedProcess([], 1, "", FAILURE))
