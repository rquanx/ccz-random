import json
from pathlib import Path
import unittest

from ccz_randomizer.recruitment_catalog import load_catalog
from ccz_randomizer.runtime.personnel_memory import read_personnel

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/personnel_22"


class RecordedReader:
    def __init__(self, _pid):
        raw = json.loads((FIXTURES / "randomized-memory.json").read_text(encoding="utf-8"))
        self.spans = [(int(key.split(":")[0]), bytes.fromhex(value)) for key, value in raw.items()]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def read(self, address, size):
        for base, data in self.spans:
            if base <= address and address + size <= base + len(data):
                return data[address-base:address-base+size]
        raise AssertionError(f"未采集的真实内存范围：{address:x}, {size}")


class PersonnelMemoryTests(unittest.TestCase):
    def test_randomized_jobs_and_talents_match_real_saved_result(self):
        catalog = load_catalog()
        actual = read_personnel(0, [p["recordIndex"] for p in catalog], planned=True,
            fixed_indices=[p["recordIndex"] for p in catalog if p["fixedConfiguration"]],
            reader_factory=RecordedReader)
        expected = json.loads((FIXTURES / "randomized-personnel.json").read_text(encoding="utf-8"))
        keys = ("recordIndex", "name", "jobId", "currentJobId", "jobTalents", "personalTalents")
        self.assertEqual([{k: r[k] for k in keys} for r in expected],
                         [{k: r[k] for k in keys} for r in actual])
        ordinary = [r for r in actual if r["recordIndex"] < 205]
        self.assertTrue(any(r["jobId"] != r["currentJobId"] for r in ordinary))
        fixed = [r for r in actual if 205 <= r["recordIndex"] <= 209]
        self.assertEqual(5, len(fixed))
        self.assertTrue(all(r["jobId"] == r["currentJobId"] for r in fixed))

    def test_legacy_read_keeps_current_job_and_real_talents(self):
        rows = read_personnel(0, [5], reader_factory=RecordedReader)
        self.assertEqual(rows[0]["currentJobId"], rows[0]["jobId"])
        self.assertFalse(rows[0]["availabilityVerified"])
