from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ccz_randomizer.app import (
    JOB_OFFSET,
    JOB_POSITIONS_R1,
    R0_MEMORY_SIZE,
    source_save_job_ids,
    validate_start_environment,
)


class StartEnvironmentTests(unittest.TestCase):
    def make_game_directory(self, root: Path) -> tuple[Path, Path]:
        game = root / "Ekd5.exe"
        game.write_bytes(b"game")
        save_dir = root / "SV"
        save_dir.mkdir()
        source_save = save_dir / "SV020.E5S"
        source_save.write_bytes(bytes(R0_MEMORY_SIZE))
        return game, source_save

    def runtime_patches(self, root: Path):
        native = root / "native"
        native.mkdir()
        (native / "ccz_injector.exe").write_bytes(b"injector")
        (native / "ccz_control.dll").write_bytes(b"dll")
        bundle = root / "original"
        bundle.mkdir()
        return (
            patch("ccz_randomizer.app.find_process_id", return_value=None),
            patch("ccz_randomizer.app.native_dir", return_value=native),
            patch("ccz_randomizer.app.bundle_root", return_value=bundle),
        )

    def test_valid_environment_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game, source_save = self.make_game_directory(root)
            process_patch, native_patch, bundle_patch = self.runtime_patches(root)
            with process_patch, native_patch, bundle_patch:
                self.assertEqual(
                    source_save,
                    validate_start_environment(game),
                )

    def test_missing_source_save_has_friendly_message(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "Ekd5.exe"
            game.write_bytes(b"game")
            (root / "SV").mkdir()
            process_patch, native_patch, bundle_patch = self.runtime_patches(root)
            with process_patch, native_patch, bundle_patch:
                with self.assertRaisesRegex(RuntimeError, "未找到第20栏存档"):
                    validate_start_environment(game)

    def test_randomized_source_save_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game, source_save = self.make_game_directory(root)
            data = bytearray(source_save.read_bytes())
            struct.pack_into(
                "<I",
                data,
                JOB_OFFSET + JOB_POSITIONS_R1[0] * 4,
                3,
            )
            source_save.write_bytes(data)
            process_patch, native_patch, bundle_patch = self.runtime_patches(root)
            with process_patch, native_patch, bundle_patch:
                with self.assertRaisesRegex(RuntimeError, "已经触发过随机"):
                    validate_start_environment(game)

    def test_incomplete_source_save_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_save = Path(directory) / "SV020.E5S"
            source_save.write_bytes(b"short")
            with self.assertRaisesRegex(RuntimeError, "文件不完整"):
                source_save_job_ids(source_save)


if __name__ == "__main__":
    unittest.main()
