"""Explicit cleanup of owned diagnostics and abandoned sandbox files."""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import psutil

from ccz_randomizer.runtime.log_retention import is_managed_log_file

CATEGORIES = {
    "logs": "运行日志",
    "screenshots": "故障截图",
    "sandboxes": "残留沙箱",
    "results": "随机结果",
    "history": "历史记录（含存档副本）",
    "statistics": "随机统计数据",
    "searches": "最近搜索记录",
}
_SESSION = re.compile(r"^(\d+)-\d+$")
_DATABASE = re.compile(r"^(history(?:-v\d+)?|statistics)\.sqlite3(?:-wal|-shm)?$")
_SEARCHES = {"recruitment_searches.json", "equipment_searches.json"}


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

    # Result images and archived round files are owned by the randomizer and
    # can be removed explicitly by the user.  Keep the scan recursive so
    # loop-round folders and per-round panel images are included as well.
    results = base / "randResult"
    if results.is_dir() and not _linked(results):
        for path in _files(results):
            yield "results", path, True

    # Only explicitly owned names are eligible; never sweep the data directory.
    history_root = base / "ccz_fast_data"
    if history_root.is_dir() and not _linked(history_root):
        for path in history_root.iterdir():
            if path.name == "sandboxes" or path.is_dir() or _linked(path):
                continue
            if path.is_file():
                match = _DATABASE.fullmatch(path.name)
                if match:
                    yield ("statistics" if match[1] == "statistics" else "history"), path, True
                elif path.name in _SEARCHES:
                    yield "searches", path, True


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
    databases = set()
    # Recheck eligibility at cleanup time instead of trusting a stale UI scan.
    for category, path, eligible in _candidates(base):
        if category not in categories or not eligible:
            continue
        if category in {"history", "statistics"}:
            # SQLite sidecars belong to the database, never delete them separately.
            database = path.with_name(re.sub(r"-(wal|shm)$", "", path.name))
            if database in databases:
                continue
            databases.add(database)
            try:
                from ccz_randomizer.runtime.storage_databases import clear_database
                clear_database(database, category)
                removed += 1
            except (OSError, ValueError):
                failed += 1
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            failed += 1
    return removed, failed
