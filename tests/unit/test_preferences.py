from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ccz_randomizer.preferences import (
    DEFAULT_RANDOM_MODE,
    load_random_mode,
    preferences_path,
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


if __name__ == "__main__":
    unittest.main()
