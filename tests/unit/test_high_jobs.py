import copy
import json
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from ccz_randomizer import app
from ccz_randomizer.rules.config import active_profile, default_rule_config, evaluate_job_rules, evaluate_skill_rules, validate_rule_config
from ccz_randomizer.rules.editor import show_rule_editor
from ccz_randomizer.rules.skill_defaults import SKILL_DEFAULTS
from ccz_randomizer.ui.inputs import TextEntry
from ccz_randomizer.ui.recruitment import show_recruit_window, high_job_names
from ccz_randomizer.ui.result_details import format_result_detail
from tests.unit.test_recruitment_ui import saved_snapshot, wait_until
from tests.unit.test_rule_editor import descendants


class HighJobTests(unittest.TestCase):
    def test_autopass_uses_selected_members_base_score_boundary_and_toggle(self):
        entries = sorted(app.JOB_MAP.values(), key=lambda row: row[1])
        low, high = entries[0], next(row for row in entries if row[1] == 9)
        jobs = [dict(name=row[0], score=row[1], type=row[2]) for row in (high, low)]
        members = [dict(name=name, primaryType="NONE", secondaryType="NONE") for name in ("曹操", "夏侯惇")]
        for mode in ("average", "total", "count"):
            for enabled, base, selected, expected in ((False, 9, ["曹操"], False),
                    (True, 8.99, ["曹操"], False), (True, 9, ["曹操"], True),
                    (True, 10, ["曹操"], True), (True, 9, ["夏侯惇"], False)):
                with self.subTest(mode=mode, enabled=enabled, base=base, selected=selected):
                    config = default_rule_config()
                    profile = active_profile(config)
                    profile["threePerson"].update(jobQualificationMode=mode, minJobAverage=20,
                                                 qualifiedMembers=selected, minQualifiedCount=1)
                    profile["jobScoring"].update(highJobAutoPass=enabled, highJobThreshold=9,
                        jobBaseScores={high[0]: base}, baseScoreWeight=.5)
                    result = evaluate_job_rules(config, "three", jobs, members)
                    self.assertEqual(expected, result.qualified)
                    self.assertEqual("high_job" if expected else "", result.metrics["autoPassReason"])
                    if expected:
                        explanation = format_result_detail({"job": {"qualified": True,
                            "metrics": result.metrics, "members": []}})["sections"][0]["explanation"]
                        self.assertIn("高阶兵种", explanation)
                        skill = evaluate_skill_rules(config, result.metrics["average"],
                            {"曹操": []}, set(), set(), set(),
                            qualification=dict(mode="total", threshold=100, requiredCount=1))
                        self.assertFalse(skill.qualified)

    def test_existing_rules_default_off_and_invalid_settings_rejected(self):
        config = default_rule_config()
        scoring = active_profile(config)["jobScoring"]
        scoring.pop("highJobThreshold")
        scoring.pop("highJobAutoPass")
        active_profile(config)["sevenPerson"]["highJobAutoPass"] = True
        current = active_profile(validate_rule_config(config))["jobScoring"]
        self.assertEqual(9, current["highJobThreshold"])
        self.assertFalse(current["highJobAutoPass"])
        for key, value in (("highJobThreshold", -1), ("highJobThreshold", float("nan")),
                           ("highJobThreshold", 21), ("highJobAutoPass", "true")):
            bad = copy.deepcopy(config)
            active_profile(bad)["jobScoring"][key] = value
            with self.assertRaises(ValueError):
                validate_rule_config(bad)

    @patch("ccz_randomizer.rules.editor.ask_rule_change", new=lambda *args, **kwargs: "confirm")
    def test_editor_saves_and_reopens_high_job_settings(self):
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        config = default_rule_config()
        config["profiles"]["自定义"] = copy.deepcopy(active_profile(config))
        config["activeProfile"] = "自定义"
        active_profile(config).update(builtin=False, editorMode="advanced")
        saved = []
        with tempfile.TemporaryDirectory() as temp, patch("ccz_randomizer.rules.editor.show_toast"):
            def open_editor(config):
                show_rule_editor(root, Path(temp), config, app.JOB_MAP, app.TEAM_MEMBERS, SKILL_DEFAULTS, saved.append)
                root.update()
                return next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
            editor = open_editor(config)
            check = next(w for w in descendants(editor) if isinstance(w, tk.Checkbutton)
                         and w.cget("text") == "出现高阶兵种时直接合格")
            self.assertEqual(0, root.getvar(check.cget("variable")))
            check.invoke()
            label = next(w for w in descendants(editor) if isinstance(w, tk.Label)
                         and w.cget("text") == "高阶兵种基础分 / 门槛")
            entry = next(w for w in label.master.grid_slaves(row=5, column=1) if isinstance(w, TextEntry))
            entry.delete(0, "end")
            entry.insert(0, "10")
            next(w for w in descendants(editor) if isinstance(w, ttk.Button) and w.cget("text") == "保存规则").invoke()
            self.assertEqual(10, active_profile(saved[-1])["jobScoring"]["highJobThreshold"])
            self.assertTrue(active_profile(saved[-1])["jobScoring"]["highJobAutoPass"])
            editor.destroy()
            editor = open_editor(saved[-1])
            check = next(w for w in descendants(editor) if isinstance(w, tk.Checkbutton)
                         and w.cget("text") == "出现高阶兵种时直接合格")
            self.assertEqual(1, root.getvar(check.cget("variable")))

    def test_recruitment_high_filter_red_names_and_rule_refresh(self):
        root = tk.Tk()
        self.addCleanup(root.destroy)
        snapshot = saved_snapshot()
        rows = snapshot["personnel"][:3]
        for row in rows:
            row["job"] = app.JOB_MAP[row["jobId"]][0]
        snapshot.update(personnel=rows, fixedPersonnel=[])
        high = rows[0]["job"]
        selected = [{"jobScoring": {"highJobThreshold": 20,
                    "jobBaseScores": {high: 20}}}]
        root._current_rule_profile = lambda: selected[0]
        self.assertIn(high, high_job_names(selected[0]))
        with tempfile.TemporaryDirectory() as temp:
            show_recruit_window(root, snapshot=snapshot, history_path=Path(temp)/"searches.json")
            root.update()
            canvas = next(w for w in descendants(root) if isinstance(w, tk.Canvas))
            def texts():
                return {canvas.itemcget(i, "text"): canvas.itemcget(i, "fill")
                        for i in canvas.find_all() if canvas.type(i) == "text"}
            wait_until(root, lambda: high in texts())
            self.assertEqual("#B42318", texts()[high])
            check = next(w for w in descendants(root) if isinstance(w, ttk.Checkbutton)
                         and w.cget("text") == "只看高阶兵种")
            check.invoke()
            wait_until(root, lambda: rows[0]["name"] + " · " in texts()
                       and not any(text.startswith(rows[1]["name"] + " ·") for text in texts()))
            selected[0]["jobScoring"]["jobBaseScores"][high] = 19
            root.event_generate("<<RulesUpdated>>")
            wait_until(root, lambda: "没有符合条件的入队人员" in texts())

    def test_recruitment_choices_combine_high_special_and_keyword_filters(self):
        root = tk.Tk()
        self.addCleanup(root.destroy)
        fixture = Path(__file__).resolve().parents[1] / "fixtures/personnel_220_1104/randomized-result.json"
        snapshot = json.loads(fixture.read_text(encoding="utf-8"))
        rule = {"jobScoring": {"highJobThreshold": 9},
                "sevenPerson": {"specialSkillWeight": 20, "skillBaseScores": {}}}
        with tempfile.TemporaryDirectory() as temp:
            show_recruit_window(root, snapshot=snapshot, rule=rule, history_path=Path(temp)/"searches.json")
            root.update()
            widgets = list(descendants(root))
            canvas = next(w for w in widgets if isinstance(w, tk.Canvas))
            entry = next(w for w in widgets if isinstance(w, ttk.Entry))
            checks = {w.cget("text"): w for w in widgets if isinstance(w, ttk.Checkbutton)}
            checks["只看高阶兵种"].invoke()
            entry.insert(0, "曹纯")
            def texts():
                return [canvas.itemcget(i, "text") for i in canvas.find_all() if canvas.type(i) == "text"]
            wait_until(root, lambda: "虎豹骑" in texts() and "曹纯 · " in texts()
                       and not any("曹休" in text for text in texts()))
            # The qualifying option is colored; the lower-tier actual job stays neutral.
            self.assertTrue(any(canvas.itemcget(i, "text") == "道士"
                                and canvas.itemcget(i, "fill") != "#B42318"
                                for i in canvas.find_all() if canvas.type(i) == "text"))
            checks["只看特殊技能"].invoke()
            wait_until(root, lambda: "没有符合条件的入队人员" in texts())
            checks["只看特殊技能"].invoke()
            wait_until(root, lambda: "虎豹骑" in texts())
