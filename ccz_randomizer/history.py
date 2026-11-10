from __future__ import annotations

import datetime as dt
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 3
DEFAULT_PAGE_SIZE = 20
SUMMARY_MEMBER_LIMIT = 3


def history_database_path(base_dir: Path) -> Path:
    return base_dir / "ccz_fast_data" / "history.sqlite3"


def compatible_history_database_path(base_dir: Path) -> Path:
    path = history_database_path(base_dir)
    return path.with_name(f"{path.stem}-v{SCHEMA_VERSION}{path.suffix}")


def _now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _summary_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Keep only fields needed to paint history cards."""
    from ccz_randomizer.history_members import history_members
    detail = snapshot.get("detail") or {}
    job = detail.get("job") or {}
    skill = detail.get("skill") or {}
    metrics = job.get("metrics") or {}
    members = history_members(snapshot)
    return {
        "slot": snapshot.get("slot"),
        "createdAt": snapshot.get("createdAt"),
        "gameVersion": snapshot.get("gameVersion"),
        "mode": snapshot.get("mode"),
        "members": members[:SUMMARY_MEMBER_LIMIT],
        "memberCount": len(members),
        "detail": {"job": {"metrics": {key: metrics.get(key) for key in ("average", "qualificationAverage")}},
                    "skill": {"metrics": {"skillScore": (skill.get("metrics") or {}).get("skillScore")}}},
    }


class HistoryRepository:
    def __init__(self, base_dir: Path):
        self.path = history_database_path(base_dir)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self._schema_version(self.path) > SCHEMA_VERSION:
            self.path = compatible_history_database_path(base_dir)
        self._initialize()

    @staticmethod
    def _schema_version(path: Path) -> int:
        if not path.is_file():
            return 0
        with closing(sqlite3.connect(path, timeout=5)) as connection:
            return int(
                connection.execute("PRAGMA user_version").fetchone()[0]
            )

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
            if version == SCHEMA_VERSION:
                return
            connection.execute("BEGIN IMMEDIATE")
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"历史数据库版本过新：{version}/{SCHEMA_VERSION}"
                )
            if version == 0:
                schema = (
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
                for statement in schema.split(";"):
                    if statement.strip():
                        connection.execute(statement)
            if version < 2:
                connection.execute(
                    "CREATE TABLE result_summaries ("
                    "result_id INTEGER PRIMARY KEY REFERENCES results(id) ON DELETE CASCADE, "
                    "summary_json TEXT NOT NULL)"
                )
            if version < 3:
                connection.execute("ALTER TABLE rounds ADD COLUMN title TEXT NOT NULL DEFAULT ''")
                connection.execute("ALTER TABLE rounds ADD COLUMN note TEXT NOT NULL DEFAULT ''")
                connection.execute("ALTER TABLE rounds ADD COLUMN marked INTEGER NOT NULL DEFAULT 0")
                connection.execute("CREATE TABLE result_annotations ("
                                   "result_id INTEGER PRIMARY KEY REFERENCES results(id) ON DELETE CASCADE, "
                                   "title TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '', "
                                   "marked INTEGER NOT NULL DEFAULT 0)")
                connection.execute("CREATE TABLE result_saves ("
                                   "result_id INTEGER PRIMARY KEY REFERENCES results(id) ON DELETE CASCADE, "
                                   "sha256 TEXT NOT NULL, data BLOB NOT NULL)")
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
                INSERT INTO runs (
                    id, started_at, finished_at, status, mode,
                    loop_random, rule_name, rule_json, build_json
                ) VALUES (?, ?, NULL, 'running', ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = 'running', finished_at = NULL,
                    mode = excluded.mode,
                    loop_random = excluded.loop_random,
                    rule_name = excluded.rule_name,
                    rule_json = excluded.rule_json,
                    build_json = excluded.build_json
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
            connection.execute(
                "DELETE FROM rounds WHERE run_id = ? AND NOT EXISTS "
                "(SELECT 1 FROM results WHERE results.round_id = rounds.id)", (run_id,))
            connection.execute(
                "DELETE FROM runs WHERE id = ? AND NOT EXISTS "
                "(SELECT 1 FROM rounds WHERE rounds.run_id = runs.id)", (run_id,))

    def start_round(self, run_id: str, round_number: int) -> int:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO rounds (
                    run_id, round_number, started_at, finished_at, status
                ) VALUES (?, ?, ?, NULL, 'running')
                ON CONFLICT(run_id, round_number) DO UPDATE SET
                    finished_at = NULL, status = 'running'
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

    def require_round(self, run_id: str, round_number: int) -> int:
        """Attach a worker without resetting shared metadata or lifecycle."""
        with closing(self._connect()) as connection:
            row = connection.execute(
                'SELECT id FROM rounds WHERE run_id=? AND round_number=?',
                (run_id, round_number),
            ).fetchone()
        if row is None:
            raise RuntimeError('随机轮次尚未由调度进程创建，不能写入历史记录')
        return int(row['id'])

    def get_round_status(self, round_id: int) -> str | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT status FROM rounds WHERE id=?", (round_id,)).fetchone()
        return str(row[0]) if row else None

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
            connection.execute(
                "DELETE FROM rounds WHERE id = ? AND NOT EXISTS "
                "(SELECT 1 FROM results WHERE results.round_id = rounds.id)", (round_id,))

    def save_result(
        self,
        round_id: int,
        snapshot: dict[str, Any],
        *,
        save_path: Path | None = None,
    ) -> int:
        detail = snapshot.get("detail") or {}
        job_metrics = ((detail.get("job") or {}).get("metrics") or {})
        skill_metrics = ((detail.get("skill") or {}).get("metrics") or {})
        save = snapshot.get("save") or {}
        backup = None
        if save_path is not None:
            from ccz_randomizer.history_saves import verified_save
            backup = verified_save(save_path, str(save.get("sha256") or ""))
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO results (
                    round_id, slot, accepted_attempt, created_at, mode,
                    job_average, skill_score, save_path, save_sha256,
                    save_verified, verification_error, snapshot_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(round_id, slot) DO UPDATE SET
                    accepted_attempt = excluded.accepted_attempt,
                    created_at = excluded.created_at, mode = excluded.mode,
                    job_average = excluded.job_average, skill_score = excluded.skill_score,
                    save_path = excluded.save_path, save_sha256 = excluded.save_sha256,
                    save_verified = excluded.save_verified,
                    verification_error = excluded.verification_error,
                    snapshot_json = excluded.snapshot_json
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
            connection.execute("INSERT INTO result_summaries(result_id,summary_json) VALUES (?,?) "
                               "ON CONFLICT(result_id) DO UPDATE SET summary_json=excluded.summary_json",
                               (row["id"], json.dumps(_summary_snapshot(snapshot), ensure_ascii=False)))
            if backup is not None:
                data, digest = backup
                connection.execute("INSERT INTO result_saves(result_id,sha256,data) VALUES (?,?,?) "
                                   "ON CONFLICT(result_id) DO UPDATE SET sha256=excluded.sha256,data=excluded.data",
                                   (row["id"], digest, data))
            else:
                connection.execute("DELETE FROM result_saves WHERE result_id=? AND sha256 != ?",
                                   (row["id"], str(save.get("sha256") or "")))
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

    @staticmethod
    def _round_filter(query: str, marked_only: bool, started_after: str | None = None,
                      started_before: str | None = None, rule_name: str | None = None) -> tuple[str, list]:
        clauses = []
        parameters = []
        matching = ["results.round_id = rounds.id"]
        if query.strip():
            # instr treats %, _ and quotes as literal search characters.
            matching.append("(instr(lower(rounds.title || ' ' || rounds.note), lower(?)) > 0 "
                           "OR EXISTS (SELECT 1 FROM runs WHERE runs.id=rounds.run_id "
                           "AND instr(lower(runs.rule_name),lower(?)) > 0) "
                           "OR instr(lower(COALESCE(a.title,'') || ' ' || COALESCE(a.note,'')),lower(?)) > 0)")
            parameters.extend([query.strip()] * 3)
        if marked_only:
            matching.append("(rounds.marked=1 OR a.marked=1)")
        join = " LEFT JOIN result_annotations a ON a.result_id=results.id" if query.strip() or marked_only else ""
        clauses.append(f"EXISTS (SELECT 1 FROM results{join} WHERE {' AND '.join(matching)})")
        if started_after:
            clauses.append("rounds.started_at >= ?")
            parameters.append(started_after)
        if started_before:
            clauses.append("rounds.started_at < ?")
            parameters.append(started_before)
        if rule_name is not None:
            clauses.append("EXISTS (SELECT 1 FROM runs WHERE runs.id=rounds.run_id AND runs.rule_name=?)")
            parameters.append(rule_name)
        return " AND ".join(clauses), parameters

    def list_rule_names(self) -> list[str]:
        """Include rules from saved history even if their current profile was deleted."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT DISTINCT rule_name FROM runs WHERE EXISTS ("
                "SELECT 1 FROM rounds JOIN results ON results.round_id=rounds.id "
                "WHERE rounds.run_id=runs.id) ORDER BY rule_name COLLATE NOCASE, rule_name"
            ).fetchall()
        return [str(row[0]) for row in rows]

    def count_rounds(self, *, query: str = "", marked_only: bool = False,
                     started_after: str | None = None, started_before: str | None = None,
                     rule_name: str | None = None) -> int:
        where, parameters = self._round_filter(query, marked_only, started_after, started_before, rule_name)
        with closing(self._connect()) as connection, connection:
            return int(
                connection.execute(
                    f"SELECT COUNT(*) FROM rounds WHERE {where}", parameters
                ).fetchone()[0]
            )

    def list_rounds(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        *,
        query: str = "",
        marked_only: bool = False,
        started_after: str | None = None,
        started_before: str | None = None,
        rule_name: str | None = None,
    ) -> list[dict[str, Any]]:
        page = max(1, int(page))
        page_size = max(1, min(100, int(page_size)))
        offset = (page - 1) * page_size
        where, parameters = self._round_filter(query, marked_only, started_after, started_before, rule_name)
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                f"""
                SELECT
                    page.id,
                    page.run_id,
                    page.round_number,
                    page.started_at,
                    page.finished_at,
                    page.status,
                    page.title,
                    page.note,
                    page.marked,
                    runs.mode,
                    runs.loop_random,
                    runs.rule_name,
                    (SELECT COUNT(*) FROM results
                     WHERE results.round_id = page.id) AS result_count
                FROM (
                    SELECT * FROM rounds
                    WHERE {where}
                    ORDER BY started_at DESC, id DESC
                    LIMIT ? OFFSET ?
                ) AS page
                JOIN runs ON runs.id = page.run_id
                ORDER BY page.started_at DESC, page.id DESC
                """,
                (*parameters, page_size, offset),
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

    def get_round_summaries(self, round_id: int) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                "SELECT results.id, result_summaries.summary_json, "
                "COALESCE(rounds.title,'') AS title, COALESCE(rounds.note,'') AS note, "
                "COALESCE(rounds.marked,0) AS marked, "
                "EXISTS (SELECT 1 FROM result_saves WHERE result_id=results.id) AS backed_up FROM results "
                "LEFT JOIN result_summaries ON result_summaries.result_id = results.id "
                "JOIN rounds ON rounds.id=results.round_id "
                "WHERE round_id = ? ORDER BY slot",
                (round_id,),
            ).fetchall()
            summaries = []
            for row in rows:
                summary = json.loads(row["summary_json"]) if row["summary_json"] is not None else None
                if summary is None:
                    # Old databases are upgraded on demand, only for the selected
                    # round. Never decode the whole history while opening it.
                    saved = connection.execute("SELECT snapshot_json FROM results WHERE id = ?", (row["id"],)).fetchone()
                    if saved is None:
                        continue
                    summary = _summary_snapshot(json.loads(saved["snapshot_json"]))
                    connection.execute("INSERT INTO result_summaries(result_id,summary_json) VALUES (?,?) "
                                       "ON CONFLICT(result_id) DO NOTHING",
                                       (row["id"], json.dumps(summary, ensure_ascii=False)))
                summary["history"] = {key: row[key] for key in ("title", "note", "marked", "backed_up")}
                summaries.append(summary)
        return summaries

    def get_result(self, round_id: int, slot: int) -> dict[str, Any] | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT snapshot_json FROM results WHERE round_id = ? AND slot = ?",
                (round_id, slot),
            ).fetchone()
        return json.loads(row["snapshot_json"]) if row else None

    def annotate_round(self, round_id: int, *, title: str, note: str, marked: bool = False) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute("UPDATE rounds SET title=?,note=?,marked=? WHERE id=?",
                               (title.strip()[:100], note.strip()[:1000], int(marked), round_id))

    def annotate_result(self, round_id: int, slot: int, *, title: str, note: str, marked: bool) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute("INSERT INTO result_annotations(result_id,title,note,marked) "
                               "SELECT id,?,?,? FROM results WHERE round_id=? AND slot=? "
                               "ON CONFLICT(result_id) DO UPDATE SET title=excluded.title,note=excluded.note,marked=excluded.marked",
                               (title.strip()[:100], note.strip()[:1000], int(marked), round_id, slot))

    def export_result_save(self, round_id: int, slot: int, destination: Path) -> None:
        from ccz_randomizer.history_saves import export_save
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT s.data,s.sha256 FROM result_saves s "
                                     "JOIN results r ON r.id=s.result_id WHERE r.round_id=? AND r.slot=?",
                                     (round_id, slot)).fetchone()
        if row is None:
            raise ValueError("这条记录没有独立存档副本；可先尝试补备份旧记录")
        export_save(Path(destination), row["data"], row["sha256"])

    def backfill_saves(self) -> dict[str, int]:
        """Only copy old files whose checksum still matches the recorded result."""
        from ccz_randomizer.history_saves import verified_save
        counts = dict(saved=0, unavailable=0)
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT r.id,r.save_path,r.save_sha256 FROM results r "
                                      "WHERE NOT EXISTS (SELECT 1 FROM result_saves s WHERE s.result_id=r.id)").fetchall()
        for row in rows:
            try:
                data, digest = verified_save(Path(row["save_path"] or ""), row["save_sha256"] or "")
            except (OSError, ValueError):
                counts["unavailable"] += 1
                continue
            with closing(self._connect()) as connection, connection:
                cursor = connection.execute("INSERT INTO result_saves(result_id,sha256,data) "
                                            "SELECT id,?,? FROM results WHERE id=? AND save_sha256=? "
                                            "ON CONFLICT(result_id) DO NOTHING", (digest, data, row["id"], digest))
                counts["saved"] += cursor.rowcount
        return counts

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
