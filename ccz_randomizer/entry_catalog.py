"""Story entry timing from 2.2 R scripts (before the matching S battle)."""
from __future__ import annotations

from ccz_randomizer.fixed_members import FIXED_MEMBER_INDICES
from ccz_randomizer.recruitment_catalog import load_catalog

# A story character can enter on different stages on the two routes.
FIXED_ENTRY_STAGES = {
    "曹操": ((0, "共通 · 颍川之战"),),
    "夏侯惇": ((0, "共通 · 颍川之战"),),
    "夏侯渊": ((0, "共通 · 颍川之战"),),
    "曹洪": ((1, "共通 · 汜水关之战"),),
    "典韦": ((4, "共通 · 青州讨伐战"),),
    "荀彧": ((4, "共通 · 青州讨伐战"),),
    "郭嘉": ((5, "共通 · 徐州之战"),),
    "许褚": ((8, "共通 · 濮阳决战"),),
    "张辽": ((15, "共通 · 徐州平定战"),),
    "司马懿": ((32, "红线 · 汉中讨伐战"), (46, "蓝线 · 定军山之战·异")),
    "庞德": ((33, "红线 · 逍遥津之战"), (46, "蓝线 · 定军山之战·异")),
    "郭淮": ((35, "红线 · 定军山之战"),),
    "曹彰": ((38, "红线 · 樊城救援战"), (46, "蓝线 · 定军山之战·异")),
    "赵云": ((47, "蓝线 · 麦城救援战"),),
}


def attach_fixed_entries(rows: list[dict]) -> list[dict]:
    by_index = {row["recordIndex"]: row for row in rows}
    result = []
    for name, entries in FIXED_ENTRY_STAGES.items():
        row = dict(by_index[FIXED_MEMBER_INDICES[name]])
        if row["name"] != name:
            raise ValueError("固定入队人物与 2.2 目录不匹配")
        stages = [label for _index, label in entries]
        row.update(entryKind="fixed", stages=stages, stage=" / ".join(stages),
                   availabilityVerified=True, recruitmentCost=0)
        result.append(row)
    return result


def missing_fixed_entries() -> list[dict]:
    return attach_fixed_entries([
        {"recordIndex": index, "name": name, "jobId": 0, "job": "未采集",
         "jobTalents": ["未采集"], "personalTalents": ["未采集"]}
        for name, index in FIXED_MEMBER_INDICES.items()
    ])


def entry_stage_order() -> dict[str, int]:
    order = {f'{stage["route"]} · {stage["name"]}': stage["stageId"]
             for person in load_catalog() for stage in person["stages"]}
    order.update({label: index for entries in FIXED_ENTRY_STAGES.values() for index, label in entries})
    return order
