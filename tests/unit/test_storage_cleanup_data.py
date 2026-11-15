from contextlib import closing
import sqlite3
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch

from ccz_randomizer.history import HistoryRepository
from ccz_randomizer.runtime.storage_cleanup import clean_storage, scan_storage
from ccz_randomizer.statistics_store import StatisticsRepository
from ccz_randomizer.ui.storage_cleanup import show_storage_cleanup


class StorageCleanupDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.history = HistoryRepository(self.base)
        self.history.start_run("run", mode="three", loop_random=False, rule_name="test", rule={}, build={})
        self.statistics = StatisticsRepository(self.base)
        with self.statistics.connect() as db:
            db.execute("INSERT INTO coverage VALUES (7)")
        self.search = self.base / "ccz_fast_data/recruitment_searches.json"
        self.search.write_text('{"version":1,"keywords":["曹操"]}', encoding="utf-8")
        self.unknown = self.base / "ccz_fast_data/notes.txt"
        self.unknown.write_text("preserve", encoding="utf-8")

    def count(self, path, table):
        with closing(sqlite3.connect(path)) as db, db:
            return db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]

    def test_categories_are_independent_and_unknown_files_survive_all_cleanup(self):
        usage = scan_storage(self.base)
        self.assertGreater(usage["statistics"].total, 0)
        self.assertEqual(usage["searches"].total, self.search.stat().st_size)
        self.assertEqual(clean_storage(self.base, {"history"}), (1, 0))
        self.assertEqual(self.count(self.history.path, "runs"), 0)
        self.assertEqual(self.count(self.statistics.path, "coverage"), 1)
        self.assertTrue(self.search.exists())
        self.assertEqual(clean_storage(self.base, {"statistics"}), (1, 0))
        self.assertEqual(self.count(self.statistics.path, "coverage"), 0)
        self.assertTrue(self.search.exists())
        clean_storage(self.base, set(usage))
        self.assertFalse(self.search.exists())
        self.assertEqual(self.unknown.read_text(), "preserve")
        # Existing repository instances can still read/write after a clear.
        self.history.start_run("new", mode="three", loop_random=False, rule_name="new", rule={}, build={})
        self.assertEqual(self.count(self.history.path, "runs"), 1)
        with self.statistics.connect() as db:
            db.execute("INSERT INTO coverage VALUES (2)")
        self.assertEqual(self.count(self.statistics.path, "coverage"), 1)

    def test_locked_database_is_not_partially_cleared(self):
        with closing(sqlite3.connect(self.statistics.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self.assertEqual(clean_storage(self.base, {"statistics"}), (0, 1))
        self.assertEqual(self.count(self.statistics.path, "coverage"), 1)

    def test_history_clears_dependent_records_and_save_copies(self):
        with closing(sqlite3.connect(self.history.path)) as db, db:
            db.execute("INSERT INTO rounds(id,run_id,round_number,started_at,status) VALUES (1,'run',1,'2026-11-15','completed')")
            db.execute("INSERT INTO results(id,round_id,slot,accepted_attempt,created_at,mode,snapshot_json) VALUES (1,1,1,1,'2026-11-15','three','{}')")
            db.execute("INSERT INTO result_saves VALUES (1,'hash',?)", (b"save copy",))
            db.execute("INSERT INTO result_summaries VALUES (1,'{}')")
            db.execute("INSERT INTO result_annotations VALUES (1,'name','note',1)")
        self.assertEqual(clean_storage(self.base, {"history"}), (1, 0))
        for table in ("runs", "rounds", "results", "result_saves", "result_summaries", "result_annotations"):
            self.assertEqual(self.count(self.history.path, table), 0)

    def test_statistics_clear_removes_observations_and_can_record_again(self):
        from ccz_randomizer.statistics import StatisticsRecorder
        from tests.unit.test_statistics import runner_fixture
        def record(run_id):
            recorder = StatisticsRecorder(self.base, run_id=run_id, rule_name="规则", rule={}, mode="three")
            with recorder.attempt(runner_fixture(), round_number=1, slot=1, attempt=1):
                pass
            recorder.close()
        record("first")
        self.assertEqual(self.count(self.statistics.path, "attempts"), 1)
        self.assertGreater(self.count(self.statistics.path, "members"), 0)
        self.assertEqual(clean_storage(self.base, {"statistics"}), (1, 0))
        for table in ("rules", "attempts", "members", "skills", "reasons", "coverage", "equipment"):
            self.assertEqual(self.count(self.statistics.path, table), 0)
        record("second")
        self.assertEqual(self.count(self.statistics.path, "attempts"), 1)
        self.assertEqual(self.count(self.history.path, "runs"), 1)

    def test_search_cleanup_updates_open_window_and_does_not_restore_on_close(self):
        from ccz_randomizer.ui.search_memory import SearchMemory
        from ccz_randomizer.search_history import SearchHistory
        root = tk.Tk()
        self.addCleanup(root.destroy)
        query = tk.StringVar(value="曹操")
        entry = ttk.Entry(root, textvariable=query)
        entry.pack()
        content = ttk.Frame(root)
        content.pack()
        memory = SearchMemory(entry, query, self.search, has_matches=lambda _: True,
                              parent=root, before=content)
        root.update()
        self.assertEqual(memory.history.items, ["曹操"])
        clean_storage(self.base, {"searches"})
        root._ccz_cleaned_categories = {"searches"}
        root.event_generate("<<StorageCleaned>>")
        root.update()
        self.assertEqual(memory.history.items, [])
        self.assertEqual(query.get(), "曹操")
        entry.destroy()
        self.assertEqual(SearchHistory(self.search).items, [])

    def test_future_database_and_unknown_sidecars_are_preserved(self):
        with closing(sqlite3.connect(self.history.path)) as db, db:
            db.execute("PRAGMA user_version=99")
        orphan = self.base / "ccz_fast_data/history-v99.sqlite3-wal"
        orphan.write_bytes(b"preserve")
        self.assertEqual(clean_storage(self.base, {"history"}), (0, 2))
        self.assertEqual(self.count(self.history.path, "runs"), 1)
        self.assertEqual(orphan.read_bytes(), b"preserve")

    def test_confirmation_cancellation_and_confirmed_clear(self):
        root = tk.Tk()
        self.addCleanup(root.destroy)
        show_storage_cleanup(root, self.base)
        dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))

        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)

        def wait_idle():
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                root.update()
                buttons = [w for w in descendants(dialog) if isinstance(w, ttk.Button)]
                if buttons and all(str(w.cget("state")) == "normal" for w in buttons):
                    return buttons
                time.sleep(.01)
            self.fail("清理未完成")

        buttons = wait_idle()
        all_button = next(w for w in buttons if w.cget("text") == "全部清理")
        with patch("ccz_randomizer.ui.storage_cleanup.messagebox.askyesno", return_value=False) as prompt:
            all_button.invoke()
        self.assertIn("随机统计数据", prompt.call_args.args[1])
        self.assertIn("历史记录（含存档副本）", prompt.call_args.args[1])
        self.assertEqual(self.count(self.history.path, "runs"), 1)
        self.assertTrue(self.search.exists())
        with patch("ccz_randomizer.ui.storage_cleanup.messagebox.askyesno", return_value=True):
            all_button.invoke()
        wait_idle()
        self.assertEqual(self.count(self.history.path, "runs"), 0)
        self.assertEqual(self.count(self.statistics.path, "coverage"), 0)
        self.assertFalse(self.search.exists())
        self.assertTrue(self.unknown.exists())

    def test_running_task_prevents_clear_without_showing_confirmation(self):
        root = tk.Tk()
        self.addCleanup(root.destroy)
        show_storage_cleanup(root, self.base, is_running=lambda: True)
        root.update()
        dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
        deadline = time.monotonic() + 5
        button = dialog.winfo_children()[0].winfo_children()[-1]
        while str(button.cget("state")) != "normal" and time.monotonic() < deadline:
            root.update()
            time.sleep(.01)
        with patch("ccz_randomizer.ui.storage_cleanup.messagebox.askyesno") as prompt:
            button.invoke()
            prompt.assert_not_called()
        self.assertEqual(self.count(self.history.path, "runs"), 1)
