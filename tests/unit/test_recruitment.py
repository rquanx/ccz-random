import copy
import json
from pathlib import Path
import unittest

from ccz_randomizer.recruitment import load_recruits, parse_recruits, filter_recruits
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
