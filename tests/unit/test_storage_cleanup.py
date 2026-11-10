import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from ccz_randomizer.runtime.storage_cleanup import CATEGORIES, clean_storage, scan_storage


class StorageCleanupTests(unittest.TestCase):
    def test_footer_buttons_are_fully_visible_at_large_display_scaling(self):
        import tkinter as tk
        from tkinter import ttk
        from ccz_randomizer.ui.storage_cleanup import show_storage_cleanup
        root = tk.Tk()
        self.addCleanup(root.destroy)
        original_scaling = root.tk.call("tk", "scaling")
        try:
            for scaling in (1.333, 2.0, 2.667):
                with self.subTest(scaling=scaling), tempfile.TemporaryDirectory() as temp:
                    root.tk.call("tk", "scaling", scaling)
                    show_storage_cleanup(root, Path(temp))
                    root.update()
                    dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
                    footer = dialog.winfo_children()[0]
                    buttons = [w for w in footer.winfo_children() if isinstance(w, ttk.Button)]
                    self.assertEqual({w.cget("text") for w in buttons}, {"刷新", "全部清理"})
                    for button in buttons:
                        self.assertTrue(button.winfo_ismapped())
                        self.assertGreaterEqual(button.winfo_height(), button.winfo_reqheight())
                        self.assertLessEqual(button.winfo_rooty() + button.winfo_height(),
                                             dialog.winfo_rooty() + dialog.winfo_height())
                    dialog.destroy()
                    root.update()
        finally:
            root.tk.call("tk", "scaling", original_scaling)

    def test_window_shows_sizes_and_all_cleanup_refreshes_them(self):
        import tkinter as tk
        from tkinter import ttk
        from ccz_randomizer.ui.storage_cleanup import show_storage_cleanup
        root = tk.Tk()
        self.addCleanup(root.destroy)
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            path = base / "ccz_fast_logs/fast_20261001_120000.log"
            path.parent.mkdir()
            path.write_bytes(b"x" * 1024)
            os.utime(path, (time.time() - 172800,) * 2)
            show_storage_cleanup(root, base)
            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)
            def wait_idle():
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    root.update()
                    buttons = [w for w in descendants(root) if isinstance(w, ttk.Button)]
                    if buttons and all(str(w.cget("state")) == "normal" for w in buttons):
                        return
                    time.sleep(0.01)
                self.fail("空间清理未完成")
            wait_idle()
            labels = [str(w.cget("text")) for w in descendants(root) if isinstance(w, ttk.Label)]
            self.assertIn("1.0 KB", labels)
            next(w for w in descendants(root) if isinstance(w, ttk.Button) and w.cget("text") == "全部清理").invoke()
            wait_idle()
            self.assertFalse(path.exists())
            labels = [str(w.cget("text")) for w in descendants(root) if isinstance(w, ttk.Label)]
            self.assertNotIn("1.0 KB", labels)

    def test_classified_cleanup_preserves_results_recent_logs_and_live_sessions(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            def write(name, old=True):
                path = base / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"12345678")
                if old:
                    os.utime(path, (time.time() - 172800,) * 2)
                return path
            log = write("ccz_fast_logs/fast_20261001_120000.log")
            screenshot = write("ccz_fast_logs/fast_20261001_120000_inspection_failure_panel.png")
            recent = write("ccz_fast_logs/fast_20261029_120000.log", False)
            unknown = write("ccz_fast_logs/notes.txt")
            dead = write("ccz_fast_data/sandboxes/123-456/workers/game.dat")
            live = write("ccz_fast_data/sandboxes/789-456/workers/game.dat")
            unowned = write("ccz_fast_data/sandboxes/unknown/game.dat")
            result = write("randResult/loop/run/round-000001/SV001.E5S")
            with patch("ccz_randomizer.runtime.storage_cleanup.psutil.pid_exists", side_effect=lambda pid: pid == 789):
                usage = scan_storage(base)
                self.assertEqual(usage["logs"].total, 16)
                self.assertEqual(usage["logs"].cleanable, 8)
                self.assertEqual(usage["screenshots"].cleanable, 8)
                self.assertEqual(usage["sandboxes"].cleanable, 8)
                self.assertEqual(clean_storage(base, {"logs"}), (1, 0))
                self.assertTrue(screenshot.exists())
                self.assertFalse(log.exists())
                self.assertEqual(
                    clean_storage(base, {"logs", "screenshots", "sandboxes"}),
                    (2, 0),
                )
                self.assertFalse(dead.exists())
                for path in (recent, unknown, live, unowned, result):
                    self.assertEqual(path.read_bytes(), b"12345678")

    def test_shared_game_files_are_not_counted_as_reclaimable_and_original_survives(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            original = base / "game.dat"
            original.write_bytes(b"game resources")
            session = base / "ccz_fast_data/sandboxes/123-456"
            session.mkdir(parents=True)
            os.link(original, session / "game.dat")
            with patch("ccz_randomizer.runtime.storage_cleanup.psutil.pid_exists", return_value=False):
                self.assertEqual(scan_storage(base)["sandboxes"].cleanable, 0)
                clean_storage(base, {"sandboxes"})
            self.assertEqual(original.read_bytes(), b"game resources")

    def test_cleanup_rechecks_session_is_not_running(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            path = base / "ccz_fast_data/sandboxes/123-456/game.dat"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"game")
            with patch("ccz_randomizer.runtime.storage_cleanup.psutil.pid_exists", return_value=False):
                self.assertEqual(scan_storage(base)["sandboxes"].cleanable, 4)
            with patch("ccz_randomizer.runtime.storage_cleanup.psutil.pid_exists", return_value=True):
                self.assertEqual(clean_storage(base, {"sandboxes"}), (0, 0))
            self.assertTrue(path.exists())

    def test_results_and_history_are_counted_and_cleaned_by_category(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            result = base / "randResult/loop/round-000001/panel.png"
            result.parent.mkdir(parents=True)
            result.write_bytes(b"result" * 100)
            history = base / "ccz_fast_data/history.sqlite3"
            history.parent.mkdir(parents=True)
            history.write_bytes(b"history" * 200)
            sidecar = base / "ccz_fast_data/history.sqlite3-wal"
            sidecar.write_bytes(b"wal" * 50)

            usage = scan_storage(base)
            self.assertEqual(usage["results"].total, result.stat().st_size)
            self.assertEqual(usage["results"].cleanable, result.stat().st_size)
            self.assertEqual(
                usage["history"].total,
                history.stat().st_size + sidecar.stat().st_size,
            )
            self.assertEqual(
                clean_storage(base, {"results"}),
                (1, 0),
            )
            self.assertFalse(result.exists())
            self.assertTrue(history.exists())
            self.assertEqual(clean_storage(base, {"history"}), (2, 0))
            self.assertFalse(history.exists())
            self.assertFalse(sidecar.exists())
