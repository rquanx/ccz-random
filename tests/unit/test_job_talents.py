from tkinter import ttk
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from ccz_randomizer.jobs import JOB_MAP
from ccz_randomizer.runtime.job_talents import read_job_talents
from ccz_randomizer.ui.job_talents import load_job_talents
from ccz_randomizer.ui.result_details import encode_result_detail, decode_result_detail, show_score_detail
from tests.unit.test_personnel_memory import RecordedReader

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/personnel_22"


class JobTalentsTests(unittest.TestCase):
    def test_runtime_catalog_includes_22_new_talents(self):
        catalog_path = Path(__file__).resolve().parents[2] / "resources/data/skills/runtime_skill_catalog.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        by_id = {row["id"]: row["name"] for row in catalog}
        self.assertEqual(
            {237: "超世之杰", 238: "战必先登", 239: "古之恶来"},
            {key: by_id[key] for key in (237, 238, 239)},
        )
        self.assertIn("辅助攻击格挡 +20%", by_id.values())
        self.assertIn("辅助全格挡 +16%", by_id.values())
        self.assertIn("辅助连击率 25%", by_id.values())

    def test_live_catalog_matches_personnel_from_same_recorded_game(self):
        jobs = read_job_talents(0, reader_factory=RecordedReader)
        by_id = {row["jobId"]: row["talents"] for row in jobs}
        self.assertEqual(set(JOB_MAP), set(by_id))
        people = json.loads((FIXTURES / "randomized-personnel.json").read_text(encoding="utf-8"))
        for person in people:
            self.assertEqual(person["jobTalents"], by_id[person["jobId"]], person["name"])

    def test_missing_history_is_distinct_from_no_talents(self):
        self.assertTrue(all(row["talents"] is None for row in load_job_talents({})))
        rows = load_job_talents({"jobTalents": [{"jobId": 0, "talents": []}]})
        self.assertEqual([], rows[0]["talents"])
        self.assertIsNone(rows[1]["talents"])

    def test_score_transport_preserves_the_result_snapshot(self):
        from ccz_randomizer.app import result_detail_for_runner
        jobs = read_job_talents(0, reader_factory=RecordedReader)
        people = json.loads((FIXTURES / "randomized-personnel.json").read_text(encoding="utf-8"))
        runner = SimpleNamespace(_result_outcome="accepted", _three_person_mode=True,
            _personnel_snapshot=people, _job_talents_snapshot=jobs)
        result = decode_result_detail(encode_result_detail(result_detail_for_runner(runner, 1, 2)))
        self.assertEqual(jobs, result["jobTalents"])
        self.assertEqual(people, result["personnel"])
        self.assertEqual(1, result["slot"])

    def test_actual_score_dialog_buttons_open_result_bound_views(self):
        import tkinter as tk
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        root.geometry("900x700")
        root.update()
        self.addCleanup(root.destroy)
        jobs = read_job_talents(0, reader_factory=RecordedReader)
        people = json.loads((FIXTURES / "randomized-personnel.json").read_text(encoding="utf-8"))
        result = dict(schemaVersion=1, gameVersion="2.2", phase="randomized", slot=1,
            resultSlot=1, attempt=1, label="合格", mode="three", jobTalents=jobs, personnel=people)
        show_score_detail(root, result)
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        buttons = {w.cget("text"): w for w in descendants(root) if isinstance(w, ttk.Button)}
        buttons["兵种天赋"].invoke()
        root.update()
        job_window = next(w for w in descendants(root) if isinstance(w, tk.Toplevel) and w.title() == "兵种天赋")
        canvas = next(w for w in descendants(job_window) if isinstance(w, tk.Canvas))
        labels = [canvas.itemcget(i, "text") for i in canvas.find_all() if canvas.type(i) == "text"]
        self.assertIn("魔王", labels)
        self.assertIn("\n".join(jobs[0]["talents"]), labels)
        search = next(w for w in descendants(job_window) if isinstance(w, ttk.Entry))
        search.insert(0, "医师")
        root.update()
        canvas = next(w for w in descendants(job_window) if isinstance(w, tk.Canvas))
        labels = [canvas.itemcget(i, "text") for i in canvas.find_all() if canvas.type(i) == "text"]
        self.assertIn("医师", labels)
        self.assertNotIn("魔王", labels)
        search.delete(0, "end")
        root.update()
        labels = [canvas.itemcget(i, "text") for i in canvas.find_all() if canvas.type(i) == "text"]
        for job in jobs:
            self.assertIn(JOB_MAP[job["jobId"]][0], labels)
        canvas.yview_moveto(1)
        root.update()
        self.assertGreater(canvas.yview()[0], 0)
        search.insert(0, "医师")
        root.update()
        self.assertEqual(0, canvas.yview()[0])
        job_window.geometry("680x480")
        root.update()
        for i in canvas.find_all():
            if canvas.type(i) == "text":
                self.assertLessEqual(canvas.bbox(i)[2], canvas.winfo_width())
        search.delete(0, "end")
        search.insert(0, "不存在的兵种")
        root.update()
        labels = [canvas.itemcget(i, "text") for i in canvas.find_all() if canvas.type(i) == "text"]
        self.assertEqual(["没有符合条件的兵种。"], labels)
        # Closing with a pending search must cancel the queued redraw.
        search.delete(0, "end")
        job_window.destroy()
        root.update()
        buttons["入队人员信息"].invoke()
        root.update()
        recruit_window = next(w for w in descendants(root) if isinstance(w, tk.Toplevel) and w.title() == "入队人员")
        canvas = next(w for w in descendants(recruit_window) if isinstance(w, tk.Canvas))
        import time
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            root.update()
            if any(canvas.itemcget(item, "text").startswith("曹仁 · ")
                   for item in canvas.find_all() if canvas.type(item) == "text"):
                break
            time.sleep(.002)
        texts = [canvas.itemcget(item, "text") for item in canvas.find_all() if canvas.type(item) == "text"]
        self.assertTrue(any(text.startswith("曹仁 · ") for text in texts))
        self.assertIn("颍川之战", texts)
