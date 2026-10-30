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
        "personnel": json.loads((FIXTURES / "randomized-personnel.json").read_text(encoding="utf-8")),
        "fixedPersonnel": json.loads((FIXTURES / "randomized-fixed-personnel.json").read_text(encoding="utf-8"))}


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
        root.deiconify()
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
        self.assertTrue(any(text.startswith("曹仁 · ") for text in texts()))
        self.assertFalse(any(isinstance(w, ttk.Checkbutton) for w in widgets))
        dialog = next(w for w in widgets if isinstance(w, tk.Toplevel))
        self.assertEqual(dialog.title(), "入队人员")
        dialog.geometry("820x560")
        root.update()
        root.after(500, root.quit); root.mainloop()
        rectangles = [canvas.coords(item) for item in canvas.find_all()
                      if canvas.type(item) == "rectangle"]
        self.assertTrue(rectangles)
        self.assertTrue(all(bounds[2] <= canvas.winfo_width() for bounds in rectangles))
        for top in {bounds[1] for bounds in rectangles}:
            self.assertEqual(len({bounds[3] for bounds in rectangles if bounds[1] == top}), 1)
        from ccz_randomizer.recruitment import parse_recruits
        snapshot = saved_snapshot()
        by_id = {row.record_index: row for row in parse_recruits(dict(snapshot, personnel=snapshot["personnel"] + snapshot["fixedPersonnel"]))}
        for item in canvas.find_all():
            if canvas.type(item) != "rectangle":
                continue
            tag = canvas.gettags(item)[0]
            row = by_id[int(tag.split(":")[1])]
            text_items = [i for i in canvas.find_withtag(tag) if canvas.type(i) == "text"]
            cost = next(i for i in text_items if canvas.itemcget(i, "text") == ("固定" if row.entry_kind == "fixed" else f"{row.cost}次"))
            title = next(i for i in text_items if canvas.itemcget(i, "text").startswith(row.name + " · "))
            self.assertLess(canvas.bbox(title)[2], canvas.bbox(cost)[0])
        # Cards wrap within the viewport, without horizontal scrolling.
        self.assertEqual(canvas.xview(), (0.0, 1.0))
        self.assertFalse(any(text.startswith("共通 · ") for text in texts()))
        self.assertIn("兵种天赋", texts())
        self.assertIn("人物天赋", texts())
        search = next(w for w in descendants(root) if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox))
        search.insert(0, "曹仁")
        root.after(150, root.quit); root.mainloop()
        self.assertEqual(1, sum(text.startswith("曹仁 · ") for text in texts()))
        search.delete(0, "end")
        stage = next(w for w in descendants(root) if isinstance(w, ttk.Combobox))
        stage.set("颍川之战")
        root.update()
        root.after(500, root.quit); root.mainloop()
        self.assertIn("颍川之战", texts())
        self.assertIn("固定入队 · 战前（随机预览）", texts())
        self.assertIn("可招募 · 战后", texts())
        fixed_bottoms, recruit_tops = [], []
        for item in canvas.find_all():
            if canvas.type(item) != "rectangle":
                continue
            index = int(canvas.gettags(item)[0].split(":")[1])
            bounds = canvas.coords(item)
            if by_id[index].entry_kind == "fixed":
                fixed_bottoms.append(bounds[3])
            else:
                recruit_tops.append(bounds[1])
        self.assertEqual(len(fixed_bottoms), 3)
        self.assertGreater(min(recruit_tops), max(fixed_bottoms))

