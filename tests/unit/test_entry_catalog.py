from unittest.mock import patch
import os
import json
from pathlib import Path
import struct
import unittest

from ccz_randomizer.entry_catalog import FIXED_ENTRY_STAGES, attach_fixed_entries, missing_fixed_entries, entry_stage_order
from ccz_randomizer.fixed_members import FIXED_MEMBER_INDICES
from ccz_randomizer.recruitment import parse_recruits, filter_recruits
from ccz_randomizer.runtime.personnel_memory import read_personnel
from tests.unit.test_personnel_memory import RecordedReader

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/personnel_22"


class EntryCatalogTests(unittest.TestCase):
    def setUp(self):
        version = patch.dict(os.environ, CCZ_GAME_VERSION="2.2")
        version.start()
        self.addCleanup(version.stop)

    def test_entry_stages_match_real_script_assignments(self):
        evidence = json.loads((FIXTURES / "fixed-entry-evidence.json").read_text(encoding="utf-8"))
        actual = set()
        for row in evidence:
            data = bytes.fromhex(row["data"])
            if row["name"] == "曹彰" and row["stageId"] == 46:
                self.assertEqual(data.decode("gbk"), "随机模式曹彰兵种固定")
            else:
                self.assertEqual(data[:22], bytes.fromhex("77005100020004000000000053000200520000000400"))
                self.assertEqual(struct.unpack_from("<I", data, 22)[0], FIXED_MEMBER_INDICES[row["name"]])
            actual.add((row["name"], row["stageId"]))
        expected = {(name, stage) for name, entries in FIXED_ENTRY_STAGES.items() for stage, _label in entries if stage}
        self.assertEqual(actual, expected)

    def test_fixed_talents_are_bound_to_real_random_result(self):
        raw = read_personnel(0, FIXED_MEMBER_INDICES.values(), planned=True, reader_factory=RecordedReader)
        attached = attach_fixed_entries(raw)
        rows = parse_recruits({"schemaVersion": 1, "gameVersion": "2.2", "personnel": attached})
        self.assertEqual(len(rows), 14)
        selected = filter_recruits(rows, stage="共通 · 青州讨伐战")
        self.assertEqual({row.name for row in selected}, {"典韦", "荀彧"})
        dianwei = next(row for row in selected if row.name == "典韦")
        self.assertEqual(dianwei.personal_talents, ("破坏精神", "固定减伤"))
        self.assertEqual(dianwei.cost, 0)
        self.assertEqual(dianwei.entry_kind, "fixed")
        self.assertNotIn("关羽", {row.name for row in rows})
        self.assertLess(entry_stage_order()["共通 · 濮阳决战"], entry_stage_order()["共通 · 天子救援战"])

    def test_old_result_missing_data_is_never_filled_with_another_roll(self):
        rows = missing_fixed_entries()
        self.assertTrue(all(row["job"] == "未采集" for row in rows))
        self.assertTrue(all(row["personalTalents"] == ["未采集"] for row in rows))
