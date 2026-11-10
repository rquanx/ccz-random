"""Audited stage assignments from the bundled 2.2 R_99 script."""
from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from ccz_randomizer.game_versions import catalog_game_version, current_game_version, normalize_game_version
from ccz_randomizer.profiles import load_profile, profile_id_for_game_version


@lru_cache(maxsize=3)
def _bundled_catalog(version: str) -> tuple[dict, ...]:
    profile = load_profile(profile_id_for_game_version(version))
    root = profile.root / profile.manifest["files"]["recruitment"]
    return load_catalog(root, version=version)


def load_catalog(path: Path | None = None, *, version: str | None = None) -> tuple[dict, ...]:
    version = normalize_game_version(version) if version is not None else current_game_version()
    if path is None:
        return _bundled_catalog(version)
    payload = json.loads(path.read_text(encoding="utf-8"))
    profile = load_profile(profile_id_for_game_version(version))
    if payload.get("schemaVersion") != 1 or payload.get("gameVersion") != profile.recruitment.get("gameVersion"):
        raise ValueError("招募目录版本不匹配")
    people = payload.get("people")
    if not isinstance(people, list) or not people:
        raise ValueError("招募目录为空")
    seen = set()
    for person in people:
        index = person.get("recordIndex")
        if type(index) is not int or not 0 <= index < 1024 or index in seen:
            raise ValueError("招募目录人物编号无效")
        seen.add(index)
        if not isinstance(person.get("name"), str) or not person["name"]:
            raise ValueError("招募目录缺少姓名")
        if type(person.get("cost")) is not int or not 1 <= person["cost"] <= 4:
            raise ValueError("招募消耗无效")
        if type(person.get("fixedConfiguration")) is not bool:
            raise ValueError("招募配置类型无效")
        if not isinstance(person.get("jobChoices"), list) or not all(isinstance(s, str) for s in person["jobChoices"]):
            raise ValueError("招募兵种选项无效")
        if not isinstance(person.get("stages"), list) or not person["stages"]:
            raise ValueError("招募目录缺少关卡")
        for stage in person["stages"]:
            if type(stage.get("stageId")) is not int or not isinstance(stage.get("name"), str) or stage.get("route") not in ("共通", "红线", "蓝线"):
                raise ValueError("招募关卡格式无效")
    return tuple(people)


def attach_recruitment(rows: list[dict], catalog: tuple[dict, ...]) -> list[dict]:
    by_index = {row["recordIndex"]: row for row in rows}
    result = []
    for person in catalog:
        row = dict(by_index[person["recordIndex"]])
        if row["name"] != person["name"]:
            raise ValueError("游戏人物与当前版本招募目录不匹配")
        stages = [f'{stage["route"]} · {stage["name"]}' for stage in person["stages"]]
        row.update(stages=stages, stage=" / ".join(stages), availabilityVerified=True,
                   recruitmentCost=person["cost"], jobChoices=person["jobChoices"],
                   fixedConfiguration=person["fixedConfiguration"])
        result.append(row)
    return result
