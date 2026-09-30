from __future__ import annotations

import datetime as dt
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_PAGE_SIZE = 20


def history_database_path(base_dir: Path) -> Path:
    return base_dir / "ccz_fast_data" / "history.sqlite3"


def _now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


class HistoryRepository:
    def __init__(self, base_dir: Path):
        self.path = history_database_path(base_dir)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            version = int(
                connection.execute("PRAGMA user_version").fetchone()[0]
            )
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"历史数据库版本过新：{version}/{SCHEMA_VERSION}"
                )
            if version == 0:
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
                        run_id TEXT NOT NULL REFERENCES runs(id)
                            ON DELETE CASCADE,
                        round_number INTEGER NOT NULL,
                        started_at TEXT NOT NULL,
                        finished_at TEXT,
                        status TEXT NOT NULL,
                        UNIQUE(run_id, round_number)
                    );

                    CREATE TABLE results (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        round_id INTEGER NOT NULL REFERENCES rounds(id)
                            ON DELETE CASCADE,
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
                        snapshot_json TEXT NOT NULL,
                        UNIQUE(round_id, slot)
                    );

                    CREATE INDEX idx_rounds_started
                        ON rounds(started_at DESC, id DESC);
                    CREATE INDEX idx_results_round_slot
                        ON results(round_id, slot);
                    """
                )
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def start_run(
        self,
        run_id: str,
        *,
        mode: str,
        loop_random: bool,
        rule_name: str,
        rule: dict[str, Any],
        build: dict[str, Any],
    ) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO runs (
                    id, started_at, finished_at, status, mode,
                    loop_random, rule_name, rule_json, build_json
                ) VALUES (?, ?, NULL, 'running', ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    _now(),
                    mode,
                    int(loop_random),
                    rule_name,
                    json.dumps(rule, ensure_ascii=False),
                    json.dumps(build, ensure_ascii=False),
                ),
            )

    def finish_run(self, run_id: str, status: str) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE runs
                SET status = ?, finished_at = ?
                WHERE id = ?
                """,
                (status, _now(), run_id),
            )

    def start_round(self, run_id: str, round_number: int) -> int:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO rounds (
                    run_id, round_number, started_at, finished_at, status
                ) VALUES (?, ?, ?, NULL, 'running')
                """,
                (run_id, round_number, _now()),
            )
            row = connection.execute(
                """
                SELECT id FROM rounds
                WHERE run_id = ? AND round_number = ?
                """,
                (run_id, round_number),
            ).fetchone()
            assert row is not None
            return int(row["id"])

    def finish_round(self, round_id: int, status: str) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE rounds
                SET status = ?, finished_at = ?
                WHERE id = ?
                """,
                (status, _now(), round_id),
            )

    def save_result(
        self,
        round_id: int,
        snapshot: dict[str, Any],
    ) -> int:
        detail = snapshot.get("detail") or {}
        job_metrics = ((detail.get("job") or {}).get("metrics") or {})
        skill_metrics = ((detail.get("skill") or {}).get("metrics") or {})
        save = snapshot.get("save") or {}
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO results (
                    round_id, slot, accepted_attempt, created_at, mode,
                    job_average, skill_score, save_path, save_sha256,
                    save_verified, verification_error, snapshot_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    round_id,
                    int(snapshot["slot"]),
                    int(snapshot["acceptedAttempt"]),
                    str(snapshot.get("createdAt") or _now()),
                    str(snapshot.get("mode") or ""),
                    job_metrics.get("average"),
                    skill_metrics.get("skillScore"),
                    str(save.get("path") or ""),
                    str(save.get("sha256") or ""),
                    int(bool(save.get("verified"))),
                    str(save.get("verificationError") or ""),
                    json.dumps(snapshot, ensure_ascii=False),
                ),
            )
            row = connection.execute(
                """
                SELECT id FROM results
                WHERE round_id = ? AND slot = ?
                """,
                (round_id, int(snapshot["slot"])),
            ).fetchone()
            assert row is not None
            return int(row["id"])

    def update_verification(
        self,
        round_id: int,
        slot: int,
        *,
        verified: bool,
        error: str = "",
    ) -> None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                """
                SELECT id, snapshot_json FROM results
                WHERE round_id = ? AND slot = ?
                """,
                (round_id, slot),
            ).fetchone()
            if row is None:
                return
            snapshot = json.loads(row["snapshot_json"])
            save = snapshot.setdefault("save", {})
            save["verified"] = bool(verified)
            save["verificationError"] = error
            connection.execute(
                """
                UPDATE results
                SET save_verified = ?, verification_error = ?,
                    snapshot_json = ?
                WHERE id = ?
                """,
                (
                    int(verified),
                    error,
                    json.dumps(snapshot, ensure_ascii=False),
                    int(row["id"]),
                ),
            )

    def count_rounds(self) -> int:
        with closing(self._connect()) as connection, connection:
            return int(
                connection.execute("SELECT COUNT(*) FROM rounds").fetchone()[0]
            )

    def list_rounds(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> list[dict[str, Any]]:
        page = max(1, int(page))
        page_size = max(1, min(100, int(page_size)))
        offset = (page - 1) * page_size
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                """
                SELECT
                    rounds.id,
                    rounds.run_id,
                    rounds.round_number,
                    rounds.started_at,
                    rounds.finished_at,
                    rounds.status,
                    runs.mode,
                    runs.loop_random,
                    runs.rule_name,
                    COUNT(results.id) AS result_count
                FROM rounds
                JOIN runs ON runs.id = rounds.run_id
                LEFT JOIN results ON results.round_id = rounds.id
                GROUP BY rounds.id
                ORDER BY rounds.started_at DESC, rounds.id DESC
                LIMIT ? OFFSET ?
                """,
                (page_size, offset),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_round_results(self, round_id: int) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                """
                SELECT snapshot_json
                FROM results
                WHERE round_id = ?
                ORDER BY slot
                """,
                (round_id,),
            ).fetchall()
        return [json.loads(row["snapshot_json"]) for row in rows]

    def delete_round(self, round_id: int) -> None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT run_id FROM rounds WHERE id = ?",
                (round_id,),
            ).fetchone()
            if row is None:
                return
            run_id = str(row["run_id"])
            connection.execute("DELETE FROM rounds WHERE id = ?", (round_id,))
            remaining = connection.execute(
                "SELECT COUNT(*) FROM rounds WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
            if not remaining:
                connection.execute("DELETE FROM runs WHERE id = ?", (run_id,))

    def clear(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM runs")
