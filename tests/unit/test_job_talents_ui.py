import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from ccz_randomizer.jobs import JOB_MAP
from ccz_randomizer.runtime.skill_memory import normalize_skill_name
from ccz_randomizer.ui.job_talents import show_job_talents_window
from tests.unit.test_recruitment_ui import saved_snapshot, wait_until


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class JobTalentFilterTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)

    def open(self, snapshot):
        with patch('ccz_randomizer.ui.job_talents.show_centered'):
            show_job_talents_window(self.root, snapshot=snapshot)
        dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
        self.assertEqual('兵种天赋', dialog.title())
        canvas = next(w for w in descendants(dialog) if isinstance(w, tk.Canvas))
        checks = {w.cget('text'): w for w in descendants(dialog) if isinstance(w, ttk.Checkbutton)}
        return dialog, canvas, checks

    def names(self, canvas):
        titles = {value[0] for value in JOB_MAP.values()}
        return {canvas.itemcget(item, 'text') for item in canvas.find_all()
                if canvas.type(item) == 'text' and canvas.itemcget(item, 'text') in titles}

    def test_special_high_search_intersection_and_live_rules_use_recorded_talents(self):
        fixture = Path(__file__).parents[1] / 'fixtures/personnel_220_1104/randomized-result.json'
        snapshot = json.loads(fixture.read_text(encoding='utf-8'))
        rows = snapshot['jobTalents']
        scores = {normalize_skill_name(talent): 0 for row in rows for talent in row['talents']}
        special = {normalize_skill_name(rows[i]['talents'][0]) for i in (0, 2)}
        scores.update(dict.fromkeys(special, 5))
        job_scores = {value[0]: 0 for value in JOB_MAP.values()}
        high = {JOB_MAP[rows[i]['jobId']][0] for i in (0, 1)}
        job_scores.update(dict.fromkeys(high, 10))
        selected = [{'sevenPerson': {'specialSkillWeight': 5, 'skillBaseScores': scores},
                     'jobScoring': {'highJobThreshold': 9, 'jobBaseScores': job_scores}}]
        self.root._current_rule_profile = lambda: selected[0]
        dialog, canvas, checks = self.open(snapshot)
        all_names = {value[0] for value in JOB_MAP.values()}
        wait_until(self.root, lambda: self.names(canvas) == all_names)
        expected = {JOB_MAP[row['jobId']][0] for row in rows
                    if special & {normalize_skill_name(t) for t in row['talents']}}
        checks['只看特殊技能'].invoke()
        wait_until(self.root, lambda: self.names(canvas) == expected)
        entry = next(w for w in descendants(dialog) if isinstance(w, ttk.Entry))
        searched = JOB_MAP[rows[2]['jobId']][0]
        entry.insert(0, searched)
        wait_until(self.root, lambda: self.names(canvas) == {searched})
        checks['只看高阶兵种'].invoke()
        wait_until(self.root, lambda: not self.names(canvas))
        entry.delete(0, 'end')
        wait_until(self.root, lambda: self.names(canvas) == expected & high)
        checks['只看特殊技能'].invoke()
        wait_until(self.root, lambda: self.names(canvas) == high)
        selected[0] = dict(selected[0], jobScoring={'highJobThreshold': 9,
            'jobBaseScores': {name: 10 if name == searched else 0 for name in all_names}})
        self.root.event_generate('<<RulesUpdated>>')
        wait_until(self.root, lambda: self.names(canvas) == {searched})
        dialog.destroy()
        self.assertFalse(self.root._ccz_window_events.callbacks['<<RulesUpdated>>'])

    def test_special_filter_does_not_treat_missing_historical_talents_as_known(self):
        dialog, canvas, checks = self.open(saved_snapshot())
        wait_until(self.root, lambda: len(self.names(canvas)) == len(JOB_MAP))
        checks['只看特殊技能'].invoke()
        wait_until(self.root, lambda: not self.names(canvas))
        checks['只看特殊技能'].invoke()
        wait_until(self.root, lambda: len(self.names(canvas)) == len(JOB_MAP))
        self.assertTrue(any('未采集' in canvas.itemcget(item, 'text') for item in canvas.find_all()
                            if canvas.type(item) == 'text'))
        dialog.destroy()
