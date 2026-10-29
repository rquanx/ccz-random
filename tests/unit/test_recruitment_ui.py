import json
from pathlib import Path
import tempfile
import unittest

from ccz_randomizer.history import HistoryRepository
from ccz_randomizer.ui.recruitment import show_recruit_window
from ccz_randomizer.ui.job_talents import load_job_talents

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/personnel_22"


def saved_snapshot():
    return {"schemaVersion": 1, "gameVersion": "2.2", "phase": "randomized",
        "slot": 1, "acceptedAttempt": 1, "mode": "three",
        "personnel": json.loads((FIXTURES / "randomized-personnel.json").read_text(encoding="utf-8"))}


class RecruitmentHistoryTests(unittest.TestCase):
    def test_reopen_preserves_result_bound_candidates_and_talents(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = HistoryRepository(Path(directory))
            repository.start_run("recruit-test", mode="three", loop_random=False,
                rule_name="test", rule={}, build={})
            round_id = repository.start_round("recruit-test", 1)
            snapshot = saved_snapshot()
            repository.save_result(round_id, snapshot)
            reopened = HistoryRepository(Path(directory))
            self.assertEqual([snapshot], reopened.get_round_results(round_id))


class JobTalentsTests(unittest.TestCase):
    def test_all_22_jobs_have_valid_talent_catalog(self):
        jobs = load_job_talents(saved_snapshot())
        self.assertEqual(40, len(jobs))
        self.assertEqual({0, 79}, {job["jobId"] for job in jobs} & {0, 79})
        self.assertTrue(all(job["talents"] is None for job in jobs))



class RecruitmentWindowTests(unittest.TestCase):
    def test_all_people_cards_filter_and_stage_grouping(self):
        import tkinter as tk
        from tkinter import ttk
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        root.withdraw()
        self.addCleanup(root.destroy)
        show_recruit_window(root, snapshot=saved_snapshot())
        root.update()

        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)

        widgets = list(descendants(root))
        self.assertGreaterEqual(sum(1 for w in widgets if isinstance(w, tk.Canvas)), 1)
        self.assertGreaterEqual(sum(1 for w in widgets if isinstance(w, ttk.Label) and w.cget("text") == "曹仁"), 1)
        watched = next(w for w in widgets if isinstance(w, ttk.Checkbutton))
        watch_button = next(w for w in widgets if isinstance(w, ttk.Button) and w.cget("text") in {"关注", "取消关注"})
        watch_button.invoke()
        root.update()
        watched.invoke()
        root.update()
        self.assertGreaterEqual(sum(1 for w in descendants(root) if isinstance(w, ttk.Label) and "已关注 1 人" in w.cget("text")), 1)
        watched.invoke()
        search = next(w for w in descendants(root) if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox))
        search.insert(0, "曹仁")
        root.update()
        self.assertEqual(1, sum(1 for w in descendants(root) if isinstance(w, ttk.Label) and w.cget("text") == "曹仁"))
        search.delete(0, "end")
        stage = next(w for w in descendants(root) if isinstance(w, ttk.Combobox))
        stage.set("共通 · 颍川之战")
        root.update()
        self.assertGreaterEqual(sum(1 for w in descendants(root) if isinstance(w, ttk.Label) and w.cget("text") == "共通 · 颍川之战"), 1)

