"""Rule identity and the filtering content that defines statistical continuity."""
from __future__ import annotations

import copy
import hashlib
import json
import uuid


def rule_identity(name, profile):
    return profile.get("statisticsId") or uuid.uuid5(uuid.NAMESPACE_URL, "ccz-rule:" + name).hex


def new_rule_identity(profile):
    profile["statisticsId"] = uuid.uuid4().hex
    profile.pop("statisticsAliases", None)
    profile.pop("statisticsGeneration", None)


def mark_overwritten(config, changes):
    for name, _ in changes:
        config["profiles"][name]["statisticsGeneration"] = uuid.uuid4().hex


def filtering_content(profile):
    content = copy.deepcopy({key: value for key, value in profile.items()
        if key not in {"builtin", "editorMode", "simpleSettings", "resultImage", "dataCollection",
                       "statisticsId", "statisticsAliases", "statisticsGeneration"}})
    # An explicit default in the editor has the same effect as an omitted override.
    from ccz_randomizer.jobs import JOB_MAP
    from ccz_randomizer.rules.skill_defaults import SKILL_DEFAULTS
    defaults = {
        ("jobScoring", "jobBaseScores"): {name: score for name, score, _ in JOB_MAP.values()},
        ("jobScoring", "jobTypeOverrides"): {name: kind for name, _, kind in JOB_MAP.values()},
        ("sevenPerson", "skillBaseScores"): {name: score for name, score, _, _ in SKILL_DEFAULTS},
        ("sevenPerson", "skillTypeOverrides"): {name: kind for name, _, _, kind in SKILL_DEFAULTS},
    }
    for (section, field), values in defaults.items():
        if section in content:
            content[section][field] = {name: value for name, value in content[section].get(field, {}).items()
                                       if name not in values or value != values[name]}
    return content


def filtering_fingerprint(profile):
    def normalize(value):
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [normalize(item) for item in value]
        if type(value) in (int, float):
            return float(value)
        return value
    raw = json.dumps(normalize(filtering_content(profile)), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def statistics_revision(name, profile):
    return hashlib.sha256((rule_identity(name, profile) + ":" + profile.get("statisticsGeneration", "")
                           + ":" + filtering_fingerprint(profile)).encode()).hexdigest()


def changed_profiles(before, after):
    originals = {rule_identity(name, profile): (name, profile) for name, profile in before["profiles"].items()}
    return [(name, originals[identity][0]) for name, profile in after["profiles"].items()
            if (identity := rule_identity(name, profile)) in originals
            and filtering_fingerprint(profile) != filtering_fingerprint(originals[identity][1])]


def save_changes_as_new(before, after, changes):
    result = copy.deepcopy(after)
    edited = [(name, old_name, result["profiles"].pop(name)) for name, old_name in changes]
    for _, old_name, _ in edited:
        if old_name in result["profiles"]:
            raise ValueError(f"请先为占用原规则名称“{old_name}”的规则重命名，再另存。")
        result["profiles"][old_name] = copy.deepcopy(before["profiles"][old_name])
    for name, _, profile in edited:
        new_rule_identity(profile)
        new_name, index = name + "副本", 2
        while new_name in result["profiles"]:
            new_name = f"{name}副本 {index}"
            index += 1
        result["profiles"][new_name] = profile
        if result["activeProfile"] == name:
            result["activeProfile"] = new_name
    return result
