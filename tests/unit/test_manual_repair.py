from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ccz_randomizer.runtime.audio_recovery import AudioMuteRecoveryResult
from ccz_randomizer.runtime.manual_repair import (
    UNSAFE_SISHUI_PROGRESS_PATCHES,
    repair_normal_game_audio,
    repair_sishui_save,
)


def build_sishui_save() -> bytes:
    data = bytearray(263760)
    marker = "汜水关之战".encode("gbk")
    data[-64 : -64 + len(marker)] = marker
    for offset, broken_values, _fixed in UNSAFE_SISHUI_PROGRESS_PATCHES:
        value = broken_values[-1]
        data[offset : offset + len(value)] = value
    return bytes(data)


class SishuiSaveRepairTests(unittest.TestCase):
    def test_sishui_save_is_not_modified_without_verified_rule(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            save_path = Path(temporary) / "SV002.E5S"
            original = build_sishui_save()
            save_path.write_bytes(original)

            result = repair_sishui_save(save_path)

            self.assertEqual("unable", result.status)
            self.assertIn("完整关卡链", result.message)
            self.assertEqual(original, save_path.read_bytes())

    def test_exact_unsafe_repair_is_restored_from_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            save_path = Path(temporary) / "SV002.E5S"
            original = build_sishui_save()
            unsafe = bytearray(original)
            for offset, _broken_values, fixed in (
                UNSAFE_SISHUI_PROGRESS_PATCHES
            ):
                unsafe[offset : offset + len(fixed)] = fixed
            save_path.write_bytes(unsafe)
            source_backup = save_path.with_name(
                f"{save_path.name}.ccz-fast-backup"
            )
            source_backup.write_bytes(original)

            result = repair_sishui_save(save_path)

            self.assertEqual("repaired", result.status)
            self.assertEqual(original, save_path.read_bytes())
            self.assertEqual(
                bytes(unsafe),
                result.backup_path.read_bytes(),
            )

    def test_non_sishui_save_is_not_modified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            save_path = Path(temporary) / "SV020.E5S"
            original = bytearray(build_sishui_save())
            marker = "汜水关之战".encode("gbk")
            original[-64 : -64 + len(marker)] = bytes(len(marker))
            save_path.write_bytes(original)

            result = repair_sishui_save(save_path)

            self.assertEqual("not_needed", result.status)
            self.assertEqual(bytes(original), save_path.read_bytes())

    def test_played_save_is_not_rolled_back_from_old_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            save_path = Path(temporary) / "SV002.E5S"
            original = bytearray(build_sishui_save())
            unsafe = bytearray(original)
            for offset, _broken_values, fixed in (
                UNSAFE_SISHUI_PROGRESS_PATCHES
            ):
                unsafe[offset : offset + len(fixed)] = fixed
            unsafe[0x120] = 0x55
            save_path.write_bytes(unsafe)
            save_path.with_name(
                f"{save_path.name}.ccz-fast-backup"
            ).write_bytes(original)

            result = repair_sishui_save(save_path)

            self.assertEqual("unable", result.status)
            self.assertEqual(bytes(unsafe), save_path.read_bytes())


class AudioRepairTests(unittest.TestCase):
    def test_audio_repair_only_targets_exact_game_path(self) -> None:
        game = Path(r"C:\game\Ekd5.exe")
        restored_pids: list[int] = []

        result = repair_normal_game_audio(
            game,
            find_process_ids=lambda _name: (101, 202),
            process_executable=lambda pid: (
                Path(r"D:\other\Ekd5.exe") if pid == 101 else game
            ),
            restore_sessions=lambda pid: (
                restored_pids.append(pid)
                or AudioMuteRecoveryResult(1, 1)
            ),
        )

        self.assertEqual("repaired", result.status)
        self.assertEqual([202], restored_pids)

    def test_audio_repair_reports_missing_running_game(self) -> None:
        result = repair_normal_game_audio(
            Path(r"C:\game\Ekd5.exe"),
            find_process_ids=lambda _name: (),
            process_executable=lambda _pid: None,
            restore_sessions=lambda _pid: AudioMuteRecoveryResult(),
        )

        self.assertEqual("unable", result.status)
        self.assertIn("未找到", result.message)


if __name__ == "__main__":
    unittest.main()
