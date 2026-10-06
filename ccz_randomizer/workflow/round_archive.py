from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


MIN_LOOP_FREE_SPACE = 500 * 1024 * 1024


@dataclass(frozen=True)
class RoundWorkspace:
    run_stamp: str
    round_number: int
    round_name: str
    root: Path
    staging_dir: Path
    final_dir: Path
    incomplete_dir: Path
    panels_dir: Path
    grid_file: Path


def loop_result_root(base_dir: Path) -> Path:
    return base_dir / "randResult" / "循环随机"


def resolve_loop_run_stamp(base_dir: Path, requested_stamp: str) -> str:
    root = loop_result_root(base_dir)
    root.mkdir(parents=True, exist_ok=True)
    candidate = requested_stamp
    duplicate = 2
    while any(root.glob(f"{candidate}-第*轮*")):
        candidate = f"{requested_stamp} ({duplicate})"
        duplicate += 1
    return candidate


def prepare_round_workspace(
    base_dir: Path,
    run_stamp: str,
    round_number: int,
) -> RoundWorkspace:
    root = loop_result_root(base_dir)
    root.mkdir(parents=True, exist_ok=True)
    round_name = f"{run_stamp}-第{round_number}轮"
    final_dir = root / round_name
    staging_dir = root / f"{round_name}-进行中"
    incomplete_dir = root / f"{round_name}-未完成"
    for path in (final_dir, staging_dir, incomplete_dir):
        if path.exists():
            raise FileExistsError(f"循环随机结果目录已存在：{path}")
    panels_dir = staging_dir / "panels"
    panels_dir.mkdir(parents=True)
    return RoundWorkspace(
        run_stamp=run_stamp,
        round_number=round_number,
        round_name=round_name,
        root=root,
        staging_dir=staging_dir,
        final_dir=final_dir,
        incomplete_dir=incomplete_dir,
        panels_dir=panels_dir,
        grid_file=staging_dir / f"{round_name}-random.png",
    )


def ensure_loop_disk_space(base_dir: Path) -> None:
    root = loop_result_root(base_dir)
    root.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(root).free
    if free < MIN_LOOP_FREE_SPACE:
        raise RuntimeError(
            "循环随机结果所在磁盘剩余空间不足500MB，"
            "已停止开始下一轮。"
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_saves(
    save_dir: Path,
    target_dir: Path,
    slots: Iterable[int],
) -> dict[str, dict[str, Any]]:
    target_dir.mkdir(parents=True, exist_ok=True)
    copied: dict[str, dict[str, Any]] = {}
    for slot in slots:
        name = f"SV{slot:03}.E5S"
        source = save_dir / name
        if not source.is_file():
            raise FileNotFoundError(f"归档时未找到第{slot}号存档：{name}")
        target = target_dir / name
        shutil.copy2(source, target)
        source_hash = _sha256(source)
        target_hash = _sha256(target)
        if source.stat().st_size != target.stat().st_size:
            raise RuntimeError(f"第{slot}号存档归档后大小不一致")
        if source_hash != target_hash:
            raise RuntimeError(f"第{slot}号存档归档后校验不一致")
        copied[name] = {
            "size": target.stat().st_size,
            "sha256": target_hash,
        }
    return copied


def finalize_round(
    workspace: RoundWorkspace,
    *,
    save_dir: Path,
    completed_slots: Iterable[int],
    expected_slots: Iterable[int] = range(1, 16),
    metadata: dict[str, Any],
    complete: bool,
) -> Path | None:
    slots = tuple(sorted(set(completed_slots)))
    expected = tuple(sorted(set(expected_slots)))
    if not slots and not complete:
        shutil.rmtree(workspace.staging_dir, ignore_errors=True)
        return None
    if complete and slots != expected:
        raise RuntimeError(
            "循环轮次归档前结果存档不完整："
            f"应有 {list(expected)}，实际 {list(slots)}"
        )
    missing_panels = [
        slot
        for slot in slots
        if not (workspace.panels_dir / f"save{slot}.png").is_file()
    ]

    save_files = _copy_saves(
        save_dir,
        workspace.staging_dir / "saves",
        slots,
    )
    info = dict(metadata)
    info.update(
        {
            "status": "complete" if complete else "incomplete",
            "runStamp": workspace.run_stamp,
            "roundNumber": workspace.round_number,
            "expectedSlots": list(expected),
            "completedSlots": list(slots),
            "saveFiles": save_files,
            "resultArtifacts": {
                "gridGenerated": workspace.grid_file.is_file(),
                "missingPanels": missing_panels,
            },
        }
    )
    (workspace.staging_dir / "round-info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    target = workspace.final_dir if complete else workspace.incomplete_dir
    workspace.staging_dir.rename(target)
    return target
