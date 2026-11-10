"""Conventional timing and per-game fallback stay independent of turbo state."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from ccz_randomizer.runtime.normal_random import NormalRandomInteraction
from ccz_randomizer.runtime.random_interaction import RandomInteractionSession


def services():
    clock = [0.0]
    def sleep(seconds):
        clock[0] += seconds
    return SimpleNamespace(
        current_game_version=lambda: '2.20-1104-night',
        native_silent_click=Mock(), native_silent_click_burst=Mock(),
        trigger_random_choice_click=Mock(return_value=(54, 57, 0)),
        check_stop_requested=Mock(), read_job_ids=Mock(return_value=(54, 57, 0)),
        read_memory=Mock(side_effect=AssertionError('常规路径不应读取极速稳定快照')),
        time=SimpleNamespace(perf_counter=lambda: clock[0]),
        interruptible_sleep=Mock(side_effect=sleep), diagnostic_log=Mock(),
    )


class RandomInteractionTests(unittest.TestCase):
    def test_normal_mode_does_not_construct_turbo_or_consult_its_version_gate(self):
        api = services()
        api.current_game_version = Mock(side_effect=AssertionError('常规模式无需极速版本判断'))
        with patch('ccz_randomizer.runtime.turbo.TurboRandomPolicy', side_effect=AssertionError('极速策略不应创建')):
            session = RandomInteractionSession(api, 123)
            normal = session.for_attempt(1)
            normal.click_npc(456, (10, 20), 1)
            normal.settle_npc()
            current = normal.select_choice(456, (0, 1, 2), (0, 0, 0), 1)
            self.assertEqual((54, 57, 0), normal.wait_for_result((0, 1, 2), (0, 0, 0), current))
        api.native_silent_click.assert_called_once_with(123, 456, 10, 20, tail_delay_ms=0)
        api.interruptible_sleep.assert_called_once_with(.5)
        api.native_silent_click_burst.assert_not_called()
        api.read_memory.assert_not_called()
        self.assertEqual(1.0, session.scene_delay(1.0))
        self.assertEqual(1.5, session.scene_delay(1.5))

    def test_normal_retries_keep_original_click_tail_and_three_second_deadline(self):
        api = services()
        api.read_job_ids.return_value = (0, 0, 0)
        normal = NormalRandomInteraction(api, 123)
        normal.click_npc(456, (10, 20), 2)
        self.assertEqual((0, 0, 0), normal.wait_for_result((0, 1, 2), (0, 0, 0), (0, 0, 0)))
        api.native_silent_click.assert_called_once_with(123, 456, 10, 20, tail_delay_ms=None)
        self.assertGreaterEqual(api.time.perf_counter(), 3)
        self.assertLess(api.time.perf_counter(), 3.06)

    def test_turbo_failure_switches_only_its_own_game_session(self):
        first_api, second_api = services(), services()
        first = RandomInteractionSession(first_api, 123, turbo_enabled=True)
        second = RandomInteractionSession(second_api, 456, turbo_enabled=True)
        failed = first.for_attempt(1)
        first.on_no_change(failed, 1.0)
        self.assertIs(first.normal, first.for_attempt(1))
        self.assertEqual(1.0, first.scene_delay(1.0))
        first_api.interruptible_sleep.assert_called_once_with(1.0)
        self.assertEqual(.05, second.scene_delay(1.0))
        self.assertIsNot(second.normal, second.for_attempt(1))
        second_api.interruptible_sleep.assert_not_called()
        self.assertIs(first.normal, first.for_attempt(3))

    def test_normal_failure_has_no_turbo_fallback_wait(self):
        api = services()
        session = RandomInteractionSession(api, 123)
        session.on_no_change(session.for_attempt(1), 1.0)
        api.interruptible_sleep.assert_not_called()
        api.diagnostic_log.assert_not_called()

    def test_unsupported_turbo_layout_uses_the_original_strategy(self):
        api = services()
        api.current_game_version = lambda: '2.10'
        session = RandomInteractionSession(api, 123, turbo_enabled=True)
        self.assertIs(session.normal, session.for_attempt(1))
        self.assertEqual(1.0, session.scene_delay(1.0))

    def test_disabled_turbo_cannot_be_reentered_on_a_later_roll(self):
        session = RandomInteractionSession(services(), 123, turbo_enabled=True)
        session.for_attempt(1).disable('unstable_result')
        self.assertIs(session.normal, session.for_attempt(1))
        self.assertEqual(1.0, session.scene_delay(1.0))

    def test_normal_polling_propagates_stop(self):
        api = services()
        api.check_stop_requested.side_effect = InterruptedError('stop')
        with self.assertRaises(InterruptedError):
            NormalRandomInteraction(api, 123).wait_for_result((0, 1, 2), (0, 0, 0), (0, 0, 0))
        api.read_job_ids.assert_not_called()
