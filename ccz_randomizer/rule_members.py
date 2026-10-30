"""Selectable permanent/story and optional party members in version 2.2."""
from ccz_randomizer.fixed_members import FIXED_MEMBER_INDICES
from ccz_randomizer.recruitment_catalog import load_catalog

RECRUIT_MEMBERS = load_catalog()
RULE_MEMBER_INDICES = dict(FIXED_MEMBER_INDICES)
for _person in RECRUIT_MEMBERS:
    _name, _index = _person["name"], _person["recordIndex"]
    if _name in RULE_MEMBER_INDICES and RULE_MEMBER_INDICES[_name] != _index:
        raise ValueError(f"入队人员同名但编号不同：{_name}")
    RULE_MEMBER_INDICES[_name] = _index
RULE_MEMBER_NAMES = tuple(RULE_MEMBER_INDICES)
FIXED_JOB_INDICES = frozenset(p["recordIndex"] for p in RECRUIT_MEMBERS if p["fixedConfiguration"])
