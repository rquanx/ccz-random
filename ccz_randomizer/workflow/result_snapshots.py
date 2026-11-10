"""Result transport and history snapshots, independent of Tk and native controls."""
from __future__ import annotations
import datetime as dt
import hashlib
import os
from pathlib import Path
from ccz_randomizer.game_versions import current_game_version
from ccz_randomizer.equipment_snapshot import serialize_equipment


def skill_result_detail(evaluation, members) -> dict:
    member_scores = evaluation.metrics.get("memberSkillScores", {})
    return {
        "qualified": bool(evaluation.qualified),
        "reasons": list(evaluation.reasons),
        "metrics": evaluation.metrics,
        "members": [
            {
                "name": member.name,
                "skills": [skill.name for skill in member.skillList],
                "score": member_scores.get(member.name, 0.0),
            }
            for member in members
        ],
    }



def result_detail_for_runner(
    runner,
    result_slot: int,
    round_index: int,
) -> dict | None:
    outcome = getattr(runner, "_result_outcome", "")
    labels = {
        "job_failed": "兵种不合格",
        "skill_failed": "特技不合格",
        "accepted": "合格",
    }
    label = labels.get(outcome)
    if label is None:
        return None
    return {
        "resultSlot": result_slot,
        "attempt": round_index,
        "status": outcome,
        "label": label,
        "mode": (
            "three"
            if getattr(runner, "_three_person_mode", False)
            else "seven"
        ),
        "job": getattr(runner, "_job_evaluation_detail", None),
        "skill": getattr(runner, "_skill_evaluation_detail", None),
        "schemaVersion": 1,
        "gameVersion": getattr(runner, "_game_version", current_game_version()),
        "slot": result_slot,
        "phase": "randomized",
        "personnel": getattr(runner, "_personnel_snapshot", None),
        "fixedPersonnel": getattr(runner, "_fixed_personnel_snapshot", None),
        "jobTalents": getattr(runner, "_job_talents_snapshot", None),
        "dataCollection": getattr(runner, "_data_collection", {}),
        "equipment": serialize_equipment(runner._equip_info, getattr(runner, "_equip_specials", ()))
        if getattr(runner, "_equip_info", None) is not None else None,
    }



def build_history_result_snapshot(
    runner,
    *,
    result_slot: int,
    accepted_attempt: int,
    round_number: int,
    equip_info,
    save_path: Path,
) -> dict:
    detail = result_detail_for_runner(
        runner,
        result_slot,
        accepted_attempt,
    )
    members = []
    job_members = {
        item.get("name"): item
        for item in ((detail or {}).get("job") or {}).get("members", [])
        if isinstance(item, dict)
    }
    for member in (getattr(runner, "_scored_members", None) or getattr(runner, "_team_members", ())):
        skills = list(getattr(member, "skillList", ()))

        def skill_rows(category: str) -> list[dict]:
            return [
                {
                    "name": str(getattr(skill, "name", "")),
                    "canonicalName": str(
                        getattr(skill, "canonical_name", "")
                    ),
                    "internalId": getattr(
                        skill, "internal_skill_id", None
                    ),
                    "formatType": str(
                        getattr(skill, "skill_format_type", "")
                    ),
                    "parameter": getattr(skill, "skill_parameter", None),
                    "score": float(getattr(skill, "score", 0.0)),
                }
                for skill in skills
                if getattr(skill, "memory_category", "") == category
            ]

        job_row = job_members.get(member.name, {})
        members.append(
            {
                "name": member.name,
                "job": str(
                    job_row.get("job")
                    or getattr(getattr(member, "job", None), "name", "")
                ),
                "jobScore": job_row.get("score"),
                "personalSkills": skill_rows("personal"),
                "jobSkills": skill_rows("job"),
            }
        )

    equipment = serialize_equipment(
        equip_info if equip_info is not None else getattr(runner, "_equip_info", None),
        getattr(runner, "_equip_specials", ()),
    )
    save_bytes = save_path.read_bytes() if save_path.is_file() else b""
    history_save_root = os.environ.get("CCZ_HISTORY_SAVE_ROOT", "").strip()
    history_save_path = (
        Path(history_save_root) / "SV" / save_path.name
        if history_save_root
        else save_path
    )
    snapshot = {
        "schemaVersion": 1,
        "gameVersion": getattr(runner, "_game_version", current_game_version()),
        "phase": "randomized" if getattr(runner, "_personnel_snapshot", None) else "unknown",
        "personnel": getattr(runner, "_personnel_snapshot", None),
        "fixedPersonnel": getattr(runner, "_fixed_personnel_snapshot", None),
        "jobTalents": getattr(runner, "_job_talents_snapshot", None),
        "dataCollection": getattr(runner, "_data_collection", {}),
        "createdAt": dt.datetime.now().astimezone().isoformat(
            timespec="seconds"
        ),
        "roundNumber": round_number,
        "slot": result_slot,
        "acceptedAttempt": accepted_attempt,
        "mode": "three"
        if getattr(runner, "_three_person_mode", False)
        else "seven",
        "detail": detail,
        "members": members,
        "equipment": equipment,
        "save": {
            "path": str(history_save_path),
            "size": len(save_bytes),
            "sha256": hashlib.sha256(save_bytes).hexdigest()
            if save_bytes
            else "",
            "verified": False,
            "verificationError": "",
        },
    }
    from ccz_randomizer.history_members import history_members
    snapshot["members"] = history_members(snapshot)
    return snapshot

