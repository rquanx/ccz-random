from __future__ import annotations

import ctypes
import csv
import datetime as dt
import io
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from tests.helpers.game_backup import GameFileBackup
from tests.integration_game.manifest import GameCase


class Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def output_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def game_process_ids() -> list[int]:
    completed = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq Ekd5.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        encoding="mbcs",
        errors="replace",
        check=False,
    )
    process_ids = []
    for row in csv.reader(io.StringIO(completed.stdout)):
        if len(row) >= 2 and row[0].lower() == "ekd5.exe":
            try:
                process_ids.append(int(row[1]))
            except ValueError:
                continue
    return process_ids


def terminate_processes(process_ids: list[int]) -> None:
    for process_id in process_ids:
        subprocess.run(
            ["taskkill", "/PID", str(process_id), "/T", "/F"],
            capture_output=True,
            check=False,
        )


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
    roots_to_watch = [
        repo_root,
        game_dir / "ccz_fast_logs",
        game_dir / "randResult",
    ]
    suite_summary = {
        "startedAt": dt.datetime.now().isoformat(timespec="seconds"),
        "gameDir": str(game_dir),
        "cases": [],
    }
    failures = 0

    with GameFileBackup(game_dir) as backup:
        suite_summary["originalFileHashes"] = backup.hashes()
        for case in cases:
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
                    "CCZ_GAME_DIR": str(game_dir),
                    "CCZ_GAME_EXE": str(game_dir / "Ekd5.exe"),
                    "CCZ_GAME_TEST_ARTIFACT_DIR": str(case_dir),
                    "CCZ_STATE_BASE_DIR": str(case_dir),
                }
            )
            script = (
                repo_root
                / "tests"
                / "integration_game"
                / "cases"
                / case.module
            )
            timed_out = False
            try:
                completed = subprocess.run(
                    [sys.executable, str(script)],
                    cwd=repo_root,
                    env=environment,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout_seconds,
                    check=False,
                )
                stdout = completed.stdout
                stderr = completed.stderr
                return_code = completed.returncode
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                stdout = output_text(exc.stdout)
                stderr = output_text(exc.stderr) + (
                    f"\n测试超过 {timeout_seconds} 秒，已终止。"
                )
                return_code = 124
            lingering_processes = game_process_ids()
            if lingering_processes:
                terminate_processes(lingering_processes)
                stderr += (
                    "\n测试结束后游戏进程仍在运行，测试框架已将其关闭："
                    + ",".join(str(pid) for pid in lingering_processes)
                )
                if return_code == 0:
                    return_code = 125
            backup.restore()
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
