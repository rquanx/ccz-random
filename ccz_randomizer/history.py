from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 5
DEFAULT_PAGE_SIZE = 20


def history_database_path(base_dir: Path) -> Path:
    return base_dir / "ccz_fast_data" / "history.sqlite3"


def _now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def rule_snapshot_hash(rule: dict[str, Any]) -> str:
    digest = hashlib.sha256(_canonical_json(rule).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _rule_metadata(
    rule_name: str,
    rule: dict[str, Any],
) -> tuple[str, str, str]:
    rule_id = str(rule.get("id") or rule.get("ruleId") or rule_name)
    schema = str(
        rule.get("schemaVersion")
        or rule.get("ruleSchemaVersion")
        or "rule-schema-v1"
    )
    return rule_id, schema, rule_snapshot_hash(rule)


def _stable_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _skill_rows(
    member: dict[str, Any],
    key: str,
) -> list[dict[str, Any]]:
    value = member.get(key)
    return [item for item in value if isinstance(item, dict)] if isinstance(
        value, list
    ) else []


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
                        rule_id TEXT NOT NULL DEFAULT '',
                        rule_schema_version TEXT NOT NULL DEFAULT '',
                        rule_snapshot_hash TEXT NOT NULL DEFAULT '',
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

                    CREATE TABLE attempts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        round_id INTEGER NOT NULL REFERENCES rounds(id)
                            ON DELETE CASCADE,
                        slot INTEGER NOT NULL,
                        attempt_number INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        failure_reason TEXT NOT NULL DEFAULT '',
                        scored INTEGER NOT NULL DEFAULT 0,
                        save_confirmed INTEGER NOT NULL DEFAULT 0,
                        published INTEGER NOT NULL DEFAULT 0,
                        is_final_result INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL,
                        completed_at TEXT,
                        snapshot_json TEXT NOT NULL,
                        UNIQUE(round_id, slot, attempt_number)
                    );

                    CREATE TABLE result_members (
                        attempt_id INTEGER NOT NULL REFERENCES attempts(id)
                            ON DELETE CASCADE,
                        position INTEGER NOT NULL,
                        member_id TEXT NOT NULL DEFAULT '',
                        member_name TEXT NOT NULL DEFAULT '',
                        job_id TEXT NOT NULL DEFAULT '',
                        job_name TEXT NOT NULL DEFAULT '',
                        job_known INTEGER NOT NULL DEFAULT 1,
                        personal_skills_json TEXT NOT NULL DEFAULT '[]',
                        job_skills_json TEXT NOT NULL DEFAULT '[]',
                        memory_read_status TEXT NOT NULL DEFAULT '',
                        PRIMARY KEY(attempt_id, position)
                    );

                    CREATE TABLE result_skills (
                        attempt_id INTEGER NOT NULL REFERENCES attempts(id)
                            ON DELETE CASCADE,
                        member_position INTEGER NOT NULL,
                        skill_scope TEXT NOT NULL,
                        skill_id TEXT NOT NULL DEFAULT '',
                        skill_name TEXT NOT NULL DEFAULT '',
                        known INTEGER NOT NULL DEFAULT 1,
                        is_empty_marker INTEGER NOT NULL DEFAULT 0
                    );

                    CREATE TABLE result_treasures (
                        attempt_id INTEGER NOT NULL REFERENCES attempts(id)
                            ON DELETE CASCADE,
                        member_position INTEGER NOT NULL,
                        treasure_id TEXT NOT NULL DEFAULT '',
                        treasure_name TEXT NOT NULL DEFAULT '',
                        properties_json TEXT NOT NULL DEFAULT '[]',
                        set_ids_json TEXT NOT NULL DEFAULT '[]',
                        known INTEGER NOT NULL DEFAULT 1
                    );

                    CREATE TABLE result_treasure_properties (
                        attempt_id INTEGER NOT NULL REFERENCES attempts(id)
                            ON DELETE CASCADE,
                        member_position INTEGER NOT NULL,
                        treasure_id TEXT NOT NULL DEFAULT '',
                        property_id TEXT NOT NULL DEFAULT '',
                        property_name TEXT NOT NULL DEFAULT '',
                        known INTEGER NOT NULL DEFAULT 1,
                        is_empty_marker INTEGER NOT NULL DEFAULT 0
                    );

                    CREATE TABLE result_combinations (
                        attempt_id INTEGER NOT NULL REFERENCES attempts(id)
                            ON DELETE CASCADE,
                        member_position INTEGER NOT NULL DEFAULT -1,
                        combination_id TEXT NOT NULL DEFAULT '',
                        combination_name TEXT NOT NULL DEFAULT '',
                        known INTEGER NOT NULL DEFAULT 1,
                        PRIMARY KEY(attempt_id, member_position, combination_id)
                    );

                    CREATE INDEX idx_rounds_started
                        ON rounds(started_at DESC, id DESC);
                    CREATE INDEX idx_runs_rule_hash
                        ON runs(rule_snapshot_hash);
                    CREATE INDEX idx_results_round_slot
                        ON results(round_id, slot);
                    CREATE INDEX idx_attempts_round_slot
                        ON attempts(round_id, slot, attempt_number);
                    CREATE INDEX idx_attempts_final
                        ON attempts(is_final_result, status);
                    CREATE INDEX idx_skills_lookup
                        ON result_skills(skill_scope, skill_id, known);
                    CREATE INDEX idx_properties_lookup
                        ON result_treasure_properties(property_id, known);
                    CREATE INDEX idx_combinations_lookup
                        ON result_combinations(combination_id);

                    CREATE TABLE statistics_hidden_runs (
                        run_id TEXT PRIMARY KEY REFERENCES runs(id)
                            ON DELETE CASCADE,
                        hidden_at TEXT NOT NULL
                    );
                    """
                )
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            elif version == 1:
                connection.executescript(
                    """
                    ALTER TABLE runs ADD COLUMN rule_id TEXT NOT NULL DEFAULT '';
                    ALTER TABLE runs ADD COLUMN rule_schema_version
                        TEXT NOT NULL DEFAULT '';
                    ALTER TABLE runs ADD COLUMN rule_snapshot_hash
                        TEXT NOT NULL DEFAULT '';

                    CREATE TABLE IF NOT EXISTS attempts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        round_id INTEGER NOT NULL REFERENCES rounds(id)
                            ON DELETE CASCADE,
                        slot INTEGER NOT NULL,
                        attempt_number INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        failure_reason TEXT NOT NULL DEFAULT '',
                        scored INTEGER NOT NULL DEFAULT 0,
                        save_confirmed INTEGER NOT NULL DEFAULT 0,
                        published INTEGER NOT NULL DEFAULT 0,
                        is_final_result INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL,
                        completed_at TEXT,
                        snapshot_json TEXT NOT NULL,
                        UNIQUE(round_id, slot, attempt_number)
                    );
                    CREATE TABLE IF NOT EXISTS result_members (
                        attempt_id INTEGER NOT NULL REFERENCES attempts(id)
                            ON DELETE CASCADE,
                        position INTEGER NOT NULL,
                        member_id TEXT NOT NULL DEFAULT '',
                        member_name TEXT NOT NULL DEFAULT '',
                        job_id TEXT NOT NULL DEFAULT '',
                        job_name TEXT NOT NULL DEFAULT '',
                        job_known INTEGER NOT NULL DEFAULT 1,
                        personal_skills_json TEXT NOT NULL DEFAULT '[]',
                        job_skills_json TEXT NOT NULL DEFAULT '[]',
                        memory_read_status TEXT NOT NULL DEFAULT '',
                        PRIMARY KEY(attempt_id, position)
                    );
                    CREATE TABLE IF NOT EXISTS result_skills (
                        attempt_id INTEGER NOT NULL REFERENCES attempts(id)
                            ON DELETE CASCADE,
                        member_position INTEGER NOT NULL,
                        skill_scope TEXT NOT NULL,
                        skill_id TEXT NOT NULL DEFAULT '',
                        skill_name TEXT NOT NULL DEFAULT '',
                        known INTEGER NOT NULL DEFAULT 1,
                        is_empty_marker INTEGER NOT NULL DEFAULT 0
                    );
                    CREATE TABLE IF NOT EXISTS result_treasures (
                        attempt_id INTEGER NOT NULL REFERENCES attempts(id)
                            ON DELETE CASCADE,
                        member_position INTEGER NOT NULL,
                        treasure_id TEXT NOT NULL DEFAULT '',
                        treasure_name TEXT NOT NULL DEFAULT '',
                        properties_json TEXT NOT NULL DEFAULT '[]',
                        set_ids_json TEXT NOT NULL DEFAULT '[]',
                        known INTEGER NOT NULL DEFAULT 1
                    );
                    CREATE TABLE IF NOT EXISTS result_treasure_properties (
                        attempt_id INTEGER NOT NULL REFERENCES attempts(id)
                            ON DELETE CASCADE,
                        member_position INTEGER NOT NULL,
                        treasure_id TEXT NOT NULL DEFAULT '',
                        property_id TEXT NOT NULL DEFAULT '',
                        property_name TEXT NOT NULL DEFAULT '',
                        known INTEGER NOT NULL DEFAULT 1,
                        is_empty_marker INTEGER NOT NULL DEFAULT 0
                    );
                    CREATE TABLE IF NOT EXISTS result_combinations (
                        attempt_id INTEGER NOT NULL REFERENCES attempts(id)
                            ON DELETE CASCADE,
                        member_position INTEGER NOT NULL DEFAULT -1,
                        combination_id TEXT NOT NULL DEFAULT '',
                        combination_name TEXT NOT NULL DEFAULT '',
                        known INTEGER NOT NULL DEFAULT 1,
                        PRIMARY KEY(attempt_id, member_position, combination_id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_attempts_round_slot
                        ON attempts(round_id, slot, attempt_number);
                    CREATE INDEX IF NOT EXISTS idx_attempts_final
                        ON attempts(is_final_result, status);
                    CREATE INDEX IF NOT EXISTS idx_skills_lookup
                        ON result_skills(skill_scope, skill_id, known);
                    CREATE INDEX IF NOT EXISTS idx_properties_lookup
                        ON result_treasure_properties(property_id, known);
                    CREATE INDEX IF NOT EXISTS idx_combinations_lookup
                        ON result_combinations(combination_id);
                    CREATE TABLE IF NOT EXISTS statistics_hidden_runs (
                        run_id TEXT PRIMARY KEY REFERENCES runs(id)
                            ON DELETE CASCADE,
                        hidden_at TEXT NOT NULL
                    );
                    """
                )
                self._migrate_legacy_results(connection)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            elif version == 2:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS statistics_hidden_runs (
                        run_id TEXT PRIMARY KEY REFERENCES runs(id)
                            ON DELETE CASCADE,
                        hidden_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS result_combinations (
                        attempt_id INTEGER NOT NULL REFERENCES attempts(id)
                            ON DELETE CASCADE,
                        member_position INTEGER NOT NULL DEFAULT -1,
                        combination_id TEXT NOT NULL DEFAULT '',
                        combination_name TEXT NOT NULL DEFAULT '',
                        known INTEGER NOT NULL DEFAULT 1,
                        PRIMARY KEY(attempt_id, member_position, combination_id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_combinations_lookup
                        ON result_combinations(combination_id);
                    """
                )
                self._rebuild_combination_index(connection)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            elif version == 3:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS result_combinations (
                        attempt_id INTEGER NOT NULL REFERENCES attempts(id)
                            ON DELETE CASCADE,
                        member_position INTEGER NOT NULL DEFAULT -1,
                        combination_id TEXT NOT NULL DEFAULT '',
                        combination_name TEXT NOT NULL DEFAULT '',
                        PRIMARY KEY(attempt_id, member_position, combination_id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_combinations_lookup
                        ON result_combinations(combination_id);
                    """
                )
                columns = {
                    str(row["name"])
                    for row in connection.execute(
                        "PRAGMA table_info(result_combinations)"
                    ).fetchall()
                }
                if "known" not in columns:
                    connection.execute(
                        "ALTER TABLE result_combinations "
                        "ADD COLUMN known INTEGER NOT NULL DEFAULT 1"
                    )
                self._rebuild_combination_index(connection)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self._ensure_statistics_indexes(connection)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self._backfill_rule_metadata(connection)

    @staticmethod
    def _ensure_statistics_indexes(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_rounds_run_number
                ON rounds(run_id, round_number);
            CREATE INDEX IF NOT EXISTS idx_members_attempt_member
                ON result_members(attempt_id, member_id);
            CREATE INDEX IF NOT EXISTS idx_skills_attempt_scope
                ON result_skills(attempt_id, skill_scope);
            CREATE INDEX IF NOT EXISTS idx_treasures_attempt
                ON result_treasures(attempt_id);
            CREATE INDEX IF NOT EXISTS idx_properties_attempt
                ON result_treasure_properties(attempt_id);
            """
        )

    def _backfill_rule_metadata(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        """Assign rule fingerprints to legacy runs that predate rule metadata."""
        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(runs)")
        }
        required = {"id", "rule_name", "rule_json", "rule_id",
                    "rule_schema_version", "rule_snapshot_hash"}
        if not required.issubset(columns):
            return
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_runs_rule_hash "
            "ON runs(rule_snapshot_hash)"
        )
        rows = connection.execute(
            "SELECT id, rule_name, rule_json, rule_id, "
            "rule_schema_version, rule_snapshot_hash FROM runs "
            "WHERE rule_snapshot_hash IS NULL OR rule_snapshot_hash = ''"
        ).fetchall()
        for row in rows:
            try:
                parsed = json.loads(row["rule_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                parsed = {}
            if not isinstance(parsed, dict):
                parsed = {}
            if not parsed:
                parsed = {"legacyRuleName": str(row["rule_name"] or "")}
            rule_id, schema, snapshot_hash = _rule_metadata(
                str(row["rule_name"] or ""),
                parsed,
            )
            connection.execute(
                "UPDATE runs SET rule_id = ?, rule_schema_version = ?, "
                "rule_snapshot_hash = ? WHERE id = ?",
                (
                    str(row["rule_id"] or rule_id),
                    str(row["rule_schema_version"] or schema),
                    snapshot_hash,
                    str(row["id"]),
                ),
            )
    def _rebuild_combination_index(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        rows = connection.execute(
            "SELECT id, snapshot_json FROM attempts"
        ).fetchall()
        for row in rows:
            try:
                snapshot = json.loads(row["snapshot_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            self._replace_combination_index(
                connection,
                int(row["id"]),
                snapshot,
            )

    def _migrate_legacy_results(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        rows = connection.execute(
            """
            SELECT round_id, slot, accepted_attempt, created_at,
                   snapshot_json, save_verified
            FROM results
            ORDER BY id
            """
        ).fetchall()
        for row in rows:
            snapshot = json.loads(row["snapshot_json"])
            snapshot.setdefault("slot", int(row["slot"]))
            snapshot.setdefault(
                "acceptedAttempt",
                int(row["accepted_attempt"]),
            )
            snapshot.setdefault("createdAt", str(row["created_at"]))
            snapshot["legacyImport"] = True
            self._save_attempt_in_connection(
                connection,
                int(row["round_id"]),
                snapshot,
                status="accepted",
                failure_reason="legacy_import",
                scored=True,
                save_confirmed=bool(row["save_verified"]),
                published=bool(row["save_verified"]),
                is_final_result=bool(row["save_verified"]),
            )

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
        rule_id, rule_schema_version, rule_hash = _rule_metadata(
            rule_name,
            rule,
        )
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO runs (
                    id, started_at, finished_at, status, mode,
                    loop_random, rule_name, rule_id, rule_schema_version,
                    rule_snapshot_hash, rule_json, build_json
                ) VALUES (?, ?, NULL, 'running', ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (
                    run_id,
                    _now(),
                    mode,
                    int(loop_random),
                    rule_name,
                    rule_id,
                    rule_schema_version,
                    rule_hash,
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
                INSERT INTO rounds (
                    run_id, round_number, started_at, finished_at, status
                ) VALUES (?, ?, ?, NULL, 'running')
                ON CONFLICT(run_id, round_number) DO NOTHING
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

    def get_round_id(self, run_id: str, round_number: int) -> int | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT id FROM rounds
                WHERE run_id = ? AND round_number = ?
                """,
                (run_id, round_number),
            ).fetchone()
        return int(row["id"]) if row is not None else None

    def finish_open_rounds(self, run_id: str, status: str) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE rounds
                SET status = ?, finished_at = ?
                WHERE run_id = ? AND status = 'running'
                """,
                (status, _now(), run_id),
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
            result_id = int(row["id"])
            save_confirmed = bool(save.get("verified"))
            published = bool(save.get("published"))
            self._save_attempt_in_connection(
                connection,
                round_id,
                snapshot,
                status="accepted",
                failure_reason="",
                scored=True,
                save_confirmed=save_confirmed,
                published=published,
                is_final_result=save_confirmed and published,
            )
            return result_id

    def save_attempt(
        self,
        round_id: int,
        snapshot: dict[str, Any],
        *,
        status: str,
        failure_reason: str = "",
        scored: bool = True,
        save_confirmed: bool = False,
        published: bool = False,
        is_final_result: bool = False,
    ) -> int:
        with closing(self._connect()) as connection, connection:
            return self._save_attempt_in_connection(
                connection,
                round_id,
                snapshot,
                status=status,
                failure_reason=failure_reason,
                scored=scored,
                save_confirmed=save_confirmed,
                published=published,
                is_final_result=is_final_result,
            )

    def _save_attempt_in_connection(
        self,
        connection: sqlite3.Connection,
        round_id: int,
        snapshot: dict[str, Any],
        *,
        status: str,
        failure_reason: str,
        scored: bool,
        save_confirmed: bool,
        published: bool,
        is_final_result: bool,
    ) -> int:
        slot = int(snapshot.get("slot") or snapshot.get("resultSlot") or 0)
        attempt_number = int(
            snapshot.get("attempt")
            or snapshot.get("acceptedAttempt")
            or 0
        )
        if slot <= 0 or attempt_number <= 0:
            raise ValueError("统计尝试必须包含有效的存档编号和尝试次数")
        created_at = str(snapshot.get("createdAt") or _now())
        final = bool(
            is_final_result
            and status == "accepted"
            and save_confirmed
            and published
        )
        connection.execute(
            """
            INSERT INTO attempts (
                round_id, slot, attempt_number, status, failure_reason,
                scored, save_confirmed, published, is_final_result,
                created_at, completed_at, snapshot_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(round_id, slot, attempt_number) DO UPDATE SET
                status = CASE
                    WHEN attempts.status = 'accepted'
                        AND excluded.status IN ('failed', 'rejected')
                    THEN attempts.status
                    WHEN attempts.status = 'failed'
                        AND excluded.status = 'rejected'
                    THEN attempts.status
                    ELSE excluded.status
                END,
                failure_reason = CASE
                    WHEN excluded.failure_reason <> ''
                    THEN excluded.failure_reason
                    ELSE attempts.failure_reason
                END,
                scored = MAX(attempts.scored, excluded.scored),
                save_confirmed = MAX(
                    attempts.save_confirmed, excluded.save_confirmed
                ),
                published = MAX(attempts.published, excluded.published),
                is_final_result = MAX(
                    attempts.is_final_result, excluded.is_final_result
                ),
                completed_at = excluded.completed_at,
                snapshot_json = CASE
                    WHEN attempts.snapshot_json = '{}' THEN excluded.snapshot_json
                    ELSE excluded.snapshot_json
                END
            """,
            (
                round_id,
                slot,
                attempt_number,
                status,
                failure_reason,
                int(scored),
                int(save_confirmed),
                int(published),
                int(final),
                created_at,
                _now(),
                json.dumps(snapshot, ensure_ascii=False),
            ),
        )
        row = connection.execute(
            """
            SELECT id FROM attempts
            WHERE round_id = ? AND slot = ? AND attempt_number = ?
            """,
            (round_id, slot, attempt_number),
        ).fetchone()
        assert row is not None
        attempt_id = int(row["id"])
        if final:
            connection.execute(
                """
                UPDATE attempts
                SET is_final_result = 0
                WHERE round_id = ? AND slot = ? AND id <> ?
                """,
                (round_id, slot, attempt_id),
            )
        self._replace_attempt_indexes(connection, attempt_id, snapshot)
        return attempt_id

    def _replace_attempt_indexes(
        self,
        connection: sqlite3.Connection,
        attempt_id: int,
        snapshot: dict[str, Any],
    ) -> None:
        for table in (
            "result_members",
            "result_skills",
            "result_treasures",
            "result_treasure_properties",
            "result_combinations",
        ):
            connection.execute(
                f"DELETE FROM {table} WHERE attempt_id = ?",
                (attempt_id,),
            )

        members = snapshot.get("members")
        if not isinstance(members, list):
            members = []
        for position, member in enumerate(members):
            if not isinstance(member, dict):
                continue
            member_position = int(member.get("position", position))
            member_name = _stable_id(
                member.get("memberName") or member.get("name")
            )
            member_id = _stable_id(
                member.get("memberId"),
                member_name,
            )
            job_name = _stable_id(
                member.get("jobName") or member.get("job")
            )
            job_id = _stable_id(member.get("jobId"), job_name)
            personal = _skill_rows(member, "personalSkills")
            job_skills = _skill_rows(member, "jobSkills")
            connection.execute(
                """
                INSERT INTO result_members (
                    attempt_id, position, member_id, member_name,
                    job_id, job_name, job_known,
                    personal_skills_json, job_skills_json,
                    memory_read_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    member_position,
                    member_id,
                    member_name,
                    job_id,
                    job_name,
                    int(bool(member.get("jobKnown", bool(job_name)))),
                    json.dumps(personal, ensure_ascii=False),
                    json.dumps(job_skills, ensure_ascii=False),
                    str(member.get("memoryReadStatus") or ""),
                ),
            )
            for scope, skills in (
                ("personal", personal),
                ("job", job_skills),
            ):
                indexed_skills = skills or [
                    {
                        "skillId": "",
                        "skillName": "",
                        "known": True,
                        "empty": True,
                    }
                ]
                for skill in indexed_skills:
                    skill_name = _stable_id(
                        skill.get("skillName") or skill.get("name")
                    )
                    skill_id = _stable_id(
                        skill.get("skillId")
                        or skill.get("internalId")
                        or skill.get("canonicalName"),
                        skill_name,
                    )
                    connection.execute(
                        """
                        INSERT INTO result_skills (
                            attempt_id, member_position, skill_scope,
                            skill_id, skill_name, known, is_empty_marker
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            attempt_id,
                            member_position,
                            scope,
                            skill_id,
                            skill_name,
                            int(bool(skill.get("known", bool(skill_name)))),
                            int(bool(skill.get("empty"))),
                        ),
                    )

        treasures = snapshot.get("treasures")
        if not isinstance(treasures, list):
            treasures = []
        if not treasures:
            equipment = snapshot.get("equipment") or {}
            for category in equipment.get("categories") or []:
                for item in category.get("items") or []:
                    treasures.append(
                        {
                            "memberPosition": -1,
                            "treasureName": item.get("name"),
                            "properties": [
                                {
                                    "propertyName": item.get("effect"),
                                    "known": bool(item.get("effect")),
                                }
                            ],
                        }
                    )
        for treasure in treasures:
            if not isinstance(treasure, dict):
                continue
            member_position = int(treasure.get("memberPosition", -1))
            treasure_name = _stable_id(
                treasure.get("treasureName") or treasure.get("name")
            )
            treasure_id = _stable_id(
                treasure.get("treasureId"),
                treasure_name,
            )
            properties = treasure.get("properties")
            if not isinstance(properties, list):
                properties = []
            sets = treasure.get("setIds")
            if not isinstance(sets, list):
                sets = []
            connection.execute(
                """
                INSERT INTO result_treasures (
                    attempt_id, member_position, treasure_id,
                    treasure_name, properties_json, set_ids_json, known
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    member_position,
                    treasure_id,
                    treasure_name,
                    json.dumps(properties, ensure_ascii=False),
                    json.dumps(sets, ensure_ascii=False),
                    int(bool(treasure.get("known", bool(treasure_name)))),
                ),
            )
            indexed_properties = properties or [
                {
                    "propertyId": "",
                    "propertyName": "",
                    "known": True,
                    "empty": True,
                }
            ]
            for property_row in indexed_properties:
                if not isinstance(property_row, dict):
                    property_row = {
                        "propertyName": str(property_row),
                    }
                property_name = _stable_id(
                    property_row.get("propertyName")
                    or property_row.get("name")
                )
                property_id = _stable_id(
                    property_row.get("propertyId"),
                    property_name,
                )
                connection.execute(
                    """
                    INSERT INTO result_treasure_properties (
                        attempt_id, member_position, treasure_id,
                        property_id, property_name, known, is_empty_marker
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        attempt_id,
                        member_position,
                        treasure_id,
                        property_id,
                        property_name,
                        int(
                            bool(
                                property_row.get(
                                    "known",
                                    bool(property_name),
                                )
                            )
                        ),
                        int(bool(property_row.get("empty"))),
                    ),
                )
        combinations = snapshot.get("combinations")
        if not isinstance(combinations, list):
            combinations = []
            seen: set[str] = set()
            for treasure in treasures:
                if not isinstance(treasure, dict):
                    continue
                ids = treasure.get("setIds")
                names = treasure.get("setNames")
                if not isinstance(ids, list):
                    continue
                if not isinstance(names, list):
                    names = []
                for index, raw_id in enumerate(ids):
                    combination_id = _stable_id(raw_id)
                    if not combination_id or combination_id in seen:
                        continue
                    seen.add(combination_id)
                    combinations.append(
                        {
                            "combinationId": combination_id,
                            "combinationName": (
                                names[index]
                                if index < len(names)
                                else combination_id
                            ),
                        }
                    )
        for combination in combinations:
            if not isinstance(combination, dict):
                continue
            combination_id = _stable_id(
                combination.get("combinationId")
                or combination.get("id")
            )
            if not combination_id:
                continue
            combination_name = _stable_id(
                combination.get("combinationName")
                or combination.get("name"),
                combination_id,
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO result_combinations (
                    attempt_id, member_position, combination_id,
                    combination_name, known
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    int(combination.get("memberPosition", -1)),
                    combination_id,
                    combination_name,
                    int(bool(combination.get("known", True))),
                ),
            )

    def _replace_combination_index(
        self,
        connection: sqlite3.Connection,
        attempt_id: int,
        snapshot: dict[str, Any],
    ) -> None:
        connection.execute(
            "DELETE FROM result_combinations WHERE attempt_id = ?",
            (attempt_id,),
        )
        combinations = snapshot.get("combinations")
        if not isinstance(combinations, list):
            combinations = []
            seen: set[str] = set()
            treasures = snapshot.get("treasures")
            if not isinstance(treasures, list):
                treasures = []
            for treasure in treasures:
                if not isinstance(treasure, dict):
                    continue
                ids = treasure.get("setIds")
                names = treasure.get("setNames")
                if not isinstance(ids, list):
                    continue
                if not isinstance(names, list):
                    names = []
                for index, raw_id in enumerate(ids):
                    combination_id = _stable_id(raw_id)
                    if not combination_id or combination_id in seen:
                        continue
                    seen.add(combination_id)
                    combinations.append(
                        {
                            "combinationId": combination_id,
                            "combinationName": (
                                names[index]
                                if index < len(names)
                                else combination_id
                            ),
                        }
                    )
        for combination in combinations:
            if not isinstance(combination, dict):
                continue
            combination_id = _stable_id(
                combination.get("combinationId")
                or combination.get("id")
            )
            if not combination_id:
                continue
            combination_name = _stable_id(
                combination.get("combinationName")
                or combination.get("name"),
                combination_id,
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO result_combinations (
                    attempt_id, member_position, combination_id,
                    combination_name, known
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    int(combination.get("memberPosition", -1)),
                    combination_id,
                    combination_name,
                    int(bool(combination.get("known", True))),
                ),
            )

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
            attempt_number = int(snapshot.get("acceptedAttempt") or 0)
            if attempt_number:
                connection.execute(
                    """
                    UPDATE attempts
                    SET save_confirmed = ?,
                        is_final_result = CASE
                            WHEN ? = 1 AND published = 1 THEN 1
                            ELSE 0
                        END
                    WHERE round_id = ? AND slot = ?
                      AND attempt_number = ?
                    """,
                    (
                        int(verified),
                        int(verified),
                        round_id,
                        slot,
                        attempt_number,
                    ),
                )

    def mark_result_published(
        self,
        *,
        round_id: int | None = None,
        run_id: str | None = None,
        slot: int,
        save_sha256: str,
    ) -> int:
        if not save_sha256:
            return 0
        with closing(self._connect()) as connection, connection:
            clauses = [
                "attempts.slot = ?",
                "attempts.status = 'accepted'",
            ]
            values: list[Any] = [slot]
            if round_id is not None:
                clauses.append("attempts.round_id = ?")
                values.append(round_id)
            if run_id is not None:
                clauses.append("runs.id = ?")
                values.append(run_id)
            rows = connection.execute(
                f"""
                SELECT attempts.id, attempts.snapshot_json
                FROM attempts
                JOIN rounds ON rounds.id = attempts.round_id
                JOIN runs ON runs.id = rounds.run_id
                WHERE {" AND ".join(clauses)}
                ORDER BY attempts.id DESC
                """,
                values,
            ).fetchall()
            updated = 0
            for row in rows:
                snapshot = json.loads(row["snapshot_json"])
                save = snapshot.get("save") or {}
                if str(save.get("sha256") or "") != save_sha256:
                    continue
                save["published"] = True
                save["verified"] = True
                snapshot["save"] = save
                connection.execute(
                    """
                    UPDATE attempts
                    SET save_confirmed = 1, published = 1,
                        is_final_result = 1, snapshot_json = ?
                    WHERE id = ?
                    """,
                    (
                        json.dumps(snapshot, ensure_ascii=False),
                        int(row["id"]),
                    ),
                )
                connection.execute(
                    """
                    UPDATE results
                    SET save_verified = 1, save_sha256 = ?,
                        snapshot_json = ?
                    WHERE round_id = (
                        SELECT round_id FROM attempts WHERE id = ?
                    )
                      AND slot = ?
                    """,
                    (
                        save_sha256,
                        json.dumps(snapshot, ensure_ascii=False),
                        int(row["id"]),
                        slot,
                    ),
                )
                updated += 1
                break
            return updated

    def clear_statistics(self) -> None:
        """Hide statistical facts without deleting snapshots or external files."""
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO statistics_hidden_runs (run_id, hidden_at)
                SELECT id, ? FROM runs
                """,
                (_now(),),
            )

    def rebuild_statistics(self) -> None:
        """Rebuild normalized projections and make all facts visible."""
        with closing(self._connect()) as connection, connection:
            for table in (
                "result_members",
                "result_skills",
                "result_treasures",
                "result_treasure_properties",
                "result_combinations",
            ):
                connection.execute(f"DELETE FROM {table}")
            rows = connection.execute(
                "SELECT id, snapshot_json FROM attempts"
            ).fetchall()
            for row in rows:
                try:
                    snapshot = json.loads(row["snapshot_json"])
                except (TypeError, json.JSONDecodeError):
                    continue
                self._replace_attempt_indexes(
                    connection,
                    int(row["id"]),
                    snapshot,
                )
            connection.execute("DELETE FROM statistics_hidden_runs")

    def hidden_run_ids(self) -> set[str]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT run_id FROM statistics_hidden_runs"
            ).fetchall()
        return {str(row["run_id"]) for row in rows}

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

    def list_runs(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> list[dict[str, Any]]:
        page = max(1, int(page))
        page_size = max(1, min(100, int(page_size)))
        offset = (page - 1) * page_size
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT
                    runs.id,
                    runs.started_at,
                    runs.finished_at,
                    runs.status,
                    runs.mode,
                    runs.loop_random,
                    runs.rule_name,
                    runs.rule_schema_version,
                    runs.rule_snapshot_hash,
                    COUNT(DISTINCT rounds.id) AS round_count,
                    COUNT(DISTINCT attempts.id) AS attempt_count
                FROM runs
                LEFT JOIN rounds ON rounds.run_id = runs.id
                LEFT JOIN attempts ON attempts.round_id = rounds.id
                GROUP BY runs.id
                ORDER BY runs.started_at DESC, runs.id DESC
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

    def delete_run(self, run_id: str) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM runs WHERE id = ?", (run_id,))

    def clear(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM runs")
