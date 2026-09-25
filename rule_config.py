from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


RULE_FILE_NAME = "random_rules.json"
RULE_VERSION = 1
TEAM_MEMBER_NAMES = (
    "曹操",
    "夏侯惇",
    "曹仁",
    "夏侯渊",
    "乐进",
    "李典",
    "曹洪",
)

DEFAULT_RULE_CONFIG: dict[str, Any] = {
    "version": RULE_VERSION,
    "activeProfile": "默认规则",
    "profiles": {
        "默认规则": {
            "threePerson": {
                "minJobAverage": 7.4,
            },
            "sevenPerson": {
                "minJobAverage": 7.4,
                "normalJobAverage": 7.6,
                "highJobAverage": 7.8,
                "mediumMinEffectiveSkills": 4,
                "lowMinEffectiveSkills": 5,
                "strongSkillWeight": 2,
                "specialSkillAutoPass": True,
                "highJobAutoPass": True,
            },
            "jobScoring": {
                "affinityEnabled": True,
                "affinityMinBaseScore": 7,
                "primaryBonusRate": 0.06,
                "secondaryBonusRate": 0.03,
                "xiahouDunMasterPenalty": 1.0,
                "extraMasterPenaltyEnabled": True,
            },
            "jobConditions": {
                "maxMasterCount": None,
                "requiredJobGroups": [],
                "memberAllowedJobs": {},
                "memberBlockedJobs": {},
            },
            "skillConditions": {
                "requiredAny": [],
                "requiredAll": [],
                "blocked": [],
                "minMembersWithQualitySkill": 0,
                "memberRequired": {},
                "memberBlocked": {},
            },
        }
    },
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
        return {
            key: _merge_defaults(default_value, source.get(key))
            for key, default_value in default.items()
        } | {
            key: copy.deepcopy(item)
            for key, item in source.items()
            if key not in default
        }
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


def _require_int(
    value: Any,
    path: str,
    minimum: int = 0,
    maximum: int = 100,
) -> int:
    number = _require_number(value, path, minimum, maximum)
    if not number.is_integer():
        raise ValueError(f"{path} 必须是整数")
    return int(number)


def _require_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{path} 必须为开启或关闭")
    return value


def _string_list(value: Any, path: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) for item in value
    ):
        raise ValueError(f"{path} 必须是名称列表")
    return list(dict.fromkeys(item.strip() for item in value if item.strip()))


def _member_map(value: Any, path: str) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} 必须是武将规则")
    result = {}
    for member, names in value.items():
        if member not in TEAM_MEMBER_NAMES:
            raise ValueError(f"{path} 包含未知武将：{member}")
        parsed = _string_list(names, f"{path}.{member}")
        if parsed:
            result[member] = parsed
    return result


def validate_rule_config(config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise ValueError("规则文件根节点必须是对象")
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
    default_profile = DEFAULT_RULE_CONFIG["profiles"]["默认规则"]
    for name, raw_profile in list(profiles.items()):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("规则名称不能为空")
        profile = _merge_defaults(default_profile, raw_profile)
        three = profile["threePerson"]
        seven = profile["sevenPerson"]
        scoring = profile["jobScoring"]
        jobs = profile["jobConditions"]
        skills = profile["skillConditions"]

        three["minJobAverage"] = _require_number(
            three["minJobAverage"], f"{name}.三人兵种门槛", 0, 20
        )
        for key, label in (
            ("minJobAverage", "七人兵种门槛"),
            ("normalJobAverage", "普通兵种分界"),
            ("highJobAverage", "高兵种分界"),
        ):
            seven[key] = _require_number(
                seven[key], f"{name}.{label}", 0, 20
            )
        if seven["normalJobAverage"] > seven["highJobAverage"]:
            raise ValueError(f"{name} 的普通兵种分界不能高于高兵种分界")
        for key, label in (
            ("mediumMinEffectiveSkills", "中等兵种有效特技数"),
            ("lowMinEffectiveSkills", "较低兵种有效特技数"),
            ("strongSkillWeight", "强力特技权重"),
        ):
            seven[key] = _require_int(seven[key], f"{name}.{label}", 0, 20)
        seven["specialSkillAutoPass"] = _require_bool(
            seven["specialSkillAutoPass"], f"{name}.特殊特技直接通过"
        )
        seven["highJobAutoPass"] = _require_bool(
            seven["highJobAutoPass"], f"{name}.高兵种直接通过"
        )

        scoring["affinityEnabled"] = _require_bool(
            scoring["affinityEnabled"], f"{name}.兵种适配加成"
        )
        scoring["affinityMinBaseScore"] = _require_number(
            scoring["affinityMinBaseScore"], f"{name}.适配最低基础分", 0, 20
        )
        scoring["primaryBonusRate"] = _require_number(
            scoring["primaryBonusRate"], f"{name}.主要类型加成", 0, 1
        )
        scoring["secondaryBonusRate"] = _require_number(
            scoring["secondaryBonusRate"], f"{name}.次要类型加成", 0, 1
        )
        scoring["xiahouDunMasterPenalty"] = _require_number(
            scoring["xiahouDunMasterPenalty"],
            f"{name}.夏侯惇文官扣分",
            0,
            20,
        )
        scoring["extraMasterPenaltyEnabled"] = _require_bool(
            scoring["extraMasterPenaltyEnabled"], f"{name}.文官过多扣分"
        )

        max_master = jobs["maxMasterCount"]
        jobs["maxMasterCount"] = (
            None
            if max_master in (None, "")
            else _require_int(max_master, f"{name}.文官人数上限", 0, 7)
        )
        groups = jobs["requiredJobGroups"]
        if not isinstance(groups, list):
            raise ValueError(f"{name}.指定兵种组合必须是列表")
        normalized_groups = []
        for index, group in enumerate(groups, 1):
            if not isinstance(group, dict):
                raise ValueError(f"{name}.指定兵种组合第 {index} 项格式错误")
            names = _string_list(
                group.get("jobs", []),
                f"{name}.指定兵种组合第 {index} 项",
            )
            minimum = _require_int(
                group.get("minCount", 1),
                f"{name}.指定兵种组合第 {index} 项数量",
                1,
                7,
            )
            if names:
                normalized_groups.append(
                    {"jobs": names, "minCount": minimum}
                )
        jobs["requiredJobGroups"] = normalized_groups
        jobs["memberAllowedJobs"] = _member_map(
            jobs["memberAllowedJobs"], f"{name}.武将允许兵种"
        )
        jobs["memberBlockedJobs"] = _member_map(
            jobs["memberBlockedJobs"], f"{name}.武将排除兵种"
        )

        for key, label in (
            ("requiredAny", "任一指定特技"),
            ("requiredAll", "全部指定特技"),
            ("blocked", "排除特技"),
        ):
            skills[key] = _string_list(skills[key], f"{name}.{label}")
        skills["minMembersWithQualitySkill"] = _require_int(
            skills["minMembersWithQualitySkill"],
            f"{name}.拥有优质特技的武将数",
            0,
            7,
        )
        skills["memberRequired"] = _member_map(
            skills["memberRequired"], f"{name}.武将指定特技"
        )
        skills["memberBlocked"] = _member_map(
            skills["memberBlocked"], f"{name}.武将排除特技"
        )
        normalized["profiles"][name] = profile
    return normalized


def load_rule_config(base_dir: Path) -> RuleLoadResult:
    path = rule_file_path(base_dir)
    if not path.is_file():
        return RuleLoadResult(default_rule_config(), "builtin")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8-sig"))
        return RuleLoadResult(validate_rule_config(parsed), "local")
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


def _name_set(values: Iterable[str]) -> set[str]:
    return {str(value) for value in values}


def evaluate_job_rules(
    config: dict[str, Any],
    mode: str,
    jobs: list[dict[str, Any]],
    members: list[dict[str, str]],
) -> RuleEvaluation:
    profile = active_profile(config)
    scoring = profile["jobScoring"]
    conditions = profile["jobConditions"]
    reasons: list[str] = []
    total_score = 0.0
    master_count = 0
    job_names = [str(job["name"]) for job in jobs]

    for index, (job, member) in enumerate(zip(jobs, members)):
        name = str(job["name"])
        score = float(job["score"])
        job_type = str(job["type"])
        member_name = member["name"]
        attach_score = 0.0
        if (
            scoring["affinityEnabled"]
            and score >= scoring["affinityMinBaseScore"]
        ):
            if job_type == member["primaryType"]:
                attach_score += score * scoring["primaryBonusRate"]
            elif job_type == member["secondaryType"]:
                attach_score += score * scoring["secondaryBonusRate"]
        if job_type == "MASTER":
            master_count += 1
            if index == 1:
                attach_score -= scoring["xiahouDunMasterPenalty"]
        total_score += score + attach_score

        allowed = conditions["memberAllowedJobs"].get(member_name, [])
        if allowed and name not in allowed:
            reasons.append(f"{member_name}的兵种不在允许范围内")
        blocked = conditions["memberBlockedJobs"].get(member_name, [])
        if name in blocked:
            reasons.append(f"{member_name}命中排除兵种“{name}”")

    if scoring["extraMasterPenaltyEnabled"] and master_count > 1:
        total_score -= (master_count - 1) ** 2
    average = total_score / max(1, len(jobs))

    max_master = conditions["maxMasterCount"]
    if max_master is not None and master_count > max_master:
        reasons.append("文官兵种人数超过规则上限")
    for group in conditions["requiredJobGroups"]:
        matches = sum(name in group["jobs"] for name in job_names)
        if matches < group["minCount"]:
            reasons.append("指定兵种组合数量未达到要求")

    threshold = profile[
        "threePerson" if mode == "three" else "sevenPerson"
    ]["minJobAverage"]
    if average < threshold:
        reasons.append("兵种平均质量未达到规则要求")

    return RuleEvaluation(
        not reasons,
        tuple(dict.fromkeys(reasons)),
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
    conditions = profile["skillConditions"]
    reasons: list[str] = []
    all_skill_items = [
        skill for skills in member_skills.values() for skill in skills
    ]
    all_skills = set(all_skill_items)

    if conditions["requiredAny"] and not (
        all_skills & _name_set(conditions["requiredAny"])
    ):
        reasons.append("未出现任一指定特技")
    missing_all = _name_set(conditions["requiredAll"]) - all_skills
    if missing_all:
        reasons.append("未集齐全部指定特技")
    blocked = all_skills & _name_set(conditions["blocked"])
    if blocked:
        reasons.append(f"出现排除特技“{sorted(blocked)[0]}”")

    for member, required in conditions["memberRequired"].items():
        if not (_name_set(required) & _name_set(member_skills.get(member, []))):
            reasons.append(f"{member}未出现指定特技")
    for member, blocked_names in conditions["memberBlocked"].items():
        matched = _name_set(blocked_names) & _name_set(
            member_skills.get(member, [])
        )
        if matched:
            reasons.append(
                f"{member}出现排除特技“{sorted(matched)[0]}”"
            )

    quality_names = (
        carry_skill_names | strong_skill_names | special_skill_names
    )
    quality_member_count = sum(
        bool(_name_set(skills) & quality_names)
        for skills in member_skills.values()
    )
    if quality_member_count < conditions["minMembersWithQualitySkill"]:
        reasons.append("拥有优质特技的武将数量未达到要求")
    if reasons:
        return RuleEvaluation(
            False,
            tuple(dict.fromkeys(reasons)),
            {"qualityMemberCount": quality_member_count},
        )

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
    effective_count = (
        carry_count + strong_count * seven["strongSkillWeight"]
    )

    if seven["specialSkillAutoPass"] and special_count > 0:
        qualified = True
    elif seven["highJobAutoPass"] and job_average >= seven["highJobAverage"]:
        qualified = True
    else:
        minimum = (
            seven["mediumMinEffectiveSkills"]
            if job_average >= seven["normalJobAverage"]
            else seven["lowMinEffectiveSkills"]
        )
        qualified = effective_count >= minimum
        if not qualified:
            reasons.append("有效特技数量未达到当前规则要求")

    return RuleEvaluation(
        qualified,
        tuple(reasons),
        {
            "carryCount": carry_count,
            "strongCount": strong_count,
            "specialCount": special_count,
            "effectiveCount": effective_count,
            "qualityMemberCount": quality_member_count,
            "jobAverage": job_average,
        },
    )
