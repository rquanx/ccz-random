from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from ccz_randomizer.history import HistoryRepository
from ccz_randomizer.statistics import StatisticsFilters, StatisticsRepository


def snapshot(
    *,
    slot: int,
    attempt: int,
    member_count: int = 3,
    personal: list[dict] | None = None,
    job_skills: list[dict] | None = None,
    job: str = "策士",
    verified: bool = True,
    published: bool = True,
) -> dict:
    members = []
    for position in range(member_count):
        members.append(
            {
                "position": position,
                "memberId": f"member-{position}",
                "name": f"武将{position}",
                "jobId": job,
                "job": job,
                "jobKnown": True,
                "personalSkills": personal or [],
                "jobSkills": job_skills or [],
            }
        )
    return {
        "schemaVersion": 2,
        "slot": slot,
        "attempt": attempt,
        "acceptedAttempt": attempt,
        "mode": "three" if member_count == 3 else "seven",
        "members": members,
        "treasures": [
            {
                "memberPosition": 0,
                "treasureId": "treasure-1",
                "treasureName": "倚天剑",
                "setIds": ["set-1"],
                "setNames": ["青龙套装"],
                "known": True,
                "properties": [
                    {
                        "propertyId": "吸血",
                        "propertyName": "吸血",
                        "known": True,
                    }
                ],
            }
        ],
        "detail": {
            "job": {"metrics": {"average": 8}},
            "skill": {"metrics": {"skillScore": 9}},
        },
        "save": {
            "verified": verified,
            "published": published,
            "sha256": f"sha-{slot}-{attempt}",
        },
    }


class StatisticsRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.base = Path(self.directory.name)
        self.history = HistoryRepository(self.base)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def add_run(self, run_id: str, rule: dict, *, mode: str = "three") -> int:
        self.history.start_run(
            run_id,
            mode=mode,
            loop_random=True,
            rule_name="同名规则",
            rule=rule,
            build={"version": "test"},
        )
        return self.history.start_round(run_id, 1)

    def test_metrics_deduplicate_attempts_and_keep_all_attempts_metric(self):
        round_id = self.add_run("run-1", {"id": "rule-a", "score": 1})
        rejected = snapshot(
            slot=1,
            attempt=1,
            verified=False,
            published=False,
        )
        self.history.save_attempt(
            round_id,
            rejected,
            status="rejected",
            failure_reason="job_rejected",
            scored=True,
        )
        accepted = snapshot(slot=1, attempt=2)
        self.history.save_result(round_id, accepted)

        repository = StatisticsRepository(self.base)
        final = repository.get_summary(StatisticsFilters())
        self.assertEqual(1, final["save_count"])
        self.assertEqual(1, final["accepted"])
        self.assertEqual(1, final["attempt_count"])

        attempts = repository.get_summary(
            StatisticsFilters(metric="attempts"),
        )
        self.assertEqual(2, attempts["attempt_count"])
        self.assertEqual(1, attempts["save_count"])
        self.assertEqual(0, attempts["rejected"])
        self.assertEqual(
            [
                {
                    "value": "job_rejected",
                    "label": "job_rejected",
                    "count": 1,
                }
            ],
            repository.get_failure_distribution(
                StatisticsFilters(metric="attempts")
            ),
        )
        self.assertEqual(
            [],
            repository.get_failure_distribution(StatisticsFilters()),
        )

        completed = repository.get_summary(
            StatisticsFilters(metric="completed"),
        )
        self.assertEqual(2, completed["attempt_count"])
        self.assertEqual(1, completed["completed_count"])

    def test_rules_can_be_merged_or_selected_by_hash(self):
        first_round = self.add_run("run-1", {"id": "rule-a", "score": 1})
        self.history.save_result(first_round, snapshot(slot=1, attempt=1))
        second_round = self.add_run("run-2", {"id": "rule-b", "score": 1})
        self.history.save_result(
            second_round,
            snapshot(slot=1, attempt=1, job="骑兵"),
        )
        repository = StatisticsRepository(self.base)
        merged = repository.get_summary(StatisticsFilters())
        self.assertEqual(2, merged["save_count"])
        self.assertEqual(2, merged["rule_count"])

        selected = repository.get_summary(
            StatisticsFilters(
                rule_mode="selected",
                rule_hashes=("sha256:does-not-exist",),
            )
        )
        self.assertEqual(0, selected["save_count"])

        connection = repository._connect()
        try:
            hashes = [
                row[0]
                for row in connection.execute(
                    "SELECT rule_snapshot_hash FROM runs ORDER BY id"
                )
            ]
        finally:
            connection.close()
        one_rule = repository.get_summary(
            StatisticsFilters(
                rule_mode="selected",
                rule_hashes=(hashes[0],),
            )
        )
        self.assertEqual(1, one_rule["save_count"])

        grouped = repository.get_grouped_summary(
            StatisticsFilters(rule_mode="all_grouped")
        )
        self.assertEqual(2, len(grouped))
        self.assertEqual(2, sum(row["save_count"] for row in grouped))

    def test_time_filter_uses_local_iso_bounds(self):
        first_round = self.add_run("run-1", {"id": "rule-a"})
        self.history.save_result(
            first_round,
            {
                **snapshot(slot=1, attempt=1),
                "createdAt": "2026-09-30T23:59:00+08:00",
            },
        )
        self.history.start_run(
            "run-2",
            mode="three",
            loop_random=False,
            rule_name="同名规则",
            rule={"id": "rule-a"},
            build={"version": "test"},
        )
        second_round = self.history.start_round("run-2", 1)
        self.history.save_result(
            second_round,
            {
                **snapshot(slot=1, attempt=1),
                "createdAt": "2026-10-01T00:01:00+08:00",
            },
        )
        connection = self.history._connect()
        try:
            connection.execute(
                "UPDATE runs SET started_at = ? WHERE id = ?",
                ("2026-09-30T23:59:00+08:00", "run-1"),
            )
            connection.execute(
                "UPDATE runs SET started_at = ? WHERE id = ?",
                ("2026-10-01T00:01:00+08:00", "run-2"),
            )
            connection.commit()
        finally:
            connection.close()
        repository = StatisticsRepository(self.base)
        filtered = repository.get_summary(
            StatisticsFilters(
                started_after="2026-10-01T00:00:00+08:00",
                started_before="2026-10-02T00:00:00+08:00",
            )
        )
        self.assertEqual(1, filtered["save_count"])

    def test_multiple_skills_unknowns_and_validation(self):
        round_id = self.add_run("run-1", {"id": "rule-a"})
        self.history.save_result(
            round_id,
            snapshot(
                slot=1,
                attempt=1,
                personal=[
                    {"skillId": "p1", "skillName": "天赋一", "known": True},
                    {"skillId": "p2", "skillName": "天赋二", "known": True},
                ],
                job_skills=[
                    {"skillId": "j1", "skillName": "技能一", "known": True},
                ],
            ),
        )
        repository = StatisticsRepository(self.base)
        personal = repository.get_personal_skill_distribution(
            StatisticsFilters()
        )
        self.assertEqual(6, sum(row["count"] for row in personal))
        job = repository.get_job_skill_distribution(StatisticsFilters())
        self.assertEqual(3, sum(row["count"] for row in job))
        combinations = repository.get_combination_distribution(
            StatisticsFilters()
        )
        self.assertEqual(1, len(combinations))
        self.assertEqual("青龙套装", combinations[0]["label"])
        presence = repository.get_skill_presence_distribution(
            StatisticsFilters()
        )
        personal_combinations = (
            repository.get_personal_skill_combination_distribution(
                StatisticsFilters()
            )
        )
        job_combinations = (
            repository.get_job_skill_combination_distribution(
                StatisticsFilters()
            )
        )
        self.assertTrue(presence)
        self.assertEqual(1, len(personal_combinations))
        self.assertEqual("天赋一 + 天赋二", personal_combinations[0]["label"])
        self.assertEqual(3, personal_combinations[0]["count"])
        self.assertEqual(1, len(job_combinations))
        self.assertEqual("技能一", job_combinations[0]["label"])
        combo_filtered = repository.get_summary(
            StatisticsFilters(
                content_kind="personal_combo",
                content_value=personal_combinations[0]["value"],
            )
        )
        self.assertEqual(1, combo_filtered["save_count"])
        self.assertTrue(repository.validate_statistics(StatisticsFilters()).valid)

    def test_clear_rebuild_and_export(self):
        round_id = self.add_run("run-1", {"id": "rule-a"})
        self.history.save_result(round_id, snapshot(slot=1, attempt=1))
        repository = StatisticsRepository(self.base)
        self.assertEqual(1, repository.get_summary(StatisticsFilters())["save_count"])
        repository.clear_statistics()
        self.assertEqual(0, repository.get_summary(StatisticsFilters())["save_count"])
        repository.rebuild_statistics()
        self.assertEqual(1, repository.get_summary(StatisticsFilters())["save_count"])

        connection = repository._connect()
        try:
            connection.execute("DELETE FROM result_members")
            connection.commit()
        finally:
            connection.close()
        self.assertFalse(
            repository.validate_statistics(StatisticsFilters()).valid
        )
        repository.rebuild_statistics()
        self.assertTrue(
            repository.validate_statistics(StatisticsFilters()).valid
        )

        csv_path = self.base / "out.csv"
        json_path = self.base / "out.json"
        repository.export_csv(StatisticsFilters(), csv_path)
        repository.export_json(StatisticsFilters(), json_path)
        with csv_path.open(encoding="utf-8-sig", newline="") as stream:
            self.assertEqual(1, len(list(csv.DictReader(stream))))
        self.assertEqual(
            1,
            len(
                json.loads(
                    json_path.read_text(encoding="utf-8")
                )["details"]
            ),
        )

    def test_trend_contains_completed_rate_attempt_and_unique_result_metrics(self):
        round_id = self.add_run("run-1", {"id": "rule-a"})
        self.history.save_attempt(
            round_id,
            snapshot(slot=1, attempt=1, verified=False, published=False),
            status="rejected",
            failure_reason="job_rejected",
            scored=True,
        )
        self.history.save_result(round_id, snapshot(slot=1, attempt=2))
        repository = StatisticsRepository(self.base)

        trend = repository.get_trend(StatisticsFilters(metric="attempts"))

        self.assertEqual(1, len(trend))
        self.assertEqual(1, trend[0]["runs"])
        self.assertEqual(1, trend[0]["saves"])
        self.assertEqual(2, trend[0]["attempts"])
        self.assertEqual(1, trend[0]["completed"])
        self.assertEqual(1, trend[0]["accepted"])
        self.assertEqual(1, trend[0]["rejected"])
        self.assertEqual(1, trend[0]["different_results"])
        self.assertEqual(1, trend[0]["different_jobs"])
        self.assertEqual(0, trend[0]["different_personal_skills"])
        self.assertEqual(0, trend[0]["different_job_skills"])
        self.assertEqual(1, trend[0]["different_treasures"])
        self.assertEqual(1, trend[0]["different_properties"])
        self.assertEqual(0.5, trend[0]["qualification_rate"])
        self.assertEqual(2.0, trend[0]["average_attempts"])

    def test_recognition_summary_preserves_unknown_positions(self):
        round_id = self.add_run("run-1", {"id": "rule-a"})
        value = snapshot(slot=1, attempt=1)
        value["members"][0]["jobKnown"] = False
        value["members"][0]["job"] = "未知兵种"
        value["members"][0]["jobId"] = "unknown:99"
        self.history.save_result(round_id, value)
        repository = StatisticsRepository(self.base)

        summary = repository.get_recognition_summary(StatisticsFilters())

        self.assertEqual(
            {"total_positions": 3, "known_positions": 2, "unknown_positions": 1},
            summary,
        )

    def test_member_and_content_filters_apply_to_all_statistics_queries(self):
        first_round = self.add_run("run-1", {"id": "rule-a"})
        first = snapshot(slot=1, attempt=1, job="策士")
        for position, member in enumerate(first["members"]):
            member["memberId"] = f"other-{position}"
        self.history.save_result(first_round, first)

        second_round = self.add_run("run-2", {"id": "rule-a"})
        second = snapshot(slot=2, attempt=1, job="骑兵")
        second["members"][0]["memberId"] = "target-member"
        second["members"][0]["name"] = "目标武将"
        self.history.save_result(second_round, second)
        repository = StatisticsRepository(self.base)

        member_filters = StatisticsFilters(member_id="target-member")
        self.assertEqual(1, repository.get_summary(member_filters)["save_count"])
        self.assertEqual(
            1,
            repository.count_detail_rows(member_filters),
        )
        self.assertEqual(
            {"骑兵"},
            {
                str(row["label"])
                for row in repository.get_job_distribution(member_filters)
            },
        )
        self.assertEqual(
            {
                "total_positions": 1,
                "known_positions": 1,
                "unknown_positions": 0,
            },
            repository.get_recognition_summary(member_filters),
        )
        self.assertEqual(
            [
                {
                    "value": "target-member",
                    "label": "目标武将",
                    "count": 1,
                    "attempt_count": 1,
                    "save_count": 1,
                    "member_count": 1,
                    "ratio": 1.0,
                    "position_count": 1,
                }
            ],
            repository.get_member_distribution(member_filters),
        )

        content_filters = StatisticsFilters(
            content_kind="job",
            content_value="策士",
        )
        self.assertEqual(1, repository.get_summary(content_filters)["save_count"])
        rows = repository.get_detail_rows(content_filters)
        self.assertEqual([1], [int(row["slot"]) for row in rows])

    def test_detail_iteration_and_latest_round_do_not_drop_pages(self):
        first_round = self.add_run("run-1", {"id": "rule-a"})
        for slot in range(1, 4):
            self.history.save_result(
                first_round,
                snapshot(slot=slot, attempt=1),
            )
        second_round = self.history.start_round("run-1", 2)
        repository = StatisticsRepository(self.base)

        rows = list(
            repository.iter_detail_rows(
                StatisticsFilters(),
                page_size=2,
            )
        )

        self.assertEqual(3, len(rows))
        self.assertEqual(second_round, repository.latest_round_id("run-1"))
        self.assertIsNone(repository.latest_round_id("missing-run"))

    def test_current_round_trend_is_cumulative_and_points_to_attempt(self):
        round_id = self.add_run("run-1", {"id": "rule-a"})
        self.history.save_attempt(
            round_id,
            snapshot(slot=1, attempt=1, verified=False, published=False),
            status="rejected",
            failure_reason="job_rejected",
            scored=True,
        )
        self.history.save_result(round_id, snapshot(slot=1, attempt=2))
        repository = StatisticsRepository(self.base)

        trend = repository.get_trend(
            StatisticsFilters(
                scope="current_round",
                round_id=round_id,
                metric="attempts",
            )
        )

        self.assertEqual(["第1次", "第2次"], [row["date"] for row in trend])
        self.assertEqual([1, 2], [row["attempts"] for row in trend])
        self.assertEqual([0, 1], [row["accepted"] for row in trend])
        self.assertTrue(all(row["attempt_id"] for row in trend))


if __name__ == "__main__":
    unittest.main()
