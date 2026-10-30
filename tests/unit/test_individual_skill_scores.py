import copy
import unittest
from types import SimpleNamespace

from ccz_randomizer import app
from ccz_randomizer.rules.config import (
    active_profile, apply_simple_settings, build_rule_export, default_rule_config,
    evaluate_skill_rules, merge_rule_export, validate_rule_config,
)
from ccz_randomizer.rules.skill_defaults import SKILL_DEFAULTS


class IndividualSkillScoreTests(unittest.TestCase):
    def setUp(self):
        self.warrior = next(row[0] for row in SKILL_DEFAULTS
                            if row[2:] == ("优质", "WARRIOR"))
        self.special = next(row[0] for row in SKILL_DEFAULTS if row[2] == "特殊")

    def evaluate(self, config, name, job_type="MASTER"):
        member = SimpleNamespace(name="张宝", job=SimpleNamespace(name="道士", type=job_type),
            skillList=[SimpleNamespace(name=name, type="WARRIOR")])
        eligible = app.effective_member_skill_names(config, [member])
        return evaluate_skill_rules(config, 10, {"张宝": [name]},
            {row[0] for row in SKILL_DEFAULTS if row[2] == "优质"},
            {row[0] for row in SKILL_DEFAULTS if row[2] == "强力"},
            {row[0] for row in SKILL_DEFAULTS if row[2] == "特殊"}, eligible,
            qualification=dict(mode="total", threshold=0.25, requiredCount=1))

    def test_migration_preserves_weights_and_previous_exemption(self):
        config = default_rule_config()
        seven = active_profile(config)["sevenPerson"]
        seven["ordinarySkillWeight"] = 1.5
        seven["skillBaseScores"][self.warrior] = 6
        seven["skillTypeOverrides"][self.warrior] = "WARRIOR"
        config = validate_rule_config(config)
        migrated = active_profile(config)["sevenPerson"]
        self.assertEqual(6, migrated["skillBaseScores"][self.warrior])
        self.assertEqual("NONE", migrated["skillTypeOverrides"][self.warrior])
        another = next(row[0] for row in SKILL_DEFAULTS if row[2] == "优质" and row[0] != self.warrior)
        self.assertEqual(1.5, migrated["skillBaseScores"][another])
        self.assertEqual(6, self.evaluate(config, self.warrior).metrics["skillScore"])
        self.assertEqual(config, validate_rule_config(config))

    def test_increasing_score_does_not_bypass_matching(self):
        config = validate_rule_config(default_rule_config())
        seven = active_profile(config)["sevenPerson"]
        seven["skillBaseScores"][self.warrior] = 10
        config = validate_rule_config(config)
        self.assertFalse(self.evaluate(config, self.warrior).qualified)
        self.assertEqual(10, self.evaluate(config, self.warrior, "WARRIOR").metrics["skillScore"])

    def test_fractional_score_counts_without_old_tier_floor(self):
        config = validate_rule_config(default_rule_config())
        seven = active_profile(config)["sevenPerson"]
        seven["skillBaseScores"][self.special] = 0.5
        result = self.evaluate(config, self.special)
        self.assertTrue(result.qualified)
        self.assertEqual(0.5, result.metrics["skillScore"])
        seven["skillTypeOverrides"][self.special] = "WARRIOR"
        self.assertFalse(self.evaluate(validate_rule_config(config), self.special).qualified)

    def test_import_and_simple_mode_preserve_independent_settings(self):
        config = validate_rule_config(default_rule_config())
        profile = active_profile(config)
        profile["sevenPerson"]["skillBaseScores"][self.warrior] = 8
        profile["simpleSettings"]["strongSkillImportance"] = "较高"
        before = copy.deepcopy(profile["sevenPerson"])
        apply_simple_settings(profile)
        self.assertEqual(before["skillBaseScores"], profile["sevenPerson"]["skillBaseScores"])
        exported = build_rule_export(config)
        imported, names = merge_rule_export(default_rule_config(), exported)
        seven = imported["profiles"][names[0]]["sevenPerson"]
        self.assertEqual(8, seven["skillBaseScores"][self.warrior])
        self.assertEqual("WARRIOR", seven["skillTypeOverrides"][self.warrior])
