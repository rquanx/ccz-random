"""Story party slots loaded from the active game profile."""
from ccz_randomizer.profiles import load_profile, profile_id_for_game_version

FIXED_MEMBER_INDICES = {
    item["name"]: item["recordIndex"]
    for item in load_profile("ccz-v2.2").fixed_entries["members"]
}
FIXED_MEMBER_NAMES = tuple(FIXED_MEMBER_INDICES)


def fixed_member_indices(version=None):
    from ccz_randomizer.game_versions import current_game_version, is_enhanced_game_version, normalize_game_version
    version = current_game_version() if version is None else normalize_game_version(version)
    profile = load_profile(profile_id_for_game_version(version))
    by_index = {item["recordIndex"]: item["name"] for item in profile.fixed_entries["members"]}
    order = profile.fixed_entries.get("memberOrder", tuple(by_index))
    return {by_index[index]: index for index in order if index in by_index}


def expand_rule_members(ids, members, selected, read_jobs):
    from ccz_randomizer.rule_members import rule_member_indices

    initial_names = {member[0] for member in members}
    extra_names = [name for name in selected if name not in initial_names]
    if not extra_names:
        return ids, members
    indices = rule_member_indices()
    positions = tuple(indices[name] for name in extra_names)
    extra_ids = tuple(read_jobs(positions))
    if len(extra_ids) != len(extra_names):
        raise RuntimeError("入队人物兵种数据不完整")
    return ids + extra_ids, members + tuple((name, "NONE", "NONE") for name in extra_names)
