from __future__ import annotations

import unittest

from tools.diagnostics.benchmark_audio_attack import (
    validate_attack_result,
    validate_move_result,
)


def attack_result(
    *,
    frame_changes: int = 10,
    max_message_ms: float = 4.0,
    max_audio_peak: float = 0.5,
    first_audio_ms: float | None = 0.0,
) -> dict[str, object]:
    return {
        "attack": {
            "responsiveness": {
                "frameChanges": frame_changes,
                "maxMessageMs": max_message_ms,
                "maxAudioPeak": max_audio_peak,
                "firstAudioMs": first_audio_ms,
            }
        }
    }


def move_result(segment_count: int = 1) -> dict[str, object]:
    return {
        "move": {
            "activeSegmentsMs": [
                {
                    "start": index * 500.0,
                    "end": index * 500.0 + 300.0,
                    "duration": 300.0,
                }
                for index in range(segment_count)
            ]
        }
    }


class AudioAttackBenchmarkTests(unittest.TestCase):
    def test_accepts_responsive_attack_with_audio(self) -> None:
        validate_attack_result(attack_result(), expect_audio=True)

    def test_rejects_main_thread_audio_stall(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "明显停顿"):
            validate_attack_result(
                attack_result(max_message_ms=300.0),
                expect_audio=True,
            )

    def test_rejects_silent_attack_when_audio_is_expected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "未检测到游戏音频"):
            validate_attack_result(
                attack_result(max_audio_peak=0.0),
                expect_audio=True,
            )

    def test_rejects_late_attack_audio(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "启动过晚"):
            validate_attack_result(
                attack_result(first_audio_ms=600.0),
                expect_audio=True,
            )

    def test_accepts_single_move_sound_segment(self) -> None:
        validate_move_result(move_result())

    def test_rejects_repeated_move_sound_segments(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "重复播放"):
            validate_move_result(move_result(segment_count=2))

    def test_rejects_silent_move(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "未检测到音效"):
            validate_move_result(move_result(segment_count=0))


if __name__ == "__main__":
    unittest.main()
