from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import cv2

import fast_randomizer as fast
from runtime_loader import install
from trace_original_flow import read_absolute


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
    cv2.imencode(".png", task.wind.getMat())[1].tofile(output)


def main() -> None:
    with fast.HiddenGameSession(GAME) as game:
        time.sleep(2)
        print("initial", state(game.pid), fast.read_job_ids(game.pid))
        fast.native_wake_game(game.pid, game.main_window, 500)
        fast.run_native_control(game.pid, ["title-load", "19"])
        print("loaded", state(game.pid), fast.read_job_ids(game.pid))
        for index in range(10):
            time.sleep(0.5)
            print(
                f"loaded-loop-{index + 1}",
                state(game.pid),
                fast.read_job_ids(game.pid),
            )
        install(fast.bundle_root())
        import task.CczReRandTask as task_module

        fast.run_native_control(game.pid, ["arm-first-choice"])
        for click_index in range(30):
            fast.run_native_control(
                game.pid, ["pulse-click", "372", "280"]
            )
            time.sleep(0.05)
            fast.run_native_control(
                game.pid, ["pulse-click", "370", "264"]
            )
            time.sleep(0.1)
            jobs = fast.read_job_ids(game.pid)
            print(
                f"pulse-{click_index + 1}",
                state(game.pid),
                jobs,
            )
            if any(jobs):
                break
        trace = GAME.parent / "ccz_random_trace.log"
        trace.unlink(missing_ok=True)
        fast.run_native_control(
            game.pid, ["trace-address", "0x0042E092", "1"]
        )
        fast.native_wake_game(game.pid, game.main_window, 1000)
        time.sleep(0.5)
        print(
            "choice-trace",
            trace.read_text(
                encoding="utf-16-le", errors="replace"
            ) if trace.is_file() else "missing",
        )
        capture(
            game.pid,
            Path(__file__).with_name("start-game-loop-after-load.png"),
        )


if __name__ == "__main__":
    main()
