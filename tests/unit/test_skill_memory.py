from __future__ import annotations

import struct
import unittest

from ccz_randomizer.runtime.skill_memory import (
    SKILL_RULE_COUNT,
    SKILL_RULE_STRIDE,
    format_skill_name,
    normalize_skill_name,
    resolve_skill_ids,
)


ABILITY_SHORT_NAMES = ("攻", "防", "精", "爆", "士", "移")
ABILITY_NAMES = (
    "全部",
    "攻击",
    "防御",
    "精神",
    "爆发",
    "士气",
    "移动",
    "等级",
)


class SkillMemoryTests(unittest.TestCase):
    def format_name(
        self,
        base_name: str,
        format_type: int,
        parameter: int,
        strategy_name: str = "",
    ) -> str:
        return format_skill_name(
            base_name,
            format_type,
            parameter,
            ability_short_names=ABILITY_SHORT_NAMES,
            ability_names=ABILITY_NAMES,
            all_ability_name="全能力",
            strategy_name=strategy_name,
        )

    def test_formats_numeric_skill_names(self) -> None:
        self.assertEqual("获得功勋 +3", self.format_name("获得功勋", 1, 3))
        self.assertEqual("伤害增幅 +30%", self.format_name("伤害增幅", 2, 30))
        self.assertEqual("减轻损伤 -30%", self.format_name("减轻损伤", 3, 30))
        self.assertEqual("鬼神之勇 12%", self.format_name("鬼神之勇", 4, 12))
        self.assertEqual("辅助移动力 2", self.format_name("辅助移动力", 5, 2))

    def test_formats_dynamic_skill_names(self) -> None:
        self.assertEqual(
            "能力替换 攻→士",
            self.format_name("能力替换", 6, 0b10000),
        )
        self.assertEqual(
            "能力辅助 精→防精",
            self.format_name("能力辅助", 6, (2 << 4) | 0b00110),
        )
        self.assertEqual(
            "能力辅助 防→攻精",
            self.format_name("能力辅助", 6, 21),
        )
        self.assertEqual(
            "攻击追加 诱惑",
            self.format_name("攻击追加", 7, 20, "诱惑"),
        )
        self.assertEqual(
            "弱点攻击 爆发",
            self.format_name("弱点攻击", 8, 4),
        )
        self.assertEqual(
            "忽视能力 精士",
            self.format_name("忽视能力", 9, 0b10100),
        )
        self.assertEqual(
            "自动提升 全能力",
            self.format_name("自动提升", 10, 0b111111),
        )

    def test_normalizes_game_text_to_existing_catalog_text(self) -> None:
        self.assertEqual(
            normalize_skill_name("能力替换-攻替士"),
            normalize_skill_name("能力替换 攻→士"),
        )
        self.assertEqual(
            normalize_skill_name("能力辅助（精辅防精）"),
            normalize_skill_name("能力辅助 精→防精"),
        )
        self.assertEqual(
            normalize_skill_name("众矢之的策略"),
            normalize_skill_name("众矢之的 策略"),
        )
        self.assertEqual(
            normalize_skill_name("提升策略命中20%"),
            normalize_skill_name("提升策略命中+20%"),
        )

    def test_resolves_personal_and_job_skills_separately(self) -> None:
        rules = bytearray(SKILL_RULE_COUNT * SKILL_RULE_STRIDE)
        struct.pack_into("<HHH", rules, 18 * SKILL_RULE_STRIDE, 6, 99, 99)
        rules[59 * SKILL_RULE_STRIDE + 6] = 39
        personal, job = resolve_skill_ids(
            record_index=6,
            job_id=39,
            rule_table=bytes(rules),
            direct_job_match=False,
        )

        self.assertEqual((18,), personal)
        self.assertEqual((59,), job)

    def test_personal_rule_is_not_replaced_by_job_skill(self) -> None:
        rules = bytearray(SKILL_RULE_COUNT * SKILL_RULE_STRIDE)
        struct.pack_into("<HHH", rules, 32 * SKILL_RULE_STRIDE, 1, 99, 99)
        struct.pack_into("<HHH", rules, 33 * SKILL_RULE_STRIDE, 1, 98, 98)
        rules[28 * SKILL_RULE_STRIDE + 6] = 21
        personal, job = resolve_skill_ids(
            record_index=1,
            job_id=21,
            rule_table=bytes(rules),
            direct_job_match=False,
        )

        self.assertEqual((32, 33), personal)
        self.assertEqual((28,), job)

    def test_resolves_multiple_personal_skills_for_same_member(self) -> None:
        rules = bytearray(SKILL_RULE_COUNT * SKILL_RULE_STRIDE)
        struct.pack_into("<HHH", rules, 7 * SKILL_RULE_STRIDE, 5, 99, 99)
        struct.pack_into("<HHH", rules, 8 * SKILL_RULE_STRIDE, 5, 98, 98)
        struct.pack_into("<HHH", rules, 20 * SKILL_RULE_STRIDE, 97, 5, 97)

        personal, _job = resolve_skill_ids(
            record_index=5,
            job_id=39,
            rule_table=bytes(rules),
            direct_job_match=False,
        )

        self.assertEqual((7, 8, 20), personal)


if __name__ == "__main__":
    unittest.main()
