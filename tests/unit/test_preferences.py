from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ccz_randomizer.preferences import (
    AUDIO_MUTE_RECOVERY_VERSION,
    AUDIO_MUTE_RECOVERY_VERSION_KEY,
    DEFAULT_COMPATIBILITY_MODE,
    DEFAULT_CONCURRENCY,
    DEFAULT_LOOP_RANDOM,
    DEFAULT_RANDOM_MODE,
    legacy_audio_mute_recovery_pending,
    load_compatibility_mode,
    load_concurrency,
    load_loop_random,
    load_random_mode,
    mark_legacy_audio_mute_recovered,
    preferences_path,
    save_random_runtime_settings,
    save_random_mode,
)


class PreferencesTests(unittest.TestCase):
    def test_missing_preferences_use_seven_person_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(
                DEFAULT_RANDOM_MODE,
                load_random_mode(Path(temporary)),
            )

    def test_saved_random_mode_is_loaded_next_time(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            app_directory = Path(temporary)
            save_random_mode(app_directory, "three")

            self.assertEqual("three", load_random_mode(app_directory))
            saved = json.loads(
                preferences_path(app_directory).read_text(encoding="utf-8")
            )
            self.assertEqual(1, saved["version"])
            self.assertEqual("three", saved["randomMode"])

    def test_invalid_or_corrupt_mode_falls_back_to_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            app_directory = Path(temporary)
            path = preferences_path(app_directory)
            path.write_text('{"randomMode": "unknown"}', encoding="utf-8")
            self.assertEqual(
                DEFAULT_RANDOM_MODE,
                load_random_mode(app_directory),
            )
            path.write_text("{", encoding="utf-8")
            self.assertEqual(
                DEFAULT_RANDOM_MODE,
                load_random_mode(app_directory),
            )

    def test_invalid_mode_is_not_saved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                save_random_mode(Path(temporary), "invalid")

    def test_runtime_settings_are_loaded_on_next_start(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            app_directory = Path(temporary)

            save_random_runtime_settings(
                app_directory,
                loop_random=True,
                concurrency=6,
                compatibility_mode=True,
            )

            self.assertTrue(load_loop_random(app_directory))
            self.assertEqual(6, load_concurrency(app_directory))
            self.assertTrue(load_compatibility_mode(app_directory))

    def test_invalid_runtime_settings_fall_back_to_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            app_directory = Path(temporary)
            preferences_path(app_directory).write_text(
                json.dumps(
                    {
                        "loopRandom": "yes",
                        "concurrency": 0,
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                DEFAULT_LOOP_RANDOM,
                load_loop_random(app_directory),
            )
            self.assertEqual(
                DEFAULT_CONCURRENCY,
                load_concurrency(app_directory),
            )
            self.assertEqual(
                DEFAULT_COMPATIBILITY_MODE,
                load_compatibility_mode(app_directory),
            )

    def test_runtime_settings_preserve_mode_and_audio_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            app_directory = Path(temporary)
            save_random_mode(app_directory, "three")
            mark_legacy_audio_mute_recovered(app_directory)

            save_random_runtime_settings(
                app_directory,
                loop_random=True,
                concurrency=4,
            )

            self.assertEqual("three", load_random_mode(app_directory))
            self.assertFalse(
                legacy_audio_mute_recovery_pending(app_directory)
            )

    def test_loop_concurrency_above_single_round_size_is_saved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            app_directory = Path(temporary)
            save_random_runtime_settings(
                app_directory,
                loop_random=True,
                concurrency=30,
            )

            self.assertEqual(30, load_concurrency(app_directory))

    def test_non_positive_concurrency_is_not_saved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            app_directory = Path(temporary)
            with self.assertRaises(ValueError):
                save_random_runtime_settings(
                    app_directory,
                    loop_random=False,
                    concurrency=0,
                )

    def test_audio_mute_recovery_marker_preserves_random_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            app_directory = Path(temporary)
            save_random_mode(app_directory, "three")

            self.assertTrue(
                legacy_audio_mute_recovery_pending(app_directory)
            )
            mark_legacy_audio_mute_recovered(app_directory)

            self.assertFalse(
                legacy_audio_mute_recovery_pending(app_directory)
            )
            saved = json.loads(
                preferences_path(app_directory).read_text(encoding="utf-8")
            )
            self.assertEqual(
                AUDIO_MUTE_RECOVERY_VERSION,
                saved[AUDIO_MUTE_RECOVERY_VERSION_KEY],
            )
            self.assertEqual("three", load_random_mode(app_directory))

    def test_old_audio_recovery_marker_requires_version_two(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            app_directory = Path(temporary)
            preferences_path(app_directory).write_text(
                json.dumps(
                    {
                        "version": 1,
                        "legacyAudioMuteRecovered": True,
                    }
                ),
                encoding="utf-8",
            )

            self.assertTrue(
                legacy_audio_mute_recovery_pending(app_directory)
            )

    def test_saving_mode_preserves_audio_mute_recovery_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            app_directory = Path(temporary)
            mark_legacy_audio_mute_recovered(app_directory)

            save_random_mode(app_directory, "three")

            self.assertFalse(
                legacy_audio_mute_recovery_pending(app_directory)
            )


if __name__ == "__main__":
    unittest.main()
