import copy
import json
from pathlib import Path
import unittest

from ccz_randomizer.recruitment import Recruit, display_job_options, load_recruits, parse_recruits, filter_recruits
from ccz_randomizer.runtime.personnel_memory import decode_personnel_record

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "personnel_22"


class RecruitmentTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads((FIXTURES / "title.json").read_text(encoding="utf-8"))
        self.rows = parse_recruits(self.payload)

    def test_real_records_decode_matching_identity_and_job(self):
        data = (FIXTURES / "records.bin").read_bytes()
        for row in self.payload["personnel"]:
            i = row["recordIndex"]
            self.assertEqual((row["name"], row["memberId"], row["jobId"]),
                decode_personnel_record(data[i*72:(i+1)*72], i))

    def test_wrong_record_index_or_truncation_is_rejected(self):
        record = (FIXTURES / "records.bin").read_bytes()[:72]
        for data, index in ((record, 1), (record[:71], 0)):
            with self.assertRaises(ValueError):
                decode_personnel_record(data, index)

    def test_real_personal_and_job_talents_remain_separate(self):
        row = self.rows[1]
        self.assertEqual("夏侯惇", row.name)
        self.assertEqual(("回马攻击 20%",), row.job_talents)
        self.assertIn("减少斜向伤害 40%", row.personal_talents)
        self.assertFalse(row.availability_verified)
        self.assertEqual("招募关系待验证", row.stage)

    def test_filter_combines_name_talent_and_selected_people(self):
        self.assertEqual((self.rows[1],), filter_recruits(self.rows, "夏侯 回马"))
        self.assertEqual((self.rows[0], self.rows[6]), filter_recruits(self.rows, selected=frozenset({0, 6})))
        self.assertEqual((), filter_recruits(self.rows, selected=frozenset()))
        self.assertEqual(self.rows, filter_recruits(self.rows, stage="招募关系待验证"))

    def test_malformed_fields_do_not_become_fake_empty_talents(self):
        for key, value in (("jobTalents", None), ("personalTalents", "回马攻击"),
                           ("recordIndex", True), ("name", None), ("jobId", -1)):
            payload = copy.deepcopy(self.payload)
            payload["personnel"][0][key] = value
            with self.assertRaises(ValueError):
                parse_recruits(payload)

    def test_duplicate_records_and_missing_verified_stage_are_rejected(self):
        payload = copy.deepcopy(self.payload)
        payload["personnel"].append(payload["personnel"][0])
        with self.assertRaises(ValueError):
            parse_recruits(payload)
        payload = copy.deepcopy(self.payload)
        payload["personnel"][0]["availabilityVerified"] = True
        with self.assertRaises(ValueError):
            parse_recruits(payload)

    def test_missing_file_is_reported_and_real_file_loads(self):
        with self.assertRaises(FileNotFoundError):
            load_recruits(FIXTURES / "absent.json")
        self.assertEqual(self.rows, load_recruits(FIXTURES / "title.json"))

    def test_saved_snapshot_remains_readable_without_its_old_profile(self):
        payload = copy.deepcopy(self.payload)
        payload["gameVersion"] = "archived-profile-build"
        self.assertEqual(self.rows, parse_recruits(payload))

    def test_display_job_options_keeps_only_concrete_recruitment_jobs(self):
        row = Recruit(152, "曹休", "青州讨伐战", "山贼", (), (),
                      True, ("青州讨伐战",), 2,
                      ("弓骑兵", "保留随机结果"))
        self.assertEqual("山贼/弓骑兵", display_job_options(row))

        row = Recruit(153, "曹纯", "虎牢关之战", "策士", (), (),
                      True, ("虎牢关之战",), 3,
                      ("虎豹骑", "保留随机结果"))
        self.assertEqual("策士/虎豹骑", display_job_options(row))

        row = Recruit(31, "邓艾", "斜谷之战", "策士", (), (),
                      True, ("斜谷之战",), 4,
                      ("名将", "随机"))
        self.assertEqual("策士/名将", display_job_options(row))

    def test_real_1104_options_preserve_order_and_current_job(self):
        from dataclasses import replace
        payload = json.loads((FIXTURES.parent / "personnel_220_1104/randomized-result.json").read_text(encoding="utf-8"))
        rows = parse_recruits(payload)
        by_name = {row.name: row for row in rows}
        expected = {
            "曹休": "山贼/弓骑兵", "黄忠": "山贼/弓兵/穿杨手/弓骑兵/神羿骑",
            "高顺": "山贼/西凉骑/先锋", "大乔": "山贼/炮车（携带床弩）/步兵（携带手戟）",
            "邓艾": "山贼/名将", "周瑜": "山贼/都督/将军/骑策",
        }
        for name, label in expected.items():
            with self.subTest(name=name):
                self.assertEqual(label, display_job_options(replace(by_name[name], job="山贼")))
        self.assertEqual("弓骑兵", display_job_options(replace(by_name["曹休"], job="弓骑兵")))
        self.assertEqual(by_name["李典"].job, display_job_options(by_name["李典"]))
        self.assertIn(by_name["曹纯"], filter_recruits(rows, "曹纯 虎豹骑"))
        self.assertEqual(23, sum(bool(row.job_choices) for row in rows))
