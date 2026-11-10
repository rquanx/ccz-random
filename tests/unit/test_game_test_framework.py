import tempfile
import unittest
import os
import shutil
from pathlib import Path
from unittest.mock import patch

from tests.helpers.game_backup import GameFileBackup
from tests.integration_game.manifest import CASES, select_cases


class GameTestFrameworkTests(unittest.TestCase):
    def test_game_cli_defaults_to_current_release_directory(self):
        import run_tests
        with patch.dict(os.environ, {}, clear=True), \
             patch("sys.argv", ["run_tests.py", "game", "--confirm-game"]):
            args = run_tests.parse_args()
        self.assertEqual(Path(r"E:\game\ccz\曹操传加强版v2.20-1104夜"), args.game_dir)

    def test_default_selection_excludes_manual_diagnostics(self):
        selected = select_cases([])

        self.assertTrue(selected)
        self.assertTrue(all(case.default for case in selected))
        self.assertNotIn(
            "scene-wait-benchmark",
            [case.name for case in selected],
        )
        names = {case.name for case in selected}
        self.assertIn("result-save-stage", names)
        self.assertNotIn("seven-result-save-stage", names)
        self.assertNotIn("seven-member-inspection", names)
        self.assertNotIn("silent-real-flow", names)
        self.assertNotIn("randomizer-seven-normal-load", names)
        self.assertNotIn("start-game-loop", names)
        self.assertTrue({"normal-save-readback", "turbo-save-readback", "turbo-fallback-readback"} <= names)

    def test_select_cases_preserves_manifest_order(self):
        selected = select_cases(["repeat-sv020", "dialog-message"])
        self.assertEqual(
            ["dialog-message", "repeat-sv020"],
            [case.name for case in selected],
        )

    def test_unknown_case_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown"):
            select_cases(["unknown"])

    def test_backup_restores_changed_and_removes_created_files(self):
        with tempfile.TemporaryDirectory() as directory:
            game_dir = Path(directory)
            save_dir = game_dir / "SV"
            rs_dir = game_dir / "RS"
            save_dir.mkdir()
            rs_dir.mkdir()
            original = save_dir / "SV020.E5S"
            original.write_bytes(b"original")

            with GameFileBackup(game_dir):
                original.write_bytes(b"changed")
                (save_dir / "SV001.E5S").write_bytes(b"created")
                (rs_dir / "S_00.eex").write_bytes(b"created")

            self.assertEqual(b"original", original.read_bytes())
            self.assertFalse((save_dir / "SV001.E5S").exists())
            self.assertFalse((rs_dir / "S_00.eex").exists())

    def test_backup_restores_existing_s00(self):
        with tempfile.TemporaryDirectory() as directory:
            game_dir = Path(directory)
            (game_dir / "SV").mkdir()
            rs_dir = game_dir / "RS"
            rs_dir.mkdir()
            s00 = rs_dir / "S_00.eex"
            s00.write_bytes(b"original")

            with GameFileBackup(game_dir):
                s00.write_bytes(b"changed")

            self.assertEqual(b"original", s00.read_bytes())

    def test_manifest_case_names_are_unique(self):
        names = [case.name for case in CASES]
        self.assertEqual(len(names), len(set(names)))

    def test_backup_restores_root_script_and_settings_after_case_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "S_00.eex"
            original.write_bytes(b"original root script")
            with self.assertRaisesRegex(ValueError, "case failed"):
                with GameFileBackup(root):
                    original.write_bytes(b"mutated root script")
                    (root / "CczCustom.ini").write_bytes(b"new settings")
                    raise ValueError("case failed")
            self.assertEqual(b"original root script", original.read_bytes())
            self.assertFalse((root / "CczCustom.ini").exists())

    def test_failed_restore_retains_backup_and_explains_recovery_location(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "CczCustom.ini"
            source.write_bytes(b"original settings")
            backup = GameFileBackup(root)
            backup.__enter__()
            self.addCleanup(shutil.rmtree, backup.backup_dir, ignore_errors=True)
            source.write_bytes(b"mutated")
            with patch("tests.helpers.game_backup.shutil.copy2", side_effect=PermissionError("locked")):
                with self.assertRaisesRegex(OSError, "备份保留在") as failure:
                    backup.__exit__(None, None, None)
            self.assertIn(str(backup.backup_dir), str(failure.exception))
            self.assertEqual(b"original settings", (backup.backup_dir / "CczCustom.ini").read_bytes())
            backup.restore()
            self.assertEqual(b"original settings", source.read_bytes())


if __name__ == "__main__":
    unittest.main()
