"""Explicit cleanup of owned diagnostics and abandoned sandbox files."""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import psutil

from ccz_randomizer.runtime.log_retention import is_managed_log_file

CATEGORIES = {"logs": "运行日志", "screenshots": "故障截图", "sandboxes": "残留沙箱"}
_SESSION = re.compile(r"^(\d+)-\d+$")


@dataclass
class StorageUsage:
    total: int = 0
    cleanable: int = 0
    files: int = 0


def _linked(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _files(root: Path):
    if not root.is_dir() or _linked(root):
        return
    for directory, dirs, files in os.walk(root, followlinks=False):
        base = Path(directory)
        dirs[:] = [name for name in dirs if not _linked(base / name)]
        for name in files:
            path = base / name
            if not _linked(path):
                yield path


def _candidates(base: Path):
    logs = base / "ccz_fast_logs"
    if logs.is_dir() and not _linked(logs):
        for path in logs.iterdir():
            if path.is_file() and not _linked(path) and is_managed_log_file(path):
                # Keep recent diagnostics, including logs of other tool instances.
                yield ("screenshots" if path.suffix.lower() == ".png" else "logs",
                       path, time.time() - path.stat().st_mtime >= 86400)
    sandboxes = base / "ccz_fast_data" / "sandboxes"
    if sandboxes.is_dir() and not _linked(sandboxes.parent) and not _linked(sandboxes):
        for session in sandboxes.iterdir():
            if not session.is_dir() or _linked(session):
                continue
            match = _SESSION.fullmatch(session.name)
            stale = bool(match) and not psutil.pid_exists(int(match.group(1)))
            for path in _files(session):
                yield "sandboxes", path, stale


def scan_storage(base: Path) -> dict[str, StorageUsage]:
    usage = {key: StorageUsage() for key in CATEGORIES}
    for category, path, eligible in _candidates(base):
        try:
            stat = path.stat()
        except OSError:
            continue
        # Sandbox resources may be hard links to the original game files.
        size = stat.st_size if stat.st_nlink == 1 else 0
        usage[category].total += size
        if eligible:
            usage[category].cleanable += size
            usage[category].files += 1
    return usage


def clean_storage(base: Path, categories: set[str]) -> tuple[int, int]:
    if not categories <= CATEGORIES.keys():
        raise ValueError("未知清理分类")
    removed = failed = 0
    # Recheck eligibility at cleanup time instead of trusting a stale UI scan.
    for category, path, eligible in _candidates(base):
        if category not in categories or not eligible:
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            failed += 1
    return removed, failed
