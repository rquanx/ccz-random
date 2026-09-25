import json
import tempfile
import unittest
from pathlib import Path

from rule_config import (
    default_rule_config,
    evaluate_job_rules,
    evaluate_skill_rules,
    load_rule_config,
    save_rule_config,
)


MEMBERS = [
    {"name": "曹操", "primaryType": "ALL_ROUNDER", "secondaryType": "WARRIOR"},
    {"name": "夏侯惇", "primaryType": "WARRIOR", "secondaryType": "ALL_ROUNDER"},
    {"name": "曹仁", "primaryType": "ALL_ROUNDER", "secondaryType": "WARRIOR"},
]


class RuleConfigTests(unittest.TestCase):
    def test_default_three_person_job_rule_matches_existing_threshold(self):
        jobs = [
            {"name": "群雄", "score": 8, "type": "ALL_ROUNDER"},
            {"name": "虎豹骑", "score": 9, "type": "WARRIOR"},
            {"name": "都督", "score": 9, "type": "ALL_ROUNDER"},
        ]
        result = evaluate_job_rules(
            default_rule_config(), "three", jobs, MEMBERS
        )
        self.assertTrue(result.qualified)

    def test_member_blocked_job_reports_plain_reason(self):
        config = default_rule_config()
        profile = config["profiles"]["默认规则"]
        profile["jobConditions"]["memberBlockedJobs"] = {
            "曹操": ["医师"]
        }
        jobs = [
            {"name": "医师", "score": 7, "type": "MASTER"},
            {"name": "虎豹骑", "score": 9, "type": "WARRIOR"},
            {"name": "都督", "score": 9, "type": "ALL_ROUNDER"},
        ]
        result = evaluate_job_rules(config, "three", jobs, MEMBERS)
        self.assertFalse(result.qualified)
        self.assertIn("曹操命中排除兵种“医师”", result.reasons)

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
        self.assertEqual(4, result.metrics["carryCount"])

    def test_strong_skills_keep_double_weight(self):
        config = default_rule_config()
        result = evaluate_skill_rules(
            config,
            7.6,
            {"曹操": ["强特技"], "夏侯惇": ["强特技"]},
            set(),
            {"强特技"},
            set(),
        )
        self.assertTrue(result.qualified)
        self.assertEqual(4, result.metrics["effectiveCount"])

    def test_required_and_blocked_skills(self):
        config = default_rule_config()
        conditions = config["profiles"]["默认规则"]["skillConditions"]
        conditions["requiredAny"] = ["二次行动", "唯我独尊"]
        conditions["blocked"] = ["物理免疫"]
        result = evaluate_skill_rules(
            config,
            8,
            {"曹操": ["物理免疫"]},
            set(),
            set(),
            set(),
        )
        self.assertFalse(result.qualified)
        self.assertIn("未出现任一指定特技", result.reasons)
        self.assertIn("出现排除特技“物理免疫”", result.reasons)

    def test_save_load_and_corrupt_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            config = default_rule_config()
            config["profiles"]["默认规则"]["threePerson"][
                "minJobAverage"
            ] = 8.2
            path = save_rule_config(base, config)
            loaded = load_rule_config(base)
            self.assertEqual("local", loaded.source)
            self.assertEqual(
                8.2,
                loaded.config["profiles"]["默认规则"]["threePerson"][
                    "minJobAverage"
                ],
            )

            path.write_text("{broken", encoding="utf-8")
            fallback = load_rule_config(base)
            self.assertEqual("builtin", fallback.source)
            self.assertTrue(fallback.warning)

    def test_unknown_fields_survive_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            config = default_rule_config()
            config["futureField"] = {"enabled": True}
            save_rule_config(base, config)
            loaded = json.loads(
                (base / "random_rules.json").read_text(encoding="utf-8")
            )
            self.assertEqual({"enabled": True}, loaded["futureField"])


if __name__ == "__main__":
    unittest.main()
