from __future__ import annotations

import tempfile
import unittest
import json
import sqlite3
from pathlib import Path

from ccz_randomizer.history import HistoryRepository
from ccz_randomizer.ui.history import (
    DETAIL_EQUIPMENT_COLUMNS,
    DETAIL_SPECIAL_MIN_WIDTH,
)


class HistoryRepositoryTests(unittest.TestCase):
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

    def test_final_result_requires_publish_and_is_unique(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = HistoryRepository(Path(directory))
            repository.start_run(
                "run-final",
                mode="three",
                loop_random=False,
                rule_name="规则",
                rule={},
                build={},
            )
            round_id = repository.start_round("run-final", 1)
            base = {
                "slot": 1,
                "attempt": 1,
                "mode": "three",
                "members": [],
                "treasures": [],
                "save": {
                    "verified": True,
                    "published": False,
                    "sha256": "hash-1",
                },
            }
            repository.save_attempt(
                round_id,
                base,
                status="accepted",
                scored=True,
                save_confirmed=True,
                published=False,
                is_final_result=True,
            )
            connection = repository._connect()
            try:
                self.assertEqual(
                    0,
                    connection.execute(
                        "SELECT COUNT(*) FROM attempts "
                        "WHERE is_final_result = 1"
                    ).fetchone()[0],
                )
            finally:
                connection.close()

            published = dict(base)
            published["attempt"] = 2
            published["save"] = {
                **base["save"],
                "published": True,
            }
            repository.save_attempt(
                round_id,
                published,
                status="accepted",
                scored=True,
                save_confirmed=True,
                published=True,
                is_final_result=True,
            )
            connection = repository._connect()
            try:
                self.assertEqual(
                    1,
                    connection.execute(
                        "SELECT COUNT(*) FROM attempts "
                        "WHERE is_final_result = 1"
                    ).fetchone()[0],
                )
            finally:
                connection.close()

    def test_v1_database_migrates_legacy_result_once(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            database_dir = base / "ccz_fast_data"
            database_dir.mkdir()
            path = database_dir / "history.sqlite3"
            connection = sqlite3.connect(path)
            connection.executescript(
                """
                CREATE TABLE runs (
                    id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    loop_random INTEGER NOT NULL,
                    rule_name TEXT NOT NULL,
                    rule_json TEXT NOT NULL,
                    build_json TEXT NOT NULL
                );
                CREATE TABLE rounds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    round_number INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    UNIQUE(run_id, round_number)
                );
                CREATE TABLE results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    round_id INTEGER NOT NULL,
                    slot INTEGER NOT NULL,
                    accepted_attempt INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    job_average REAL,
                    skill_score REAL,
                    save_path TEXT,
                    save_sha256 TEXT,
                    save_verified INTEGER NOT NULL DEFAULT 0,
                    verification_error TEXT,
                    snapshot_json TEXT NOT NULL
                );
                """
            )
            connection.execute("PRAGMA user_version = 1")
            connection.execute(
                "INSERT INTO runs VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?)",
                (
                    "run-old",
                    "2026-10-01T00:00:00+08:00",
                    "completed",
                    "three",
                    0,
                    "旧规则",
                    "{}",
                    "{}",
                ),
            )
            connection.execute(
                "INSERT INTO rounds VALUES (?, ?, ?, ?, NULL, ?)",
                (1, "run-old", 1, "2026-10-01T00:00:00+08:00", "completed"),
            )
            connection.execute(
                "INSERT INTO results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    1,
                    1,
                    1,
                    2,
                    "2026-10-01T00:00:01+08:00",
                    "three",
                    8,
                    9,
                    "SV001.E5S",
                    "hash",
                    1,
                    "",
                    json.dumps({"slot": 1, "acceptedAttempt": 2}),
                ),
            )
            connection.commit()
            connection.close()

            repository = HistoryRepository(base)
            self.assertEqual(5, connection_version(path))
            statistics_count = table_count(path, "attempts")
            self.assertEqual(1, statistics_count)
            migrated = sqlite3.connect(path)
            try:
                rule_hash = migrated.execute(
                    "SELECT rule_snapshot_hash FROM runs WHERE id = ?",
                    ("run-old",),
                ).fetchone()[0]
            finally:
                migrated.close()
            self.assertTrue(str(rule_hash).startswith("sha256:"))

            HistoryRepository(base)
            statistics_count = table_count(path, "attempts")
            self.assertEqual(1, statistics_count)
            self.assertEqual(1, repository.count_rounds())

    def test_v3_database_adds_combination_known_and_rebuilds_index(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = HistoryRepository(base)
            repository.start_run(
                "run-v3",
                mode="three",
                loop_random=False,
                rule_name="规则",
                rule={},
                build={},
            )
            round_id = repository.start_round("run-v3", 1)
            repository.save_result(
                round_id,
                {
                    "slot": 1,
                    "attempt": 1,
                    "acceptedAttempt": 1,
                    "mode": "three",
                    "members": [],
                    "treasures": [
                        {
                            "memberPosition": 0,
                            "treasureName": "宝物",
                            "setIds": ["set-a"],
                            "setNames": ["套装 A"],
                        }
                    ],
                    "save": {
                        "verified": True,
                        "published": True,
                        "sha256": "v3-hash",
                    },
                },
            )
            connection = repository._connect()
            try:
                connection.execute("DROP TABLE result_combinations")
                connection.execute(
                    """
                    CREATE TABLE result_combinations (
                        attempt_id INTEGER NOT NULL,
                        member_position INTEGER NOT NULL DEFAULT -1,
                        combination_id TEXT NOT NULL DEFAULT '',
                        combination_name TEXT NOT NULL DEFAULT '',
                        PRIMARY KEY(
                            attempt_id, member_position, combination_id
                        )
                    )
                    """
                )
                connection.execute("PRAGMA user_version = 3")
                connection.commit()
            finally:
                connection.close()

            migrated = HistoryRepository(base)
            connection = migrated._connect()
            try:
                columns = {
                    row["name"]
                    for row in connection.execute(
                        "PRAGMA table_info(result_combinations)"
                    )
                }
                self.assertIn("known", columns)
                self.assertEqual(
                    1,
                    connection.execute(
                        "SELECT COUNT(*) FROM result_combinations "
                        "WHERE combination_id = 'set-a'"
                    ).fetchone()[0],
                )
            finally:
                connection.close()

    def test_publishing_one_round_does_not_update_same_slot_in_other_run(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = HistoryRepository(Path(directory))
            repository.start_run(
                "run-a",
                mode="three",
                loop_random=False,
                rule_name="规则",
                rule={},
                build={},
            )
            first_round = repository.start_round("run-a", 1)
            repository.start_run(
                "run-b",
                mode="three",
                loop_random=False,
                rule_name="规则",
                rule={},
                build={},
            )
            second_round = repository.start_round("run-b", 1)
            for round_id in (first_round, second_round):
                repository.save_attempt(
                    round_id,
                    {
                        "slot": 1,
                        "attempt": 1,
                        "mode": "three",
                        "members": [],
                        "treasures": [],
                        "save": {"sha256": "same-hash"},
                    },
                    status="accepted",
                    scored=True,
                    save_confirmed=True,
                    published=False,
                )

            self.assertEqual(
                1,
                repository.mark_result_published(
                    round_id=first_round,
                    run_id="run-a",
                    slot=1,
                    save_sha256="same-hash",
                ),
            )
            connection = repository._connect()
            try:
                states = connection.execute(
                    "SELECT round_id, published, is_final_result "
                    "FROM attempts ORDER BY round_id"
                ).fetchall()
            finally:
                connection.close()
            self.assertEqual(
                [(first_round, 1, 1), (second_round, 0, 0)],
                [tuple(row) for row in states],
            )


def connection_version(path: Path) -> int:
    connection = sqlite3.connect(path)
    try:
        return int(connection.execute("PRAGMA user_version").fetchone()[0])
    finally:
        connection.close()


def table_count(path: Path, table: str) -> int:
    connection = sqlite3.connect(path)
    try:
        return int(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        )
    finally:
        connection.close()


if __name__ == "__main__":
    unittest.main()
