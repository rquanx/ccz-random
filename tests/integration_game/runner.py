from __future__ import annotations

import ctypes
import datetime as dt
import json
import os
import shutil
import time
from pathlib import Path

from tests.helpers.game_copy import isolated_game_copy
from tests.helpers.case_process import run_case_process
from tests.integration_game.manifest import GameCase


class Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def desktop_state() -> dict[str, object]:
    point = Point()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
    foreground = int(ctypes.windll.user32.GetForegroundWindow())
    return {
        "foregroundWindow": foreground,
        "cursor": {"x": point.x, "y": point.y},
    }


def snapshot_files(paths: list[Path]) -> dict[Path, tuple[int, int]]:
    result: dict[Path, tuple[int, int]] = {}
    for root in paths:
        if root.is_dir():
            for current_root, directories, files in os.walk(root):
                directories[:] = [
                    name
                    for name in directories
                    if name
                    not in {
                        ".git",
                        "__pycache__",
                        "artifacts",
                        "build",
                        "dist",
                        "release",
                        "vendor",
                    }
                    and not name.startswith(".venv")
                ]
                current = Path(current_root)
                for name in files:
                    path = (current / name).resolve()
                    stat = path.stat()
                    result[path] = (stat.st_mtime_ns, stat.st_size)
    return result


def copy_new_artifacts(
    before: dict[Path, tuple[int, int]],
    roots: list[Path],
    destination: Path,
) -> list[str]:
    copied = []
    after = snapshot_files(roots)
    changed = [
        path
        for path, signature in after.items()
        if before.get(path) != signature
    ]
    for source in sorted(changed):
        if source.suffix.lower() not in {
            ".bin",
            ".bmp",
            ".json",
            ".jsonl",
            ".log",
            ".png",
            ".txt",
        }:
            continue
        target = destination / "captured" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target = target.with_name(f"{source.parent.name}-{source.name}")
        shutil.copy2(source, target)
        copied.append(str(target.relative_to(destination)))
    return copied


def run_game_cases(
    *,
    repo_root: Path,
    game_dir: Path,
    cases: tuple[GameCase, ...],
    timeout_seconds: int,
) -> int:
    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H.%M.%S")
    suite_dir = repo_root / "artifacts" / "game-tests" / timestamp
    suite_dir.mkdir(parents=True, exist_ok=False)
    suite_summary = {
        "startedAt": dt.datetime.now().isoformat(timespec="seconds"),
        "gameDir": str(game_dir),
        "cases": [],
    }
    failures = 0

    for case in cases:
        with isolated_game_copy(game_dir) as case_game_dir:
            roots_to_watch = [repo_root, case_game_dir]
            case_dir = suite_dir / case.name
            case_dir.mkdir()
            before_files = snapshot_files(roots_to_watch)
            before_state = desktop_state()
            started_at = dt.datetime.now().isoformat(timespec="seconds")
            started = time.perf_counter()
            environment = os.environ.copy()
            environment.update(
                {
                    "PYTHONPATH": str(repo_root),
                    "CCZ_GAME_DIR": str(case_game_dir),
                    "CCZ_GAME_EXE": str(case_game_dir / "Ekd5.exe"),
                    "CCZ_GAME_TEST_ARTIFACT_DIR": str(case_dir),
                    "CCZ_STATE_BASE_DIR": str(case_dir / "state"),
                }
            )
            script = (
                repo_root
                / "tests"
                / "integration_game"
                / "cases"
                / case.module
            )
            completed, timed_out, lingering_processes = run_case_process(
                script, repo_root, environment, timeout_seconds,
            )
            stdout, stderr, return_code = completed.stdout, completed.stderr, completed.returncode
            elapsed = round(time.perf_counter() - started, 3)
            (case_dir / "stdout.log").write_text(
                stdout,
                encoding="utf-8",
            )
            (case_dir / "stderr.log").write_text(
                stderr,
                encoding="utf-8",
            )
            metadata = {
                "name": case.name,
                "isolatedGameDir": str(case_game_dir),
                "description": case.description,
                "script": str(script.relative_to(repo_root)),
                "startedAt": started_at,
                "finishedAt": dt.datetime.now().isoformat(timespec="seconds"),
                "durationSeconds": elapsed,
                "returnCode": return_code,
                "timedOut": timed_out,
                "lingeringGamePids": lingering_processes,
                "desktopBefore": before_state,
                "desktopAfter": desktop_state(),
                "capturedFiles": copy_new_artifacts(
                    before_files,
                    roots_to_watch,
                    case_dir,
                ),
            }
            (case_dir / "case.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            suite_summary["cases"].append(metadata)
            status = "通过" if return_code == 0 else "失败"
            print(f"[{status}] {case.name} ({elapsed:.1f}s)")
            if return_code != 0:
                failures += 1

    suite_summary["finishedAt"] = dt.datetime.now().isoformat(timespec="seconds")
    suite_summary["failureCount"] = failures
    (suite_dir / "suite.json").write_text(
        json.dumps(suite_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"游戏测试记录：{suite_dir}")
    return 1 if failures else 0
