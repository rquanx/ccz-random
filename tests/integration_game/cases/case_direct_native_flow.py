from __future__ import annotations

import os
import time
from pathlib import Path

import cv2
import fast_randomizer as fast
from runtime_loader import install
from trace_original_flow import read_absolute
from tests.integration_game.cases.case_direct_native_random import (
    write_absolute,
)


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


def main() -> None:
    with fast.HiddenGameSession(GAME) as game:
        time.sleep(2)
        # The native load routine only performs its post-load UI
        # transition when the game's modal state byte is 3.
        write_absolute(game.pid, 0x004AC63C, b"\x03")
        fast.native_direct_load(game.pid, 19)
        fast.native_wake_game(game.pid, game.main_window, 8000)
        install(fast.bundle_root())
        import task.CczReRandTask as task_module

        screenshot_task = task_module.CczReRandTask(0)
        screenshot_task.initWind()
        try:
            cv2.imencode(".png", screenshot_task.wind.getMat())[1].tofile(
                Path(__file__).with_name("direct-flow-after-load.png")
            )
        except Exception as exc:
            print(f"screenshot-error={exc}")
        print(f"loaded={state(game.pid)} jobs={fast.read_job_ids(game.pid)}")
        flags = int.from_bytes(
            read_absolute(game.pid, 0x004ABF9C, 4), "little"
        )
        write_absolute(game.pid, 0x004AB020, b"\0")
        write_absolute(
            game.pid,
            0x004ABF9C,
            (flags & ~8).to_bytes(4, "little"),
        )
        fast.native_wake_game(game.pid, game.main_window, 500)
        print(f"normalized={state(game.pid)}")

        fast.patch_runtime(task_module, game.pid)
        runner = task_module.CczReRandTask(0)
        runner.initWind()
        fast.run_native_control(
            game.pid, ["frame-click", "372", "280"]
        )
        print("npc=frame-click")
        time.sleep(1)
        print(f"after_npc={state(game.pid)}")
        fast.run_native_control(
            game.pid, ["frame-click", "370", "264"]
        )
        print("choice=frame-click")
        print(f"random={state(game.pid)} jobs={fast.read_job_ids(game.pid)}")


if __name__ == "__main__":
    main()
