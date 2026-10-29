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
        from tkinter import ttk
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        root.withdraw()
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
        buttons = {w.cget("text"): w for w in descendants(root) if isinstance(w, tk.Button)}
        buttons["兵种天赋"].invoke()
        root.update()
        job_window = next(w for w in descendants(root) if isinstance(w, tk.Toplevel) and w.title() == "2.2 兵种天赋")
        labels = [w.cget("text") for w in descendants(job_window) if isinstance(w, (tk.Label, ttk.Label))]
        self.assertIn("魔王", labels)
        self.assertIn("\n".join(jobs[0]["talents"]), labels)
        search = next(w for w in descendants(job_window) if isinstance(w, ttk.Entry))
        search.insert(0, "医师")
        root.update()
        labels = [w.cget("text") for w in descendants(job_window) if isinstance(w, (tk.Label, ttk.Label))]
        self.assertIn("医师", labels)
        self.assertNotIn("魔王", labels)
        job_window.destroy()
        buttons["招募人员信息"].invoke()
        root.update()
        recruit_window = next(w for w in descendants(root) if isinstance(w, tk.Toplevel) and w.title() == "2.2 招募人物")
        labels = [w.cget("text") for w in descendants(recruit_window) if isinstance(w, ttk.Label)]
        self.assertIn("曹仁", labels)
        self.assertIn("共通 · 颍川之战", labels)
