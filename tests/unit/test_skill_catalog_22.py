import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ccz_randomizer import app
from ccz_randomizer.rules.config import default_rule_config, active_profile
from ccz_randomizer.runtime.skill_memory import read_skill_memory, normalize_skill_name
from tests.unit.test_personnel_memory import RecordedReader


class SkillCatalog22Tests(unittest.TestCase):
    def test_catalog_matches_all_real_22_names_formats_and_parameters(self):
        snapshot = read_skill_memory(0, [0], reader_factory=RecordedReader)
        rows = app.runtime_skill_catalog_rows()
        self.assertEqual(240, len(rows))
        for row in rows:
            definition = snapshot.catalog[row["id"]]
            self.assertEqual(
                (definition.display_name, definition.base_name, definition.format_type, definition.parameter),
                (row["name"], row["baseName"], row["formatType"], row["parameter"]),
                row["id"],
            )

    def test_editor_and_live_scoring_agree_for_changed_numeric_talents(self):
        # This also initializes the shipped legacy scoring model.
        catalog = {row[0]: row[1:] for row in app.skill_score_catalog()}
        import task.CczReRandTask as task_module
        snapshot = read_skill_memory(0, [0], reader_factory=RecordedReader)
        definitions = tuple(snapshot.catalog[i] for i in (32, 33, 34, 72, 115, 210, 237, 238, 239))
        memory_member = SimpleNamespace(record_index=0, member_id=0, job_id=0,
                                        personal=definitions, job=())
        snapshot = SimpleNamespace(members=(memory_member,), record_array_base=0,
                                   rule_table_base=0, direct_job_match=False)
        member = SimpleNamespace(name="曹操", job=SimpleNamespace(name="群雄", type="ALL_ROUNDER"))
        with patch.object(app, "read_skill_memory", return_value=snapshot):
            app.load_member_skills_from_memory(task_module, 0, (0,), (member,))
        canonical = {skill.internal_skill_id: skill.canonical_name for skill in member.skillList}
        self.assertEqual("减轻远距损伤50%", canonical[34])
        self.assertEqual("盾反20%", canonical[115])
        rules = default_rule_config()
        evaluation = app.evaluate_task_skill_rules(rules, task_module, (member,), 5.0)
        for detail in evaluation.metrics["skillDetails"]:
            self.assertEqual(catalog[detail["name"]][0], detail["score"], detail["name"])
        self.assertIn("盾反 15%", catalog)
        self.assertIn("减轻远距损伤 -40%", catalog)
        self.assertNotIn("盾反20%", catalog)
        self.assertNotIn("减轻远距损伤50%", catalog)
        self.assertNotIn("能力替换-攻替爆", catalog)

        # Existing user overrides follow numeric adjustments, with new names
        # retained in the result rather than replacing them with legacy text.
        active_profile(rules)["sevenPerson"]["skillBaseScores"] = {"盾反20%": 3.5}
        result = app.evaluate_task_skill_rules(rules, task_module, (member,), 5.0)
        score = next(d["score"] for d in result.metrics["skillDetails"] if d["name"] == "盾反 15%")
        self.assertEqual(3.5, score)

    def test_editor_keeps_saved_score_and_type_when_numeric_name_changes(self):
        from ccz_randomizer.rules.editor import skill_override
        self.assertEqual(3.5, skill_override({"盾反20%": 3.5}, "盾反 15%", 0))
        self.assertEqual("WARRIOR", skill_override({"盾反20%": "WARRIOR"}, "盾反 15%", "ALL_ROUNDER"))
        self.assertEqual(4, skill_override({"盾反20%": 3.5, "盾反 15%": 4}, "盾反 15%", 0))

    def test_changed_effects_do_not_inherit_scores_from_different_targets(self):
        for old, new in (("能力替换 攻→爆", "能力替换 防→攻"),
                         ("能力替换 攻→防精", "能力替换 攻→防"),
                         ("策略反击 浊流", "策略反击 烈火")):
            self.assertNotEqual(normalize_skill_name(old), normalize_skill_name(new))
