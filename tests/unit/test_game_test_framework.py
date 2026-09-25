import tempfile
import unittest
from pathlib import Path

from tests.helpers.game_backup import GameFileBackup
from tests.integration_game.manifest import CASES, select_cases


class GameTestFrameworkTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
