from __future__ import annotations

import unittest
from unittest.mock import Mock

from ccz_randomizer.runtime.audio_recovery import (
    AudioMuteRecoveryResult,
    LegacyAudioRecoveryMonitor,
    ProcessAudioMuteMonitor,
)
from ccz_randomizer.runtime.window_capture import (
    WindowCaptureError,
    capture_window_with_fallbacks,
)


class SizedImage:
    size = 1


class RuntimeComponentTests(unittest.TestCase):
    def test_legacy_audio_monitor_recovers_late_normal_game(self) -> None:
        recovery_pending = Mock(side_effect=[True, True])
        recover = Mock(return_value=True)
        monitor = LegacyAudioRecoveryMonitor(
            recovery_pending=recovery_pending,
            recover=recover,
            interval=0,
        )

        monitor._run()

        recover.assert_called_once_with()

    def test_random_audio_monitor_mutes_only_its_exact_pid(self) -> None:
        process_is_alive = Mock(side_effect=[True, False])
        logger = Mock()
        mute_sessions = Mock(
            return_value=AudioMuteRecoveryResult(
                matched_sessions=1,
                restored_sessions=1,
            )
        )
        monitor = ProcessAudioMuteMonitor(
            456,
            process_is_alive=process_is_alive,
            logger=logger,
            mute_sessions=mute_sessions,
            interval=0,
        )

        monitor._run()

        mute_sessions.assert_called_once_with(456)
        logger.assert_any_call(
            "random_game_audio_muted",
            pid=456,
            matched_sessions=1,
            changed_sessions=1,
        )

    def test_window_capture_recovers_after_waking_game(self) -> None:
        recovered = SizedImage()
        print_window = Mock(side_effect=[None, None, recovered])
        bitblt = Mock(return_value=None)
        wake = Mock()
        sleep_after_wake = Mock()

        result = capture_window_with_fallbacks(
            print_window=print_window,
            bitblt=bitblt,
            wake=wake,
            is_usable=lambda image, _require_variance: image is recovered,
            sleep_after_wake=sleep_after_wake,
        )

        self.assertIs(recovered, result.image)
        self.assertEqual("print_window_after_wake", result.method)
        self.assertTrue(result.recovered)
        self.assertEqual(
            [
                unittest.mock.call(2),
                unittest.mock.call(0),
                unittest.mock.call(0),
            ],
            print_window.call_args_list,
        )
        bitblt.assert_called_once_with()
        wake.assert_called_once_with()
        sleep_after_wake.assert_called_once_with()

    def test_window_capture_reports_all_failed_strategies(self) -> None:
        with self.assertRaises(WindowCaptureError) as raised:
            capture_window_with_fallbacks(
                print_window=lambda _flags: None,
                bitblt=lambda: None,
                wake=lambda: None,
                is_usable=lambda _image, _require_variance: False,
                sleep_after_wake=lambda: None,
            )

        self.assertEqual(5, len(raised.exception.errors))
        self.assertTrue(
            raised.exception.errors[0].startswith(
                "print_window_full:"
            )
        )
