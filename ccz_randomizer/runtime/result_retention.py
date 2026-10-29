from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


DEFAULT_RESULT_LIMIT_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_RESULT_TARGET_BYTES = 1536 * 1024 * 1024


@dataclass(frozen=True)
class ResultCleanup:
    removed_files: int
    removed_bytes: int
    remaining_bytes: int


def result_limits() -> tuple[int, int]:
    """Read optional byte limits without allowing an accidental zero limit."""
    try:
        limit = int(os.environ.get("CCZ_RESULT_LIMIT_BYTES", DEFAULT_RESULT_LIMIT_BYTES))
        target = int(os.environ.get("CCZ_RESULT_TARGET_BYTES", DEFAULT_RESULT_TARGET_BYTES))
    except ValueError:
        return DEFAULT_RESULT_LIMIT_BYTES, DEFAULT_RESULT_TARGET_BYTES
    if limit <= 0 or target < 0 or target > limit:
        return DEFAULT_RESULT_LIMIT_BYTES, DEFAULT_RESULT_TARGET_BYTES
    return limit, target


def _managed_entries(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    entries: list[Path] = []
    # Group each run directory independently so retaining a recent run does
    # not accidentally delete the whole panels/loop tree.
    for child in root.iterdir():
        if child.is_dir() and child.name in {"panels", "loop", "循环随机"}:
            entries.extend(item for item in child.iterdir())
        else:
            entries.append(child)
    return entries


def cleanup_result_directory(
    root: Path,
    *,
    protected: tuple[Path, ...] = (),
    limit_bytes: int | None = None,
    target_bytes: int | None = None,
) -> ResultCleanup:
    limit, target = result_limits()
    limit = limit if limit_bytes is None else limit_bytes
    target = target if target_bytes is None else target_bytes
    if limit <= 0 or target < 0 or target > limit:
        raise ValueError("invalid result size limits")
    root = root.resolve()
    protected_paths = tuple(path.resolve() for path in protected)
    entries: list[tuple[float, Path, int]] = []
    total = 0
    for path in _managed_entries(root):
        try:
            if any(path == item or item in path.parents for item in protected_paths):
                continue
            size = sum(item.stat().st_size for item in path.rglob("*") if item.is_file()) if path.is_dir() else path.stat().st_size
            mtime = path.stat().st_mtime
        except OSError:
            continue
        entries.append((mtime, path, size))
        total += size
    removed_files = removed_bytes = 0
    for _mtime, path, size in sorted(entries):
        if total <= limit:
            break
        try:
            if path.is_dir():
                file_count = sum(1 for item in path.rglob("*") if item.is_file())
                shutil.rmtree(path)
                removed_files += file_count
            else:
                path.unlink()
                removed_files += 1
            removed_bytes += size
            total -= size
        except OSError:
            continue
    return ResultCleanup(removed_files, removed_bytes, total)
