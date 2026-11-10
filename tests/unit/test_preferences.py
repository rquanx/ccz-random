from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ccz_randomizer.preferences import (
    AUDIO_MUTE_RECOVERY_VERSION,
    AUDIO_MUTE_RECOVERY_VERSION_KEY,
    DEFAULT_COMPATIBILITY_MODE,
    DEFAULT_CONCURRENCY,
    DEFAULT_LOOP_RANDOM,
    DEFAULT_RANDOM_MODE,
    FIRST_USE_NOTICE_VERSION,
    FIRST_USE_NOTICE_VERSION_KEY,
    first_use_notice_directory,
    acknowledge_first_use_notice,
    first_use_notice_acknowledged,
    legacy_audio_mute_recovery_pending,
    load_first_use_notice_seen,
    load_compatibility_mode,
    load_concurrency,
    load_loop_random,
    load_random_mode,
    mark_legacy_audio_mute_recovered,
    mark_first_use_notice_seen,
    preferences_path,
    save_random_runtime_settings,
    save_random_mode,
)


class PreferencesTests(unittest.TestCase):
    def test_notice_primary_save_does_not_write_game_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            game = Path(temporary) / "game"
            with patch("ccz_randomizer.preferences.first_use_notice_directory", return_value=Path(temporary) / "local"):
                self.assertTrue(acknowledge_first_use_notice(game))
                self.assertTrue(first_use_notice_acknowledged(game))
                self.assertFalse(preferences_path(game).exists())

    def test_notice_fallback_survives_restart_and_preserves_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            game = Path(temporary) / "game"
            save_random_runtime_settings(game, loop_random=True, concurrency=4)
            with patch("ccz_randomizer.preferences.first_use_notice_directory", return_value=Path(temporary) / "local"), patch("ccz_randomizer.preferences._notice_device_key", return_value="device-a"):
                with patch("ccz_randomizer.preferences.mark_first_use_notice_seen", side_effect=PermissionError):
                    self.assertTrue(acknowledge_first_use_notice(game))
                self.assertTrue(first_use_notice_acknowledged(game))
                self.assertTrue(load_loop_random(game))
                self.assertEqual(4, load_concurrency(game))
                with patch("ccz_randomizer.preferences.FIRST_USE_NOTICE_VERSION", 2):
                    self.assertFalse(first_use_notice_acknowledged(game))
                with patch("ccz_randomizer.preferences._notice_device_key", return_value="device-b"):
                    self.assertFalse(first_use_notice_acknowledged(game))

    def test_notice_both_locations_unwritable_returns_session_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            game = Path(temporary) / "game"
            with patch("ccz_randomizer.preferences.first_use_notice_directory", return_value=Path(temporary) / "local"), patch("ccz_randomizer.preferences._save_preferences", side_effect=PermissionError):
                self.assertFalse(acknowledge_first_use_notice(game))
                self.assertFalse(first_use_notice_acknowledged(game))

    def test_notice_version_bump_and_return_to_old_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            mark_first_use_notice_seen(directory)
            with patch("ccz_randomizer.preferences.FIRST_USE_NOTICE_VERSION", 2):
                self.assertFalse(load_first_use_notice_seen(directory))
                mark_first_use_notice_seen(directory)
                self.assertTrue(load_first_use_notice_seen(directory))
            self.assertTrue(load_first_use_notice_seen(directory))
            mark_first_use_notice_seen(directory)
            with patch("ccz_randomizer.preferences.FIRST_USE_NOTICE_VERSION", 2):
                self.assertTrue(load_first_use_notice_seen(directory))

    def test_notice_is_local_to_device_user_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict("os.environ", {"LOCALAPPDATA": str(Path(temporary) / "a")}):
                mark_first_use_notice_seen(first_use_notice_directory())
                self.assertTrue(load_first_use_notice_seen(first_use_notice_directory()))
            with patch.dict("os.environ", {"LOCALAPPDATA": str(Path(temporary) / "b")}):
                self.assertFalse(load_first_use_notice_seen(first_use_notice_directory()))

    def test_legacy_marker_does_not_skip_new_notice_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            preferences_path(directory).write_text(
                '{"firstUseNoticeSeen": true}', encoding="utf-8"
            )
            with patch("ccz_randomizer.preferences.FIRST_USE_NOTICE_VERSION", 2):
                self.assertFalse(load_first_use_notice_seen(directory))

    def test_first_use_notice_is_unseen_until_acknowledged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            app_directory = Path(temporary)
            self.assertFalse(load_first_use_notice_seen(app_directory))

            mark_first_use_notice_seen(app_directory)

            self.assertTrue(load_first_use_notice_seen(app_directory))
            saved = json.loads(
                preferences_path(app_directory).read_text(encoding="utf-8")
            )
            self.assertEqual(
                FIRST_USE_NOTICE_VERSION,
                saved[FIRST_USE_NOTICE_VERSION_KEY],
            )

    def test_legacy_first_use_marker_is_migrated_without_repeating_notice(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            app_directory = Path(temporary)
            preferences_path(app_directory).write_text(
                json.dumps({"firstUseNoticeSeen": True}),
                encoding="utf-8",
            )

            self.assertTrue(load_first_use_notice_seen(app_directory))

    def test_missing_preferences_use_three_person_mode(self) -> None:
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
