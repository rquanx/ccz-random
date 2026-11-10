"""Selectable permanent/story and optional party members in version 2.2."""
from ccz_randomizer.fixed_members import FIXED_MEMBER_INDICES
from ccz_randomizer.recruitment_catalog import load_catalog
from ccz_randomizer.profiles import load_profile

RECRUIT_MEMBERS = load_catalog()
RULE_MEMBER_INDICES = dict(FIXED_MEMBER_INDICES)
for _person in RECRUIT_MEMBERS:
    _name, _index = _person["name"], _person["recordIndex"]
    if _name in RULE_MEMBER_INDICES and RULE_MEMBER_INDICES[_name] != _index:
        raise ValueError(f"入队人员同名但编号不同：{_name}")
    RULE_MEMBER_INDICES[_name] = _index
RULE_MEMBER_NAMES = tuple(RULE_MEMBER_INDICES)
FIXED_JOB_INDICES = frozenset(p["recordIndex"] for p in RECRUIT_MEMBERS if p["fixedConfiguration"])


def rule_member_indices(version=None):
    from ccz_randomizer.fixed_members import fixed_member_indices
    result = fixed_member_indices(version)
    for person in load_catalog(version=version):
        result[person["name"]] = person["recordIndex"]
    return result


# Validation accepts saved choices from either supported edition without
# dropping preferences. The editor and runtime use the selected edition.
ALL_RULE_MEMBER_NAMES = tuple(dict.fromkeys((*RULE_MEMBER_NAMES, *rule_member_indices(load_profile().game_version))))


def validate_selected_members(names, version=None):
    available = rule_member_indices(version)
    missing = [name for name in names if name not in available]
    if missing:
        raise ValueError("当前游戏版本不支持所选人物：" + "、".join(missing))


def validate_profile_members(profile, version=None):
    names = list(profile["threePerson"]["qualifiedMembers"])
    display = profile.get("resultImage", {})
    if display.get("mode") == "custom":
        names.extend(display.get("members", ()))
    validate_selected_members(tuple(dict.fromkeys(names)), version)


def required_data_collection(profile):
    """Resolve runtime dependencies without changing the saved preferences."""
    collection = dict(profile.get("dataCollection", {}))
    if profile.get("resultImage", {}).get("mode") == "custom":
        collection["recruitment"] = True
    return collection
