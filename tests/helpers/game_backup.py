from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path


class GameFileBackup:
    """Protect known mutable files for standalone legacy diagnostics.

    The integration runner uses complete copies instead. This is not a general
    backup of every possible game write.
    """

    ROOT_FILES = ("S_00.eex", "CczCustom.ini", "randomizer_settings.json")

    def __init__(self, game_dir: Path):
        self.game_dir = game_dir.resolve()
        self.backup_dir: Path | None = None
        self.original_files: dict[Path, Path] = {}
        self.original_save_names: set[str] = set()
        self.original_optional_files: set[Path] = set()

    def __enter__(self) -> "GameFileBackup":
        self.backup_dir = Path(tempfile.mkdtemp(prefix="ccz-game-test-"))
        save_dir = self.game_dir / "SV"
        self.original_save_names = {
            path.name for path in save_dir.glob("*.E5S") if path.is_file()
        }
        candidates = list(save_dir.glob("*.E5S"))
        optional = [self.game_dir / "RS/S_00.eex", *(self.game_dir / name for name in self.ROOT_FILES)]
        self.original_optional_files = {path for path in optional if path.is_file()}
        candidates.extend(optional)
        try:
            for source in candidates:
                if not source.is_file():
                    continue
                relative = source.relative_to(self.game_dir)
                backup = self.backup_dir / relative
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, backup)
                self.original_files[source] = backup
        except BaseException:
            shutil.rmtree(self.backup_dir, ignore_errors=True)
            raise
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        try:
            self.restore()
        except Exception as error:
            raise OSError(f"测试文件还原失败，备份保留在：{self.backup_dir}") from error
        if self.backup_dir is not None:
            shutil.rmtree(self.backup_dir, ignore_errors=True)

    def restore(self) -> None:
        save_dir = self.game_dir / "SV"
        for current in save_dir.glob("*.E5S"):
            if current.name not in self.original_save_names:
                current.unlink(missing_ok=True)
        for path in [self.game_dir / "RS/S_00.eex", *(self.game_dir / name for name in self.ROOT_FILES)]:
            if path not in self.original_optional_files:
                path.unlink(missing_ok=True)
        for destination, backup in self.original_files.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, destination)
            if hashlib.sha256(destination.read_bytes()).digest() != hashlib.sha256(backup.read_bytes()).digest():
                raise OSError(f"测试文件还原后校验失败：{destination}")

    def hashes(self) -> dict[str, str]:
        return {
            str(path.relative_to(self.game_dir)): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in self.original_files
            if path.is_file()
        }
