import struct
import tempfile
import unittest
from pathlib import Path

from ccz_randomizer.diagnostics.skill_storage import (
    LEGACY_RECORD_COUNT,
    LEGACY_RECORD_SIZE,
    LEGACY_SKILL_OFFSET,
    SkillObservation,
    read_legacy_records,
    read_skill_evidence,
    stable_direct_offsets,
    summarize_changed_ranges,
    write_skill_evidence,
)


class SkillStorageTests(unittest.TestCase):
    def test_reads_all_legacy_records_without_assigning_member_meaning(self):
        data = bytearray(
            LEGACY_SKILL_OFFSET + LEGACY_RECORD_COUNT * LEGACY_RECORD_SIZE
        )
        struct.pack_into("<4H", data, LEGACY_SKILL_OFFSET, 1, 2, 3, 4)
        struct.pack_into(
            "<4H",
            data,
            LEGACY_SKILL_OFFSET + (LEGACY_RECORD_COUNT - 1) * LEGACY_RECORD_SIZE,
            5,
            6,
            7,
            8,
        )

        records = read_legacy_records(bytes(data))

        self.assertEqual(LEGACY_RECORD_COUNT, len(records))
        self.assertEqual((1, 2, 3, 4), records[0])
        self.assertEqual((5, 6, 7, 8), records[-1])

    def test_finds_only_offsets_that_match_all_observations(self):
        saves = {}
        for number, value in ((1, 12), (2, 34), (3, 56)):
            data = bytearray(16)
            struct.pack_into("<H", data, 6, value)
            struct.pack_into("<H", data, 10, value if number != 3 else 99)
            saves[number] = bytes(data)
        observations = [
            SkillObservation(number, 0, 0, value, 1.0)
            for number, value in ((1, 12), (2, 34), (3, 56))
        ]

        result = stable_direct_offsets(saves, observations, value_size=2)

        self.assertEqual((6,), result[(0, 0)])

    def test_changed_ranges_merge_nearby_offsets(self):
        before = bytes(32)
        after = bytearray(before)
        after[2] = 1
        after[5] = 1
        after[20] = 1

        self.assertEqual(
            ((2, 6), (20, 21)),
            summarize_changed_ranges(before, bytes(after), merge_gap=4),
        )

    def test_skill_evidence_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.zip"
            write_skill_evidence(
                path,
                candidate_save=b"save",
                before_jump_memory=b"before",
                after_render_memory=b"after",
                metadata={"skills": [["先手攻击"]]},
            )

            evidence = read_skill_evidence(path)

        self.assertEqual({"skills": [["先手攻击"]]}, evidence["metadata"])
        self.assertEqual(b"save", evidence["candidate_save"])
        self.assertEqual(b"before", evidence["before_jump_memory"])
        self.assertEqual(b"after", evidence["after_render_memory"])


if __name__ == "__main__":
    unittest.main()
