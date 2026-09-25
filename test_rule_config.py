import json
import tempfile
import unittest
from pathlib import Path

from rule_config import (
    DEFAULT_PROFILE_NAME,
    apply_simple_settings,
    default_rule_config,
    evaluate_job_rules,
    evaluate_skill_rules,
    load_rule_config,
    save_rule_config,
    validate_rule_config,
)


MEMBERS = [
    {"name": "曹操", "primaryType": "ALL_ROUNDER", "secondaryType": "WARRIOR"},
    {"name": "夏侯惇", "primaryType": "WARRIOR", "secondaryType": "ALL_ROUNDER"},
    {"name": "曹仁", "primaryType": "ALL_ROUNDER", "secondaryType": "WARRIOR"},
]


class RuleConfigTests(unittest.TestCase):
    def test_default_job_rule_matches_existing_threshold(self):
        jobs = [
            {"name": "群雄", "score": 8, "type": "ALL_ROUNDER"},
            {"name": "虎豹骑", "score": 9, "type": "WARRIOR"},
            {"name": "都督", "score": 9, "type": "ALL_ROUNDER"},
        ]
        result = evaluate_job_rules(
            default_rule_config(), "three", jobs, MEMBERS
        )
        self.assertTrue(result.qualified)

    def test_job_base_score_override_changes_result(self):
        config = default_rule_config()
        profile = config["profiles"][DEFAULT_PROFILE_NAME]
        profile["jobScoring"]["jobBaseScores"] = {
            "群雄": 1,
            "虎豹骑": 1,
            "都督": 1,
        }
        jobs = [
            {"name": "群雄", "score": 8, "type": "ALL_ROUNDER"},
            {"name": "虎豹骑", "score": 9, "type": "WARRIOR"},
            {"name": "都督", "score": 9, "type": "ALL_ROUNDER"},
        ]
        result = evaluate_job_rules(config, "three", jobs, MEMBERS)
        self.assertFalse(result.qualified)
        self.assertEqual(
            ("兵种综合评价未达到当前规则要求",), result.reasons
        )

    def test_member_affinity_is_configurable_by_type(self):
        config = default_rule_config()
        profile = config["profiles"][DEFAULT_PROFILE_NAME]
        profile["threePerson"]["minJobAverage"] = 8.4
        profile["memberAffinity"]["曹操"] = {
            "primaryType": "MASTER",
            "secondaryType": "WARRIOR",
        }
        jobs = [
            {"name": "群雄", "score": 8, "type": "ALL_ROUNDER"},
            {"name": "虎豹骑", "score": 8, "type": "WARRIOR"},
            {"name": "都督", "score": 8, "type": "ALL_ROUNDER"},
        ]
        result = evaluate_job_rules(config, "three", jobs, MEMBERS)
        self.assertFalse(result.qualified)

    def test_member_affinity_can_be_disabled(self):
        config = default_rule_config()
        profile = config["profiles"][DEFAULT_PROFILE_NAME]
        profile["memberAffinity"]["曹操"] = {
            "primaryType": "NONE",
            "secondaryType": "NONE",
        }
        normalized = validate_rule_config(config)
        jobs = [
            {"name": "群雄", "score": 7.4, "type": "ALL_ROUNDER"},
        ]
        result = evaluate_job_rules(
            normalized,
            "three",
            jobs,
            [{"name": "曹操"}],
        )
        self.assertTrue(result.qualified)
        self.assertEqual(7.4, result.metrics["average"])

    def test_duplicate_skills_are_counted_per_occurrence(self):
        config = default_rule_config()
        result = evaluate_skill_rules(
            config,
            7.6,
            {
                "曹操": ["好特技", "好特技"],
                "夏侯惇": ["好特技"],
                "曹仁": ["好特技"],
            },
            {"好特技"},
            set(),
            set(),
        )
        self.assertTrue(result.qualified)
        self.assertEqual(4, result.metrics["skillScore"])

    def test_skill_weights_are_configurable(self):
        config = default_rule_config()
        seven = config["profiles"][DEFAULT_PROFILE_NAME]["sevenPerson"]
        seven["strongSkillWeight"] = 1.5
        result = evaluate_skill_rules(
            config,
            7.6,
            {"曹操": ["强特技"], "夏侯惇": ["强特技"]},
            set(),
            {"强特技"},
            set(),
        )
        self.assertFalse(result.qualified)
        self.assertEqual(3, result.metrics["skillScore"])

    def test_individual_skill_score_overrides_category_weight(self):
        config = default_rule_config()
        seven = config["profiles"][DEFAULT_PROFILE_NAME]["sevenPerson"]
        seven["skillBaseScores"] = {"强特技": 4.5}
        result = evaluate_skill_rules(
            config,
            7.6,
            {"曹操": ["强特技"]},
            set(),
            {"强特技"},
            set(),
        )
        self.assertTrue(result.qualified)
        self.assertEqual(4.5, result.metrics["skillScore"])

    def test_other_skill_can_receive_custom_score(self):
        config = default_rule_config()
        seven = config["profiles"][DEFAULT_PROFILE_NAME]["sevenPerson"]
        seven["skillBaseScores"] = {"普通特技": 5}
        result = evaluate_skill_rules(
            config,
            7.6,
            {"曹操": ["普通特技"]},
            set(),
            set(),
            set(),
        )
        self.assertTrue(result.qualified)
        self.assertEqual(5, result.metrics["skillScore"])

    def test_custom_skill_score_counts_duplicate_occurrences(self):
        config = default_rule_config()
        seven = config["profiles"][DEFAULT_PROFILE_NAME]["sevenPerson"]
        seven["skillBaseScores"] = {"普通特技": 2}
        result = evaluate_skill_rules(
            config,
            7.6,
            {"曹操": ["普通特技", "普通特技"]},
            set(),
            set(),
            set(),
        )
        self.assertTrue(result.qualified)
        self.assertEqual(4, result.metrics["skillScore"])

    def test_incompatible_quality_skill_does_not_receive_override(self):
        config = default_rule_config()
        seven = config["profiles"][DEFAULT_PROFILE_NAME]["sevenPerson"]
        seven["skillBaseScores"] = {"优质特技": 10}
        result = evaluate_skill_rules(
            config,
            7.6,
            {"曹操": ["优质特技"]},
            {"优质特技"},
            set(),
            set(),
            effective_skill_names=[],
        )
        self.assertFalse(result.qualified)
        self.assertEqual(0, result.metrics["skillScore"])

    def test_simple_preset_updates_abstract_weights(self):
        config = default_rule_config()
        profile = config["profiles"][DEFAULT_PROFILE_NAME]
        profile["simpleSettings"].update(
            {
                "jobQuality": "严格",
                "affinityImportance": "较高",
                "teamBalance": "严格",
                "skillQuality": "严格",
                "strongSkillImportance": "较高",
                "highJobPreference": "较高",
            }
        )
        apply_simple_settings(profile)
        self.assertEqual(7.7, profile["threePerson"]["minJobAverage"])
        self.assertEqual(0.09, profile["jobScoring"]["primaryBonusRate"])
        self.assertEqual(
            2.5, profile["sevenPerson"]["strongSkillWeight"]
        )

    def test_multiple_profiles_survive_save_and_load(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            config = default_rule_config()
            custom = json.loads(
                json.dumps(config["profiles"][DEFAULT_PROFILE_NAME])
            )
            custom["builtin"] = False
            custom["threePerson"]["minJobAverage"] = 8.2
            config["profiles"]["严格规则"] = custom
            config["activeProfile"] = "严格规则"
            save_rule_config(base, config)
            loaded = load_rule_config(base)
            self.assertEqual("local", loaded.source)
            self.assertEqual("严格规则", loaded.config["activeProfile"])
            self.assertEqual(
                8.2,
                loaded.config["profiles"]["严格规则"]["threePerson"][
                    "minJobAverage"
                ],
            )

    def test_version_one_config_migrates_without_exact_conditions(self):
        old = {
            "version": 1,
            "activeProfile": "默认规则",
            "profiles": {
                "默认规则": {
                    "threePerson": {"minJobAverage": 7.5},
                    "sevenPerson": {
                        "minJobAverage": 7.5,
                        "normalJobAverage": 7.7,
                        "highJobAverage": 7.9,
                        "mediumMinEffectiveSkills": 4,
                        "lowMinEffectiveSkills": 5,
                        "strongSkillWeight": 2,
                        "specialSkillAutoPass": True,
                        "highJobAutoPass": True,
                    },
                    "jobConditions": {
                        "memberBlockedJobs": {"曹操": ["医师"]}
                    },
                }
            },
        }
        migrated = validate_rule_config(old)
        profile = migrated["profiles"][DEFAULT_PROFILE_NAME]
        self.assertEqual(2, migrated["version"])
        self.assertNotIn("jobConditions", profile)
        self.assertEqual(7.5, profile["threePerson"]["minJobAverage"])

    def test_corrupt_file_falls_back_to_builtin(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            path = base / "random_rules.json"
            path.write_text("{broken", encoding="utf-8")
            fallback = load_rule_config(base)
            self.assertEqual("builtin", fallback.source)
            self.assertTrue(fallback.warning)


if __name__ == "__main__":
    unittest.main()
