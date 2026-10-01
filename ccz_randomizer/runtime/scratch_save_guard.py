from __future__ import annotations

import os
import tempfile
from pathlib import Path


SCRATCH_BACKUP_NAME = ".SV016.E5S.ccz-fast.backup"
SCRATCH_STATE_NAME = ".SV016.E5S.ccz-fast.state"


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


def publish_candidate_save(target: Path, content: bytes) -> None:
    """Publish an unchanged game-created save to a result slot."""
    if not content:
        raise ValueError("候选存档内容为空，不能发布")
    _atomic_write(target, content)
    if target.read_bytes() != content:
        raise RuntimeError(f"{target.name} 发布后内容与候选存档不一致")


class ScratchSaveGuard:
    """Protect the temporary No. 16 save across forced process exits."""

    def __init__(self, game_dir: Path) -> None:
        self.target = game_dir / "SV" / "SV016.E5S"
        self.backup_path = self.target.parent / SCRATCH_BACKUP_NAME
        self.state_path = self.target.parent / SCRATCH_STATE_NAME
        self._prepared = False
        self._active = False

    def prepare(self) -> bool:
        recovered = self._restore_transaction()
        if not self.state_path.exists():
            self.backup_path.unlink(missing_ok=True)
        self._prepared = True
        return recovered

    def begin(self) -> None:
        if not self._prepared:
            raise RuntimeError("临时存档保护器尚未准备")
        if self._active or self.state_path.exists():
            self._restore_transaction()

        if self.target.is_file():
            _atomic_write(self.backup_path, self.target.read_bytes())
            state = b"present"
        else:
            self.backup_path.unlink(missing_ok=True)
            state = b"missing"
        _atomic_write(self.state_path, state)
        self._active = True

    def restore(self) -> bool:
        if not self._prepared and not self.state_path.is_file():
            return False
        try:
            return self._restore_transaction()
        finally:
            self._active = False

    def _restore_transaction(self) -> bool:
        if not self.state_path.is_file():
            return False

        state = self.state_path.read_text(encoding="ascii").strip()
        if state == "present":
            if not self.backup_path.is_file():
                raise RuntimeError("第 16 号存档恢复事务缺少原存档备份")
            _atomic_write(self.target, self.backup_path.read_bytes())
        elif state == "missing":
            self.target.unlink(missing_ok=True)
        else:
            raise RuntimeError("第 16 号存档恢复事务状态无效")

        self.state_path.unlink(missing_ok=True)
        self.backup_path.unlink(missing_ok=True)
        return True

    @property
    def active(self) -> bool:
        return self._active
