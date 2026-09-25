from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


RULE_FILE_NAME = "random_rules.json"
RULE_VERSION = 2
DEFAULT_PROFILE_NAME = "默认规则"
TEAM_MEMBER_NAMES = (
    "曹操",
    "夏侯惇",
    "曹仁",
    "夏侯渊",
    "乐进",
    "李典",
    "曹洪",
)
AFFINITY_TYPES = ("ALL_ROUNDER", "WARRIOR", "MASTER", "NONE")

DEFAULT_MEMBER_AFFINITY = {
    "曹操": {"primaryType": "ALL_ROUNDER", "secondaryType": "WARRIOR"},
    "夏侯惇": {"primaryType": "WARRIOR", "secondaryType": "ALL_ROUNDER"},
    "曹仁": {"primaryType": "ALL_ROUNDER", "secondaryType": "WARRIOR"},
    "夏侯渊": {"primaryType": "MASTER", "secondaryType": "ALL_ROUNDER"},
    "乐进": {"primaryType": "MASTER", "secondaryType": "ALL_ROUNDER"},
    "李典": {"primaryType": "MASTER", "secondaryType": "ALL_ROUNDER"},
    "曹洪": {"primaryType": "ALL_ROUNDER", "secondaryType": "WARRIOR"},
}

SIMPLE_PRESET_OPTIONS = {
    "jobQuality": {
        "宽松": {"three": 7.1, "seven": 7.1},
        "标准": {"three": 7.4, "seven": 7.4},
        "严格": {"three": 7.7, "seven": 7.7},
    },
    "affinityImportance": {
        "较低": {"primary": 0.03, "secondary": 0.015},
        "标准": {"primary": 0.06, "secondary": 0.03},
        "较高": {"primary": 0.09, "secondary": 0.045},
    },
    "teamBalance": {
        "宽松": 0.5,
        "标准": 1.0,
        "严格": 1.5,
    },
    "skillQuality": {
        "宽松": {"medium": 3.0, "low": 4.0},
        "标准": {"medium": 4.0, "low": 5.0},
        "严格": {"medium": 5.0, "low": 6.0},
    },
    "strongSkillImportance": {
        "较低": 1.5,
        "标准": 2.0,
        "较高": 2.5,
    },
    "highJobPreference": {
        "较低": 8.0,
        "标准": 7.8,
        "较高": 7.6,
    },
}


def _default_profile() -> dict[str, Any]:
    return {
        "builtin": True,
        "editorMode": "simple",
        "simpleSettings": {
            "jobQuality": "标准",
            "affinityImportance": "标准",
            "teamBalance": "标准",
            "skillQuality": "标准",
            "strongSkillImportance": "标准",
            "highJobPreference": "标准",
        },
        "threePerson": {
            "minJobAverage": 7.4,
        },
        "sevenPerson": {
            "minJobAverage": 7.4,
            "normalJobAverage": 7.6,
            "highJobAverage": 7.8,
            "mediumMinSkillScore": 4.0,
            "lowMinSkillScore": 5.0,
            "ordinarySkillWeight": 1.0,
            "strongSkillWeight": 2.0,
            "specialSkillWeight": 5.0,
            "skillBaseScores": {},
            "specialSkillAutoPass": True,
            "highJobAutoPass": True,
        },
        "jobScoring": {
            "baseScoreWeight": 1.0,
            "jobBaseScores": {},
            "affinityEnabled": True,
            "affinityMinBaseScore": 7.0,
            "primaryBonusRate": 0.06,
            "secondaryBonusRate": 0.03,
            "xiahouDunMasterPenalty": 1.0,
            "extraMasterPenaltyEnabled": True,
            "extraMasterPenaltyWeight": 1.0,
        },
        "memberAffinity": copy.deepcopy(DEFAULT_MEMBER_AFFINITY),
    }


DEFAULT_RULE_CONFIG: dict[str, Any] = {
    "version": RULE_VERSION,
    "activeProfile": DEFAULT_PROFILE_NAME,
    "profiles": {DEFAULT_PROFILE_NAME: _default_profile()},
}


@dataclass(frozen=True)
class RuleLoadResult:
    config: dict[str, Any]
    source: str
    warning: str = ""


@dataclass(frozen=True)
class RuleEvaluation:
    qualified: bool
    reasons: tuple[str, ...]
    metrics: dict[str, Any]


def default_rule_config() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_RULE_CONFIG)


def rule_file_path(base_dir: Path) -> Path:
    return base_dir / RULE_FILE_NAME


def _merge_defaults(default: Any, value: Any) -> Any:
    if isinstance(default, dict):
        source = value if isinstance(value, dict) else {}
        merged = {
            key: _merge_defaults(default_value, source.get(key))
            for key, default_value in default.items()
        }
        merged.update(
            {
                key: copy.deepcopy(item)
                for key, item in source.items()
                if key not in default
            }
        )
        return merged
    if value is None and default is not None:
        return copy.deepcopy(default)
    return copy.deepcopy(value)


def _require_number(
    value: Any,
    path: str,
    minimum: float = 0,
    maximum: float = 100,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} 必须是数字")
    number = float(value)
    if not minimum <= number <= maximum:
        raise ValueError(f"{path} 必须在 {minimum:g}-{maximum:g} 之间")
    return number


def _require_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{path} 必须为开启或关闭")
    return value


def _require_choice(
    value: Any,
    path: str,
    options: Iterable[str],
) -> str:
    choices = tuple(options)
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"{path} 必须从 {', '.join(choices)} 中选择")
    return value


def apply_simple_settings(profile: dict[str, Any]) -> dict[str, Any]:
    settings = profile["simpleSettings"]
    job_quality = SIMPLE_PRESET_OPTIONS["jobQuality"][
        settings["jobQuality"]
    ]
    affinity = SIMPLE_PRESET_OPTIONS["affinityImportance"][
        settings["affinityImportance"]
    ]
    profile["threePerson"]["minJobAverage"] = job_quality["three"]
    profile["sevenPerson"]["minJobAverage"] = job_quality["seven"]
    profile["jobScoring"]["primaryBonusRate"] = affinity["primary"]
    profile["jobScoring"]["secondaryBonusRate"] = affinity["secondary"]
    profile["jobScoring"]["extraMasterPenaltyWeight"] = (
        SIMPLE_PRESET_OPTIONS["teamBalance"][settings["teamBalance"]]
    )
    skill_quality = SIMPLE_PRESET_OPTIONS["skillQuality"][
        settings["skillQuality"]
    ]
    profile["sevenPerson"]["mediumMinSkillScore"] = (
        skill_quality["medium"]
    )
    profile["sevenPerson"]["lowMinSkillScore"] = skill_quality["low"]
    profile["sevenPerson"]["strongSkillWeight"] = SIMPLE_PRESET_OPTIONS[
        "strongSkillImportance"
    ][settings["strongSkillImportance"]]
    profile["sevenPerson"]["highJobAverage"] = SIMPLE_PRESET_OPTIONS[
        "highJobPreference"
    ][settings["highJobPreference"]]
    return profile


def _migrate_v1(config: dict[str, Any]) -> dict[str, Any]:
    migrated = default_rule_config()
    migrated["profiles"] = {}
    raw_profiles = config.get("profiles", {})
    for name, old in raw_profiles.items():
        profile = _default_profile()
        profile["builtin"] = name == DEFAULT_PROFILE_NAME
        profile["editorMode"] = "advanced"
        old_three = old.get("threePerson", {})
        old_seven = old.get("sevenPerson", {})
        old_scoring = old.get("jobScoring", {})
        profile["threePerson"]["minJobAverage"] = old_three.get(
            "minJobAverage", 7.4
        )
        profile["sevenPerson"].update(
            {
                "minJobAverage": old_seven.get("minJobAverage", 7.4),
                "normalJobAverage": old_seven.get(
                    "normalJobAverage", 7.6
                ),
                "highJobAverage": old_seven.get("highJobAverage", 7.8),
                "mediumMinSkillScore": old_seven.get(
                    "mediumMinEffectiveSkills", 4
                ),
                "lowMinSkillScore": old_seven.get(
                    "lowMinEffectiveSkills", 5
                ),
                "strongSkillWeight": old_seven.get(
                    "strongSkillWeight", 2
                ),
                "specialSkillAutoPass": old_seven.get(
                    "specialSkillAutoPass", True
                ),
                "highJobAutoPass": old_seven.get(
                    "highJobAutoPass", True
                ),
            }
        )
        for key in (
            "affinityEnabled",
            "affinityMinBaseScore",
            "primaryBonusRate",
            "secondaryBonusRate",
            "xiahouDunMasterPenalty",
            "extraMasterPenaltyEnabled",
        ):
            if key in old_scoring:
                profile["jobScoring"][key] = old_scoring[key]
        migrated["profiles"][name] = profile
    if DEFAULT_PROFILE_NAME not in migrated["profiles"]:
        migrated["profiles"][DEFAULT_PROFILE_NAME] = _default_profile()
    active = config.get("activeProfile", DEFAULT_PROFILE_NAME)
    migrated["activeProfile"] = (
        active if active in migrated["profiles"] else DEFAULT_PROFILE_NAME
    )
    return migrated


def validate_rule_config(config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise ValueError("规则文件根节点必须是对象")
    if config.get("version") == 1:
        config = _migrate_v1(config)
    version = config.get("version")
    if version != RULE_VERSION:
        raise ValueError(
            f"规则版本 {version!r} 不受支持，当前版本为 {RULE_VERSION}"
        )
    profiles = config.get("profiles")
    active_name = config.get("activeProfile")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("规则文件没有可用配置")
    if not isinstance(active_name, str) or active_name not in profiles:
        raise ValueError("当前规则名称不存在")

    normalized = copy.deepcopy(config)
    normalized["version"] = RULE_VERSION
    default_profile = _default_profile()
    for name, raw_profile in list(profiles.items()):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("规则名称不能为空")
        profile = _merge_defaults(default_profile, raw_profile)
        profile["builtin"] = bool(
            name == DEFAULT_PROFILE_NAME and profile.get("builtin", False)
        )
        profile["editorMode"] = _require_choice(
            profile["editorMode"], f"{name}.编辑模式", ("simple", "advanced")
        )
        for key, options in SIMPLE_PRESET_OPTIONS.items():
            profile["simpleSettings"][key] = _require_choice(
                profile["simpleSettings"][key],
                f"{name}.{key}",
                options,
            )

        three = profile["threePerson"]
        seven = profile["sevenPerson"]
        scoring = profile["jobScoring"]
        three["minJobAverage"] = _require_number(
            three["minJobAverage"], f"{name}.三人兵种门槛", 0, 20
        )
        for key, label in (
            ("minJobAverage", "七人兵种门槛"),
            ("normalJobAverage", "普通兵种分界"),
            ("highJobAverage", "高兵种分界"),
            ("mediumMinSkillScore", "普通兵种特技要求"),
            ("lowMinSkillScore", "较低兵种特技要求"),
            ("ordinarySkillWeight", "普通优质特技权重"),
            ("strongSkillWeight", "强力特技权重"),
            ("specialSkillWeight", "特殊特技权重"),
        ):
            seven[key] = _require_number(seven[key], f"{name}.{label}", 0, 20)
        if seven["normalJobAverage"] > seven["highJobAverage"]:
            raise ValueError(f"{name} 的普通兵种分界不能高于高兵种分界")
        seven["specialSkillAutoPass"] = _require_bool(
            seven["specialSkillAutoPass"], f"{name}.特殊特技直接通过"
        )
        seven["highJobAutoPass"] = _require_bool(
            seven["highJobAutoPass"], f"{name}.高兵种直接通过"
        )
        skill_scores = seven["skillBaseScores"]
        if not isinstance(skill_scores, dict):
            raise ValueError(f"{name}.特技基础分必须是映射")
        seven["skillBaseScores"] = {
            str(skill_name): _require_number(
                score, f"{name}.{skill_name}基础分", 0, 20
            )
            for skill_name, score in skill_scores.items()
            if str(skill_name).strip()
        }

        for key, label, minimum, maximum in (
            ("baseScoreWeight", "兵种基础分权重", 0, 5),
            ("affinityMinBaseScore", "适配最低基础分", 0, 20),
            ("primaryBonusRate", "主要类型加成", 0, 1),
            ("secondaryBonusRate", "次要类型加成", 0, 1),
            ("xiahouDunMasterPenalty", "夏侯惇文官扣分", 0, 20),
            ("extraMasterPenaltyWeight", "文官过多扣分权重", 0, 10),
        ):
            scoring[key] = _require_number(
                scoring[key], f"{name}.{label}", minimum, maximum
            )
        scoring["affinityEnabled"] = _require_bool(
            scoring["affinityEnabled"], f"{name}.兵种适配加成"
        )
        scoring["extraMasterPenaltyEnabled"] = _require_bool(
            scoring["extraMasterPenaltyEnabled"], f"{name}.文官过多扣分"
        )
        base_scores = scoring["jobBaseScores"]
        if not isinstance(base_scores, dict):
            raise ValueError(f"{name}.兵种基础分必须是映射")
        scoring["jobBaseScores"] = {
            str(job_name): _require_number(
                score, f"{name}.{job_name}基础分", 0, 20
            )
            for job_name, score in base_scores.items()
            if str(job_name).strip()
        }

        affinity = profile["memberAffinity"]
        if not isinstance(affinity, dict):
            raise ValueError(f"{name}.人物倾向格式错误")
        normalized_affinity = {}
        for member in TEAM_MEMBER_NAMES:
            row = affinity.get(member, DEFAULT_MEMBER_AFFINITY[member])
            if not isinstance(row, dict):
                raise ValueError(f"{name}.{member}倾向格式错误")
            primary = _require_choice(
                row.get("primaryType"),
                f"{name}.{member}主要倾向",
                AFFINITY_TYPES[:-1],
            )
            secondary = _require_choice(
                row.get("secondaryType", "NONE"),
                f"{name}.{member}次要倾向",
                AFFINITY_TYPES,
            )
            normalized_affinity[member] = {
                "primaryType": primary,
                "secondaryType": secondary,
            }
        profile["memberAffinity"] = normalized_affinity
        normalized["profiles"][name] = profile

    if DEFAULT_PROFILE_NAME not in normalized["profiles"]:
        normalized["profiles"][DEFAULT_PROFILE_NAME] = _default_profile()
    normalized["profiles"][DEFAULT_PROFILE_NAME]["builtin"] = True
    return normalized


def load_rule_config(base_dir: Path) -> RuleLoadResult:
    path = rule_file_path(base_dir)
    if not path.is_file():
        return RuleLoadResult(default_rule_config(), "builtin")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8-sig"))
        migrated = parsed.get("version") == 1
        warning = (
            "本地规则已转换为新版评分规则，请保存一次以完成升级。"
            if migrated
            else ""
        )
        return RuleLoadResult(
            validate_rule_config(parsed), "local", warning
        )
    except Exception as exc:
        return RuleLoadResult(
            default_rule_config(),
            "builtin",
            f"本地规则文件无法使用：{exc}。本次已使用内置默认规则。",
        )


def save_rule_config(base_dir: Path, config: dict[str, Any]) -> Path:
    normalized = validate_rule_config(config)
    path = rule_file_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path


def active_profile(config: dict[str, Any]) -> dict[str, Any]:
    return config["profiles"][config["activeProfile"]]


def evaluate_job_rules(
    config: dict[str, Any],
    mode: str,
    jobs: list[dict[str, Any]],
    members: list[dict[str, str]],
) -> RuleEvaluation:
    profile = active_profile(config)
    scoring = profile["jobScoring"]
    affinity = profile["memberAffinity"]
    total_score = 0.0
    master_count = 0
    job_names = [str(job["name"]) for job in jobs]

    for index, (job, fallback_member) in enumerate(zip(jobs, members)):
        name = str(job["name"])
        raw_score = float(job["score"])
        score = float(scoring["jobBaseScores"].get(name, raw_score))
        weighted_score = score * scoring["baseScoreWeight"]
        job_type = str(job["type"])
        member_name = fallback_member["name"]
        member = affinity.get(member_name, fallback_member)
        attach_score = 0.0
        if (
            scoring["affinityEnabled"]
            and score >= scoring["affinityMinBaseScore"]
        ):
            if job_type == member["primaryType"]:
                attach_score += weighted_score * scoring["primaryBonusRate"]
            elif job_type == member["secondaryType"]:
                attach_score += weighted_score * scoring["secondaryBonusRate"]
        if job_type == "MASTER":
            master_count += 1
            if index == 1:
                attach_score -= scoring["xiahouDunMasterPenalty"]
        total_score += weighted_score + attach_score

    if scoring["extraMasterPenaltyEnabled"] and master_count > 1:
        total_score -= (
            (master_count - 1) ** 2
        ) * scoring["extraMasterPenaltyWeight"]
    average = total_score / max(1, len(jobs))
    threshold = profile[
        "threePerson" if mode == "three" else "sevenPerson"
    ]["minJobAverage"]
    reasons = (
        ()
        if average >= threshold
        else ("兵种综合评价未达到当前规则要求",)
    )
    return RuleEvaluation(
        not reasons,
        reasons,
        {
            "average": average,
            "masterCount": master_count,
            "jobNames": job_names,
            "threshold": threshold,
        },
    )


def evaluate_skill_rules(
    config: dict[str, Any],
    job_average: float,
    member_skills: dict[str, list[str]],
    carry_skill_names: set[str],
    strong_skill_names: set[str],
    special_skill_names: set[str],
    effective_skill_names: Iterable[str] | None = None,
) -> RuleEvaluation:
    profile = active_profile(config)
    seven = profile["sevenPerson"]
    all_skill_items = [
        skill for skills in member_skills.values() for skill in skills
    ]
    effective_items = (
        list(effective_skill_names)
        if effective_skill_names is not None
        else all_skill_items
    )
    strong_count = sum(
        skill in strong_skill_names for skill in effective_items
    )
    carry_count = sum(
        skill in carry_skill_names and skill not in strong_skill_names
        for skill in effective_items
    )
    special_count = sum(
        skill in special_skill_names for skill in all_skill_items
    )
    overrides = seven["skillBaseScores"]
    effective_remaining: dict[str, int] = {}
    for skill in effective_items:
        effective_remaining[skill] = effective_remaining.get(skill, 0) + 1
    skill_score = 0.0
    for skill in all_skill_items:
        if skill in special_skill_names:
            default_score = seven["specialSkillWeight"]
        elif skill in strong_skill_names:
            if effective_remaining.get(skill, 0) <= 0:
                continue
            effective_remaining[skill] -= 1
            default_score = seven["strongSkillWeight"]
        elif skill in carry_skill_names:
            if effective_remaining.get(skill, 0) <= 0:
                continue
            effective_remaining[skill] -= 1
            default_score = seven["ordinarySkillWeight"]
        else:
            default_score = 0.0
        skill_score += float(overrides.get(skill, default_score))

    if seven["specialSkillAutoPass"] and special_count > 0:
        qualified = True
        minimum = 0.0
    elif seven["highJobAutoPass"] and job_average >= seven["highJobAverage"]:
        qualified = True
        minimum = 0.0
    else:
        minimum = (
            seven["mediumMinSkillScore"]
            if job_average >= seven["normalJobAverage"]
            else seven["lowMinSkillScore"]
        )
        qualified = skill_score >= minimum
    reasons = (
        ()
        if qualified
        else ("特技综合评价未达到当前规则要求",)
    )
    return RuleEvaluation(
        qualified,
        reasons,
        {
            "carryCount": carry_count,
            "strongCount": strong_count,
            "specialCount": special_count,
            "skillScore": skill_score,
            "effectiveCount": skill_score,
            "requiredSkillScore": minimum,
            "jobAverage": job_average,
        },
    )
