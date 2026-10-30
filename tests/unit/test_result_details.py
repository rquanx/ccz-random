import unittest

from ccz_randomizer.ui.result_details import (
    decode_result_detail,
    encode_result_detail,
    format_result_detail,
)


class ResultDetailTests(unittest.TestCase):
    def test_single_selected_person_shows_score_and_gap_without_repeated_roster(self):
        for score, passed, expected in ((7, False, '门槛 8 分，还差 1 分'), (8, True, '门槛 8 分，已达标')):
            view = format_result_detail(dict(mode='three', job=dict(qualified=passed,
                members=[dict(name='张宝', job='道士', score=score)],
                metrics=dict(qualificationMode='count', threshold=8, requiredCount=1,
                    qualifiedCount=int(passed), eligibleMembers=['张宝']))))
            section = view['sections'][0]
            self.assertEqual([f'张宝：道士　{score} 分'], section['rows'])
            self.assertEqual(expected, section['explanation'])

    def test_multiple_selected_people_explain_missing_count(self):
        view = format_result_detail(dict(mode='three', job=dict(qualified=False,
            members=[dict(name='张宝', job='道士', score=7), dict(name='曹操', job='虎豹骑', score=8.5)],
            metrics=dict(qualificationMode='count', threshold=8, requiredCount=2,
                qualifiedCount=1, eligibleMembers=['张宝', '曹操']))))
        section = view['sections'][0]
        self.assertEqual(['张宝：道士　7 分　还差 1 分', '曹操：虎豹骑　8.5 分　已达标'], section['rows'])
        self.assertEqual('需至少 2 人达到 8 分；本次 1 人达标，还差 1 人', section['explanation'])

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
        self.assertIn("所选人物平均 8.5 分，门槛 9 分，还差 0.5 分", view["sections"][0]["explanation"])
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
