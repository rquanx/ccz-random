import json
import tempfile
import unittest
from pathlib import Path

from rule_config import (
    DEFAULT_PROFILE_NAME,
    apply_simple_settings,
    build_rule_export,
    classify_skill_score,
    default_rule_config,
    evaluate_job_rules,
    evaluate_skill_rules,
    load_rule_config,
    merge_rule_export,
    save_rule_config,
    validate_rule_config,
)


MEMBERS = [
    {"name": "曹操", "primaryType": "ALL_ROUNDER", "secondaryType": "WARRIOR"},
    {"name": "夏侯惇", "primaryType": "WARRIOR", "secondaryType": "ALL_ROUNDER"},
    {"name": "夏侯渊", "primaryType": "MASTER", "secondaryType": "ALL_ROUNDER"},
]


class RuleConfigTests(unittest.TestCase):
    def test_skill_score_classification_uses_configured_thresholds(self):
        self.assertEqual("other", classify_skill_score(0.5, 1, 2, 5))
        self.assertEqual("ordinary", classify_skill_score(1, 1, 2, 5))
        self.assertEqual("strong", classify_skill_score(3, 1, 2, 5))
        self.assertEqual("special", classify_skill_score(5, 1, 2, 5))

    def test_skill_thresholds_must_be_ordered(self):
        config = default_rule_config()
        seven = config["profiles"][DEFAULT_PROFILE_NAME]["sevenPerson"]
        seven["strongSkillWeight"] = 6
        with self.assertRaisesRegex(ValueError, "普通优质 ≤ 强力 ≤ 特殊"):
            validate_rule_config(config)

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

    def test_job_count_rule_uses_inclusive_threshold(self):
        config = default_rule_config()
        profile = config["profiles"][DEFAULT_PROFILE_NAME]
        profile["jobScoring"]["affinityEnabled"] = False
        profile["threePerson"].update(
            {
                "minJobAverage": 7,
                "jobQualificationMode": "count",
                "minQualifiedCount": 2,
            }
        )
        jobs = [
            {"name": "甲", "score": 7, "type": "ALL_ROUNDER"},
            {"name": "乙", "score": 7, "type": "WARRIOR"},
            {"name": "丙", "score": 1, "type": "MASTER"},
        ]
        result = evaluate_job_rules(config, "three", jobs, MEMBERS)
        self.assertTrue(result.qualified)
        self.assertEqual(2, result.metrics["qualifiedCount"])
        self.assertEqual(2, result.metrics["requiredCount"])

    def test_job_count_rule_fails_when_too_few_members_reach_threshold(self):
        config = default_rule_config()
        profile = config["profiles"][DEFAULT_PROFILE_NAME]
        profile["jobScoring"]["affinityEnabled"] = False
        profile["threePerson"].update(
            {
                "minJobAverage": 7,
                "jobQualificationMode": "count",
                "minQualifiedCount": 3,
            }
        )
        jobs = [
            {"name": "甲", "score": 9, "type": "ALL_ROUNDER"},
            {"name": "乙", "score": 8, "type": "WARRIOR"},
            {"name": "丙", "score": 1, "type": "MASTER"},
        ]
        result = evaluate_job_rules(config, "three", jobs, MEMBERS)
        self.assertFalse(result.qualified)
        self.assertEqual(2, result.metrics["qualifiedCount"])

    def test_job_count_rule_only_counts_selected_members(self):
        config = default_rule_config()
        profile = config["profiles"][DEFAULT_PROFILE_NAME]
        profile["jobScoring"]["affinityEnabled"] = False
        profile["threePerson"].update(
            {
                "minJobAverage": 7,
                "jobQualificationMode": "count",
                "minQualifiedCount": 2,
                "qualifiedMembers": ["曹操", "夏侯渊"],
            }
        )
        jobs = [
            {"name": "甲", "score": 7, "type": "ALL_ROUNDER"},
            {"name": "乙", "score": 10, "type": "WARRIOR"},
            {"name": "丙", "score": 7, "type": "MASTER"},
        ]
        result = evaluate_job_rules(config, "three", jobs, MEMBERS)
        self.assertTrue(result.qualified)
        self.assertEqual(["曹操", "夏侯渊"], result.metrics["eligibleMembers"])
        self.assertEqual(
            ["曹操", "夏侯渊"],
            result.metrics["qualifiedMemberNames"],
        )

    def test_unselected_high_score_member_does_not_help_count_rule(self):
        config = default_rule_config()
        profile = config["profiles"][DEFAULT_PROFILE_NAME]
        profile["jobScoring"]["affinityEnabled"] = False
        profile["threePerson"].update(
            {
                "minJobAverage": 7,
                "jobQualificationMode": "count",
                "minQualifiedCount": 2,
                "qualifiedMembers": ["曹操", "夏侯渊"],
            }
        )
        jobs = [
            {"name": "甲", "score": 7, "type": "ALL_ROUNDER"},
            {"name": "乙", "score": 10, "type": "WARRIOR"},
            {"name": "丙", "score": 1, "type": "MASTER"},
        ]
        result = evaluate_job_rules(config, "three", jobs, MEMBERS)
        self.assertFalse(result.qualified)
        self.assertEqual(1, result.metrics["qualifiedCount"])
        self.assertEqual(["曹操"], result.metrics["qualifiedMemberNames"])

    def test_old_rule_defaults_to_all_members_for_count_rule(self):
        config = default_rule_config()
        del config["profiles"][DEFAULT_PROFILE_NAME]["threePerson"][
            "qualifiedMembers"
        ]
        normalized = validate_rule_config(config)
        self.assertEqual(
            ["曹操", "夏侯惇", "夏侯渊"],
            normalized["profiles"][DEFAULT_PROFILE_NAME]["threePerson"][
                "qualifiedMembers"
            ],
        )

    def test_job_count_member_selection_must_not_be_empty(self):
        config = default_rule_config()
        config["profiles"][DEFAULT_PROFILE_NAME]["threePerson"][
            "qualifiedMembers"
        ] = []
        with self.assertRaisesRegex(ValueError, "至少选择一名人物"):
            validate_rule_config(config)

    def test_job_count_member_selection_rejects_wrong_mode_member(self):
        config = default_rule_config()
        config["profiles"][DEFAULT_PROFILE_NAME]["threePerson"][
            "qualifiedMembers"
        ] = ["曹操", "曹仁"]
        with self.assertRaisesRegex(ValueError, "不适用于当前模式"):
            validate_rule_config(config)

    def test_job_count_member_selection_rejects_duplicates(self):
        config = default_rule_config()
        config["profiles"][DEFAULT_PROFILE_NAME]["threePerson"][
            "qualifiedMembers"
        ] = ["曹操", "曹操"]
        with self.assertRaisesRegex(ValueError, "不能重复选择"):
            validate_rule_config(config)

    def test_job_count_cannot_require_more_than_selected_members(self):
        config = default_rule_config()
        three = config["profiles"][DEFAULT_PROFILE_NAME]["threePerson"]
        three["qualifiedMembers"] = ["曹操"]
        three["minQualifiedCount"] = 2
        with self.assertRaisesRegex(ValueError, "不能超过已选人物数量"):
            validate_rule_config(config)

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

    def test_job_type_override_changes_affinity_and_balance(self):
        config = default_rule_config()
        profile = config["profiles"][DEFAULT_PROFILE_NAME]
        profile["jobScoring"]["jobTypeOverrides"] = {
            "群雄": "MASTER",
        }
        jobs = [
            {"name": "群雄", "score": 8, "type": "ALL_ROUNDER"},
        ]
        result = evaluate_job_rules(
            config,
            "three",
            jobs,
            [{"name": "曹操"}],
        )
        self.assertEqual(1, result.metrics["masterCount"])
        self.assertEqual(8, result.metrics["average"])

    def test_job_type_override_rejects_unknown_type(self):
        config = default_rule_config()
        profile = config["profiles"][DEFAULT_PROFILE_NAME]
        profile["jobScoring"]["jobTypeOverrides"] = {
            "群雄": "UNKNOWN",
        }
        with self.assertRaisesRegex(ValueError, "群雄所属类型"):
            validate_rule_config(config)

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
        self.assertEqual(1, result.metrics["specialCount"])

    def test_score_override_promotes_skill_to_special_auto_pass(self):
        config = default_rule_config()
        seven = config["profiles"][DEFAULT_PROFILE_NAME]["sevenPerson"]
        seven["skillBaseScores"] = {"优质特技": 5}
        result = evaluate_skill_rules(
            config,
            7.6,
            {"曹操": ["优质特技"]},
            {"优质特技"},
            set(),
            set(),
            effective_skill_names=[],
        )
        self.assertTrue(result.qualified)
        self.assertEqual(1, result.metrics["specialCount"])
        self.assertEqual(5, result.metrics["skillScore"])

    def test_score_override_demotes_special_and_requires_type_match(self):
        config = default_rule_config()
        seven = config["profiles"][DEFAULT_PROFILE_NAME]["sevenPerson"]
        seven["skillBaseScores"] = {"特殊特技": 1}
        result = evaluate_skill_rules(
            config,
            7.6,
            {"曹操": ["特殊特技"]},
            set(),
            set(),
            {"特殊特技"},
            effective_skill_names=[],
        )
        self.assertFalse(result.qualified)
        self.assertEqual(0, result.metrics["specialCount"])
        self.assertEqual(0, result.metrics["skillScore"])

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

    def test_incompatible_strong_skill_does_not_receive_override(self):
        config = default_rule_config()
        seven = config["profiles"][DEFAULT_PROFILE_NAME]["sevenPerson"]
        seven["skillBaseScores"] = {"优质特技": 4}
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

    def test_export_can_include_one_selected_profile(self):
        config = default_rule_config()
        custom = json.loads(
            json.dumps(config["profiles"][DEFAULT_PROFILE_NAME])
        )
        custom["builtin"] = False
        config["profiles"]["自定义"] = custom
        payload = build_rule_export(config, ("自定义",))
        self.assertEqual(("自定义",), tuple(payload["profiles"]))

    def test_import_appends_profiles_and_renames_duplicates(self):
        config = default_rule_config()
        payload = build_rule_export(config)
        merged, first_names = merge_rule_export(config, payload)
        merged, second_names = merge_rule_export(merged, payload)
        self.assertEqual(("默认规则(1)",), first_names)
        self.assertEqual(("默认规则(2)",), second_names)
        self.assertFalse(
            merged["profiles"]["默认规则(1)"]["builtin"]
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
