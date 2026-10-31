import copy
import json
import unittest
from pathlib import Path

from ccz_randomizer.history_members import history_members
from ccz_randomizer.jobs import JOB_MAP
from ccz_randomizer.ui.history import _summary_member_text


class HistoryMembersTests(unittest.TestCase):
    def snapshot(self):
        fixtures = Path(__file__).parents[1] / "fixtures" / "personnel_22"
        return {
            "members": [{"name": name} for name in ("曹操", "夏侯惇", "夏侯渊")],
            "detail": {"job": {"metrics": {"eligibleMembers": ["张宝"]},
                               "members": [{"name": "张宝", "score": 7}]}},
            "personnel": json.loads((fixtures / "randomized-personnel.json").read_text(encoding="utf-8")),
            "fixedPersonnel": json.loads((fixtures / "randomized-fixed-personnel.json").read_text(encoding="utf-8")),
        }

    def test_stale_initial_members_reconstructed_from_recorded_personnel(self):
        snapshot = self.snapshot()
        before = copy.deepcopy(snapshot)
        row = next(row for row in snapshot["personnel"] if row["name"] == "张宝")
        members = history_members(snapshot)
        self.assertEqual(["张宝"], [m["name"] for m in members])
        self.assertEqual(JOB_MAP[row["jobId"]][0], members[0]["job"])
        self.assertEqual(row["personalTalents"], [s["name"] for s in members[0]["personalSkills"]])
        self.assertEqual(row["jobTalents"], [s["name"] for s in members[0]["jobSkills"]])
        text = _summary_member_text(snapshot)
        self.assertIn("张宝", text)
        self.assertNotIn("曹操", text)
        self.assertEqual(before, snapshot)

    def test_fixed_recruit_and_saved_members_follow_selection_order(self):
        snapshot = self.snapshot()
        snapshot["detail"]["job"]["metrics"]["eligibleMembers"] = ["典韦", "张宝", "曹操"]
        members = history_members(snapshot)
        self.assertEqual(["典韦", "张宝", "曹操"], [m["name"] for m in members])
        self.assertIn("personalSkills", members[0])

    def test_missing_data_does_not_show_unselected_initial_people(self):
        snapshot = self.snapshot()
        del snapshot["personnel"]
        result = history_members(snapshot)
        self.assertEqual(["张宝"], [m["name"] for m in result])
        self.assertEqual("历史记录未保存", result[0]["personalSkills"][0]["name"])

    def test_legacy_without_selection_keeps_original_members(self):
        snapshot = self.snapshot()
        snapshot.pop("detail")
        self.assertEqual(snapshot["members"], history_members(snapshot))

    def test_summary_member_text_limits_long_people_lists(self):
        snapshot = self.snapshot()
        snapshot.pop("detail")
        snapshot["members"] = [{"name": name} for name in ("甲", "乙", "丙", "丁", "戊")]
        text = _summary_member_text(snapshot)
        self.assertIn("甲", text)
        self.assertIn("丙", text)
        self.assertNotIn("丁 ·", text)
        self.assertIn("其余 2 人请查看完整详情", text)
