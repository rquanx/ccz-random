import unittest

from ccz_randomizer.ui.result_details import (
    decode_result_detail,
    encode_result_detail,
    format_result_detail,
)


class ResultDetailTests(unittest.TestCase):
    def test_result_detail_round_trip_preserves_chinese_text(self):
        detail = {
            "resultSlot": 1,
            "attempt": 2,
            "label": "兵种不合格",
        }

        self.assertEqual(detail, decode_result_detail(encode_result_detail(detail)))

    def test_job_failure_explains_average_and_skipped_skill_check(self):
        view = format_result_detail(
            {
                "resultSlot": 1,
                "attempt": 6,
                "label": "兵种不合格",
                "mode": "seven",
                "job": {
                    "qualified": False,
                    "metrics": {
                        "qualificationMode": "average",
                        "average": 8.5,
                        "threshold": 9,
                    },
                    "members": [
                        {"name": "曹操", "job": "虎豹骑", "score": 8.5}
                    ],
                },
                "skill": None,
            }
        )

        self.assertEqual("兵种不合格", view["status"])
        self.assertIn("平均分 8.5 < 门槛 9", view["sections"][0]["explanation"])
        self.assertIn("未继续检查特技", view["sections"][1]["explanation"])

    def test_skill_auto_pass_reason_is_human_readable(self):
        view = format_result_detail(
            {
                "resultSlot": 3,
                "attempt": 8,
                "label": "合格",
                "mode": "three",
                "job": None,
                "skill": {
                    "qualified": True,
                    "metrics": {
                        "autoPassReason": "special_skill",
                        "memberSkillScores": {"曹操": 5},
                    },
                    "members": [
                        {"name": "曹操", "skills": ["特殊特技"], "score": 5}
                    ],
                },
            }
        )

        self.assertIn(
            "特殊特技",
            view["sections"][0]["explanation"],
        )


if __name__ == "__main__":
    unittest.main()
