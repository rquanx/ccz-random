from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from ccz_randomizer.history import HistoryRepository
from tools.diagnostics.recover_loop_history import (
    R0_SIZE, apply_recovery, recovery_candidates, stage_recovery, target_state,
)


class HistoryRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repository = HistoryRepository(self.root)
        self.repository.start_run("incident", mode="three", loop_random=False, rule_name="rule", rule={}, build={})
        first = self.repository.start_round("incident", 1)
        self.repository.save_result(first, dict(slot=1, acceptedAttempt=1))
        self.repository.finish_run("incident", "stopped")
        self.archive = self.root / "archive"
        folder = self.archive / "round-000002" / "SV"
        folder.mkdir(parents=True)
        self.save = folder / "SV001.E5S"
        self.save.write_bytes(b"r" * R0_SIZE + b"save-trailer")
        self.fixture = json.loads((Path(__file__).parents[1] / "fixtures/history_loop_failure.json").read_text(encoding="utf-8"))
        self.failure = self.fixture["failure"]
        self.failure["failure"]["game_state"]["memory"]["sha256"] = hashlib.sha256(b"r" * R0_SIZE).hexdigest()
        self.diagnostic = self.root / "worker_diagnostic.jsonl"
        self.diagnostic.write_text(json.dumps(self.failure), encoding="utf-8")
        self.log = self.root / "worker.log"
        self.log.write_text("@@CCZ_RESULT_DETAIL@@" + json.dumps(self.fixture["detail"]), encoding="utf-8")
        self.timing = self.root / "timing.jsonl"
        self.timing.write_text(json.dumps(dict(event="timing_started", phase="worker_launch",
                                               round_number=2, time="2026-11-10T17:49:26.000")), encoding="utf-8")

    def stage(self):
        return stage_recovery(self.root, "incident", self.archive, [self.diagnostic], self.root / "recovery", self.timing)

    def state(self):
        with closing(sqlite3.connect(self.repository.path)) as connection:
            return target_state(connection, "incident")

    def test_preview_and_atomic_merge_preserve_existing_and_restore_backup(self):
        before = self.state()
        plan = self.stage()
        self.assertEqual(before, self.state())
        self.assertTrue(Path(plan["backup"]).is_file())
        self.assertEqual([(2, 1)], plan["missing"])
        plan = json.loads(json.dumps(plan))  # Plans are reviewable and reloadable from disk.
        apply_recovery(self.root, plan)
        after = self.state()
        self.assertEqual(before["results"][0], after["results"][0])
        self.assertEqual(before["rounds"][0], after["rounds"][0])
        round_id = self.repository.require_round("incident", 2)
        result = self.repository.get_round_results(round_id)[0]
        self.assertEqual(self.fixture["detail"], result["detail"])
        self.assertEqual("unknown", result["phase"])
        self.assertTrue(all(row["personalSkills"] == [{"name": "历史记录未保存"}] for row in result["members"]))
        with closing(sqlite3.connect(self.repository.path)) as connection:
            self.assertEqual(self.save.read_bytes(), connection.execute("SELECT data FROM result_saves").fetchone()[0])
            self.assertEqual((1, "stopped"), connection.execute("SELECT loop_random,status FROM runs").fetchone())
        with self.assertRaisesRegex(ValueError, "changed after preview"):
            apply_recovery(self.root, plan)

    def test_hash_mismatch_cannot_recover(self):
        self.save.write_bytes(b"different")
        self.assertEqual({}, recovery_candidates(self.archive, [self.diagnostic]))
        with self.assertRaisesRegex(ValueError, "Missing hash-matched"):
            self.stage()
        self.assertEqual(1, len(self.state()["results"]))

    def test_unaccepted_details_cannot_recover(self):
        detail = copy.deepcopy(self.fixture["detail"])
        detail["status"] = "skill_failed"
        self.log.write_text("@@CCZ_RESULT_DETAIL@@" + json.dumps(detail), encoding="utf-8")
        self.assertEqual({}, recovery_candidates(self.archive, [self.diagnostic]))

    def test_stale_history_or_changed_archive_rolls_back(self):
        plan = self.stage()
        before = self.state()
        self.save.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "Archive changed"):
            apply_recovery(self.root, plan)
        self.assertEqual(before, self.state())
        with closing(sqlite3.connect(self.repository.path)) as connection, connection:
            connection.execute("UPDATE rounds SET note='keep user note'")
        with self.assertRaisesRegex(ValueError, "history changed"):
            apply_recovery(self.root, plan)
        self.assertEqual(1, len(self.state()["results"]))

    def test_ambiguous_matching_details_are_rejected(self):
        other = self.root / "other_diagnostic.jsonl"
        other.write_text(json.dumps(self.failure), encoding="utf-8")
        detail = copy.deepcopy(self.fixture["detail"])
        detail["job"]["metrics"]["average"] = 0
        other.with_name("other.log").write_text("@@CCZ_RESULT_DETAIL@@" + json.dumps(detail), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            recovery_candidates(self.archive, [self.diagnostic, other])
