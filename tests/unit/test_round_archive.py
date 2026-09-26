from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ccz_randomizer.workflow.round_archive import (
    MIN_LOOP_FREE_SPACE,
    ensure_loop_disk_space,
    finalize_round,
    prepare_round_workspace,
    resolve_loop_run_stamp,
)


class RoundArchiveTests(unittest.TestCase):
    def test_complete_round_archives_fifteen_saves(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            save_dir = base / "SV"
            save_dir.mkdir()
            for slot in range(1, 16):
                (save_dir / f"SV{slot:03}.E5S").write_bytes(
                    f"save-{slot}".encode()
                )
            workspace = prepare_round_workspace(
                base,
                "2026-09-26 15.30.00",
                1,
            )
            workspace.grid_file.write_bytes(b"grid")
            for slot in range(1, 16):
                (workspace.panels_dir / f"save{slot}.png").write_bytes(
                    f"panel-{slot}".encode()
                )
            target = finalize_round(
                workspace,
                save_dir=save_dir,
                completed_slots=range(1, 16),
                metadata={"mode": "seven"},
                complete=True,
            )
            self.assertEqual(workspace.final_dir, target)
            self.assertTrue((target / "saves" / "SV015.E5S").is_file())
            info = json.loads(
                (target / "round-info.json").read_text(encoding="utf-8")
            )
            self.assertEqual("complete", info["status"])
            self.assertEqual(list(range(1, 16)), info["completedSlots"])

    def test_complete_round_preserves_saves_when_images_are_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            save_dir = base / "SV"
            save_dir.mkdir()
            for slot in range(1, 16):
                (save_dir / f"SV{slot:03}.E5S").write_bytes(b"save")
            workspace = prepare_round_workspace(
                base,
                "2026-09-26 15.30.00",
                1,
            )
            target = finalize_round(
                workspace,
                save_dir=save_dir,
                completed_slots=range(1, 16),
                metadata={},
                complete=True,
            )
            info = json.loads(
                (target / "round-info.json").read_text(encoding="utf-8")
            )
            self.assertTrue((target / "saves" / "SV015.E5S").is_file())
            self.assertFalse(info["resultArtifacts"]["gridGenerated"])
            self.assertEqual(
                list(range(1, 16)),
                info["resultArtifacts"]["missingPanels"],
            )

    def test_incomplete_round_preserves_only_completed_saves(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            save_dir = base / "SV"
            save_dir.mkdir()
            for slot in (1, 2):
                (save_dir / f"SV{slot:03}.E5S").write_bytes(b"save")
            workspace = prepare_round_workspace(
                base,
                "2026-09-26 15.30.00",
                2,
            )
            target = finalize_round(
                workspace,
                save_dir=save_dir,
                completed_slots=(1, 2),
                metadata={},
                complete=False,
            )
            self.assertEqual(workspace.incomplete_dir, target)
            self.assertTrue((target / "saves" / "SV002.E5S").is_file())
            self.assertFalse((target / "saves" / "SV003.E5S").exists())

    def test_empty_incomplete_round_removes_staging_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = prepare_round_workspace(
                Path(directory),
                "2026-09-26 15.30.00",
                1,
            )
            target = finalize_round(
                workspace,
                save_dir=Path(directory) / "SV",
                completed_slots=(),
                metadata={},
                complete=False,
            )
            self.assertIsNone(target)
            self.assertFalse(workspace.staging_dir.exists())

    def test_duplicate_run_stamp_gets_suffix(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            first = prepare_round_workspace(
                base,
                "2026-09-26 15.30.00",
                1,
            )
            first.staging_dir.rename(first.final_dir)
            self.assertEqual(
                "2026-09-26 15.30.00 (2)",
                resolve_loop_run_stamp(base, "2026-09-26 15.30.00"),
            )

    def test_disk_space_check_rejects_less_than_500_mb(self):
        usage = mock.Mock(free=MIN_LOOP_FREE_SPACE - 1)
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch(
                "ccz_randomizer.workflow.round_archive.shutil.disk_usage",
                return_value=usage,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "剩余空间不足500MB",
                ):
                    ensure_loop_disk_space(Path(directory))


if __name__ == "__main__":
    unittest.main()
