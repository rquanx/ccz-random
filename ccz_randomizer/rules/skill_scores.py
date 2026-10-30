"""Independent skill scores, with a one-time conversion of tier-based rules."""
from ccz_randomizer.runtime.skill_memory import normalize_skill_name
from ccz_randomizer.rules.skill_defaults import SKILL_DEFAULTS


def resolve_setting(values, name, default):
    if name in values:
        return values[name]
    normalized = normalize_skill_name(name)
    return next((value for key, value in reversed(tuple(values.items()))
                 if normalize_skill_name(key) == normalized), default)


def migrate_skill_scores(profile, catalog=SKILL_DEFAULTS):
    seven = profile["sevenPerson"]
    if seven.get("individualSkillScores"):
        return
    weights = {"优质": seven["ordinarySkillWeight"],
               "强力": seven["strongSkillWeight"],
               "特殊": seven["specialSkillWeight"], "其他": 0.0}
    scores = seven["skillBaseScores"]
    types = seven["skillTypeOverrides"]
    # Snapshot aliases before inserting exact names so parameter variants retain
    # their original overrides, independently of catalog order.
    old_scores, old_types = dict(scores), dict(types)
    for name, default, category, kind in catalog:
        score = resolve_setting(old_scores, name, weights.get(category, default))
        if score != default or name in old_scores:
            scores[name] = score
        # Previously the final score, not the original tier, determined exemption.
        kind = ("NONE" if score >= seven["specialSkillWeight"] else
                resolve_setting(old_types, name, kind))
        types[name] = kind
    for name, score in old_scores.items():
        if score >= seven["specialSkillWeight"]:
            types[name] = "NONE"
    seven["individualSkillScores"] = True


DEFAULT_SCORES = {name: score for name, score, _category, _kind in SKILL_DEFAULTS}
DEFAULT_TYPES = {name: ("NONE" if category == "特殊" else kind)
                 for name, _score, category, kind in SKILL_DEFAULTS}
