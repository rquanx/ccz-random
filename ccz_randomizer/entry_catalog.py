"""Story entry timing from 2.2 R scripts (before the matching S battle)."""
from __future__ import annotations

from ccz_randomizer.fixed_members import fixed_member_indices
from ccz_randomizer.game_versions import current_game_version, is_enhanced_game_version, normalize_game_version
from ccz_randomizer.recruitment_catalog import load_catalog
from ccz_randomizer.profiles import load_profile, profile_id_for_game_version

FIXED_ENTRY_STAGES = {
    item["name"]: tuple((stage["stageId"], stage["label"]) for stage in item.get("stages", ()))
    for item in load_profile("ccz-v2.2").fixed_entries["members"]
}


def fixed_entry_stages(version=None):
    version = current_game_version() if version is None else normalize_game_version(version)
    profile = load_profile(profile_id_for_game_version(version))
    return {item["name"]: tuple((stage["stageId"], stage["label"]) for stage in item.get("stages", ())) for item in profile.fixed_entries["members"]}


def attach_fixed_entries(rows: list[dict], *, version=None) -> list[dict]:
    indices = fixed_member_indices(version)
    by_index = {row["recordIndex"]: row for row in rows}
    result = []
    for name, entries in fixed_entry_stages(version).items():
        row = dict(by_index[indices[name]])
        if row["name"] != name:
            raise ValueError("固定入队人物与当前版本目录不匹配")
        stages = [label for _index, label in entries]
        row.update(entryKind="fixed", stages=stages, stage=" / ".join(stages),
                   availabilityVerified=True, recruitmentCost=0)
        result.append(row)
    return result


def missing_fixed_entries(version=None) -> list[dict]:
    return attach_fixed_entries([
        {"recordIndex": index, "name": name, "jobId": 0, "job": "未采集",
         "jobTalents": ["未采集"], "personalTalents": ["未采集"]}
        for name, index in fixed_member_indices(version).items()
    ], version=version)


def entry_stage_order(version=None) -> dict[str, int]:
    order = {f'{stage["route"]} · {stage["name"]}': stage["stageId"]
             for person in load_catalog(version=version) for stage in person["stages"]}
    order.update({label: index for entries in fixed_entry_stages(version).values() for index, label in entries})
    return order
