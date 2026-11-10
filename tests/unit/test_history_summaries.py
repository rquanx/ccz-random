from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
from contextlib import closing
import unittest
from unittest.mock import patch

from ccz_randomizer.history import HistoryRepository, SCHEMA_VERSION
from ccz_randomizer.ui.history import _summary_member_text


class HistorySummaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repository = HistoryRepository(self.base)
        self.repository.start_run("real", mode="three", loop_random=True,
                                  rule_name="默认规则", rule={}, build={})
        fixture = Path(__file__).parents[1] / "fixtures/personnel_220_1104/randomized-result.json"
        self.snapshot = json.loads(fixture.read_text(encoding="utf-8"))
        self.snapshot.update(slot=1, acceptedAttempt=1)
        self.round_id = self.repository.start_round("real", 1)
        self.repository.save_result(self.round_id, self.snapshot)

    def small_loads(self, value):
        self.assertLess(len(value), 10_000, "摘要读取不应解析完整的143人快照")
        return self.loads(value)

    def test_summary_preserves_visible_members_scores_and_remaining_count(self):
        summary = self.repository.get_round_summaries(self.round_id)[0]
        self.assertEqual(_summary_member_text(self.snapshot), _summary_member_text(summary))
        self.assertEqual(143, summary["memberCount"])
        self.assertEqual(3, len(summary["members"]))
        self.assertLess(len(json.dumps(summary)), len(json.dumps(self.snapshot)) / 20)
        for kind, key in (("job", "average"), ("skill", "skillScore")):
            self.assertEqual(self.snapshot["detail"][kind]["metrics"][key],
                             summary["detail"][kind]["metrics"][key])
        self.assertEqual(self.snapshot, self.repository.get_result(self.round_id, 1))

    def test_warm_summary_reads_only_small_json_and_full_detail_is_unchanged(self):
        self.loads = json.loads
        with patch("ccz_randomizer.history.json.loads", side_effect=self.small_loads):
            summary = self.repository.get_round_summaries(self.round_id)
        self.assertEqual(143, summary[0]["memberCount"])
        self.assertEqual([self.snapshot], self.repository.get_round_results(self.round_id))

    def test_old_database_upgrades_without_decoding_and_only_caches_selected_round(self):
        second = self.repository.start_round("real", 2)
        self.repository.save_result(second, self.snapshot)
        with closing(self.repository._connect()) as connection, connection:
            before = connection.execute("SELECT id,snapshot_json FROM results ORDER BY id").fetchall()
            connection.execute("DROP TABLE result_summaries")
            connection.execute("DROP TABLE result_saves")
            connection.execute("DROP TABLE result_annotations")
            for column in ("title", "note", "marked"):
                connection.execute(f"ALTER TABLE rounds DROP COLUMN {column}")
            connection.execute("PRAGMA user_version = 1")
        with patch("ccz_randomizer.history.json.loads", side_effect=AssertionError("不应扫描旧记录")):
            upgraded = HistoryRepository(self.base)
        with closing(upgraded._connect()) as connection:
            self.assertEqual(SCHEMA_VERSION, connection.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM result_summaries").fetchone()[0])
        summary = upgraded.get_round_summaries(second)
        self.assertEqual(_summary_member_text(self.snapshot), _summary_member_text(summary[0]))
        with closing(upgraded._connect()) as connection:
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM result_summaries").fetchone()[0])
            self.assertEqual([tuple(row) for row in before],
                             [tuple(row) for row in connection.execute("SELECT id,snapshot_json FROM results ORDER BY id")])
        self.loads = json.loads
        with patch("ccz_randomizer.history.json.loads", side_effect=self.small_loads):
            self.assertEqual(summary, upgraded.get_round_summaries(second))

    def test_replacing_result_replaces_summary_and_deleting_round_cleans_cache(self):
        revised = copy.deepcopy(self.snapshot)
        first = revised["members"][0]["name"]
        revised["detail"]["job"]["metrics"]["eligibleMembers"] = [first]
        self.repository.save_result(self.round_id, revised)
        summary = self.repository.get_round_summaries(self.round_id)[0]
        self.assertEqual(1, summary["memberCount"])
        self.assertEqual(_summary_member_text(revised), _summary_member_text(summary))
        with closing(self.repository._connect()) as connection:
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM result_summaries").fetchone()[0])
        self.repository.delete_round(self.round_id)
        with closing(self.repository._connect()) as connection:
            self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM result_summaries").fetchone()[0])

    def test_verification_keeps_summary_and_complete_detail_consistent(self):
        before = self.repository.get_round_summaries(self.round_id)
        self.repository.update_verification(self.round_id, 1, verified=True)
        self.assertEqual(before, self.repository.get_round_summaries(self.round_id))
        self.assertTrue(self.repository.get_result(self.round_id, 1)["save"]["verified"])
        self.repository.clear()
        self.assertEqual([], self.repository.get_round_summaries(self.round_id))


if __name__ == "__main__":
    unittest.main()
