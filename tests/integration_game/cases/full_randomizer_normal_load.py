from __future__ import annotations

import os
import time
from pathlib import Path

import fast_randomizer as fast
from runtime_loader import install


def trigger_random(
    pid: int,
    hwnd: int,
    positions: tuple[int, ...],
) -> tuple[int, ...]:
    before = fast.read_job_ids(pid, positions)
    for attempt in range(1, 4):
        fast.native_silent_click(
            pid,
            hwnd,
            fast.XU_CLIENT_POSITION[0],
            fast.XU_CLIENT_POSITION[1],
        )
        time.sleep(0.5)
        current = fast.trigger_random_choice_click(
            pid,
            hwnd,
            positions,
            before,
            attempt,
        )
        deadline = time.perf_counter() + 3
        while time.perf_counter() < deadline:
            current = fast.read_job_ids(pid, positions)
            if current != before and any(current):
                return current
            time.sleep(0.05)
        fast.native_wake_game(pid, hwnd, 900)
    raise RuntimeError(f"连续三次未触发随机：{before}->{current}")


def run(mode: str) -> None:
    game_executable = Path(os.environ["CCZ_GAME_EXE"])
    source_save = game_executable.parent / "SV" / "SV020.E5S"
    positions = (
        fast.JOB_POSITIONS_R0
        if mode == "three"
        else fast.JOB_POSITIONS_R1
    )

    install(fast.bundle_root())
    import task.CczReRandTask as task_module

    with fast.HiddenGameSession(game_executable) as game:
        fast.patch_runtime(
            task_module,
            game.pid,
            three_person_mode=mode == "three",
        )
        runner = task_module.CczReRandTask(0)
        runner.initWind()

        if not fast.title_load_verified(
            game.pid,
            fast.SOURCE_TITLE_LIST_INDEX,
            source_save,
        ):
            raise RuntimeError("标题界面读取第20号存档失败")
        time.sleep(1.5)
        first_jobs = trigger_random(game.pid, game.main_window, positions)

        fast.normal_load_verified(
            game.pid,
            game.main_window,
            20,
            source_save,
            runner.loadAndConfirm,
        )
        time.sleep(1)
        source_jobs = fast.read_job_ids(game.pid, positions)
        if any(source_jobs):
            raise RuntimeError(f"正常读档后源存档兵种未复位：{source_jobs}")
        second_jobs = trigger_random(game.pid, game.main_window, positions)

        fast.normal_load_verified(
            game.pid,
            game.main_window,
            20,
            source_save,
            runner.loadAndConfirm,
        )
        reloaded_jobs = fast.read_job_ids(game.pid, positions)
        if any(reloaded_jobs):
            raise RuntimeError(
                f"第二次正常读档后源存档兵种未复位：{reloaded_jobs}"
            )
        third_jobs = trigger_random(game.pid, game.main_window, positions)

        print(
            f"{mode} 模式正常读档验证通过："
            f"{first_jobs} -> {source_jobs} -> "
            f"{second_jobs} -> {reloaded_jobs} -> {third_jobs}"
        )
