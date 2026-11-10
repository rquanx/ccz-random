"""Result-bound personnel data; unknown availability is never inferred."""
from __future__ import annotations

import json
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Recruit:
    record_index: int
    name: str
    stage: str
    job: str
    job_talents: tuple[str, ...]
    personal_talents: tuple[str, ...]
    availability_verified: bool = False
    stages: tuple[str, ...] = ()
    cost: int = 1
    job_choices: tuple[str, ...] = ()
    fixed_configuration: bool = False
    entry_kind: str = "recruit"


def display_job_options(row: Recruit) -> str:
    """Return the random job followed by concrete recruitment job choices."""
    values = [row.job]
    for choice in row.job_choices:
        # These entries are dialog actions, rather than another job name.
        if choice == "随机" or "随机结果" in choice or "原兵种" in choice:
            continue
        if choice not in values:
            values.append(choice)
    return "/".join(values)


def _talents(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("天赋数据必须为文本数组")
    return tuple(item.strip() for item in value if item.strip())


def parse_recruits(payload: object) -> tuple[Recruit, ...]:
    # A result snapshot is self-contained, and may outlive its game profile.
    # Live game compatibility is checked before memory access, not here.
    if not isinstance(payload, dict) or not isinstance(payload.get("gameVersion"), str) or not payload["gameVersion"].strip():
        raise ValueError("人员快照缺少游戏版本")
    if payload.get("schemaVersion") != 1:
        raise ValueError("不支持的人员快照格式")
    rows = payload.get("personnel")
    if not isinstance(rows, list):
        raise ValueError("快照缺少人员数据")
    result = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("人物记录格式错误")
        index = row.get("recordIndex")
        if type(index) is not int or index < 0 or index in seen:
            raise ValueError("人物记录编号无效或重复")
        seen.add(index)
        name = row.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("人物名称为空")
        verified = row.get("availabilityVerified") is True
        stage = row.get("stage")
        if verified and (not isinstance(stage, str) or not stage.strip()):
            raise ValueError("已确认招募记录缺少关卡")
        stages = _talents(row.get("stages", [stage] if verified else []))
        cost = row.get("recruitmentCost", 1)
        entry_kind = row.get("entryKind", "recruit")
        if entry_kind not in {"fixed", "recruit"}:
            raise ValueError("入队类型无效")
        if type(cost) is not int or not (cost == 0 if entry_kind == "fixed" else 1 <= cost <= 4):
            raise ValueError("招募消耗无效")
        choices = _talents(row.get("jobChoices", []))
        job_id = row.get("jobId")
        if type(job_id) is not int or not 0 <= job_id <= 255:
            raise ValueError("兵种编号无效")
        job = row.get("job")
        if job is not None and not isinstance(job, str):
            raise ValueError("兵种名称格式错误")
        result.append(Recruit(
            index, name.strip(), stage.strip() if verified else "招募关系待验证",
            job or f"兵种 #{job_id}",
            _talents(row.get("jobTalents")), _talents(row.get("personalTalents")), verified,
            stages, cost, choices, row.get("fixedConfiguration") is True, entry_kind,
        ))
    return tuple(result)


def load_recruits(path: Path) -> tuple[Recruit, ...]:
    return parse_recruits(json.loads(path.read_text(encoding="utf-8")))


@lru_cache(maxsize=1024)
def _search_text(row: Recruit) -> str:
    return " ".join((row.name, row.stage, display_job_options(row),
                     *row.job_talents, *row.personal_talents)).casefold()


def filter_recruits(recruits: tuple[Recruit, ...], query: str = "", *,
                    stage: str = "", selected: frozenset[int] | None = None) -> tuple[Recruit, ...]:
    terms = query.casefold().split()
    return tuple(row for row in recruits
        if (not stage or row.stage == stage or stage in row.stages)
        and (selected is None or row.record_index in selected)
        and all(term in _search_text(row) for term in terms))
