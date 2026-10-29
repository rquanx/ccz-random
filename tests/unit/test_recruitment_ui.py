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
        canvas = next(w for w in widgets if isinstance(w, tk.Canvas))
        def texts():
            return [canvas.itemcget(item, "text") for item in canvas.find_all() if canvas.type(item) == "text"]
        self.assertIn("曹仁", texts())
        watched = next(w for w in widgets if isinstance(w, ttk.Checkbutton))
        watch_item = next(item for item in canvas.find_all() if any(tag.startswith("watch:") for tag in canvas.gettags(item)))
        x1, y1, x2, y2 = canvas.bbox(watch_item)
        canvas.event_generate("<Button-1>", x=(x1+x2)//2, y=(y1+y2)//2)
        root.update()
        search = next(w for w in descendants(root) if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox))
        search.insert(0, "曹仁")
        root.after(150, root.quit); root.mainloop()
        self.assertEqual(1, texts().count("曹仁"))
        search.delete(0, "end")
        stage = next(w for w in descendants(root) if isinstance(w, ttk.Combobox))
        stage.set("共通 · 颍川之战")
        root.update()
        self.assertIn("共通 · 颍川之战", texts())

