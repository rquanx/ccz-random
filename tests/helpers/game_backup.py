from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path


class GameFileBackup:
    """Restore save files and S_00.eex after a real-game test suite."""

    def __init__(self, game_dir: Path):
        self.game_dir = game_dir.resolve()
        self.backup_dir: Path | None = None
        self.original_files: dict[Path, Path] = {}
        self.original_save_names: set[str] = set()
        self.original_s00_exists = False

    def __enter__(self) -> "GameFileBackup":
        self.backup_dir = Path(tempfile.mkdtemp(prefix="ccz-game-test-"))
        save_dir = self.game_dir / "SV"
        self.original_save_names = {
            path.name for path in save_dir.glob("*.E5S") if path.is_file()
        }
        candidates = list(save_dir.glob("*.E5S"))
        s00_path = self.game_dir / "RS" / "S_00.eex"
        self.original_s00_exists = s00_path.is_file()
        candidates.append(s00_path)
        for source in candidates:
            if not source.is_file():
                continue
            relative = source.relative_to(self.game_dir)
            backup = self.backup_dir / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, backup)
            self.original_files[source] = backup
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.restore()
        if self.backup_dir is not None:
            shutil.rmtree(self.backup_dir, ignore_errors=True)

    def restore(self) -> None:
        save_dir = self.game_dir / "SV"
        for current in save_dir.glob("*.E5S"):
            if current.name not in self.original_save_names:
                current.unlink(missing_ok=True)
        s00_path = self.game_dir / "RS" / "S_00.eex"
        if not self.original_s00_exists:
            s00_path.unlink(missing_ok=True)
        for destination, backup in self.original_files.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, destination)

    def hashes(self) -> dict[str, str]:
        return {
            str(path.relative_to(self.game_dir)): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in self.original_files
            if path.is_file()
        }
