from __future__ import annotations

import json
import hashlib
import os
import struct
import time
from collections import Counter
from pathlib import Path

import fast_randomizer as fr
from runtime_loader import install
from ccz_randomizer.runtime.skill_memory import (
    JOB_ID_OFFSET,
    MEMBER_ID_OFFSET,
    ProcessMemoryReader,
    RECORD_ARRAY_BASE_POINTER_ADDRESS,
    RECORD_SIZE,
    SKILL_RULE_COUNT,
    SKILL_RULE_STRIDE,
    SKILL_RULE_TABLE_POINTER_ADDRESS,
    normalize_skill_name,
    read_skill_memory,
)
from tools.project_paths import APP_RESOURCES_DIR, ARTIFACTS_DIR


GAME_DIR = Path(
    r"E:\game\ccz\曹操传加强版V2.10.4c\曹操传加强版V2.10.4c"
)
GAME_EXE = GAME_DIR / "Ekd5.exe"
OUTPUT = ARTIFACTS_DIR / "skill-ground-truth"
S00_PATHS = (
    GAME_DIR / "S_00.eex",
    GAME_DIR / "RS" / "S_00.eex",
)
RANDOM_S00 = APP_RESOURCES_DIR / "random_s00.eex"
REFERENCE_SAVE = GAME_DIR / "随即工具" / "1" / "SV001.E5S"


def find_job(models, name: str):
    for job in models.CCZ_MODELS.jobs:
        if job.name == name:
            return job
    raise LookupError(name)


def main() -> None:
    slot = int(os.environ.get("CCZ_PROBE_SLOT", "1"))
    member_count = int(os.environ.get("CCZ_PROBE_MEMBER_COUNT", "7"))
    save_path = GAME_DIR / "SV" / f"SV{slot:03}.E5S"
    if not save_path.is_file():
        raise FileNotFoundError(save_path)

    OUTPUT.mkdir(exist_ok=True)
    install(fr.bundle_root())
    import models.CczModels as models
    import task.CczReRandTask as task_module
    from window.CczWindow import CczPeopleInfoWindow

    original_s00 = {
        path: path.read_bytes() for path in S00_PATHS if path.is_file()
    }
    original_save = save_path.read_bytes()
    original_hash = {
        path: hashlib.sha256(data).hexdigest()
        for path, data in original_s00.items()
    }
    started = time.perf_counter()
    try:
        for path in S00_PATHS:
            path.write_bytes(RANDOM_S00.read_bytes())
        if os.environ.get("CCZ_PROBE_REFERENCE", "1") == "1":
            save_path.write_bytes(REFERENCE_SAVE.read_bytes())

        with fr.HiddenGameSession(GAME_EXE) as game:
            fr.patch_runtime(task_module, game.pid)
            runner = task_module.CczReRandTask(slot - 1)
            runner.savePos = slot
            runner.is2_08 = False
            if not fr.title_load_verified(game.pid, slot - 1, save_path):
                raise RuntimeError(f"第 {slot} 号存档读取失败")
            fr.native_wake_game(game.pid, game.main_window, 1800)
            time.sleep(2.0)

            ids = fr.read_job_ids(game.pid, fr.JOB_POSITIONS_R1)
            for member, job_id in zip(task_module.TEAM_MEMBER_LIST, ids):
                job_name = fr.JOB_MAP[job_id][0]
                member.job = find_job(models, job_name)

            memory_snapshot = read_skill_memory(
                game.pid,
                fr.JOB_POSITIONS_R1,
            )
            with ProcessMemoryReader(game.pid) as memory_reader:
                rule_table_base = struct.unpack(
                    "<I",
                    memory_reader.read(
                        SKILL_RULE_TABLE_POINTER_ADDRESS,
                        4,
                    ),
                )[0]
                rule_table = memory_reader.read(
                    rule_table_base,
                    SKILL_RULE_COUNT * SKILL_RULE_STRIDE,
                )
                record_array_base = struct.unpack(
                    "<I",
                    memory_reader.read(
                        RECORD_ARRAY_BASE_POINTER_ADDRESS,
                        4,
                    ),
                )[0]
                records = memory_reader.read(
                    record_array_base,
                    (max(fr.JOB_POSITIONS_R1) + 1) * RECORD_SIZE,
                )
            task_module.TEAM_MEMBER_LIST = (
                task_module.TEAM_MEMBER_LIST[:member_count]
            )
            runner.initWind()
            if not runner.wind.isInitSuccess():
                raise RuntimeError("主窗口初始化失败")
            runner.openPeople()
            fr.native_wake_game(game.pid, game.main_window, 1500)
            time.sleep(1.0)
            runner.initPeopleWind()
            if not runner.peopleWind.isInitSuccess():
                raise RuntimeError("部队情报一览窗口打开失败")

            model_ids = {
                skill.name: index
                for index, skill in enumerate(models.CCZ_MODELS.skills)
            }
            ui_slot_samples = []
            original_get_skill_mats = CczPeopleInfoWindow.getSkillMatList
            original_get_all_skill_mat = CczPeopleInfoWindow.getAllSkillMat

            def capture_skill_slots(window):
                mats = original_get_skill_mats(window)
                slots = []
                for slot_index, mat in enumerate(mats):
                    skill = task_module.CczUtils.getCczSkillWithMat(mat)
                    slots.append(
                        {
                            "slot": slot_index + 1,
                            "category": (
                                "personal" if slot_index < 3 else "job"
                            ),
                            "model_id": (
                                model_ids.get(skill.name)
                                if skill is not None
                                else None
                            ),
                            "name": (
                                skill.name if skill is not None else None
                            ),
                        }
                    )
                ui_slot_samples.append(slots)
                return mats

            def capture_skill_panel(window):
                panel = original_get_all_skill_mat(window)
                fr.write_cv_image(
                    OUTPUT
                    / f"slot-{slot:03}-member-{len(ui_slot_samples)}.png",
                    panel,
                )
                return panel

            CczPeopleInfoWindow.getSkillMatList = capture_skill_slots
            CczPeopleInfoWindow.getAllSkillMat = capture_skill_panel
            render_started = time.perf_counter()
            try:
                runner._getTeamSkillsInfo()
            finally:
                CczPeopleInfoWindow.getSkillMatList = original_get_skill_mats
                CczPeopleInfoWindow.getAllSkillMat = original_get_all_skill_mat
            render_seconds = time.perf_counter() - render_started
            panel_path = OUTPUT / f"slot-{slot:03}-panels.png"
            panel_mat = getattr(runner, "teamJobAndSkillInfoMat", None)
            if panel_mat is not None:
                fr.write_cv_image(panel_path, panel_mat)
            ui_skills = [
                [skill.name for skill in member.skillList]
                for member in task_module.TEAM_MEMBER_LIST
            ]
            memory_skills = [
                {
                    "personal": [
                        skill.display_name for skill in member.personal
                    ],
                    "job": [skill.display_name for skill in member.job],
                    "personal_ids": [
                        skill.internal_id for skill in member.personal
                    ],
                    "job_ids": [
                        skill.internal_id for skill in member.job
                    ],
                    "personal_rule_hex": {
                        str(skill.internal_id): rule_table[
                            skill.internal_id * SKILL_RULE_STRIDE
                            : (skill.internal_id + 1) * SKILL_RULE_STRIDE
                        ].hex()
                        for skill in member.personal
                    },
                    "all_personal_candidates": [
                        skill_id
                        for skill_id in range(SKILL_RULE_COUNT)
                        if member.record_index
                        in struct.unpack_from(
                            "<HHH",
                            rule_table,
                            skill_id * SKILL_RULE_STRIDE,
                        )
                    ],
                    "member_id_personal_candidates": [
                        skill_id
                        for skill_id in range(SKILL_RULE_COUNT)
                        if member.member_id
                        in struct.unpack_from(
                            "<HHH",
                            rule_table,
                            skill_id * SKILL_RULE_STRIDE,
                        )
                    ],
                    "comparison_names": [
                        skill.display_name
                        for skill in member.personal + member.job
                    ],
                }
                for member in memory_snapshot.members
            ]
            result = {
                "slot": slot,
                "jobs": list(ids),
                "render_seconds": render_seconds,
                "panel_path": str(panel_path) if panel_mat is not None else "",
                "memory_skills": memory_skills,
                "records": [
                    {
                        "record_index": record_index,
                        "member_id": struct.unpack_from(
                            "<I",
                            records,
                            record_index * RECORD_SIZE + MEMBER_ID_OFFSET,
                        )[0],
                        "job_id": records[
                            record_index * RECORD_SIZE + JOB_ID_OFFSET
                        ],
                        "hex": records[
                            record_index * RECORD_SIZE
                            : (record_index + 1) * RECORD_SIZE
                        ].hex(),
                    }
                    for record_index in fr.JOB_POSITIONS_R1
                ],
                "memory_matches_ui": [
                    (
                        Counter(
                            normalize_skill_name(name)
                            for name in memory["comparison_names"]
                        )
                        == Counter(
                            normalize_skill_name(name) for name in ui
                        )
                    )
                    for memory, ui in zip(memory_skills, ui_skills)
                ],
                "ui_slots": ui_slot_samples,
                "members": [
                    {
                        "name": member.name,
                        "job": member.job.name,
                        "skills": [
                            {
                                "name": skill.name,
                                "score": skill.score,
                                "type": skill.type.value,
                            }
                            for skill in member.skillList
                        ],
                    }
                    for member in task_module.TEAM_MEMBER_LIST
                ],
                "memory_6800": fr.read_memory(game.pid, 0x6800, 0x800).hex(),
                "total_seconds": time.perf_counter() - started,
            }
            runner.closePeopleWindow()
    finally:
        for path, data in original_s00.items():
            path.write_bytes(data)
            if hashlib.sha256(path.read_bytes()).hexdigest() != original_hash[path]:
                raise RuntimeError(f"{path} 恢复校验失败")
        save_path.write_bytes(original_save)

    output = OUTPUT / f"slot-{slot:03}.json"
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"输出: {output}")


if __name__ == "__main__":
    main()
