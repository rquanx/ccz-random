"""Equipment statistics use the recorded randomized 70-item game fixture."""
from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from ccz_randomizer.statistics_equipment import capture_equipment_statistics
from ccz_randomizer.equipment_labels import equipment_label_resolver
from tests.unit import test_statistics as statistics_tests
from tests.unit.test_statistics import runner_fixture


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/personnel_22/randomized-equipment.json"


def equipment_fixture():
    data = json.loads(FIXTURE.read_text("utf-8"))
    return [([(item["name"], item["effect"]) for item in category["items"]], category["name"])
            for category in data["categories"]]


class EquipmentStatisticsTests(unittest.TestCase):
    setUp = statistics_tests.StatisticsTests.setUp
    tearDown = statistics_tests.StatisticsTests.tearDown
    recorder = statistics_tests.StatisticsTests.recorder
    capture = statistics_tests.StatisticsTests.capture

    def test_legacy_strategy_labels_merge_search_and_paginate_without_rewriting_records(self):
        names = [name for items, _ in equipment_fixture() for name, _ in items][:5]
        legacy = ['攻击追加-策略编号11', '策略先手-策略编号22',
                  '攻击追加-策略编号2', '策略反击-策略编号2', '攻击追加-火阵']
        runner = runner_fixture(reject=True)
        runner._statistics_equipment = [dict(name=name, effect=effect) for name, effect in zip(names, legacy)]
        recorder = self.recorder()
        self.capture(recorder, runner)
        recorder.close()
        expected = {'攻击追加-龙卷': 1, '策略先手-谍报': 1, '攻击追加-火阵': 2, '策略反击-火阵': 1}
        self.assertEqual(expected, dict(self.repo.query()['equipment']))
        self.assertEqual(expected, dict(self.repo.ranking('equipment')['rows']))
        first = self.repo.ranking('equipment', query='火阵', page_size=1)
        second = self.repo.ranking('equipment', query='火阵', page_size=1, page=2)
        self.assertEqual(2, first['count'])
        self.assertEqual(5, first['total'])
        self.assertEqual({'攻击追加-火阵': 2, '策略反击-火阵': 1}, dict(first['rows'] + second['rows']))
        self.assertEqual([('攻击追加-火阵', 1)], self.repo.query(equipment_name=names[2])['equipment'])
        with self.repo.connect() as db:
            self.assertEqual(set(legacy), {r[0] for r in db.execute('SELECT effect FROM equipment_effects')})
            self.assertEqual(5, db.execute('SELECT COUNT(*) FROM equipment_samples').fetchone()[0])

    def test_unrecognized_strategy_labels_remain_distinguishable(self):
        label = equipment_label_resolver()
        for value in ('攻击追加-策略编号999', '策略先手-策略编号144', '其他-策略编号2'):
            self.assertEqual(value, label(value))

    def test_legacy_remote_aliases_merge_by_range_and_leave_distinct_ranges_separate(self):
        names = [name for items, _ in equipment_fixture() for name, _ in items][:5]
        effects = ['远距攻击3', '远程攻击 3', '远距攻击-菱形2～3格', '远距攻击16', '远距攻击255']
        runner = runner_fixture(reject=True)
        runner._statistics_equipment = [dict(name=name, effect=effect) for name, effect in zip(names, effects)]
        recorder = self.recorder()
        self.capture(recorder, runner)
        recorder.close()
        expected = {'远距攻击3(菱形2～3格)': 3, '远距攻击16(菱形3格)': 1, '远距攻击255': 1}
        self.assertEqual(expected, dict(self.repo.query()['equipment']))
        self.assertEqual(expected, dict(self.repo.ranking('equipment')['rows']))
        self.assertEqual([('远距攻击16(菱形3格)', 1)], self.repo.ranking('equipment', query='菱形3格')['rows'])
        self.assertEqual([('远距攻击3(菱形2～3格)', 1)], self.repo.query(equipment_name=names[1])['equipment'])
        with self.repo.connect() as db:
            self.assertEqual(set(effects), {row[0] for row in db.execute('SELECT effect FROM equipment_effects')})

    def test_legacy_penetration_ranges_merge_and_search_without_rewriting_records(self):
        names = [name for items, _ in equipment_fixture() for name, _ in items][:4]
        effects = ['穿透攻击-1', '穿透攻击-十字', '穿透攻击-2', '穿透攻击-255']
        runner = runner_fixture(reject=True)
        runner._statistics_equipment = [dict(name=name, effect=effect) for name, effect in zip(names, effects)]
        recorder = self.recorder()
        self.capture(recorder, runner)
        recorder.close()
        expected = {'穿透攻击-十字': 2, '穿透攻击-九宫': 1, '穿透攻击-255': 1}
        self.assertEqual(expected, dict(self.repo.query()['equipment']))
        self.assertEqual(expected, dict(self.repo.ranking('equipment')['rows']))
        self.assertEqual([('穿透攻击-十字', 2)], self.repo.ranking('equipment', query='十字')['rows'])
        self.assertEqual([('穿透攻击-十字', 1)], self.repo.query(equipment_name=names[0])['equipment'])
        with self.repo.connect() as db:
            self.assertEqual(set(effects), {r[0] for r in db.execute('SELECT effect FROM equipment_effects')})
            self.assertEqual(4, db.execute('SELECT COUNT(*) FROM equipment_samples').fetchone()[0])

    def test_failed_and_qualified_attempts_store_actual_effects_and_item_filter(self):
        recorder = self.recorder()
        info = equipment_fixture()
        reports = Mock()
        for rejected in (True, False):
            runner = runner_fixture(reject=rejected)
            capture_equipment_statistics(runner, lambda: info, reports)
            self.capture(recorder, runner, saved=not rejected)
        recorder.close()
        reports.assert_not_called()
        label = equipment_label_resolver()
        expected = Counter(label(effect) for items, _ in info for _, effect in items)
        self.assertEqual(70, sum(expected.values()))
        all_data = self.repo.ranking("equipment", page_size=200)
        self.assertEqual({effect: count*2 for effect, count in expected.items()}, dict(all_data["rows"]))
        self.assertEqual(140, all_data["total"])
        self.assertEqual(2, self.repo.query()["equipment_samples"])
        rejected_data = self.repo.query(result="rejected")
        self.assertEqual(1, rejected_data["equipment_samples"])
        self.assertEqual(dict(rejected_data["equipment"]), dict(expected))
        item, effect = info[0][0][0]
        single = self.repo.query(equipment_name=item, result="qualified", person="曹操")
        self.assertEqual([(effect, 1)], single["equipment"])
        self.assertEqual(1, single["equipment_samples"])
        self.assertEqual([(effect, 1)], self.repo.ranking("equipment", equipment_name=item,
            result="qualified", person="曹操")["rows"])

    def test_full_ranking_pagination_search_and_literal_characters(self):
        recorder = self.recorder()
        runner = runner_fixture(reject=True)
        capture_equipment_statistics(runner, equipment_fixture, self.fail)
        self.capture(recorder, runner)
        recorder.close()
        first = self.repo.ranking("equipment", page_size=12)
        second = self.repo.ranking("equipment", page_size=12, page=2)
        full = self.repo.ranking("equipment", page_size=200)
        self.assertGreater(full["count"], 12)
        self.assertEqual(full["rows"][:24], first["rows"] + second["rows"])
        label = full["rows"][-1][0]
        result = self.repo.ranking("equipment", query=label)
        self.assertTrue(any(name == label for name, _ in result["rows"]))
        # Search is literal; SQL wildcards and quotes never become executable SQL.
        self.assertEqual([], self.repo.ranking("equipment", query="%' OR 1=1 --")["rows"])
        self.assertEqual(70, self.repo.ranking("equipment", query=label)["total"])

    def test_capture_failure_does_not_erase_other_results_or_fabricate_equipment(self):
        recorder = self.recorder()
        runner = runner_fixture(reject=True)
        report = Mock()
        capture_equipment_statistics(runner, Mock(side_effect=OSError("read failed")), report)
        self.capture(recorder, runner)
        recorder.close()
        self.assertEqual(1, report.call_count)
        self.assertEqual(1, self.repo.query()["totals"][0])
        self.assertEqual(0, self.repo.query()["equipment_samples"])
        self.assertEqual([], self.repo.ranking("equipment")["rows"])

    def test_capture_does_not_replace_accepted_display_snapshot(self):
        runner = SimpleNamespace(_equip_info="accepted-display-snapshot")
        capture_equipment_statistics(runner, equipment_fixture, self.fail)
        self.assertEqual("accepted-display-snapshot", runner._equip_info)
        self.assertEqual(70, len(runner._statistics_equipment))

    def test_upgrade_keeps_old_attempts_without_inventing_equipment_samples(self):
        recorder = self.recorder()
        self.capture(recorder, runner_fixture(reject=True))
        recorder.close()
        # Reproduce the released v1 schema: no equipment table, all attempt data retained.
        with closing(sqlite3.connect(self.repo.path)) as db:
            db.execute("DROP VIEW equipment")
            db.execute("PRAGMA user_version=1")
        data = self.repo.query()
        self.assertEqual(1, data["totals"][0])
        self.assertEqual([], data["equipment"])
        self.assertEqual(0, data["equipment_samples"])
        with self.repo.connect() as db:
            self.assertEqual(3, db.execute("PRAGMA user_version").fetchone()[0])

    def test_job_and_skill_rankings_include_items_beyond_preview(self):
        from ccz_randomizer.jobs import JOB_MAP
        from ccz_randomizer.statistics import observation
        recorder = self.recorder()
        # Job names/scores come from the active game catalog; the event shape
        # comes from the real report builders exercised by runner_fixture.
        unique_jobs = dict((name, score) for name, score, _ in JOB_MAP.values())
        events = []
        for name, score in list(unique_jobs.items())[:20]:
            event = observation(runner_fixture(reject=True), saved=False, interrupted=False, failed=False, elapsed=1)
            event.update(round_number=1, slot=1, attempt=1)
            event["members"] = [dict(name="曹操", job=name, job_score=score)]
            events.append(event)
        self.repo.append(recorder.context, events)
        recorder.close()
        self.assertEqual(20, len(self.repo.query()["jobs"]))
        full = self.repo.ranking("jobs", person="曹操", result="rejected")
        self.assertEqual(20, full["count"])
        self.assertEqual(20, len(full["rows"]))
        self.assertEqual(20, full["total"])

    def test_skill_chart_query_includes_all_observed_positive_frequencies(self):
        from ccz_randomizer.rules.skill_defaults import SKILL_DEFAULTS
        from ccz_randomizer.statistics import observation
        recorder = self.recorder()
        events = []
        expected = {}
        for name, score, _, _ in SKILL_DEFAULTS[:20]:
            event = observation(runner_fixture(), saved=False, interrupted=False, failed=False, elapsed=1)
            event.update(round_number=1, slot=1, attempt=1)
            event["members"] = [dict(name="曹操", job="群雄", job_score=8, skills=[name], skill_score=score)]
            expected[name] = expected.get(name, 0)+1
            events.append(event)
        self.repo.append(recorder.context, events)
        recorder.close()
        self.assertGreater(len(expected), 12)
        self.assertEqual(dict(self.repo.query()["skills"]), expected)
        self.assertEqual(dict(self.repo.query(person="曹操")["skills"]), expected)
        self.assertEqual(self.repo.query(person="夏侯惇")["skills"], [])
