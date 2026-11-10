import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from ccz_randomizer.preferences import load_turbo_mode, preferences_path, save_random_runtime_settings
from ccz_randomizer.runtime.turbo import TurboRandomPolicy

FIXTURES = Path(__file__).parents[1] / 'fixtures/personnel_22'


class TurboTests(unittest.TestCase):
    def services(self, jobs=None, snapshots=None):
        # Job IDs observed in the 1104 real-game benchmark; zero is valid.
        self.clock = 0
        def sleep(seconds):
            self.clock += seconds
        return SimpleNamespace(
            current_game_version=lambda: '2.20-1104-night',
            check_stop_requested=Mock(), native_silent_click_burst=Mock(),
            CONFIRM_FIRST_CLIENT_POSITION=(200, 100), R0_MEMORY_SIZE=0x30000,
            time=SimpleNamespace(perf_counter=lambda: self.clock),
            interruptible_sleep=Mock(side_effect=sleep),
            read_job_ids=Mock(side_effect=jobs) if jobs is not None else Mock(return_value=(0, 0, 0)),
            read_memory=Mock(side_effect=snapshots),
            InteractionNotTriggered=RuntimeError, diagnostic_log=Mock(),
        )

    def test_opt_in_is_saved_defaults_off_and_invalid_values_stay_off(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertFalse(load_turbo_mode(root))
            save_random_runtime_settings(root, loop_random=False, concurrency=2, turbo_mode=True)
            self.assertTrue(load_turbo_mode(root))
            save_random_runtime_settings(root, loop_random=False, concurrency=2, turbo_mode=False)
            self.assertFalse(load_turbo_mode(root))
            preferences_path(root).write_text('{"turboMode":"true"}', encoding='utf-8')
            self.assertFalse(load_turbo_mode(root))
            with self.assertRaises(ValueError):
                save_random_runtime_settings(root, loop_random=False, concurrency=2, turbo_mode=1)

    def test_normal_mode_retains_delays_and_unsupported_version_uses_normal(self):
        services = self.services()
        normal = TurboRandomPolicy(services, 123)
        self.assertEqual(1.0, normal.scene_delay(1.0))
        self.assertEqual(1.5, normal.scene_delay(1.5))
        services.current_game_version = lambda: '2.10'
        self.assertFalse(TurboRandomPolicy(services, 123, enabled=True).enabled)

    def test_turbo_shortens_reused_scene_only_and_can_be_disabled_for_session(self):
        turbo = TurboRandomPolicy(self.services(), 123, enabled=True)
        self.assertEqual(.05, turbo.scene_delay(1.0))
        self.assertEqual(1.5, turbo.scene_delay(1.5))
        turbo.disable('lost_npc_click')
        self.assertFalse(turbo.enabled)
        self.assertEqual(1.0, turbo.scene_delay(1.0))

    def test_waits_for_changed_memory_to_settle_and_accepts_zero_job_id(self):
        # Treat real memory fixtures as opaque snapshots, without parsing them.
        before = (FIXTURES / 'recruitment-before.bin').read_bytes()
        after = (FIXTURES / 'recruitment-after.bin').read_bytes()
        services = self.services(jobs=[(0, 0, 0), (54, 57, 0), (54, 57, 0), (54, 57, 0)],
                                 snapshots=[before, after, after])
        turbo = TurboRandomPolicy(services, 123, enabled=True)
        self.assertEqual((54, 57, 0), turbo.select_choice(456, (1, 2, 3), (0, 0, 0)))
        self.assertAlmostEqual(.15, self.clock)

    def test_missing_click_returns_no_result_for_conventional_retry(self):
        turbo = TurboRandomPolicy(self.services(), 123, enabled=True)
        self.assertEqual((0, 0, 0), turbo.select_choice(456, (1, 2, 3), (0, 0, 0)))

    def test_unstable_changed_result_is_never_published(self):
        services = self.services()
        services.read_job_ids.return_value = (54, 57, 0)
        services.read_memory.side_effect = lambda *args: str(self.clock).encode()
        turbo = TurboRandomPolicy(services, 123, enabled=True)
        with self.assertRaisesRegex(RuntimeError, '尚未稳定'):
            turbo.select_choice(456, (1, 2, 3), (0, 0, 0))
        self.assertFalse(turbo.enabled)

    def test_stop_propagates_before_sending_input(self):
        services = self.services()
        services.check_stop_requested.side_effect = InterruptedError('stop')
        with self.assertRaises(InterruptedError):
            TurboRandomPolicy(services, 123, enabled=True).click(456, (1, 2))
        services.native_silent_click_burst.assert_not_called()
