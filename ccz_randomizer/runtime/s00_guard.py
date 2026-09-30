from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class S00RepairResult:
    active_script_repaired: bool
    stale_helper_replaced: bool
    transaction_recovered: bool = False


@dataclass(frozen=True)
class ManualS00RestoreResult:
    restored: bool
    backup_path: Path | None = None


OVERRIDE_BACKUP_NAME = ".S_00.eex.ccz-fast.backup"
OVERRIDE_STATE_NAME = ".S_00.eex.ccz-fast.state"


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


def _restore_override_transaction(
    game_dir: Path,
    original: bytes,
    helper: bytes,
) -> bool:
    override_dir = game_dir / "RS"
    override_target = override_dir / "S_00.eex"
    backup_path = override_dir / OVERRIDE_BACKUP_NAME
    state_path = override_dir / OVERRIDE_STATE_NAME
    if not state_path.is_file():
        return False

    state = state_path.read_text(encoding="ascii").strip()
    if state == "present":
        if not backup_path.is_file():
            if (
                override_target.is_file()
                and override_target.read_bytes() != helper
            ):
                state_path.unlink(missing_ok=True)
                return True
            raise RuntimeError("S_00 恢复事务缺少原覆盖文件备份")
        _atomic_write(override_target, backup_path.read_bytes())
    elif state == "missing":
        # Compatibility with transactions created by older builds, which
        # incorrectly treated a missing RS script as the normal state.
        if not override_target.is_file() or override_target.read_bytes() == helper:
            _atomic_write(override_target, original)
    else:
        raise RuntimeError("S_00 恢复事务状态无效")

    state_path.unlink(missing_ok=True)
    backup_path.unlink(missing_ok=True)
    return True


def repair_game_s00(
    game_dir: Path,
    original_script: Path,
    helper_script: Path,
) -> S00RepairResult:
    original = original_script.read_bytes()
    helper = helper_script.read_bytes()
    override_target = game_dir / "RS" / "S_00.eex"
    stale_helper_replaced = (
        override_target.is_file() and override_target.read_bytes() == helper
    )
    transaction_recovered = _restore_override_transaction(
        game_dir,
        original,
        helper,
    )

    active_script_repaired = (
        not override_target.is_file()
        or override_target.read_bytes() == helper
    )
    if active_script_repaired:
        _atomic_write(override_target, original)

    return S00RepairResult(
        active_script_repaired=active_script_repaired,
        stale_helper_replaced=stale_helper_replaced,
        transaction_recovered=transaction_recovered,
    )


def restore_bundled_original_s00(
    game_dir: Path,
    original_script: Path,
    helper_script: Path,
) -> ManualS00RestoreResult:
    original = original_script.read_bytes()
    helper = helper_script.read_bytes()
    override_dir = game_dir / "RS"
    override_target = override_dir / "S_00.eex"
    override_dir.mkdir(parents=True, exist_ok=True)

    transaction_recovered = _restore_override_transaction(
        game_dir,
        original,
        helper,
    )
    current = (
        override_target.read_bytes()
        if override_target.is_file()
        else None
    )
    if current == original:
        return ManualS00RestoreResult(transaction_recovered)

    backup_path = None
    if current is not None and current != helper:
        backup_path = override_dir / ".S_00.eex.ccz-fast-manual-backup"
        suffix = 2
        while backup_path.exists():
            backup_path = override_dir / (
                f".S_00.eex.ccz-fast-manual-backup-{suffix}"
            )
            suffix += 1
        _atomic_write(backup_path, current)

    _atomic_write(override_target, original)
    if override_target.read_bytes() != original:
        raise RuntimeError("内置正常 S_00.eex 写入校验失败")
    return ManualS00RestoreResult(True, backup_path)


class S00ScriptGuard:
    def __init__(
        self,
        game_dir: Path,
        original_script: Path,
        helper_script: Path,
    ) -> None:
        self.game_dir = game_dir
        self.original_script = original_script
        self.helper_script = helper_script
        self.override_target = game_dir / "RS" / "S_00.eex"
        self.override_backup_path = (
            self.override_target.parent / OVERRIDE_BACKUP_NAME
        )
        self.override_state_path = (
            self.override_target.parent / OVERRIDE_STATE_NAME
        )
        self._override_existed = False
        self._override_backup: bytes | None = None
        self._prepared = False
        self._installed = False

    def prepare(self) -> S00RepairResult:
        result = repair_game_s00(
            self.game_dir,
            self.original_script,
            self.helper_script,
        )
        self._override_existed = self.override_target.is_file()
        self._override_backup = (
            self.override_target.read_bytes()
            if self._override_existed
            else None
        )
        self._prepared = True
        return result

    def install(self) -> None:
        if not self._prepared:
            raise RuntimeError("S_00 保护器尚未准备")
        if self._override_existed:
            assert self._override_backup is not None
            _atomic_write(self.override_backup_path, self._override_backup)
            state = b"present"
        else:
            self.override_backup_path.unlink(missing_ok=True)
            state = b"missing"
        _atomic_write(self.override_state_path, state)
        _atomic_write(self.override_target, self.helper_script.read_bytes())
        self._installed = True

    def restore(self) -> None:
        if not self._prepared:
            return
        try:
            _restore_override_transaction(
                self.game_dir,
                self.original_script.read_bytes(),
                self.helper_script.read_bytes(),
            )
            repair_game_s00(
                self.game_dir,
                self.original_script,
                self.helper_script,
            )
        finally:
            self._installed = False

    @property
    def installed(self) -> bool:
        return self._installed
