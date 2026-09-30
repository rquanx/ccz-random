from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import cv2

import fast_randomizer as fast
from runtime_loader import install
from tests.integration_game.cases.case_direct_native_random import (
    write_absolute,
)
from tools.diagnostics.trace_original_flow import read_absolute


GAME = Path(
    os.environ.get(
        "CCZ_GAME_EXE",
        r"E:\game\ccz\曹操传加强版V2.10.4c"
        r"\曹操传加强版V2.10.4c\Ekd5.exe",
    )
)


def main() -> None:
    with fast.HiddenGameSession(GAME) as game:
        time.sleep(2)
        fast.native_direct_load(game.pid, 19)
        install(fast.bundle_root())
        import task.CczReRandTask as task_module

        runner = task_module.CczReRandTask(0)
        runner.initWind()
        injector = fast.native_dir() / "ccz_injector.exe"
        dll = fast.native_dir() / "ccz_control.dll"
        process = subprocess.Popen(
            [str(injector), str(game.pid), str(dll), "tick"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        time.sleep(2)
        try:
            frame = runner.wind.getMat()
            cv2.imencode(".png", frame)[1].tofile(
                Path(__file__).with_name("tick-transition.png")
            )
        except Exception as exc:
            print(f"screenshot-error={exc}")
        print(
            "state="
            + repr(
                {
                    "active": read_absolute(
                        game.pid, 0x004AB020, 1
                    ).hex(),
                    "state": read_absolute(
                        game.pid, 0x0048B4C8, 4
                    ).hex(),
                    "branch": read_absolute(
                        game.pid, 0x00497738, 4
                    ).hex(),
                    "jobs": fast.read_job_ids(game.pid),
                }
            )
        )
        process.terminate()
        process.wait(3)


if __name__ == "__main__":
    main()
