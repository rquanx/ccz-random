"""Import 2.10 rules using their separately persisted runtime mode."""
import copy
import json
from pathlib import Path


class LegacyModeRequired(ValueError):
    pass


def read_legacy_mode(rule_path):
    path = Path(rule_path).parent / "randomizer_settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    mode = data.get("randomMode") if isinstance(data, dict) else None
    return mode if mode in ("three", "seven") else None


def migrate_imported_profile(raw, mode):
    if "skillQualification" in raw:
        return copy.deepcopy(raw)
    if mode not in ("three", "seven"):
        raise LegacyModeRequired("旧版规则没有记录运行模式，需要旧版 randomizer_settings.json 或手动选择。")
    # Import here avoids a config/importer module cycle.
    from ccz_randomizer.rules.config import _default_profile, _merge_defaults
    profile = _merge_defaults(_default_profile(), raw)
    profile["simpleSettings"]["difficulty"] = "自定义"
    profile["threePerson"]["jobQualificationMode"] = raw.get("threePerson", {}).get("jobQualificationMode", "average")
    source = profile["threePerson" if mode == "three" else "sevenPerson"]
    profile["threePerson"] = {key: copy.deepcopy(source[key]) for key in (
        "minJobAverage", "jobQualificationMode", "minQualifiedCount", "qualifiedMembers")}
    seven = profile["sevenPerson"]
    profile["skillQualification"] = dict(mode="total",
        threshold=seven["lowMinSkillScore"], requiredCount=1)
    # Saving in simple mode would overwrite the imported numeric thresholds.
    profile["editorMode"] = "advanced"
    seven.update(specialSkillAutoPass=False, highJobAutoPass=False)
    profile["jobScoring"].update(xiahouDunMasterPenalty=0,
        extraMasterPenaltyEnabled=False, extraMasterPenaltyWeight=0)
    profile["legacyImport"] = {"source": "2.10", "mode": mode}
    return profile
