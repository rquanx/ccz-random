"""Defaults supplied by the active game data profile."""
from ccz_randomizer.profiles import load_profile
from ccz_randomizer.runtime.skill_memory import catalog_skill_name


def profile_skill_defaults(data):
    names = {row["name"]: catalog_skill_name(row, data if "displayRules" in data else None) for row in data["runtimeCatalog"]}
    return tuple((names.get(name, name), score, category, kind)
                 for name, score, category, kind in data["defaults"])

_data = load_profile().skills
SKILL_DEFAULTS = profile_skill_defaults(_data)
EXCLUSIVE_SKILLS_22 = frozenset(_data["exclusive"])
