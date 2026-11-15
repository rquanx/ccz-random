from tkinter import ttk
from ccz_randomizer.ui.inputs import TextEntry
"""Restore the optional special gate without changing existing independent gates."""
import copy
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from ccz_randomizer import app
from ccz_randomizer.rules.config import active_profile, default_rule_config, evaluate_skill_rules, validate_rule_config
from ccz_randomizer.rules.editor import ScoreGrid, show_rule_editor
from ccz_randomizer.rules.skill_defaults import SKILL_DEFAULTS
from ccz_randomizer.ui.result_details import format_result_detail
from tests.unit.test_rule_editor import descendants


class SpecialSkillAutoPassTests(unittest.TestCase):
    def test_special_gate_respects_toggle_effective_skills_and_score_boundary(self):
        # Actual game/profile entry, also shown in the user's screenshot.
        name = "特效模仿"
        self.assertTrue(any(row[0] == name and row[1] == 5 for row in SKILL_DEFAULTS))
        for mode in ("total", "average", "count"):
            for enabled, score, effective, expected in (
                (False, 5, True, False), (True, 4.9, True, False),
                (True, 5, True, True), (True, 6, True, True),
                (True, 5, False, False), (True, 0, True, False),
            ):
                with self.subTest(mode=mode, enabled=enabled, score=score, effective=effective):
                    config = default_rule_config()
                    profile = active_profile(config)
                    profile["sevenPerson"]["skillBaseScores"][name] = score
                    gate = dict(mode=mode, threshold=100, requiredCount=1, specialSkillAutoPass=enabled)
                    result = evaluate_skill_rules(config, 20, {"曹操": [name]}, set(), set(), {name},
                        qualification=gate, effective_skills_by_member={"曹操": [name] if effective else []})
                    self.assertEqual(expected, result.qualified)
                    self.assertEqual("special_skill" if expected else "", result.metrics["autoPassReason"])
                    self.assertEqual(score if effective else 0, result.metrics["skillScore"])
                    if expected:
                        view = format_result_detail(dict(mode="three", skill=app.skill_result_detail(result, ())))
                        self.assertIn("存在特殊特技", view["sections"][0]["explanation"])

    def test_existing_rule_does_not_enable_new_gate_from_obsolete_flag(self):
        config = default_rule_config()
        profile = active_profile(config)
        profile["sevenPerson"]["specialSkillAutoPass"] = True
        profile["skillQualification"].update(mode="total", threshold=100)
        current = active_profile(validate_rule_config(config))
        self.assertFalse(current["skillQualification"].get("specialSkillAutoPass", False))
        result = evaluate_skill_rules(config, 20, {"曹操": ["特效模仿"]}, set(), set(), {"特效模仿"},
            qualification=current["skillQualification"], effective_skills_by_member={"曹操": ["特效模仿"]})
        self.assertFalse(result.qualified)

    @patch("ccz_randomizer.rules.editor.ask_rule_change", new=lambda *args, **kwargs: "confirm")
    def test_editor_restores_controls_live_special_label_and_persists_settings(self):
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        config = default_rule_config()
        config["profiles"]["自定义"] = copy.deepcopy(active_profile(config))
        config["activeProfile"] = "自定义"
        active_profile(config).update(builtin=False, editorMode="advanced")
        saved = []
        with tempfile.TemporaryDirectory() as temp, patch("ccz_randomizer.rules.editor.show_toast"):
            show_rule_editor(root, Path(temp), config, app.JOB_MAP, app.TEAM_MEMBERS, SKILL_DEFAULTS, saved.append)
            root.update()
            editor = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
            check = next(w for w in descendants(editor) if isinstance(w, tk.Checkbutton)
                         and w.cget("text") == "出现特殊特技时直接合格")
            self.assertEqual(0, root.getvar(check.cget("variable")))
            check.invoke()
            label = next(w for w in descendants(editor) if isinstance(w, tk.Label)
                         and w.cget("text") == "特殊特技基础分 / 门槛")
            entry = next(w for w in label.master.grid_slaves(row=0, column=1) if isinstance(w, TextEntry))
            grid = next(w for w in descendants(editor) if isinstance(w, ScoreGrid) and w.exclusive_names)
            grid.search_var.set("特效模仿")
            root.update()
            def displayed_text():
                return {grid.canvas.itemcget(item, "text") for item in grid.canvas.find_all()
                        if grid.canvas.type(item) == "text"}
            self.assertIn("特殊 · 基础分", displayed_text())
            resolver = grid.category_resolver
            self.assertEqual("特殊", resolver("特效模仿", "5", ""))
            self.assertEqual("", resolver("特效模仿", "4.9", ""))
            entry.delete(0, "end")
            self.assertEqual("", resolver("特效模仿", "5", ""))
            entry.insert(0, "6")
            self.assertIn("基础分", displayed_text())
            self.assertNotIn("特殊 · 基础分", displayed_text())
            self.assertEqual("", resolver("特效模仿", "5", ""))
            self.assertEqual("特殊", resolver("特效模仿", "6", ""))
            next(variable for name, variable, _category in grid.items if name == "特效模仿").set("6")
            grid.refresh()
            self.assertIn("特殊 · 基础分", displayed_text())
            next(w for w in descendants(editor) if isinstance(w, ttk.Button) and w.cget("text") == "保存规则").invoke()
            root.update()
            current = active_profile(saved[-1])
            self.assertTrue(current["skillQualification"]["specialSkillAutoPass"])
            self.assertEqual(6, current["sevenPerson"]["specialSkillWeight"])
            editor.destroy()
            show_rule_editor(root, Path(temp), saved[-1], app.JOB_MAP, app.TEAM_MEMBERS, SKILL_DEFAULTS, saved.append)
            root.update()
            check = next(w for w in descendants(root) if isinstance(w, tk.Checkbutton)
                         and w.cget("text") == "出现特殊特技时直接合格")
            self.assertEqual(1, root.getvar(check.cget("variable")))
