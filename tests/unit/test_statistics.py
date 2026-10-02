from __future__ import annotations

import csv
import datetime as dt
import json
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest import mock

from ccz_randomizer.catalogs import (
    job_catalog_rows,
    skill_catalog_rows,
    treasure_property_catalog_rows,
)
from ccz_randomizer.history import HistoryRepository
from ccz_randomizer.statistics import StatisticsFilters, StatisticsRepository
from ccz_randomizer.ui.statistics import (
    _choice_picker,
    _include_zero_rows,
    _line_chart,
    _ranked_distribution,
    _release_entry_focus,
    _scroll_canvas,
    _show_calendar,
    show_statistics_window,
)


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


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

    def test_other_status_group_excludes_accepted_and_rejected(self):
        round_id = self.add_run("run-status-groups", {"id": "rule-a"})
        self.history.save_attempt(
            round_id,
            snapshot(slot=1, attempt=1, verified=False, published=False),
            status="rejected",
            scored=True,
        )
        self.history.save_attempt(
            round_id,
            snapshot(slot=2, attempt=1, verified=False, published=False),
            status="failed",
            scored=False,
        )
        repository = StatisticsRepository(self.base)

        other = repository.get_summary(
            StatisticsFilters(
                metric="attempts",
                status_group="other",
            )
        )

        self.assertEqual(1, other["attempt_count"])
        self.assertEqual(1, other["failed"])
        self.assertEqual(0, other["rejected"])

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

    def test_named_unknown_skill_keeps_its_recorded_name(self):
        round_id = self.add_run("run-named-unknown", {"id": "rule-a"})
        self.history.save_result(
            round_id,
            snapshot(
                slot=1,
                attempt=1,
                personal=[
                    {
                        "skillId": "future-skill-1",
                        "skillName": "新版天赋",
                        "known": False,
                    }
                ],
            ),
        )
        repository = StatisticsRepository(self.base)

        rows = repository.get_personal_skill_distribution(StatisticsFilters())

        self.assertEqual(["新版天赋"], [row["label"] for row in rows])

    def test_related_distributions_only_count_the_selected_relation(self):
        round_id = self.add_run("run-related", {"id": "rule-a"})
        value = snapshot(slot=1, attempt=1)
        value["members"] = [
            {
                "position": 0,
                "memberId": "cao-cao",
                "name": "曹操",
                "jobId": "strategist",
                "job": "策士",
                "jobKnown": True,
                "personalSkills": [
                    {
                        "skillId": "merit",
                        "skillName": "获得功勋",
                        "known": True,
                    }
                ],
                "jobSkills": [],
            },
            {
                "position": 1,
                "memberId": "xiahou-dun",
                "name": "夏侯惇",
                "jobId": "cavalry",
                "job": "骑兵",
                "jobKnown": True,
                "personalSkills": [
                    {
                        "skillId": "guard",
                        "skillName": "一夫当关",
                        "known": True,
                    }
                ],
                "jobSkills": [],
            },
            {
                "position": 2,
                "memberId": "xiahou-yuan",
                "name": "夏侯渊",
                "jobId": "archer",
                "job": "弓兵",
                "jobKnown": True,
                "personalSkills": [],
                "jobSkills": [],
            },
        ]
        value["treasures"] = [
            {
                "memberPosition": 0,
                "treasureId": "heaven-sword",
                "treasureName": "倚天剑",
                "known": True,
                "properties": [
                    {
                        "propertyId": "life-steal",
                        "propertyName": "吸血",
                        "known": True,
                    }
                ],
            },
            {
                "memberPosition": 1,
                "treasureId": "qinggang-sword",
                "treasureName": "青釭剑",
                "known": True,
                "properties": [
                    {
                        "propertyId": "armor-break",
                        "propertyName": "破甲",
                        "known": True,
                    }
                ],
            },
        ]
        self.history.save_result(round_id, value)
        repository = StatisticsRepository(self.base)
        filters = StatisticsFilters()

        self.assertEqual(
            ["曹操"],
            [
                row["label"]
                for row in repository.get_members_for_job(
                    filters,
                    "strategist",
                )
            ],
        )
        self.assertEqual(
            ["夏侯惇"],
            [
                row["label"]
                for row in repository.get_members_for_skill(
                    filters,
                    scope="personal",
                    skill_id="guard",
                )
            ],
        )
        self.assertEqual(
            ["吸血"],
            [
                row["label"]
                for row in repository.get_properties_for_treasure(
                    filters,
                    "heaven-sword",
                )
            ],
        )
        self.assertEqual(
            ["青釭剑"],
            [
                row["label"]
                for row in repository.get_treasures_for_property(
                    filters,
                    "armor-break",
                )
            ],
        )

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

    def test_global_treasures_remain_visible_with_member_filter(self):
        round_id = self.add_run("run-global-treasure", {"id": "rule-a"})
        value = snapshot(slot=1, attempt=1)
        value["members"][0]["memberId"] = "target-member"
        value["members"][0]["name"] = "目标武将"
        value["treasures"][0]["memberPosition"] = -1
        self.history.save_result(round_id, value)
        repository = StatisticsRepository(self.base)
        filters = StatisticsFilters(member_id="target-member")

        self.assertEqual(
            ["倚天剑"],
            [
                row["label"]
                for row in repository.get_treasure_distribution(filters)
            ],
        )
        self.assertEqual(
            ["吸血"],
            [
                row["label"]
                for row in repository.get_treasure_property_distribution(
                    filters
                )
            ],
        )
        self.assertEqual(
            ["青龙套装"],
            [
                row["label"]
                for row in repository.get_combination_distribution(filters)
            ],
        )

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

    def test_statistics_window_loads_only_the_visible_tab(self):
        round_id = self.add_run("run-ui", {"id": "rule-ui"})
        self.history.save_result(round_id, snapshot(slot=1, attempt=1))
        repository = StatisticsRepository(self.base)
        root = tk.Tk()
        root.withdraw()

        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)

        try:
            with (
                mock.patch.object(
                    repository,
                    "get_job_distribution",
                    wraps=repository.get_job_distribution,
                ) as job_distribution,
                mock.patch.object(
                    repository,
                    "get_personal_skill_distribution",
                    wraps=repository.get_personal_skill_distribution,
                ) as personal_distribution,
                mock.patch.object(
                    repository,
                    "get_treasure_distribution",
                    wraps=repository.get_treasure_distribution,
                ) as treasure_distribution,
            ):
                show_statistics_window(root, repository)
                root.update()
                time.sleep(0.08)
                root.update()

                self.assertFalse(job_distribution.called)
                self.assertFalse(personal_distribution.called)
                self.assertFalse(treasure_distribution.called)

                dialog = next(
                    child
                    for child in root.winfo_children()
                    if isinstance(child, tk.Toplevel)
                )
                widgets = list(descendants(dialog))
                selected_picker_values = {
                    str(widget.getvar(widget.cget("textvariable")))
                    for widget in widgets
                    if isinstance(widget, tk.Button)
                    and str(widget.cget("textvariable"))
                }
                label_texts = {
                    str(widget.cget("text"))
                    for widget in widgets
                    if isinstance(widget, tk.Label)
                }
                self.assertIn("全部", selected_picker_values)
                self.assertIn("全部规则", selected_picker_values)
                self.assertNotIn("筛选条件", label_texts)
                self.assertNotIn("统计范围", label_texts)
                self.assertNotIn("存档范围", label_texts)
                filter_fields = [
                    widget.master
                    for widget in widgets
                    if isinstance(widget, tk.Label)
                    and str(widget.cget("text"))
                    in {"统计内容", "随机模式", "规则配置", "时间"}
                ]
                self.assertEqual(4, len(filter_fields))
                self.assertEqual(
                    {0},
                    {
                        int(field.grid_info()["row"])
                        for field in filter_fields
                    },
                )
                for field in filter_fields:
                    picker = next(
                        child
                        for child in field.winfo_children()
                        if isinstance(child, tk.Button)
                        and str(child.cget("textvariable"))
                    )
                    self.assertEqual(16, int(picker.cget("width")))

                scrolling_canvas = next(
                    widget
                    for widget in widgets
                    if isinstance(widget, tk.Canvas)
                    and str(widget.cget("yscrollcommand"))
                )
                scrolling_canvas.master.event_generate("<Enter>")
                fake_canvas = mock.Mock()
                _scroll_canvas(
                    fake_canvas,
                    type(
                        "MouseWheelEvent",
                        (),
                        {"widget": scrolling_canvas, "delta": -120},
                    )(),
                )
                fake_canvas.yview_scroll.assert_called_once_with(3, "units")

                notebook = next(
                    child
                    for child in widgets
                    if isinstance(child, ttk.Notebook)
                )
                notebook.select(1)
                root.update()
                time.sleep(0.08)
                root.update()

                self.assertTrue(job_distribution.called)
                self.assertFalse(personal_distribution.called)
                self.assertFalse(treasure_distribution.called)
                job_labels = {
                    str(widget.cget("text"))
                    for widget in descendants(dialog)
                    if isinstance(widget, tk.Label)
                }
                self.assertIn("兵种出现分布", job_labels)
                self.assertIn("武将0的兵种分布", job_labels)
                self.assertIn("策士分配给不同武将的分布", job_labels)
                self.assertNotIn("武将分布", job_labels)
                member_picker = next(
                    widget
                    for widget in descendants(dialog)
                    if isinstance(widget, tk.Button)
                    and str(widget.cget("textvariable"))
                    and str(
                        widget.getvar(widget.cget("textvariable"))
                    )
                    == "武将0"
                )
                calls_before_picker_change = job_distribution.call_count
                member_picker.invoke()
                root.update()
                member_popup = member_picker._choice_popup
                member_option = next(
                    widget
                    for widget in descendants(member_popup)
                    if isinstance(widget, tk.Button)
                    and str(widget.cget("text")) == "武将1"
                )
                member_option.invoke()
                root.update()
                self.assertEqual(
                    calls_before_picker_change + 1,
                    job_distribution.call_count,
                )

                notebook.select(2)
                root.update()
                time.sleep(0.08)
                root.update()
                skill_labels = {
                    str(widget.cget("text"))
                    for widget in descendants(dialog)
                    if isinstance(widget, tk.Label)
                }
                self.assertIn("个人天赋出现分布", skill_labels)
                self.assertIn("兵种技能出现分布", skill_labels)
                self.assertIn("武将0的个人天赋分布", skill_labels)
                self.assertTrue(
                    any(
                        label.endswith("分配给不同武将的分布")
                        for label in skill_labels
                    )
                )
                self.assertNotIn("个人天赋组合", skill_labels)
                self.assertNotIn("个人天赋有无分布", skill_labels)

                notebook.select(3)
                root.update()
                time.sleep(0.08)
                root.update()
                treasure_labels = {
                    str(widget.cget("text"))
                    for widget in descendants(dialog)
                    if isinstance(widget, tk.Label)
                }
                self.assertIn("宝物特性出现分布", treasure_labels)
                self.assertIn("倚天剑的特性分布", treasure_labels)
                self.assertIn("吸血分配给不同宝物的分布", treasure_labels)
                self.assertNotIn("宝物出现分布", treasure_labels)
                self.assertNotIn("宝物套装与组合", treasure_labels)
        finally:
            root.destroy()

    def test_choice_picker_uses_custom_popup_and_updates_selection(self):
        root = tk.Tk()
        root.geometry("420x240")
        variable = tk.StringVar(value="全部规则")
        selected = []
        try:
            picker = _choice_picker(
                root,
                variable,
                ("全部规则", "规则一", "规则二"),
                command=lambda: selected.append(variable.get()),
            )
            picker.pack()
            root.update()
            arrow = picker._choice_arrow
            self.assertGreater(
                arrow.winfo_rootx(),
                picker.winfo_rootx() + picker.winfo_width() * 0.75,
            )

            picker.invoke()
            root.update()
            popup = next(
                child
                for child in picker.winfo_children()
                if isinstance(child, tk.Toplevel)
            )
            option = next(
                widget
                for widget in descendants(popup)
                if isinstance(widget, tk.Button)
                and str(widget.cget("text")) == "规则二"
            )
            option.invoke()
            root.update()

            self.assertEqual("规则二", variable.get())
            self.assertEqual(["规则二"], selected)

            picker.invoke()
            root.update()
            popup = picker._choice_popup
            popup.event_generate(
                "<ButtonPress-1>",
                x=-20,
                y=-20,
                rootx=popup.winfo_rootx() - 20,
                rooty=popup.winfo_rooty() - 20,
            )
            root.update()
            self.assertFalse(popup.winfo_exists())
        finally:
            root.destroy()

    def test_choice_picker_scrolls_while_pointer_is_over_option(self):
        root = tk.Tk()
        root.geometry("420x240")
        variable = tk.StringVar(value="选项 01")
        values = tuple(f"选项 {index:02d}" for index in range(1, 21))
        try:
            picker = _choice_picker(
                root,
                variable,
                values,
                command=lambda: None,
            )
            picker.pack()
            root.update()
            picker.invoke()
            root.update()
            popup = picker._choice_popup
            canvas = next(
                widget
                for widget in descendants(popup)
                if isinstance(widget, tk.Canvas)
            )
            option = next(
                widget
                for widget in descendants(popup)
                if isinstance(widget, tk.Button)
                and str(widget.cget("text")) == "选项 05"
            )
            before = canvas.yview()

            option.event_generate("<MouseWheel>", delta=-120)
            root.update()

            self.assertNotEqual(before, canvas.yview())
            popup.destroy()
        finally:
            root.destroy()

    def test_choice_picker_width_fits_long_history_metric(self):
        root = tk.Tk()
        root.geometry("520x240")
        value = "每日不同宝物特性数量"
        variable = tk.StringVar(value=value)
        try:
            picker = _choice_picker(
                root,
                variable,
                ("合格数", value),
                command=lambda: None,
            )
            picker.pack()
            root.update()

            self.assertGreaterEqual(int(picker.cget("width")), 20)
            self.assertEqual(value, picker.cget("textvariable") and variable.get())
        finally:
            root.destroy()

    def test_zero_rows_are_added_only_when_explicitly_requested(self):
        rows = [
            {
                "value": "job-1",
                "label": "策士",
                "count": 2,
                "ratio": 1.0,
            }
        ]
        universe = [
            {"value": "job-1", "label": "策士"},
            {"value": "job-2", "label": "道士"},
        ]

        result = _include_zero_rows(rows, universe)

        self.assertEqual(["策士", "道士"], [row["label"] for row in result])
        self.assertEqual([2, 0], [int(row["count"]) for row in result])
        self.assertEqual(0.0, float(result[1]["ratio"]))

    def test_distribution_catalogs_cover_unseen_enum_values(self):
        jobs = job_catalog_rows()
        skills = skill_catalog_rows()
        properties = treasure_property_catalog_rows()

        self.assertGreaterEqual(len(jobs), 40)
        self.assertGreaterEqual(len(skills), 230)
        self.assertGreaterEqual(len(properties), 200)
        self.assertIn("魔王", {row["label"] for row in jobs})
        self.assertIn("万夫莫敌3%", {row["label"] for row in skills})
        self.assertIn("吸血攻击33%", {row["label"] for row in properties})

    def test_ranked_distribution_can_disable_search_for_detail_chart(self):
        root = tk.Tk()
        root.geometry("720x480")
        rows = [
            {
                "value": f"job-{index}",
                "label": f"兵种 {index}",
                "count": index,
                "ratio": index / 100,
            }
            for index in range(1, 14)
        ]
        try:
            chart = _ranked_distribution(
                root,
                rows,
                title="指定武将的兵种分布",
                searchable=False,
            )
            chart.pack(fill="both", expand=True)
            root.update()

            self.assertFalse(
                any(
                    isinstance(widget, tk.Entry)
                    for widget in descendants(chart)
                )
            )
        finally:
            root.destroy()

    def test_line_chart_limits_date_ticks_and_labels_the_x_axis(self):
        root = tk.Tk()
        root.geometry("640x320")
        rows = [
            {
                "date": f"2026-09-{day:02d}",
                "accepted": day,
            }
            for day in range(1, 21)
        ]
        try:
            chart = _line_chart(
                root,
                rows,
                title="历史趋势",
                x_label="日期",
            )
            chart.pack(fill="both", expand=True)
            root.update()
            canvas = next(
                widget
                for widget in descendants(chart)
                if isinstance(widget, tk.Canvas)
            )
            texts = [
                str(canvas.itemcget(item, "text"))
                for item in canvas.find_all()
                if canvas.type(item) == "text"
            ]
            date_ticks = [
                text
                for text in texts
                if len(text) == 5 and text[2] == "-"
            ]

            self.assertLessEqual(len(date_ticks), 6)
            self.assertIn("横轴：日期", texts)
        finally:
            root.destroy()

    def test_clicking_outside_search_releases_entry_focus(self):
        root = tk.Tk()
        root.geometry("320x180")
        entry = tk.Entry(root)
        outside = tk.Label(root, text="图表")
        entry.pack()
        outside.pack()
        try:
            root.update()
            entry.focus_force()
            root.update()
            self.assertIs(entry, root.focus_get())

            _release_entry_focus(
                root,
                type("ClickEvent", (), {"widget": outside})(),
            )
            root.update()

            self.assertIsNot(entry, root.focus_get())
        finally:
            root.destroy()

    def test_calendar_selects_a_date_without_text_entry(self):
        root = tk.Tk()
        root.geometry("420x420")
        selected = []
        try:
            popup = _show_calendar(
                root,
                title="选择日期",
                initial=dt.date(2026, 10, 1),
                on_select=selected.append,
            )
            root.update()
            self.assertFalse(
                any(
                    isinstance(widget, tk.Entry)
                    for widget in descendants(popup)
                )
            )
            day_button = next(
                widget
                for widget in descendants(popup)
                if isinstance(widget, tk.Button)
                and str(widget.cget("text")) == "15"
            )
            day_button.invoke()
            root.update()

            self.assertEqual([dt.date(2026, 10, 15)], selected)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
