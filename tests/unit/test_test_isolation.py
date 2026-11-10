"""Regression tests for the test infrastructure, without launching a game."""
import gc
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import psutil

from tests.helpers.case_process import run_case_process
from tests.helpers.game_copy import isolated_game_copy
from tests.unit_runner import StrictResult

ROOT = Path(__file__).resolve().parents[2]


class StrictRunnerTests(unittest.TestCase):
    def run_inner(self, action):
        class InnerCase(unittest.TestCase):
            def runTest(self):
                action()
        return unittest.TextTestRunner(stream=io.StringIO(), resultclass=StrictResult).run(
            unittest.TestSuite([InnerCase()]))

    def test_environment_leak_fails_and_does_not_contaminate_next_case(self):
        previous = os.environ.get("CCZ_GAME_VERSION")
        result = self.run_inner(lambda: os.environ.__setitem__("CCZ_GAME_VERSION", "leaked-test-version"))
        self.assertEqual(1, len(result.failures))
        self.assertIn("CCZ_GAME_VERSION", result.failures[0][1])
        self.assertEqual(previous, os.environ.get("CCZ_GAME_VERSION"))

    def test_worker_exception_fails_the_test(self):
        def action():
            def fail():
                raise RuntimeError("worker failed")
            worker = threading.Thread(target=fail)
            worker.start()
            worker.join(timeout=3)
            self.assertFalse(worker.is_alive())
        result = self.run_inner(action)
        self.assertEqual(1, len(result.failures))
        self.assertIn("worker failed", result.failures[0][1])

    def test_tk_callback_exception_fails_the_test(self):
        def action():
            root = tk.Tk()
            root.withdraw()
            try:
                def fail():
                    raise ValueError("callback failed")
                root.after(0, fail)
                root.update()
            finally:
                root.destroy()
        result = self.run_inner(action)
        self.assertEqual(1, len(result.failures))
        self.assertIn("callback failed", result.failures[0][1])

    def test_destructor_exception_fails_the_test(self):
        def action():
            class Broken:
                def __del__(self):
                    raise RuntimeError("destructor failed")
            value = Broken()
            del value
            gc.collect()
        result = self.run_inner(action)
        self.assertEqual(1, len(result.failures))
        self.assertIn("destructor failed", result.failures[0][1])


class GameCopyTests(unittest.TestCase):
    def test_all_mutations_and_case_failure_leave_original_files_untouched(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            originals = {"Ekd5.exe": b"fixture executable", "S_00.eex": b"root script",
                         "RS/S_00.eex": b"scene script", "SV/SV020.E5S": b"save",
                         "CczCustom.ini": b"settings", "data/resource.bin": b"resource"}
            for name, data in originals.items():
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            copy = None
            with self.assertRaisesRegex(RuntimeError, "case failed"):
                with isolated_game_copy(source) as copy:
                    for name in originals:
                        self.assertFalse(os.path.samefile(source / name, copy / name))
                        (copy / name).write_bytes(b"mutated")
                    (copy / "SV/SV001.E5S").write_bytes(b"new save")
                    raise RuntimeError("case failed")
            self.assertFalse(copy.exists())
            self.assertFalse((source / "SV/SV001.E5S").exists())
            self.assertEqual(originals, {name: (source / name).read_bytes() for name in originals})


@unittest.skipUnless(os.name == "nt", "Windows Job Object")
class CaseProcessTests(unittest.TestCase):
    def wait_gone(self, pid):
        try:
            psutil.Process(pid).wait(timeout=5)
        except psutil.NoSuchProcess:
            pass
        self.assertFalse(psutil.pid_exists(pid), f"测试子进程 {pid} 未退出")

    def test_orphan_cleanup_keeps_unrelated_process_alive(self):
        unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        try:
            with tempfile.TemporaryDirectory() as temporary:
                script = Path(temporary) / "case.py"
                script.write_text('''import subprocess, sys
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(child.pid, flush=True)
''', encoding="utf-8")
                env = dict(os.environ, PYTHONPATH=str(ROOT))
                # The venv redirector may kill its descendants on exit itself.
                # Use the base interpreter to exercise a genuine orphan in the Job.
                with patch("tests.helpers.case_process.sys", SimpleNamespace(executable=sys._base_executable)):
                    result, timed_out, lingering = run_case_process(script, ROOT, env, 10)
                pid = int(result.stdout.strip())
                self.assertEqual(125, result.returncode, repr((result.stdout, result.stderr, lingering, psutil.pid_exists(pid))))
                self.assertFalse(timed_out)
                self.assertIn(pid, lingering)
                self.wait_gone(pid)
                self.assertIsNone(unrelated.poll())
        finally:
            unrelated.kill()
            unrelated.wait(timeout=5)

    def test_timeout_cleans_descendant_tree_including_non_game_workers(self):
        with tempfile.TemporaryDirectory() as temporary:
            script = Path(temporary) / "case.py"
            marker = Path(temporary) / "child.pid"
            script.write_text('''import os, subprocess, sys, time
from pathlib import Path
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
Path(os.environ['CHILD_MARKER']).write_text(str(child.pid))
time.sleep(60)
''', encoding="utf-8")
            env = dict(os.environ, PYTHONPATH=str(ROOT), CHILD_MARKER=str(marker))
            started = time.monotonic()
            result, timed_out, _ = run_case_process(script, ROOT, env, 2)
            self.assertTrue(timed_out)
            self.assertEqual(124, result.returncode)
            self.assertLess(time.monotonic() - started, 10)
            self.assertTrue(marker.exists())
            self.wait_gone(int(marker.read_text()))
