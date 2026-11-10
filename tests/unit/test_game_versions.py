import hashlib
import unittest
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from ccz_randomizer.game_versions import DEFAULT_GAME_VERSION, effective_random_mode, normalize_game_version


class GameVersionTests(unittest.TestCase):
    def test_unknown_fingerprint_uses_active_profile_and_activates_worker_version(self):
        from ccz_randomizer.game_versions import activate_game_version, current_game_version
        from ccz_randomizer.profiles import load_profile
        profile = load_profile()
        # File bytes only exercise advisory hashing, not an invented PE layout.
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, CCZ_GAME_VERSION="2.2"):
            executable = Path(temp) / "Ekd5.exe"
            for content in (b"distribution A", b"distribution B", b""):
                executable.write_bytes(content)
                self.assertEqual(profile.game_version, activate_game_version(executable))
                self.assertEqual(profile.game_version, current_game_version())

    def test_unknown_fingerprint_follows_newly_active_profile_not_static_default(self):
        from ccz_randomizer.game_versions import detect_game_version
        with tempfile.TemporaryDirectory() as temp:
            executable = Path(temp) / "Ekd5.exe"
            executable.write_bytes(b"not in the reference hash list")
            with patch("ccz_randomizer.game_versions.load_profile", return_value=SimpleNamespace(game_version="profile-next")):
                self.assertEqual("profile-next", detect_game_version(executable, manifest={}))

    def test_actual_file_errors_are_not_swallowed_or_misreported_as_version_mismatch(self):
        from ccz_randomizer.game_versions import activate_game_version
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, CCZ_GAME_VERSION="2.2"):
            with self.assertRaises(FileNotFoundError):
                activate_game_version(Path(temp) / "missing.exe")
            with patch.object(Path, "read_bytes", side_effect=PermissionError("access denied")):
                with self.assertRaises(PermissionError):
                    activate_game_version(Path(temp) / "Ekd5.exe")
            self.assertEqual("2.2", os.environ["CCZ_GAME_VERSION"])

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

    def test_night_build_is_a_supported_1104_catalog_variant(self):
        from pathlib import Path
        from ccz_randomizer.fixed_members import fixed_member_indices
        from ccz_randomizer.recruitment_catalog import load_catalog
        version = "2.20-1104-night"
        self.assertEqual(version, normalize_game_version(version))
        self.assertEqual(126, len(load_catalog(version=version)))
        self.assertEqual(18, len(fixed_member_indices(version)))
        self.assertEqual(
            "2.20-1104-night",
            __import__("ccz_randomizer.game_versions", fromlist=["detect_game_version"])
            .detect_game_version(Path(r"E:/game/ccz/曹操传加强版v2.20-1104夜/Ekd5.exe")),
        )
