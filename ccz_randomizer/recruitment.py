"""Result-bound personnel data; unknown availability is never inferred."""
from __future__ import annotations

import json
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


def _talents(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("天赋数据必须为文本数组")
    return tuple(item.strip() for item in value if item.strip())


def parse_recruits(payload: object) -> tuple[Recruit, ...]:
    if not isinstance(payload, dict) or payload.get("gameVersion") != "2.2":
        raise ValueError("请选择 2.2 人员快照")
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
        if type(cost) is not int or not 1 <= cost <= 4:
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
            stages, cost, choices, row.get("fixedConfiguration") is True,
        ))
    return tuple(result)


def load_recruits(path: Path) -> tuple[Recruit, ...]:
    return parse_recruits(json.loads(path.read_text(encoding="utf-8")))


def filter_recruits(recruits: tuple[Recruit, ...], query: str = "", *,
                    stage: str = "", selected: frozenset[int] | None = None) -> tuple[Recruit, ...]:
    terms = query.casefold().split()
    return tuple(row for row in recruits
        if (not stage or row.stage == stage or stage in row.stages)
        and (selected is None or row.record_index in selected)
        and all(term in " ".join((row.name, row.stage, row.job,
            *row.job_talents, *row.personal_talents)).casefold() for term in terms))
