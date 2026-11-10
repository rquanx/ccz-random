"""Activate a validated data snapshot at an idle GUI boundary.

Workers keep their own process snapshot. The GUI calls this only when no task
or editor is open, so existing forms never mix two revisions.
"""
from __future__ import annotations

import os
from pathlib import Path


def _activate_compatibility(profile):
    from ccz_randomizer import profiles, jobs, game_versions, rule_members, recruitment_catalog
    from ccz_randomizer.rules import config, editor, skill_defaults, skill_scores
    from ccz_randomizer.runtime import skill_memory, personnel_memory
    from ccz_randomizer.workflow import recruitment
    from ccz_randomizer import app

    new_jobs = {p["id"]: (p["name"], p["score"], p["type"]) for p in profile.jobs["jobs"]}
    new_defaults = skill_defaults.profile_skill_defaults(profile.skills)
    new_exclusive = frozenset(profile.skills["exclusive"])
    members = {row["name"]: row["recordIndex"] for row in profile.fixed_entries["members"]}
    members.update({row["name"]: row["recordIndex"] for row in profile.recruitment["people"]})
    all_names = tuple(dict.fromkeys((*rule_members.RULE_MEMBER_NAMES, *members)))
    addresses = {key: profile.address(key) for key in (
        "recordArrayBasePointerAddress", "plannedJobArrayAddress",
        "SKILL_RULE_TABLE_POINTER_ADDRESS", "DIRECT_JOB_MATCH_FLAG_ADDRESS",
        "SKILL_NAME_TABLE_ADDRESS", "ABILITY_SHORT_NAMES_ADDRESS", "ALL_ABILITY_NAME_ADDRESS",
        "ABILITY_NAMES_ADDRESS", "STRATEGY_NAMES_ADDRESS", "SKILL_RULE_COUNT", "SKILL_RULE_STRIDE",
        "SKILL_NAME_RECORD_SIZE", "STRATEGY_RECORD_SIZE")}
    marker = profile.script_rules["recruitmentEnabledMarker"].encode("gb18030")

    # All validation/conversion precedes publication on the Tk thread.
    profiles._PINNED_PROFILE_DIRECTORY = profile.root.name
    jobs.JOB_MAP.clear()
    jobs.JOB_MAP.update(new_jobs)
    skill_defaults.SKILL_DEFAULTS = skill_scores.SKILL_DEFAULTS = new_defaults
    skill_defaults.EXCLUSIVE_SKILLS_22 = editor.EXCLUSIVE_SKILLS_22 = new_exclusive
    skill_scores.DEFAULT_SCORES.clear()
    skill_scores.DEFAULT_SCORES.update({name: score for name, score, _, _ in new_defaults})
    skill_scores.DEFAULT_TYPES.clear()
    skill_scores.DEFAULT_TYPES.update({name: "NONE" if category == "特殊" else kind
                                      for name, _, category, kind in new_defaults})
    rule_members.ALL_RULE_MEMBER_NAMES = config.RULE_MEMBER_NAMES = all_names
    for name in all_names:
        config.DEFAULT_MEMBER_AFFINITY.setdefault(name, {"primaryType": "NONE", "secondaryType": "NONE"})
    recruitment_catalog._bundled_catalog.cache_clear()
    game_versions.APP_DEFAULT_GAME_VERSION = app.APP_DEFAULT_GAME_VERSION = profile.game_version
    game_versions.VALID_GAME_VERSIONS = app.VALID_GAME_VERSIONS = frozenset(
        (*game_versions.VALID_GAME_VERSIONS, profile.game_version))
    os.environ["CCZ_GAME_VERSION"] = profile.game_version
    skill_memory._PROFILE = profile
    app.apply_equipment_profile(profile)
    for key, value in addresses.items():
        if key.isupper():
            setattr(skill_memory, key, value)
    skill_memory.RECORD_ARRAY_BASE_POINTER_ADDRESS = addresses["recordArrayBasePointerAddress"]
    personnel_memory.RECORD_ARRAY_BASE_POINTER_ADDRESS = addresses["recordArrayBasePointerAddress"]
    personnel_memory.PLANNED_JOB_ARRAY_ADDRESS = addresses["plannedJobArrayAddress"]
    app.JOB_OFFSET = addresses["plannedJobArrayAddress"] - app.MEMORY_BASE
    recruitment.RECRUITMENT_ENABLED_MARKER = marker
    for cached in (app.canonical_skill_names, app.model_skill_by_name, app.runtime_skill_catalog_rows):
        cached.cache_clear()
    app._SKILL_SCORE_CATALOG = None
    return profile


def activate_installed_profile(directory: Path):
    """Prepare first, roll back legacy bindings on failure, publish one snapshot."""
    from ccz_randomizer import profiles, jobs, game_versions, rule_members, recruitment_catalog, app
    from ccz_randomizer.rules import config, editor, skill_defaults, skill_scores
    from ccz_randomizer.runtime import skill_memory, personnel_memory
    from ccz_randomizer.workflow import recruitment
    from ccz_randomizer.profile_context import ProfileContext, publish_context

    profile = profiles.load_profile(app_directory=directory)
    context = ProfileContext.from_profile(profile)
    modules = (profiles, jobs, game_versions, rule_members, recruitment_catalog, app,
               config, editor, skill_defaults, skill_scores, skill_memory, personnel_memory, recruitment)
    bindings = {module: dict(vars(module)) for module in modules}
    mutable = [jobs.JOB_MAP, skill_scores.DEFAULT_SCORES, skill_scores.DEFAULT_TYPES,
               config.DEFAULT_MEMBER_AFFINITY]
    previous_maps = [(value, dict(value)) for value in mutable]
    previous_version = os.environ.get("CCZ_GAME_VERSION")
    try:
        _activate_compatibility(profile)
    except Exception:
        for value, previous in previous_maps:
            value.clear()
            value.update(previous)
        for module, previous in bindings.items():
            for key in set(vars(module)) - set(previous):
                delattr(module, key)
            for key, value in previous.items():
                if vars(module).get(key) is not value:
                    setattr(module, key, value)
        if previous_version is None:
            os.environ.pop("CCZ_GAME_VERSION", None)
        else:
            os.environ["CCZ_GAME_VERSION"] = previous_version
        raise
    publish_context(context)
    return profile
