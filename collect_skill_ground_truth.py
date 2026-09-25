from __future__ import annotations

import json
import hashlib
import os
import time
from pathlib import Path

import fast_randomizer as fr
from runtime_loader import install


GAME_DIR = Path(
    r"E:\game\ccz\曹操传加强版V2.10.4c\曹操传加强版V2.10.4c"
)
GAME_EXE = GAME_DIR / "Ekd5.exe"
OUTPUT = Path(__file__).resolve().parent / "skill-ground-truth"
S00_PATHS = (
    GAME_DIR / "S_00.eex",
    GAME_DIR / "RS" / "S_00.eex",
)
RANDOM_S00 = Path(__file__).resolve().parent / "random_s00.eex"
REFERENCE_SAVE = GAME_DIR / "随即工具" / "1" / "SV001.E5S"


def find_job(models, name: str):
    for job in models.CCZ_MODELS.jobs:
        if job.name == name:
            return job
    raise LookupError(name)


def main() -> None:
    slot = int(os.environ.get("CCZ_PROBE_SLOT", "1"))
    save_path = GAME_DIR / "SV" / f"SV{slot:03}.E5S"
    if not save_path.is_file():
        raise FileNotFoundError(save_path)

    OUTPUT.mkdir(exist_ok=True)
    install(fr.bundle_root())
    import models.CczModels as models
    import task.CczReRandTask as task_module

    original_s00 = {path: path.read_bytes() for path in S00_PATHS}
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

            runner.initWind()
            if not runner.wind.isInitSuccess():
                raise RuntimeError("主窗口初始化失败")
            runner.openPeople()
            fr.native_wake_game(game.pid, game.main_window, 1500)
            time.sleep(1.0)
            runner.initPeopleWind()
            if not runner.peopleWind.isInitSuccess():
                raise RuntimeError("部队情报一览窗口打开失败")

            render_started = time.perf_counter()
            runner._getTeamSkillsInfo()
            render_seconds = time.perf_counter() - render_started
            result = {
                "slot": slot,
                "jobs": list(ids),
                "render_seconds": render_seconds,
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
