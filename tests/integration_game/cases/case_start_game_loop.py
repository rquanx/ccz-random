from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import cv2

import fast_randomizer as fast
from runtime_loader import install
from tools.diagnostics.trace_original_flow import read_absolute
from full_randomizer_normal_load import trigger_random


GAME = Path(
    os.environ.get(
        "CCZ_GAME_EXE",
        r"E:\game\ccz\曹操传加强版V2.10.4c"
        r"\曹操传加强版V2.10.4c\Ekd5.exe",
    )
)


def state(pid: int) -> dict[str, str]:
    return {
        hex(address): read_absolute(pid, address, size).hex()
        for address, size in (
            (0x0048B4C8, 4),
            (0x004AB020, 1),
            (0x004ABF9C, 4),
            (0x00497738, 4),
            (0x004AC63C, 1),
        )
    }


def capture(pid: int, output: Path) -> None:
    install(fast.bundle_root())
    import task.CczReRandTask as task_module

    task = task_module.CczReRandTask(0)
    task.initWind()
    if not task.wind.isInitSuccess():
        print("capture skipped: 游戏窗口初始化失败")
        return
    try:
        cv2.imencode(".png", task.wind.getMat())[1].tofile(output)
    except Exception as exc:
        print(f"capture skipped: {exc}")


def main() -> None:
    with fast.HiddenGameSession(GAME) as game:
        source_save = GAME.parent / "SV" / "SV020.E5S"
        print("initial", state(game.pid), fast.read_job_ids(game.pid))
        if not fast.title_load_verified(
            game.pid,
            fast.SOURCE_TITLE_LIST_INDEX,
            source_save,
        ):
            raise RuntimeError("标题界面读取第20号源存档失败")
        print("loaded", state(game.pid), fast.read_job_ids(game.pid))
        jobs = trigger_random(
            game.pid,
            game.main_window,
            fast.JOB_POSITIONS_R0,
        )
        print("random", state(game.pid), jobs)
        capture(
            game.pid,
            Path(__file__).with_name("start-game-loop-after-load.png"),
        )


if __name__ == "__main__":
    main()
