"""Replay recorded zero labels without inventing a meaning for code zero."""
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from ccz_randomizer.statistics_equipment import (
    capture_equipment_statistics, completed_equipment_records,
)
from tests.unit import test_statistics_equipment as equipment_tests
from tests.unit.test_statistics import runner_fixture


ROOT = Path(__file__).resolve().parents[2]


class EquipmentSamplingTests(unittest.TestCase):
    def setUp(self):
        self.clock = 0
        self.report = Mock()
        self.stop = Mock()
        rows = json.loads((ROOT / 'resources/data/equipment/equip_ground_truth.json').read_text('utf-8'))
        self.complete = tuple(bytes(row['bytes']) for row in rows if row['slot'] == 1)
        self.assertEqual(70, len(self.complete))

    def sleep(self, seconds):
        self.clock += seconds

    def collect(self, read):
        return completed_equipment_records(read, clock=lambda: self.clock,
            sleep=self.sleep, check_stop=self.stop, report=self.report, timeout=.2)

    def test_zero_labels_from_both_real_attempts_are_never_accepted_as_stable(self):
        evidence = json.loads((ROOT / 'tests/fixtures/equipment_zero_samples_20261117.json').read_text('utf-8'))
        for attempt in {row['id'] for row in evidence['rows']}:
            zeros = [row for row in evidence['rows'] if row['id'] == attempt
                     and row['effect'] == '未知特效(0x00/0x00)']
            self.assertIn(len(zeros), (4, 20))
            # Only the observed code/parameter are replayed. These are not
            # fabricated complete native records or a claim of recovery data.
            pending = tuple(bytes((0, 0)) for _ in zeros)
            read = Mock(side_effect=[pending, pending, self.complete, self.complete])
            self.assertEqual(self.complete, self.collect(read))
            self.assertGreaterEqual(self.clock, .15)

    def test_stable_complete_native_records_need_only_one_poll_interval(self):
        self.assertEqual(self.complete, self.collect(lambda: self.complete))
        self.assertAlmostEqual(.05, self.clock)
        self.report.assert_not_called()

    def test_changing_nonzero_native_snapshots_are_not_returned_early(self):
        rows = json.loads((ROOT / 'resources/data/equipment/equip_ground_truth.json').read_text('utf-8'))
        next_slot = tuple(bytes(row['bytes']) for row in rows if row['slot'] == 2)
        self.assertNotEqual(self.complete, next_slot)
        read = Mock(side_effect=[self.complete, next_slot, next_slot])
        self.assertEqual(next_slot, self.collect(read))
        self.assertAlmostEqual(.1, self.clock)

    def test_empty_snapshot_is_not_a_completed_sample(self):
        with self.assertRaisesRegex(RuntimeError, '未计入'):
            self.collect(lambda: ())

    def test_persistent_zero_is_unconfirmed_even_when_bytes_are_unchanged(self):
        with self.assertRaisesRegex(RuntimeError, '未计入'):
            self.collect(lambda: (bytes((0, 0)),))
        self.assertLessEqual(self.clock, .2)
        self.assertEqual([0], self.report.call_args.kwargs['zero_indices'])

    def test_nonzero_unknown_effects_are_preserved_without_mapping_or_hiding(self):
        records = (bytes((255, 1)),)
        self.assertEqual(records, self.collect(lambda: records))

    def test_stop_and_read_errors_propagate(self):
        self.stop.side_effect = KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.collect(lambda: self.complete)
        self.stop.side_effect = None
        with self.assertRaises(OSError):
            self.collect(Mock(side_effect=OSError('read failed')))


class UnconfirmedEquipmentStatisticsTests(unittest.TestCase):
    setUp = equipment_tests.EquipmentStatisticsTests.setUp
    tearDown = equipment_tests.EquipmentStatisticsTests.tearDown
    recorder = equipment_tests.EquipmentStatisticsTests.recorder
    capture = equipment_tests.EquipmentStatisticsTests.capture

    def test_unconfirmed_equipment_does_not_reuse_last_sample_or_drop_attempt(self):
        recorder = self.recorder()
        runner = runner_fixture(reject=True)
        runner._statistics_equipment = [{'name': '青龙宝玉', 'effect': '上轮结果'}]
        errors = Mock()
        capture_equipment_statistics(runner,
            Mock(side_effect=RuntimeError('宝物采样尚未完整或稳定')), errors)
        self.capture(recorder, runner)
        recorder.close()
        self.assertEqual([], runner._statistics_equipment)
        self.assertEqual(1, self.repo.query()['totals'][0])
        self.assertEqual(0, self.repo.query()['equipment_samples'])
        self.assertEqual([], self.repo.ranking('equipment')['rows'])
