from __future__ import annotations

import csv
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ccz_randomizer.history import HistoryRepository


@dataclass(frozen=True)
class StatisticsFilters:
    """Independent rule and result filters used by every statistics view."""

    scope: str = "history"
    metric: str = "final"
    mode: str = "all"
    rule_mode: str = "all_summary"
    rule_hashes: tuple[str, ...] = ()
    current_rule_hash: str | None = None
    run_id: str | None = None
    round_id: int | None = None
    slots: tuple[int, ...] = ()
    member_id: str | None = None
    attempt_id: int | None = None
    status: str | None = None
    status_group: str | None = None
    failure_reason: str | None = None
    content_kind: str | None = None
    content_value: str | None = None
    started_after: str | None = None
    started_before: str | None = None


@dataclass(frozen=True)
class ValidationReport:
    valid: bool
    issues: tuple[str, ...] = ()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class StatisticsRepository:
    """Query and validate the normalized history projection."""

    def __init__(self, base_dir: Path):
        self.history = HistoryRepository(base_dir)
        self.path = self.history.path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _where(
        self,
        filters: StatisticsFilters,
        *,
        alias: str = "a",
    ) -> tuple[str, list[Any]]:
        clauses = [
            "1 = 1",
            "NOT EXISTS ("
            "SELECT 1 FROM statistics_hidden_runs shr "
            "WHERE shr.run_id = r.id"
            ")",
        ]
        values: list[Any] = []
        if filters.metric == "final":
            clauses.extend(
                [
                    f"{alias}.is_final_result = 1",
                    f"{alias}.status = 'accepted'",
                    f"{alias}.save_confirmed = 1",
                    f"{alias}.published = 1",
                ]
            )
        elif filters.metric == "completed":
            clauses.append(f"{alias}.scored = 1")
        elif filters.metric != "attempts":
            raise ValueError(f"未知统计口径：{filters.metric}")

        if filters.scope == "current_run":
            if not filters.run_id:
                clauses.append("0 = 1")
            else:
                clauses.append("r.id = ?")
                values.append(filters.run_id)
        elif filters.scope == "current_round":
            if filters.round_id is None:
                clauses.append("0 = 1")
            else:
                clauses.append("rd.id = ?")
                values.append(filters.round_id)
        elif filters.scope != "history":
            raise ValueError(f"未知统计范围：{filters.scope}")

        if filters.mode != "all":
            clauses.append("r.mode = ?")
            values.append(filters.mode)
        if filters.run_id and filters.scope != "current_run":
            clauses.append("r.id = ?")
            values.append(filters.run_id)
        if filters.round_id is not None and filters.scope != "current_round":
            clauses.append("rd.id = ?")
            values.append(filters.round_id)
        if filters.slots:
            marks = ",".join("?" for _ in filters.slots)
            clauses.append(f"{alias}.slot IN ({marks})")
            values.extend(filters.slots)
        if filters.member_id:
            clauses.append(
                "EXISTS ("
                "SELECT 1 FROM result_members rm_filter "
                f"WHERE rm_filter.attempt_id = {alias}.id "
                "AND rm_filter.member_id = ?"
                ")"
            )
            values.append(filters.member_id)
        if filters.attempt_id is not None:
            clauses.append(f"{alias}.id = ?")
            values.append(int(filters.attempt_id))
        if filters.status:
            clauses.append(f"{alias}.status = ?")
            values.append(filters.status)
        if filters.status_group == "other":
            clauses.append(
                f"{alias}.status NOT IN ('accepted', 'rejected')"
            )
        elif filters.status_group not in {None, ""}:
            raise ValueError(f"未知状态分组：{filters.status_group}")
        if filters.failure_reason:
            clauses.append(f"{alias}.failure_reason = ?")
            values.append(filters.failure_reason)
        if filters.content_kind and filters.content_value is not None:
            content_value = filters.content_value
            if filters.content_kind == "job":
                clauses.append(
                    "EXISTS ("
                    "SELECT 1 FROM result_members rm_content "
                    f"WHERE rm_content.attempt_id = {alias}.id "
                    "AND (rm_content.job_id = ? OR rm_content.job_name = ?)"
                    ")"
                )
                values.extend((content_value, content_value))
            elif filters.content_kind in {"personal", "job_skill"}:
                scope = (
                    "personal"
                    if filters.content_kind == "personal"
                    else "job"
                )
                clauses.append(
                    "EXISTS ("
                    "SELECT 1 FROM result_skills rs_content "
                    f"WHERE rs_content.attempt_id = {alias}.id "
                    "AND rs_content.skill_scope = ? "
                    "AND (rs_content.skill_id = ? "
                    "OR rs_content.skill_name = ? "
                    "OR (? = '无' AND rs_content.is_empty_marker = 1) "
                    "OR (? = '未知' AND rs_content.known = 0))"
                    ")"
                )
                values.extend(
                    (
                        scope,
                        content_value,
                        content_value,
                        content_value,
                        content_value,
                    )
                )
            elif filters.content_kind in {
                "personal_combo",
                "job_skill_combo",
            }:
                try:
                    combo_ids = json.loads(content_value)
                except (TypeError, json.JSONDecodeError):
                    combo_ids = []
                if not isinstance(combo_ids, list) or not combo_ids:
                    clauses.append("0 = 1")
                else:
                    scope = (
                        "personal"
                        if filters.content_kind == "personal_combo"
                        else "job"
                    )
                    member_match = ""
                    member_match_values: list[Any] = []
                    if filters.member_id:
                        member_match = (
                            " AND EXISTS ("
                            "SELECT 1 FROM result_members rm_combo "
                            f"WHERE rm_combo.attempt_id = {alias}.id "
                            "AND rm_combo.position = rs_combo.member_position "
                            "AND rm_combo.member_id = ?)"
                        )
                        member_match_values.append(filters.member_id)
                    if combo_ids == ["__empty__"]:
                        clauses.append(
                            "EXISTS ("
                            "SELECT 1 FROM result_skills rs_combo "
                            f"WHERE rs_combo.attempt_id = {alias}.id "
                            "AND rs_combo.skill_scope = ?"
                            + member_match
                            + " GROUP BY rs_combo.member_position "
                            "HAVING SUM(CASE WHEN rs_combo.is_empty_marker = 0 "
                            "THEN 1 ELSE 0 END) = 0)"
                        )
                        values.append(scope)
                        values.extend(member_match_values)
                    else:
                        marks = ",".join("?" for _ in combo_ids)
                        identity = (
                            "CASE WHEN rs_combo.skill_id <> '' "
                            "THEN rs_combo.skill_id "
                            "ELSE 'name:' || rs_combo.skill_name END"
                        )
                        clauses.append(
                            "EXISTS ("
                            "SELECT 1 FROM result_skills rs_combo "
                            f"WHERE rs_combo.attempt_id = {alias}.id "
                            "AND rs_combo.skill_scope = ?"
                            + member_match
                            + " GROUP BY rs_combo.member_position "
                            "HAVING SUM(CASE WHEN rs_combo.is_empty_marker = 0 "
                            "THEN 1 ELSE 0 END) = ? "
                            f"AND SUM(CASE WHEN {identity} IN ({marks}) "
                            "THEN 1 ELSE 0 END) = ?)"
                        )
                        values.append(scope)
                        values.extend(member_match_values)
                        values.append(len(combo_ids))
                        values.extend(str(value) for value in combo_ids)
                        values.append(len(combo_ids))
            elif filters.content_kind == "treasure":
                clauses.append(
                    "EXISTS ("
                    "SELECT 1 FROM result_treasures rt_content "
                    f"WHERE rt_content.attempt_id = {alias}.id "
                    "AND (rt_content.treasure_id = ? "
                    "OR rt_content.treasure_name = ?)"
                    ")"
                )
                values.extend((content_value, content_value))
            elif filters.content_kind == "property":
                clauses.append(
                    "EXISTS ("
                    "SELECT 1 FROM result_treasure_properties rp_content "
                    f"WHERE rp_content.attempt_id = {alias}.id "
                    "AND (rp_content.property_id = ? "
                    "OR rp_content.property_name = ? "
                    "OR (? = '无' AND rp_content.is_empty_marker = 1) "
                    "OR (? = '未知' AND rp_content.known = 0))"
                    ")"
                )
                values.extend(
                    (
                        content_value,
                        content_value,
                        content_value,
                        content_value,
                    )
                )
            elif filters.content_kind == "combination":
                clauses.append(
                    "EXISTS ("
                    "SELECT 1 FROM result_combinations rc_content "
                    f"WHERE rc_content.attempt_id = {alias}.id "
                    "AND (rc_content.combination_id = ? "
                    "OR rc_content.combination_name = ?)"
                    ")"
                )
                values.extend((content_value, content_value))
            else:
                raise ValueError(
                    f"未知内容筛选类型：{filters.content_kind}"
                )

        if filters.rule_mode == "current":
            rule_hash = filters.current_rule_hash
            if not rule_hash and len(filters.rule_hashes) == 1:
                rule_hash = filters.rule_hashes[0]
            if rule_hash:
                clauses.append("r.rule_snapshot_hash = ?")
                values.append(rule_hash)
            else:
                clauses.append("0 = 1")
        elif filters.rule_mode == "selected":
            if not filters.rule_hashes:
                clauses.append("0 = 1")
            else:
                marks = ",".join("?" for _ in filters.rule_hashes)
                clauses.append(f"r.rule_snapshot_hash IN ({marks})")
                values.extend(filters.rule_hashes)
        elif filters.rule_mode not in {"all_summary", "all_grouped"}:
            raise ValueError(f"未知规则范围：{filters.rule_mode}")

        if filters.started_after:
            clauses.append("r.started_at >= ?")
            values.append(filters.started_after)
        if filters.started_before:
            clauses.append("r.started_at < ?")
            values.append(filters.started_before)
        return " AND ".join(clauses), values

    def _base_query(
        self,
        filters: StatisticsFilters,
    ) -> tuple[str, list[Any]]:
        where, values = self._where(filters)
        return (
            """
            FROM attempts a
            JOIN rounds rd ON rd.id = a.round_id
            JOIN runs r ON r.id = rd.run_id
            WHERE
            """
            + where,
            values,
        )

    def get_summary(self, filters: StatisticsFilters) -> dict[str, Any]:
        base, values = self._base_query(filters)
        query = (
            """
            WITH filtered AS (
                SELECT a.id, a.slot, a.attempt_number, a.status,
                       a.failure_reason, a.scored, a.save_confirmed,
                       a.published, a.is_final_result,
                       r.id AS run_id, rd.id AS round_id,
                       r.rule_snapshot_hash
            """
            + base
            + """
            ),
            ranked AS (
                SELECT filtered.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY run_id, round_id, slot
                           ORDER BY attempt_number DESC, id DESC
                       ) AS task_rank,
                       run_id || ':' || round_id || ':' || slot AS task_key
                FROM filtered
            )
            SELECT
                COUNT(*) AS attempt_count,
                COUNT(DISTINCT task_key) AS save_count,
                COUNT(DISTINCT CASE WHEN scored = 1 THEN task_key END)
                    AS completed_count,
                COUNT(DISTINCT CASE
                    WHEN task_rank = 1 AND status = 'accepted'
                        AND save_confirmed = 1 AND published = 1
                    THEN task_key END) AS accepted,
                COUNT(DISTINCT CASE
                    WHEN task_rank = 1 AND status = 'rejected'
                    THEN task_key END) AS rejected,
                COUNT(DISTINCT CASE
                    WHEN task_rank = 1 AND status = 'failed'
                    THEN task_key END) AS failed,
                COUNT(DISTINCT CASE
                    WHEN task_rank = 1 AND status = 'stopped'
                    THEN task_key END) AS stopped,
                COUNT(DISTINCT CASE
                    WHEN task_rank = 1 AND status = 'unfinished'
                    THEN task_key END) AS unfinished,
                COUNT(DISTINCT rule_snapshot_hash) AS rule_count
            FROM ranked
            """
        )
        with closing(self._connect()) as connection:
            row = connection.execute(query, values).fetchone()
        result = dict(row or {})
        for key in (
            "attempt_count",
            "save_count",
            "completed_count",
            "accepted",
            "rejected",
            "failed",
            "stopped",
            "unfinished",
            "rule_count",
        ):
            result[key] = int(result.get(key) or 0)
        accepted = result["accepted"]
        rejected = result["rejected"]
        result["qualification_rate"] = (
            accepted / (accepted + rejected)
            if accepted + rejected
            else None
        )
        result["average_attempts"] = (
            result["attempt_count"] / result["save_count"]
            if result["save_count"]
            else 0.0
        )
        result["cross_rule_summary"] = filters.rule_mode == "all_summary"
        result["rule_mode"] = filters.rule_mode
        return result

    def get_grouped_summary(
        self,
        filters: StatisticsFilters,
    ) -> list[dict[str, Any]]:
        """Return independent summary rows for each selected rule fingerprint."""
        if filters.rule_mode != "all_grouped":
            return []
        base, values = self._base_query(filters)
        with closing(self._connect()) as connection:
            options = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT DISTINCT r.rule_snapshot_hash, r.rule_name,
                           r.rule_schema_version
                    """
                    + base
                    + """
                    ORDER BY r.rule_name, r.rule_snapshot_hash
                    """,
                    values,
                )
            ]
        result: list[dict[str, Any]] = []
        for option in options:
            rule_hash = str(option["rule_snapshot_hash"] or "")
            scoped = StatisticsFilters(
                scope=filters.scope,
                metric=filters.metric,
                mode=filters.mode,
                rule_mode="selected",
                rule_hashes=(rule_hash,),
                current_rule_hash=filters.current_rule_hash,
                run_id=filters.run_id,
                round_id=filters.round_id,
                slots=filters.slots,
                member_id=filters.member_id,
                attempt_id=filters.attempt_id,
                status=filters.status,
                status_group=filters.status_group,
                failure_reason=filters.failure_reason,
                content_kind=filters.content_kind,
                content_value=filters.content_value,
                started_after=filters.started_after,
                started_before=filters.started_before,
            )
            summary = self.get_summary(scoped)
            summary["rule_name"] = option["rule_name"]
            summary["rule_schema_version"] = option["rule_schema_version"]
            summary["rule_snapshot_hash"] = rule_hash
            result.append(summary)
        return result

    def list_rule_options(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT r.rule_snapshot_hash, r.rule_name,
                       r.rule_schema_version, COUNT(DISTINCT r.id) AS run_count
                FROM runs r
                WHERE NOT EXISTS (
                    SELECT 1 FROM statistics_hidden_runs shr
                    WHERE shr.run_id = r.id
                )
                GROUP BY r.rule_snapshot_hash, r.rule_name,
                         r.rule_schema_version
                ORDER BY r.rule_name, r.rule_snapshot_hash
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def list_run_options(self, *, page_size: int = 200) -> list[dict[str, Any]]:
        return self.history.list_runs(page=1, page_size=page_size)

    def list_round_options(self, *, page_size: int = 500) -> list[dict[str, Any]]:
        return self.history.list_rounds(page=1, page_size=page_size)

    def latest_round_id(self, run_id: str | None) -> int | None:
        if not run_id:
            return None
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT id
                FROM rounds
                WHERE run_id = ?
                ORDER BY round_number DESC, id DESC
                LIMIT 1
                """,
                (run_id,),
            ).fetchone()
        return int(row["id"]) if row is not None else None

    def list_slot_options(self) -> list[int]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT a.slot
                FROM attempts a
                JOIN rounds rd ON rd.id = a.round_id
                JOIN runs r ON r.id = rd.run_id
                WHERE NOT EXISTS (
                    SELECT 1 FROM statistics_hidden_runs shr
                    WHERE shr.run_id = r.id
                )
                ORDER BY a.slot
                """
            ).fetchall()
        return [int(row[0]) for row in rows]

    def list_member_options(self) -> list[dict[str, str]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT member_id, member_name
                FROM result_members rm
                JOIN attempts a ON a.id = rm.attempt_id
                JOIN rounds rd ON rd.id = a.round_id
                JOIN runs r ON r.id = rd.run_id
                WHERE NOT EXISTS (
                    SELECT 1 FROM statistics_hidden_runs shr
                    WHERE shr.run_id = r.id
                )
                ORDER BY member_name, member_id
                """
            ).fetchall()
        return [
            {
                "member_id": str(row["member_id"]),
                "member_name": str(row["member_name"]),
            }
            for row in rows
        ]

    def delete_run(self, run_id: str) -> None:
        self.history.delete_run(run_id)

    def _member_scope(
        self,
        filters: StatisticsFilters,
        *,
        member_column: str,
        include_global: bool = False,
    ) -> tuple[str, tuple[Any, ...]]:
        if not filters.member_id:
            return "", ()
        if member_column == "x.member_id":
            return " AND x.member_id = ?", (filters.member_id,)
        global_clause = (
            f"{member_column} = -1 OR "
            if include_global
            else ""
        )
        return (
            " AND ("
            + global_clause
            + "EXISTS ("
            "SELECT 1 FROM result_members rm_filter "
            "WHERE rm_filter.attempt_id = x.attempt_id "
            f"AND rm_filter.position = {member_column} "
            "AND rm_filter.member_id = ?))",
            (filters.member_id,),
        )

    def _distribution(
        self,
        filters: StatisticsFilters,
        *,
        value_field: str,
        label_field: str,
        table: str,
        scope_clause: str = "",
        scope_values: Iterable[Any] = (),
        empty_field: str | None = None,
        known_field: str | None = "known",
    ) -> list[dict[str, Any]]:
        where, values = self._where(filters)
        values = [*values, *scope_values]
        rule_select = (
            ", r.rule_snapshot_hash AS rule_snapshot_hash"
            if filters.rule_mode == "all_grouped"
            else ""
        )
        group_rule = (
            ", r.rule_snapshot_hash"
            if filters.rule_mode == "all_grouped"
            else ""
        )
        member_count_field = (
            "x.member_id" if table == "result_members" else "x.member_position"
        )
        if empty_field and known_field:
            label = (
                f"CASE WHEN x.{empty_field} = 1 THEN '无' "
                f"ELSE COALESCE(NULLIF(x.{label_field}, ''), '未知') END"
            )
        elif known_field:
            label = (
                f"COALESCE(NULLIF(x.{label_field}, ''), '未知')"
            )
        else:
            label = (
                f"COALESCE(NULLIF(x.{label_field}, ''), '未知')"
            )
        query = (
            f"""
            SELECT
                x.{value_field} AS value,
                {label} AS label,
                COUNT(*) AS count,
                COUNT(DISTINCT a.id) AS attempt_count,
                COUNT(DISTINCT r.id || ':' || rd.id || ':' || a.slot)
                    AS save_count,
                COUNT(DISTINCT {member_count_field}) AS member_count
                {rule_select}
            FROM {table} x
            JOIN attempts a ON a.id = x.attempt_id
            JOIN rounds rd ON rd.id = a.round_id
            JOIN runs r ON r.id = rd.run_id
            WHERE {where}
            {scope_clause}
            GROUP BY x.{value_field}, label {group_rule}
            ORDER BY count DESC, label
            """
        )
        with closing(self._connect()) as connection:
            rows = [dict(row) for row in connection.execute(query, values)]
        if filters.rule_mode == "all_grouped":
            totals: dict[str, int] = {}
            for row in rows:
                key = str(row.get("rule_snapshot_hash") or "")
                totals[key] = totals.get(key, 0) + int(row["count"])
            for row in rows:
                total = totals.get(str(row.get("rule_snapshot_hash") or ""), 0)
                row["ratio"] = row["count"] / total if total else 0.0
                row["position_count"] = total
        else:
            total = sum(int(row["count"]) for row in rows)
            for row in rows:
                row["ratio"] = row["count"] / total if total else 0.0
                row["position_count"] = total
        return rows

    def _related_distribution(
        self,
        filters: StatisticsFilters,
        *,
        value_expression: str,
        label_expression: str,
        from_clause: str,
        relation_clause: str,
        relation_values: Iterable[Any],
        member_expression: str,
    ) -> list[dict[str, Any]]:
        where, values = self._where(filters)
        rule_select = (
            ", r.rule_snapshot_hash AS rule_snapshot_hash"
            if filters.rule_mode == "all_grouped"
            else ""
        )
        group_rule = (
            ", r.rule_snapshot_hash"
            if filters.rule_mode == "all_grouped"
            else ""
        )
        query = f"""
            SELECT
                {value_expression} AS value,
                {label_expression} AS label,
                COUNT(*) AS count,
                COUNT(DISTINCT a.id) AS attempt_count,
                COUNT(DISTINCT r.id || ':' || rd.id || ':' || a.slot)
                    AS save_count,
                COUNT(DISTINCT {member_expression}) AS member_count
                {rule_select}
            {from_clause}
            JOIN attempts a ON a.id = x.attempt_id
            JOIN rounds rd ON rd.id = a.round_id
            JOIN runs r ON r.id = rd.run_id
            WHERE {where}
              AND {relation_clause}
            GROUP BY value, label {group_rule}
            ORDER BY count DESC, label
        """
        with closing(self._connect()) as connection:
            rows = [
                dict(row)
                for row in connection.execute(
                    query,
                    [*values, *relation_values],
                )
            ]
        if filters.rule_mode == "all_grouped":
            totals: dict[str, int] = {}
            for row in rows:
                key = str(row.get("rule_snapshot_hash") or "")
                totals[key] = totals.get(key, 0) + int(row["count"])
            for row in rows:
                total = totals.get(str(row.get("rule_snapshot_hash") or ""), 0)
                row["ratio"] = row["count"] / total if total else 0.0
                row["position_count"] = total
        else:
            total = sum(int(row["count"]) for row in rows)
            for row in rows:
                row["ratio"] = row["count"] / total if total else 0.0
                row["position_count"] = total
        return rows

    def get_job_distribution(
        self,
        filters: StatisticsFilters,
    ) -> list[dict[str, Any]]:
        clause, values = self._member_scope(filters, member_column="x.member_id")
        return self._distribution(
            filters,
            value_field="job_id",
            label_field="job_name",
            table="result_members",
            scope_clause=clause,
            scope_values=values,
            known_field="job_known",
        )

    def get_member_distribution(
        self,
        filters: StatisticsFilters,
    ) -> list[dict[str, Any]]:
        clause, values = self._member_scope(
            filters,
            member_column="x.member_id",
        )
        return self._distribution(
            filters,
            value_field="member_id",
            label_field="member_name",
            table="result_members",
            scope_clause=clause,
            scope_values=values,
            known_field=None,
        )

    def get_member_job_distribution(
        self,
        filters: StatisticsFilters,
    ) -> list[dict[str, Any]]:
        return self.get_job_distribution(filters)

    def get_members_for_job(
        self,
        filters: StatisticsFilters,
        job_id: str,
    ) -> list[dict[str, Any]]:
        return self._related_distribution(
            filters,
            value_expression="x.member_id",
            label_expression=(
                "COALESCE(NULLIF(x.member_name, ''), '未知武将')"
            ),
            from_clause="FROM result_members x",
            relation_clause="x.job_id = ?",
            relation_values=(job_id,),
            member_expression="x.member_id",
        )

    def get_skill_distribution(
        self,
        filters: StatisticsFilters,
        *,
        scope: str,
    ) -> list[dict[str, Any]]:
        if scope not in {"personal", "job"}:
            raise ValueError("skill scope must be personal or job")
        clause, values = self._member_scope(
            filters,
            member_column="x.member_position",
        )
        clause += " AND x.skill_scope = ?"
        values += (scope,)
        return self._distribution(
            filters,
            value_field="skill_id",
            label_field="skill_name",
            table="result_skills",
            scope_clause=clause,
            scope_values=values,
            empty_field="is_empty_marker",
        )

    def get_personal_skill_distribution(
        self,
        filters: StatisticsFilters,
    ) -> list[dict[str, Any]]:
        return self.get_skill_distribution(filters, scope="personal")

    def get_job_skill_distribution(
        self,
        filters: StatisticsFilters,
    ) -> list[dict[str, Any]]:
        return self.get_skill_distribution(filters, scope="job")

    def get_members_for_skill(
        self,
        filters: StatisticsFilters,
        *,
        scope: str,
        skill_id: str,
    ) -> list[dict[str, Any]]:
        if scope not in {"personal", "job"}:
            raise ValueError("skill scope must be personal or job")
        return self._related_distribution(
            filters,
            value_expression="rm.member_id",
            label_expression=(
                "COALESCE(NULLIF(rm.member_name, ''), '未知武将')"
            ),
            from_clause=(
                "FROM result_skills x "
                "JOIN result_members rm "
                "ON rm.attempt_id = x.attempt_id "
                "AND rm.position = x.member_position"
            ),
            relation_clause=(
                "x.skill_scope = ? AND x.skill_id = ? "
                "AND x.is_empty_marker = 0"
            ),
            relation_values=(scope, skill_id),
            member_expression="rm.member_id",
        )

    def get_skill_combination_distribution(
        self,
        filters: StatisticsFilters,
        *,
        scope: str,
    ) -> list[dict[str, Any]]:
        if scope not in {"personal", "job"}:
            raise ValueError("skill scope must be personal or job")
        where, values = self._where(filters)
        member_clause, member_values = self._member_scope(
            filters,
            member_column="x.member_position",
        )
        rows_query = (
            """
            SELECT a.id AS attempt_id, a.slot, rd.id AS round_id,
                   r.id AS run_id, r.rule_snapshot_hash,
                   x.member_position, x.skill_id, x.skill_name,
                   x.known, x.is_empty_marker,
                   COALESCE(rm.member_id, '') AS member_id
            FROM result_skills x
            JOIN attempts a ON a.id = x.attempt_id
            JOIN rounds rd ON rd.id = a.round_id
            JOIN runs r ON r.id = rd.run_id
            LEFT JOIN result_members rm
              ON rm.attempt_id = x.attempt_id
             AND rm.position = x.member_position
            WHERE """
            + where
            + member_clause
            + """
              AND x.skill_scope = ?
            ORDER BY a.id, x.member_position, x.skill_id, x.skill_name
            """
        )
        with closing(self._connect()) as connection:
            source = connection.execute(
                rows_query,
                [*values, *member_values, scope],
            ).fetchall()
        positions: dict[
            tuple[str, int, int],
            dict[str, Any],
        ] = {}
        for row in source:
            rule_hash = (
                str(row["rule_snapshot_hash"] or "")
                if filters.rule_mode == "all_grouped"
                else ""
            )
            position_key = (
                rule_hash,
                int(row["attempt_id"]),
                int(row["member_position"]),
            )
            entry = positions.setdefault(
                position_key,
                {
                    "rule_snapshot_hash": rule_hash,
                    "run_id": str(row["run_id"]),
                    "round_id": int(row["round_id"]),
                    "slot": int(row["slot"]),
                    "member_id": str(row["member_id"] or ""),
                    "skills": [],
                },
            )
            if int(row["is_empty_marker"]):
                continue
            skill_id = str(row["skill_id"] or "")
            skill_name = (
                "未知"
                if int(row["known"]) == 0
                else str(row["skill_name"] or "未知")
            )
            entry["skills"].append((skill_id, skill_name))

        aggregated: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
        for entry in positions.values():
            skills = sorted(
                entry["skills"],
                key=lambda item: (item[0], item[1]),
            )
            ids = tuple(
                skill_id or f"name:{skill_name}"
                for skill_id, skill_name in skills
            )
            labels = tuple(skill_name for _skill_id, skill_name in skills)
            if not ids:
                ids = ("__empty__",)
                labels = ("无",)
            key = (entry["rule_snapshot_hash"], ids)
            row = aggregated.setdefault(
                key,
                {
                    "value": json.dumps(ids, ensure_ascii=False),
                    "label": " + ".join(labels),
                    "count": 0,
                    "save_keys": set(),
                    "member_keys": set(),
                    "rule_snapshot_hash": entry["rule_snapshot_hash"],
                },
            )
            row["count"] += 1
            row["save_keys"].add(
                f"{entry['run_id']}:{entry['round_id']}:{entry['slot']}"
            )
            row["member_keys"].add(entry["member_id"])

        totals: dict[str, int] = {}
        for row in aggregated.values():
            rule_hash = str(row["rule_snapshot_hash"])
            totals[rule_hash] = totals.get(rule_hash, 0) + int(row["count"])
        result: list[dict[str, Any]] = []
        for row in aggregated.values():
            total = totals[str(row["rule_snapshot_hash"])]
            result.append(
                {
                    "value": row["value"],
                    "label": row["label"],
                    "count": row["count"],
                    "save_count": len(row["save_keys"]),
                    "member_count": len(row["member_keys"]),
                    "position_count": total,
                    "ratio": row["count"] / total if total else 0.0,
                    "rule_snapshot_hash": (
                        row["rule_snapshot_hash"]
                        if filters.rule_mode == "all_grouped"
                        else None
                    ),
                }
            )
        result.sort(key=lambda row: (-int(row["count"]), str(row["label"])))
        return result

    def get_personal_skill_combination_distribution(
        self,
        filters: StatisticsFilters,
    ) -> list[dict[str, Any]]:
        return self.get_skill_combination_distribution(
            filters,
            scope="personal",
        )

    def get_job_skill_combination_distribution(
        self,
        filters: StatisticsFilters,
    ) -> list[dict[str, Any]]:
        return self.get_skill_combination_distribution(
            filters,
            scope="job",
        )

    def get_treasure_distribution(
        self,
        filters: StatisticsFilters,
    ) -> list[dict[str, Any]]:
        clause, values = self._member_scope(
            filters,
            member_column="x.member_position",
            include_global=True,
        )
        return self._distribution(
            filters,
            value_field="treasure_id",
            label_field="treasure_name",
            table="result_treasures",
            scope_clause=clause,
            scope_values=values,
        )

    def get_treasure_property_distribution(
        self,
        filters: StatisticsFilters,
    ) -> list[dict[str, Any]]:
        clause, values = self._member_scope(
            filters,
            member_column="x.member_position",
            include_global=True,
        )
        return self._distribution(
            filters,
            value_field="property_id",
            label_field="property_name",
            table="result_treasure_properties",
            scope_clause=clause,
            scope_values=values,
            empty_field="is_empty_marker",
        )

    def get_properties_for_treasure(
        self,
        filters: StatisticsFilters,
        treasure_id: str,
    ) -> list[dict[str, Any]]:
        return self._related_distribution(
            filters,
            value_expression="x.property_id",
            label_expression=(
                "CASE WHEN x.is_empty_marker = 1 THEN '无' "
                "ELSE COALESCE(NULLIF(x.property_name, ''), '未知') END"
            ),
            from_clause="FROM result_treasure_properties x",
            relation_clause="x.treasure_id = ?",
            relation_values=(treasure_id,),
            member_expression="x.member_position",
        )

    def get_treasures_for_property(
        self,
        filters: StatisticsFilters,
        property_id: str,
    ) -> list[dict[str, Any]]:
        return self._related_distribution(
            filters,
            value_expression="t.treasure_id",
            label_expression=(
                "COALESCE(NULLIF(t.treasure_name, ''), '未知宝物')"
            ),
            from_clause=(
                "FROM result_treasure_properties x "
                "JOIN result_treasures t "
                "ON t.attempt_id = x.attempt_id "
                "AND t.member_position = x.member_position "
                "AND t.treasure_id = x.treasure_id"
            ),
            relation_clause=(
                "x.property_id = ? AND x.is_empty_marker = 0"
            ),
            relation_values=(property_id,),
            member_expression="t.treasure_id",
        )

    def get_combination_distribution(
        self,
        filters: StatisticsFilters,
    ) -> list[dict[str, Any]]:
        clause, values = self._member_scope(
            filters,
            member_column="x.member_position",
            include_global=True,
        )
        return self._distribution(
            filters,
            value_field="combination_id",
            label_field="combination_name",
            table="result_combinations",
            scope_clause=clause,
            scope_values=values,
        )

    def get_skill_presence_distribution(
        self,
        filters: StatisticsFilters,
    ) -> list[dict[str, Any]]:
        where, values = self._where(filters)
        member_clause, member_values = self._member_scope(
            filters,
            member_column="x.member_position",
        )
        values = [*values, *member_values]
        query = (
            """
            SELECT
                x.skill_scope,
                CASE
                    WHEN x.is_empty_marker = 1 THEN '无'
                    ELSE '有'
                END AS label,
                COUNT(DISTINCT x.attempt_id || ':' || x.member_position)
                    AS count
            FROM result_skills x
            JOIN attempts a ON a.id = x.attempt_id
            JOIN rounds rd ON rd.id = a.round_id
            JOIN runs r ON r.id = rd.run_id
            WHERE """
            + where
            + member_clause
            + """
            GROUP BY x.skill_scope, label
            ORDER BY x.skill_scope, label
            """
        )
        with closing(self._connect()) as connection:
            rows = [dict(row) for row in connection.execute(query, values)]
        return rows

    def get_failure_distribution(
        self,
        filters: StatisticsFilters,
    ) -> list[dict[str, Any]]:
        base, values = self._base_query(filters)
        query = (
            """
            SELECT
                COALESCE(NULLIF(a.failure_reason, ''), 'unknown') AS value,
                COALESCE(NULLIF(a.failure_reason, ''), '未知') AS label,
                COUNT(*) AS count
            """
            + base
            + """
            AND a.failure_reason <> ''
            AND a.status IN ('rejected', 'failed')
            GROUP BY value, label
            ORDER BY count DESC, label
            """
        )
        with closing(self._connect()) as connection:
            return [dict(row) for row in connection.execute(query, values)]

    def get_trend(self, filters: StatisticsFilters) -> list[dict[str, Any]]:
        if filters.scope in {"current_run", "current_round"}:
            return self._get_cumulative_trend(filters)
        base, values = self._base_query(filters)
        query = (
            """
            SELECT substr(rd.started_at, 1, 10) AS date,
                   COUNT(DISTINCT r.id || ':' || rd.id) AS runs,
                   COUNT(DISTINCT r.id || ':' || rd.id || ':' || a.slot)
                       AS saves,
                   COUNT(*) AS attempts,
                   COUNT(DISTINCT CASE WHEN a.scored = 1
                       THEN r.id || ':' || rd.id || ':' || a.slot END)
                       AS completed,
                   COUNT(DISTINCT CASE WHEN a.status = 'accepted'
                       AND a.scored = 1
                       THEN r.id || ':' || rd.id || ':' || a.slot END)
                       AS accepted,
                   COUNT(DISTINCT CASE WHEN a.status = 'rejected'
                       AND a.scored = 1
                       THEN r.id || ':' || rd.id || ':' || a.slot END)
                       AS rejected,
                   COUNT(DISTINCT CASE
                       WHEN a.status = 'accepted'
                            AND a.is_final_result = 1
                       THEN COALESCE(
                           json_extract(a.snapshot_json, '$.save.sha256'),
                           'attempt:' || a.id
                       )
                   END) AS different_results
            """
            + base
            + """
            GROUP BY date
            ORDER BY date
            """
        )
        with closing(self._connect()) as connection:
            rows = [dict(row) for row in connection.execute(query, values)]
        for row in rows:
            accepted = int(row.get("accepted") or 0)
            rejected = int(row.get("rejected") or 0)
            saves = int(row.get("saves") or 0)
            row["qualification_rate"] = (
                accepted / (accepted + rejected)
                if accepted + rejected
                else None
            )
            row["average_attempts"] = (
                int(row.get("attempts") or 0) / saves if saves else 0.0
            )
        distinct_specs = (
            ("different_jobs", "result_members", "job_id", ""),
            (
                "different_personal_skills",
                "result_skills",
                "skill_id",
                " AND x.skill_scope = 'personal' "
                "AND x.is_empty_marker = 0",
            ),
            (
                "different_job_skills",
                "result_skills",
                "skill_id",
                " AND x.skill_scope = 'job' "
                "AND x.is_empty_marker = 0",
            ),
            (
                "different_treasures",
                "result_treasures",
                "treasure_id",
                "",
            ),
            (
                "different_properties",
                "result_treasure_properties",
                "property_id",
                " AND x.is_empty_marker = 0",
            ),
        )
        by_date = {str(row["date"]): row for row in rows}
        where, where_values = self._where(filters)
        with closing(self._connect()) as connection:
            for key, table, field, extra in distinct_specs:
                distinct_rows = connection.execute(
                    f"""
                    SELECT substr(rd.started_at, 1, 10) AS date,
                           COUNT(DISTINCT x.{field}) AS value
                    FROM {table} x
                    JOIN attempts a ON a.id = x.attempt_id
                    JOIN rounds rd ON rd.id = a.round_id
                    JOIN runs r ON r.id = rd.run_id
                    WHERE {where} {extra}
                    GROUP BY date
                    """,
                    where_values,
                ).fetchall()
                counts = {
                    str(item["date"]): int(item["value"] or 0)
                    for item in distinct_rows
                }
                for date, row in by_date.items():
                    row[key] = counts.get(date, 0)
        return rows

    def _get_cumulative_trend(
        self,
        filters: StatisticsFilters,
    ) -> list[dict[str, Any]]:
        base, values = self._base_query(filters)
        query = (
            """
            SELECT a.id, a.slot, a.status, a.scored, a.is_final_result,
                   a.snapshot_json, r.id AS run_id, rd.id AS round_id
            """
            + base
            + """
            ORDER BY a.created_at, a.id
            """
        )
        with closing(self._connect()) as connection:
            source = connection.execute(query, values).fetchall()
        tasks: set[str] = set()
        completed_tasks: set[str] = set()
        accepted_tasks: set[str] = set()
        rejected_tasks: set[str] = set()
        result_signatures: set[str] = set()
        result: list[dict[str, Any]] = []
        for index, row in enumerate(source, start=1):
            task_key = f"{row['run_id']}:{row['round_id']}:{row['slot']}"
            tasks.add(task_key)
            if int(row["scored"] or 0):
                completed_tasks.add(task_key)
            if (
                str(row["status"]) == "accepted"
                and int(row["scored"] or 0)
            ):
                accepted_tasks.add(task_key)
            elif (
                str(row["status"]) == "rejected"
                and int(row["scored"] or 0)
            ):
                rejected_tasks.add(task_key)
            try:
                snapshot = json.loads(row["snapshot_json"])
            except (TypeError, json.JSONDecodeError):
                snapshot = {}
            save = snapshot.get("save") or {}
            signature = save.get("sha256")
            if signature:
                result_signatures.add(str(signature))
            accepted = len(accepted_tasks)
            rejected = len(rejected_tasks - accepted_tasks)
            result.append(
                {
                    "date": f"第{index}次",
                    "attempt_id": int(row["id"]),
                    "runs": 1,
                    "saves": len(tasks),
                    "attempts": index,
                    "completed": len(completed_tasks),
                    "accepted": accepted,
                    "rejected": rejected,
                    "different_results": len(result_signatures),
                    "qualification_rate": (
                        accepted / (accepted + rejected)
                        if accepted + rejected
                        else None
                    ),
                    "average_attempts": index / len(tasks),
                }
            )
        return result

    def get_recognition_summary(
        self,
        filters: StatisticsFilters,
    ) -> dict[str, int]:
        """Return known/unknown member-position coverage for the active sample."""
        where, values = self._where(filters)
        query = (
            """
            SELECT
                COUNT(*) AS total_positions,
                SUM(CASE WHEN rm.job_known = 1 THEN 1 ELSE 0 END)
                    AS known_positions,
                SUM(CASE WHEN rm.job_known = 0 THEN 1 ELSE 0 END)
                    AS unknown_positions
            FROM result_members rm
            JOIN attempts a ON a.id = rm.attempt_id
            JOIN rounds rd ON rd.id = a.round_id
            JOIN runs r ON r.id = rd.run_id
            WHERE """
            + where
        )
        member_values: list[Any] = []
        if filters.member_id:
            query += " AND rm.member_id = ?"
            member_values.append(filters.member_id)
        with closing(self._connect()) as connection:
            row = connection.execute(
                query,
                [*values, *member_values],
            ).fetchone()
        result = dict(row or {})
        return {
            "total_positions": int(result.get("total_positions") or 0),
            "known_positions": int(result.get("known_positions") or 0),
            "unknown_positions": int(result.get("unknown_positions") or 0),
        }

    def get_detail_rows(
        self,
        filters: StatisticsFilters,
        *,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        base, values = self._base_query(filters)
        query = (
            """
            SELECT
                a.id AS attempt_id,
                a.slot,
                a.attempt_number,
                a.status,
                a.failure_reason,
                a.is_final_result,
                a.scored,
                a.save_confirmed,
                a.published,
                a.snapshot_json,
                rd.round_number,
                rd.id AS round_id,
                rd.started_at AS round_started_at,
                r.id AS run_id,
                r.started_at AS run_started_at,
                r.mode,
                r.rule_name,
                r.rule_schema_version,
                r.rule_snapshot_hash
            """
            + base
            + """
            ORDER BY rd.started_at DESC, a.slot, a.attempt_number
            LIMIT ? OFFSET ?
            """
        )
        with closing(self._connect()) as connection:
            query_values = [*values, max(1, int(limit)), max(0, int(offset))]
            rows = [dict(row) for row in connection.execute(query, query_values)]
        for row in rows:
            try:
                row["snapshot"] = json.loads(row.pop("snapshot_json"))
            except (TypeError, json.JSONDecodeError):
                row["snapshot"] = {}
        return rows

    def count_detail_rows(self, filters: StatisticsFilters) -> int:
        base, values = self._base_query(filters)
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT COUNT(*) " + base,
                values,
            ).fetchone()
        return int(row[0] if row is not None else 0)

    def iter_detail_rows(
        self,
        filters: StatisticsFilters,
        *,
        page_size: int = 500,
    ) -> Iterable[dict[str, Any]]:
        offset = 0
        size = max(1, int(page_size))
        while True:
            rows = self.get_detail_rows(filters, limit=size, offset=offset)
            if not rows:
                return
            yield from rows
            if len(rows) < size:
                return
            offset += len(rows)

    def validate_statistics(
        self,
        filters: StatisticsFilters,
    ) -> ValidationReport:
        base, values = self._base_query(filters)
        where, where_values = self._where(filters)
        issues: list[str] = []
        with closing(self._connect()) as connection:
            attempts = connection.execute(
                "SELECT a.id, a.snapshot_json, a.status, "
                "a.save_confirmed, a.published, a.is_final_result, "
                "a.slot, a.attempt_number, rd.id AS round_id, "
                "r.id AS run_id, r.rule_snapshot_hash " + base,
                values,
            ).fetchall()
            members_by_attempt: dict[int, list[sqlite3.Row]] = {}
            skills_by_attempt: dict[int, list[sqlite3.Row]] = {}
            treasures_by_attempt: dict[int, list[sqlite3.Row]] = {}
            properties_by_attempt: dict[int, list[sqlite3.Row]] = {}
            combinations_by_attempt: dict[int, list[sqlite3.Row]] = {}
            projection_specs = (
                (
                    "result_members",
                    "rm",
                    "rm.*",
                    members_by_attempt,
                    "rm.position",
                ),
                (
                    "result_skills",
                    "rs",
                    "rs.*",
                    skills_by_attempt,
                    "rs.member_position, rs.skill_scope, "
                    "rs.skill_id, rs.skill_name",
                ),
                (
                    "result_treasures",
                    "rt",
                    "rt.*",
                    treasures_by_attempt,
                    "rt.member_position, rt.treasure_id",
                ),
                (
                    "result_treasure_properties",
                    "rp",
                    "rp.*",
                    properties_by_attempt,
                    "rp.member_position, rp.treasure_id, rp.property_id",
                ),
                (
                    "result_combinations",
                    "rc",
                    "rc.*",
                    combinations_by_attempt,
                    "rc.member_position, rc.combination_id",
                ),
            )
            for table, alias, select, target, order_by in projection_specs:
                rows = connection.execute(
                    f"""
                    SELECT {select}
                    FROM {table} {alias}
                    JOIN attempts a ON a.id = {alias}.attempt_id
                    JOIN rounds rd ON rd.id = a.round_id
                    JOIN runs r ON r.id = rd.run_id
                    WHERE {where}
                    ORDER BY {alias}.attempt_id, {order_by}
                    """,
                    where_values,
                ).fetchall()
                for projection_row in rows:
                    target.setdefault(
                        int(projection_row["attempt_id"]),
                        [],
                    ).append(projection_row)
            for row in attempts:
                attempt_id = int(row["id"])
                try:
                    snapshot = json.loads(row["snapshot_json"])
                except (TypeError, json.JSONDecodeError):
                    issues.append(f"尝试 {attempt_id} 的快照不是有效 JSON")
                    continue
                members = snapshot.get("members")
                expected_members = (
                    [item for item in members if isinstance(item, dict)]
                    if isinstance(members, list)
                    else []
                )
                actual_member_rows = members_by_attempt.get(attempt_id, [])
                if len(expected_members) != len(actual_member_rows):
                    issues.append(f"尝试 {attempt_id} 的武将索引数量不一致")
                for position, (expected, actual) in enumerate(
                    zip(expected_members, actual_member_rows)
                ):
                    expected_position = int(
                        expected.get("position", position)
                    )
                    if int(actual["position"]) != expected_position:
                        issues.append(
                            f"尝试 {attempt_id} 的武将位置索引不一致"
                        )
                    expected_member_id = str(
                        expected.get("memberId")
                        or expected.get("memberName")
                        or expected.get("name")
                        or ""
                    )
                    expected_job_id = str(
                        expected.get("jobId")
                        or expected.get("jobName")
                        or expected.get("job")
                        or ""
                    )
                    if (
                        str(actual["member_id"] or "") != expected_member_id
                        or str(actual["job_id"] or "") != expected_job_id
                    ):
                        issues.append(
                            f"尝试 {attempt_id} 的武将稳定 ID 索引不一致"
                        )
                    expected_job_name = str(
                        expected.get("jobName")
                        or expected.get("job")
                        or ""
                    )
                    if str(actual["job_name"] or "") != expected_job_name:
                        issues.append(
                            f"尝试 {attempt_id} 的兵种名称索引不一致"
                        )
                expected_skill_rows = 0
                for member in expected_members:
                    for key in ("personalSkills", "jobSkills"):
                        skill_items = member.get(key)
                        if isinstance(skill_items, list):
                            expected_skill_rows += max(
                                1,
                                len(
                                    [
                                        item
                                        for item in skill_items
                                        if isinstance(item, dict)
                                    ]
                                ),
                            )
                        else:
                            expected_skill_rows += 1
                actual_skill_rows = skills_by_attempt.get(attempt_id, [])
                if expected_skill_rows != len(actual_skill_rows):
                    issues.append(f"尝试 {attempt_id} 的特技索引数量不一致")
                expected_treasures = snapshot.get("treasures")
                if not isinstance(expected_treasures, list):
                    expected_treasures = []
                    equipment = snapshot.get("equipment") or {}
                    for category in equipment.get("categories") or []:
                        for item in category.get("items") or []:
                            expected_treasures.append(item)
                actual_treasure_rows = treasures_by_attempt.get(
                    attempt_id,
                    [],
                )
                if len(expected_treasures) != len(actual_treasure_rows):
                    issues.append(f"尝试 {attempt_id} 的宝物索引数量不一致")
                expected_properties = 0
                for treasure in expected_treasures:
                    if not isinstance(treasure, dict):
                        continue
                    properties = treasure.get("properties")
                    if not isinstance(properties, list) or not properties:
                        expected_properties += 1
                    else:
                        expected_properties += len(
                            [
                                item
                                for item in properties
                                if isinstance(item, dict)
                                or item is not None
                            ]
                        )
                actual_properties = properties_by_attempt.get(
                    attempt_id,
                    [],
                )
                if expected_properties != len(actual_properties):
                    issues.append(
                        f"尝试 {attempt_id} 的宝物特性索引数量不一致"
                    )
                expected_combinations = snapshot.get("combinations")
                if not isinstance(expected_combinations, list):
                    expected_combinations = []
                if not expected_combinations:
                    seen_combinations: set[str] = set()
                    for treasure in expected_treasures:
                        if not isinstance(treasure, dict):
                            continue
                        ids = treasure.get("setIds")
                        if not isinstance(ids, list):
                            continue
                        for value in ids:
                            value = str(value or "")
                            if value and value not in seen_combinations:
                                seen_combinations.add(value)
                                expected_combinations.append(
                                    {"combinationId": value}
                                )
                actual_combinations = combinations_by_attempt.get(
                    attempt_id,
                    [],
                )
                if len(
                    [
                        item
                        for item in expected_combinations
                        if isinstance(item, dict)
                    ]
                ) != len(actual_combinations):
                    issues.append(
                        f"尝试 {attempt_id} 的套装组合索引数量不一致"
                    )
                unknown_counts = snapshot.get("unknownCounts") or {}
                if isinstance(unknown_counts, dict):
                    actual_unknown = {
                        "jobs": sum(
                            1
                            for item in actual_member_rows
                            if int(item["job_known"]) == 0
                        ),
                        "personalSkills": sum(
                            1
                            for item in actual_skill_rows
                            if item["skill_scope"] == "personal"
                            and int(item["known"]) == 0
                        ),
                        "jobSkills": sum(
                            1
                            for item in actual_skill_rows
                            if item["skill_scope"] == "job"
                            and int(item["known"]) == 0
                        ),
                        "properties": sum(
                            1
                            for item in actual_properties
                            if int(item["known"]) == 0
                        ),
                    }
                    for key, actual_count in actual_unknown.items():
                        declared = int(unknown_counts.get(key, actual_count))
                        if declared != int(actual_count):
                            issues.append(
                                f"尝试 {attempt_id} 的未知项计数不一致：{key}"
                            )
                if (
                    int(row["is_final_result"])
                    and not (
                        str(row["status"]) == "accepted"
                        and int(row["save_confirmed"])
                        and int(row["published"])
                    )
                ):
                    issues.append(
                        f"尝试 {attempt_id} 被标记为最终结果但确认状态不完整"
                    )

            duplicate_final = connection.execute(
                "SELECT run_id, round_id, slot, COUNT(*) AS count "
                + base
                + " AND a.is_final_result = 1 "
                "GROUP BY run_id, round_id, slot HAVING COUNT(*) > 1"
                ,
                values,
            ).fetchall()
            if duplicate_final:
                issues.append("存在同一存档任务的多个最终结果")

            if filters.rule_mode == "all_grouped":
                grouped = connection.execute(
                    "SELECT r.rule_snapshot_hash, "
                    "COUNT(DISTINCT r.id || ':' || rd.id || ':' || a.slot) "
                    "AS sample_count "
                    + base
                    + " GROUP BY r.rule_snapshot_hash",
                    values,
                ).fetchall()
                grouped_total = sum(int(item["sample_count"]) for item in grouped)
                total = connection.execute(
                    "SELECT COUNT(DISTINCT r.id || ':' || rd.id || ':' || a.slot) "
                    + base,
                    values,
                ).fetchone()[0]
                if grouped_total != int(total):
                    issues.append("规则分组样本数与基础样本数不守恒")

        if filters.mode in {"three", "seven"} and attempts:
            member_count = sum(
                len(members_by_attempt.get(int(row["id"]), []))
                for row in attempts
            )
            divisor = 3 if filters.mode == "three" else 7
            if member_count % divisor:
                issues.append(
                    f"{'3' if divisor == 3 else '7'} 人模式武将位置数量"
                    "不是对应人数的倍数"
                )
        return ValidationReport(not issues, tuple(dict.fromkeys(issues)))

    def export_csv(self, filters: StatisticsFilters, target: Path) -> Path:
        summary = self.get_summary(filters)
        filter_json = _json(
            {
                field: getattr(filters, field)
                for field in filters.__dataclass_fields__
            }
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        fields = [
            "run_id",
            "round_id",
            "round_number",
            "slot",
            "attempt_number",
            "mode",
            "rule_name",
            "rule_schema_version",
            "rule_snapshot_hash",
            "status",
            "failure_reason",
            "scored",
            "is_final_result",
            "save_confirmed",
            "published",
            "members",
            "jobs",
            "personal_skills",
            "job_skills",
            "treasures",
            "treasure_properties",
            "filters_json",
            "summary_save_count",
            "summary_completed_count",
            "summary_accepted",
            "summary_rejected",
            "summary_attempt_count",
        ]
        with target.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in self.iter_detail_rows(filters):
                snapshot = row.get("snapshot") or {}
                writer.writerow(
                    {
                        **{field: row.get(field, "") for field in fields},
                        "members": self._snapshot_member_text(
                            snapshot,
                            "member",
                        ),
                        "jobs": self._snapshot_member_text(
                            snapshot,
                            "job",
                        ),
                        "personal_skills": self._snapshot_member_text(
                            snapshot,
                            "personalSkills",
                        ),
                        "job_skills": self._snapshot_member_text(
                            snapshot,
                            "jobSkills",
                        ),
                        "treasures": self._snapshot_treasure_text(snapshot),
                        "treasure_properties": (
                            self._snapshot_treasure_property_text(snapshot)
                        ),
                        "filters_json": filter_json,
                        "summary_save_count": summary["save_count"],
                        "summary_completed_count": summary["completed_count"],
                        "summary_accepted": summary["accepted"],
                        "summary_rejected": summary["rejected"],
                        "summary_attempt_count": summary["attempt_count"],
                    }
                )
        return target

    @staticmethod
    def _snapshot_member_text(
        snapshot: dict[str, Any],
        field: str,
    ) -> str:
        values: list[str] = []
        for member in snapshot.get("members") or []:
            if not isinstance(member, dict):
                continue
            member_name = str(
                member.get("memberName")
                or member.get("name")
                or "未知"
            )
            if field == "member":
                values.append(member_name)
                continue
            if field == "job":
                value = member.get("jobName") or member.get("job")
                if value:
                    values.append(f"{member_name}:{value}")
                continue
            names = []
            for item in member.get(field) or []:
                if isinstance(item, dict):
                    names.append(
                        str(
                            item.get("skillName")
                            or item.get("name")
                            or "未知"
                        )
                    )
            values.append(
                f"{member_name}:{'、'.join(names) if names else '无'}"
            )
        return "；".join(values)

    @staticmethod
    def _snapshot_treasure_text(snapshot: dict[str, Any]) -> str:
        values: list[str] = []
        for item in snapshot.get("treasures") or []:
            if isinstance(item, dict):
                values.append(
                    str(
                        item.get("treasureName")
                        or item.get("name")
                        or "未知"
                    )
                )
        return "、".join(values)

    @staticmethod
    def _snapshot_treasure_property_text(
        snapshot: dict[str, Any],
    ) -> str:
        values: list[str] = []
        for item in snapshot.get("treasures") or []:
            if not isinstance(item, dict):
                continue
            for prop in item.get("properties") or []:
                if isinstance(prop, dict):
                    name = prop.get("propertyName") or prop.get("name")
                else:
                    name = prop
                if name:
                    values.append(str(name))
        return "、".join(values)

    def export_json(self, filters: StatisticsFilters, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            _json(
                {
                    "filters": {
                        field: getattr(filters, field)
                        for field in filters.__dataclass_fields__
                    },
                    "summary": self.get_summary(filters),
                    "details": list(self.iter_detail_rows(filters)),
                    "validation": self.validate_statistics(filters).__dict__,
                }
            ),
            encoding="utf-8",
        )
        return target

    def export_statistics(
        self,
        filters: StatisticsFilters,
        format_name: str,
        target: Path,
    ) -> Path:
        normalized = format_name.casefold().lstrip(".")
        if normalized == "csv":
            return self.export_csv(filters, target)
        if normalized == "json":
            return self.export_json(filters, target)
        raise ValueError(f"不支持的统计导出格式：{format_name}")

    def clear_statistics(self) -> None:
        self.history.clear_statistics()

    def rebuild_statistics(self) -> None:
        self.history.rebuild_statistics()
