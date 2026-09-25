from __future__ import annotations

import ctypes
import hashlib
import os
import shutil
import time
from pathlib import Path

import fast_randomizer as fast
from runtime_loader import install


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    game_executable = Path(os.environ["CCZ_GAME_EXE"])
    source_slot = int(os.environ.get("CCZ_SOURCE_SLOT", "20"))
    save_path = game_executable.parent / "SV001.E5S"
    backup_path = Path(__file__).resolve().parent / "SV001.before-test.E5S"
    if save_path.is_file():
        shutil.copy2(save_path, backup_path)
        before_hash = file_hash(save_path)
    else:
        before_hash = ""

    foreground_before = fast.user32.GetForegroundWindow()
    point_before = fast.Point()
    fast.user32.GetCursorPos(ctypes.byref(point_before))

    with fast.HiddenGameSession(game_executable) as game:
        install(fast.bundle_root())
        import task.CczReRandTask as task_module

        fast.patch_runtime(task_module, game.pid)
        runner = task_module.CczReRandTask(0)
        runner.initWind()
        if not runner.wind.isInitSuccess():
            raise RuntimeError("游戏窗口初始化失败")
        fast.native_direct_load(game.pid, source_slot - 1)
        time.sleep(1)
        source_jobs = fast.read_job_ids(game.pid)
        if not runner.startRand():
            raise RuntimeError("随机操作返回失败")
        time.sleep(1.5)
        random_jobs = fast.read_job_ids(game.pid)
        if random_jobs == source_jobs or random_jobs == (0, 0, 0):
            raise RuntimeError(
                f"随机操作未改变兵种内存：{source_jobs}->{random_jobs}"
            )

        scores = tuple(fast.JOB_MAP[job_id][1] for job_id in random_jobs)
        runner.saveAndConfirm(1)
        time.sleep(0.5)
        if not save_path.is_file():
            raise RuntimeError("随机结果没有生成第 1 号存档")
        after_hash = file_hash(save_path)
        if after_hash == before_hash:
            raise RuntimeError("第 1 号存档内容没有变化")

        runner.loadAndConfirm(1)
        time.sleep(0.5)
        saved_jobs = fast.read_job_ids(game.pid)
        if saved_jobs != random_jobs:
            raise RuntimeError(
                f"重新读取第 1 号存档后兵种不一致："
                f"{random_jobs}->{saved_jobs}"
            )

        foreground_after = fast.user32.GetForegroundWindow()
        point_after = fast.Point()
        fast.user32.GetCursorPos(ctypes.byref(point_after))
        print(f"source_jobs={source_jobs}")
        print(f"random_jobs={random_jobs}")
        print(f"scores={scores}")
        print(f"saved_jobs={saved_jobs}")
        print(f"save_hash={before_hash}->{after_hash}")
        print(f"foreground={foreground_before}->{foreground_after}")
        print(
            f"cursor={(point_before.x, point_before.y)}"
            f"->{(point_after.x, point_after.y)}"
        )
        if fast.window_process_id(foreground_after) == game.pid:
            raise RuntimeError("测试结束时游戏仍占据前台")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
