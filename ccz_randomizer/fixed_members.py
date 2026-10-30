"""2.2 story party slots, separate from the optional R_99 recruit catalog.

Story members may be route-dependent or leave later. These are previews of
the initial roll, not guarantees about later story changes.
"""

FIXED_MEMBER_INDICES = {
    "曹操": 0, "夏侯惇": 1, "夏侯渊": 6,
    "曹洪": 12, "典韦": 16, "许褚": 15,
    "荀彧": 20, "郭嘉": 22, "张辽": 2,
    "司马懿": 19, "庞德": 9, "曹彰": 4,
    "郭淮": 29, "赵云": 34,
}
FIXED_MEMBER_NAMES = tuple(FIXED_MEMBER_INDICES)


def expand_rule_members(ids, members, selected, read_jobs):
    from ccz_randomizer.rule_members import RULE_MEMBER_INDICES

    initial_names = {member[0] for member in members}
    extra_names = [name for name in selected if name not in initial_names]
    if not extra_names:
        return ids, members
    positions = tuple(RULE_MEMBER_INDICES[name] for name in extra_names)
    extra_ids = tuple(read_jobs(positions))
    if len(extra_ids) != len(extra_names):
        raise RuntimeError("入队人物兵种数据不完整")
    return ids + extra_ids, members + tuple((name, "NONE", "NONE") for name in extra_names)
