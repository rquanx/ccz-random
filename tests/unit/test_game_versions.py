import hashlib
import unittest
from ccz_randomizer.game_versions import DEFAULT_GAME_VERSION, effective_random_mode, normalize_game_version


class GameVersionTests(unittest.TestCase):
    def test_only_22_script_is_supported(self):
        from ccz_randomizer import app
        script = app.bundled_original_s00()
        self.assertEqual("cd6b8129dfcd27df9c032b8a3e91416baa90f3dadcfc37274a82de4de5a8a49c", hashlib.sha256(script.read_bytes()).hexdigest())

    def test_22_always_uses_three_people(self):
        self.assertEqual(DEFAULT_GAME_VERSION, normalize_game_version())
        self.assertEqual("three", effective_random_mode("2.2", "seven"))
        self.assertEqual("three", effective_random_mode("2.2", "three"))

    def test_legacy_version_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_game_version("2.10")
        with self.assertRaises(ValueError):
            effective_random_mode("2.10", "seven")
