from __future__ import annotations

import tempfile
import unittest
import sqlite3
from contextlib import closing
from pathlib import Path

from ccz_randomizer.history import (
    HistoryRepository,
    compatible_history_database_path,
    history_database_path,
)
from ccz_randomizer.ui.history import (
    DETAIL_EQUIPMENT_COLUMNS,
    DETAIL_SPECIAL_MIN_WIDTH,
)


class HistoryRepositoryTests(unittest.TestCase):
    def test_empty_rounds_hidden_and_not_retained_after_finish(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = HistoryRepository(Path(directory))
            for status in ("completed", "stopped", "failed"):
                repository.start_run(status, mode="three", loop_random=False,
                                     rule_name="规则", rule={}, build={})
                round_id = repository.start_round(status, 1)
                self.assertEqual(0, repository.count_rounds())
                self.assertEqual([], repository.list_rounds())
                repository.finish_round(round_id, status)
                repository.finish_run(status, status)
            with closing(sqlite3.connect(repository.path)) as connection:
                self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM rounds").fetchone()[0])
                self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0])

    def test_partial_results_survive_stop_and_empty_rounds_do_not_affect_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = HistoryRepository(Path(directory))
            repository.start_run("partial", mode="three", loop_random=True,
                                 rule_name="规则", rule={}, build={})
            first = repository.start_round("partial", 1)
            repository.save_result(first, dict(slot=1, acceptedAttempt=2))
            repository.start_round("partial", 2)  # Legacy/interrupted empty round.
            third = repository.start_round("partial", 3)
            repository.save_result(third, dict(slot=1, acceptedAttempt=5))
            self.assertEqual(2, repository.count_rounds())
            self.assertEqual([third], [r["id"] for r in repository.list_rounds(page=1, page_size=1)])
            self.assertEqual([first], [r["id"] for r in repository.list_rounds(page=2, page_size=1)])
            repository.finish_round(third, "stopped")
            repository.finish_run("partial", "stopped")
            self.assertEqual(2, repository.count_rounds())
            self.assertEqual(5, repository.get_round_results(third)[0]["acceptedAttempt"])

    def test_detail_equipment_layout_is_compact(self):
        self.assertEqual(4, DETAIL_EQUIPMENT_COLUMNS)
        self.assertEqual(220, DETAIL_SPECIAL_MIN_WIDTH)

    def test_round_results_are_saved_paged_and_cleared(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = HistoryRepository(Path(directory))
            repository.start_run(
                "run-1",
                mode="three",
                loop_random=False,
                rule_name="默认规则",
                rule={"name": "默认规则"},
                build={"version": "2.1.2"},
            )
            round_id = repository.start_round("run-1", 1)
            repository.save_result(
                round_id,
                {
                    "slot": 1,
                    "acceptedAttempt": 3,
                    "createdAt": "2026-09-28T14:00:00+08:00",
                    "mode": "three",
                    "detail": {
                        "job": {"metrics": {"average": 8.5}},
                        "skill": {"metrics": {"skillScore": 6}},
                    },
                    "members": [],
                    "equipment": {},
                    "save": {
                        "path": "SV001.E5S",
                        "sha256": "abc",
                        "verified": False,
                    },
                },
            )
            repository.update_verification(
                round_id,
                1,
                verified=True,
            )
            repository.finish_round(round_id, "completed")
            repository.finish_run("run-1", "completed")

            rounds = repository.list_rounds()
            self.assertEqual(1, len(rounds))
            self.assertEqual(1, rounds[0]["result_count"])
            results = repository.get_round_results(round_id)
            self.assertEqual(3, results[0]["acceptedAttempt"])
            self.assertTrue(results[0]["save"]["verified"])

            repository.clear()
            self.assertEqual(0, repository.count_rounds())

    def test_shared_concurrent_run_keeps_one_round_for_all_slots(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = HistoryRepository(Path(directory))
            for slot in (1, 2):
                repository.start_run(
                    "shared-concurrent-run",
                    mode="three",
                    loop_random=False,
                    rule_name="规则",
                    rule={},
                    build={},
                )
                round_id = repository.start_round("shared-concurrent-run", 1)
                repository.save_result(
                    round_id,
                    {
                        "slot": slot,
                        "acceptedAttempt": 1,
                        "mode": "three",
                        "detail": {},
                        "save": {},
                    },
                )
            rounds = repository.list_rounds()
            self.assertEqual(1, len(rounds))
            self.assertEqual(2, rounds[0]["result_count"])
            self.assertEqual([1, 2], [
                result["slot"]
                for result in repository.get_round_results(round_id)
            ])

    def test_deleting_last_round_removes_run(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = HistoryRepository(Path(directory))
            repository.start_run(
                "run-2",
                mode="seven",
                loop_random=True,
                rule_name="规则",
                rule={},
                build={},
            )
            round_id = repository.start_round("run-2", 1)
            repository.delete_round(round_id)
            self.assertEqual([], repository.list_rounds())

    def test_newer_history_database_is_preserved_and_uses_compatible_file(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            newer_path = history_database_path(base)
            newer_path.parent.mkdir(parents=True)
            with closing(sqlite3.connect(newer_path)) as connection:
                connection.execute("CREATE TABLE newer_data (value TEXT)")
                connection.execute("INSERT INTO newer_data VALUES ('keep')")
                connection.execute("PRAGMA user_version = 5")
                connection.commit()

            repository = HistoryRepository(base)

            self.assertEqual(
                compatible_history_database_path(base),
                repository.path,
            )
            self.assertTrue(repository.path.is_file())
            with closing(sqlite3.connect(newer_path)) as connection:
                self.assertEqual(
                    5,
                    connection.execute("PRAGMA user_version").fetchone()[0],
                )
                self.assertEqual(
                    "keep",
                    connection.execute(
                        "SELECT value FROM newer_data"
                    ).fetchone()[0],
                )


if __name__ == "__main__":
    unittest.main()
