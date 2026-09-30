from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from ccz_randomizer.runtime.audio_recovery import AudioMuteRecoveryResult


RepairStatus = Literal["repaired", "not_needed", "unable"]


@dataclass(frozen=True)
class ManualRepairResult:
    status: RepairStatus
    message: str
    backup_path: Path | None = None


SISHUI_STAGE_MARKER = "汜水关之战".encode("gbk")
LEGACY_SISHUI_WRONG_PATCHES = (
    (0x668, bytes(10), bytes.fromhex("73017301730173017301")),
    (0xA69, bytes(2), b"\x01\x01"),
    (
        0x1838,
        bytes(12),
        bytes.fromhex("42000000430000006C000000"),
    ),
    (0x1848, bytes(56), b"\x01\x00\x00\x00" * 14),
    (0x4EC8, bytes(4), b"\x01\x00\x00\x00"),
    (0x4F04, b"\x64\x00\x00\x00", b"\x73\x00\x00\x00"),
    (0x4F38, bytes(4), b"\x01\x00\x00\x00"),
    (0xE61E, b"\xC9\x00", b"\x27\x01"),
    (0xE668, bytes(10), bytes.fromhex("26012601260126012601")),
)
LEGACY_SISHUI_SECOND_WRONG_PATCHES = (
    (0x7B18, b"\x01", b"\x00"),
    (0x30035, b"\x50", b"\x64"),
    (0x31722, b"\x08", b"\x00"),
)
UNSAFE_SISHUI_PROGRESS_PATCHES = (
    (0x30003, (b"\x00",), b"\x63"),
    (0x30035, (b"\x50",), b"\x64"),
    (0x30038, (b"\x00", b"\x01"), b"\xC6"),
    (0x31722, (b"\x08",), b"\x00"),
)


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _save_backup_path(save_path: Path) -> Path:
    base = save_path.with_name(f"{save_path.name}.ccz-fast-backup")
    if not base.exists():
        return base
    index = 2
    while True:
        candidate = save_path.with_name(
            f"{save_path.name}.ccz-fast-backup-{index}"
        )
        if not candidate.exists():
            return candidate
        index += 1


def _known_unsafe_repair_results(original: bytes) -> tuple[bytes, ...]:
    results: list[bytes] = []

    def add_result(patches: tuple[tuple[int, bytes], ...]) -> None:
        repaired = bytearray(original)
        for offset, value in patches:
            repaired[offset : offset + len(value)] = value
        candidate = bytes(repaired)
        if candidate != original and candidate not in results:
            results.append(candidate)

    add_result(((0x30038, b"\xC6"),))
    add_result(
        tuple(
            (offset, wrong_value)
            for offset, _original_value, wrong_value
            in LEGACY_SISHUI_SECOND_WRONG_PATCHES
        )
        + ((0x30038, b"\xC6"),)
    )
    add_result(
        tuple(
            (offset, fixed)
            for offset, _broken_values, fixed
            in UNSAFE_SISHUI_PROGRESS_PATCHES
        )
    )
    return tuple(results)


def _restore_exact_unsafe_repair(
    save_path: Path,
    current: bytes,
) -> ManualRepairResult | None:
    backup_pattern = f"{save_path.name}.ccz-fast-backup*"
    backups = sorted(
        (
            path
            for path in save_path.parent.glob(backup_pattern)
            if path.is_file()
        ),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    for source_backup in backups:
        try:
            original = source_backup.read_bytes()
        except OSError:
            continue
        if current not in _known_unsafe_repair_results(original):
            continue

        rollback_backup = _save_backup_path(save_path)
        try:
            _atomic_write(rollback_backup, current)
            _atomic_write(save_path, original)
            written = save_path.read_bytes()
        except OSError as exc:
            return ManualRepairResult(
                "unable",
                f"撤销旧修复失败：{exc}",
                rollback_backup if rollback_backup.exists() else None,
            )
        if written != original:
            return ManualRepairResult(
                "unable",
                "撤销旧修复后的存档校验失败，未继续处理。",
                rollback_backup,
            )
        return ManualRepairResult(
            "repaired",
            "已撤销旧版本中未经完整关卡链验证的修改。"
            f"撤销前文件已备份为 {rollback_backup.name}。",
            rollback_backup,
        )
    return None


def repair_sishui_save(save_path: Path) -> ManualRepairResult:
    save_path = save_path.resolve()
    if not save_path.is_file():
        return ManualRepairResult("unable", "未找到所选存档文件。")
    if save_path.suffix.casefold() != ".e5s":
        return ManualRepairResult("unable", "所选文件不是 E5S 存档。")

    try:
        original = save_path.read_bytes()
    except OSError as exc:
        return ManualRepairResult("unable", f"存档无法读取：{exc}")

    minimum_size = max(
        offset + len(fixed)
        for offset, _broken_values, fixed
        in UNSAFE_SISHUI_PROGRESS_PATCHES
    )
    if len(original) < minimum_size:
        return ManualRepairResult(
            "unable",
            "存档长度不符合当前游戏版本，无法处理。",
        )
    rollback = _restore_exact_unsafe_repair(save_path, original)
    if rollback is not None:
        return rollback

    if SISHUI_STAGE_MARKER not in original:
        return ManualRepairResult(
            "not_needed",
            "该存档不是可识别的汜水关异常存档，未作修改。",
        )
    return ManualRepairResult(
        "unable",
        "当前没有经过后续完整关卡链验证的安全修复规则。"
        "为避免影响后续几十个关卡，本次未修改存档。",
    )


def repair_normal_game_audio(
    game_executable: Path,
    *,
    find_process_ids: Callable[[str], tuple[int, ...]],
    process_executable: Callable[[int], Path | None],
    restore_sessions: Callable[[int], AudioMuteRecoveryResult],
) -> ManualRepairResult:
    expected_path = game_executable.resolve()
    matched_sessions = 0
    restored_sessions = 0
    matched_processes = 0
    errors: list[str] = []

    for pid in find_process_ids(expected_path.name):
        running_path = process_executable(pid)
        if running_path is None:
            continue
        try:
            if running_path.resolve() != expected_path:
                continue
            result = restore_sessions(pid)
        except Exception as exc:
            errors.append(str(exc))
            continue
        matched_processes += 1
        matched_sessions += result.matched_sessions
        restored_sessions += result.restored_sessions

    if restored_sessions:
        return ManualRepairResult(
            "repaired",
            "游戏声音已恢复，请回到游戏确认音量。",
        )
    if matched_sessions:
        return ManualRepairResult(
            "not_needed",
            "正常游戏进程没有被静音，不需要修复。",
        )
    if errors:
        return ManualRepairResult(
            "unable",
            f"声音状态检查失败：{errors[0]}",
        )
    if matched_processes:
        return ManualRepairResult(
            "unable",
            "已找到正常游戏，但尚未建立声音会话。"
            "请进入能播放声音的界面后重试。",
        )
    return ManualRepairResult(
        "unable",
        "未找到正在运行的正常游戏。请先启动 Ekd5.exe，"
        "进入能播放声音的界面后重试。",
    )
