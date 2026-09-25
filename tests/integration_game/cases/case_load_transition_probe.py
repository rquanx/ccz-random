from __future__ import annotations

import os
import time
import ctypes
from pathlib import Path

import fast_randomizer as fast
from runtime_loader import install
from tests.integration_game.cases.case_direct_native_random import (
    write_absolute,
)
from trace_original_flow import read_absolute


GAME = Path(
    os.environ.get(
        "CCZ_GAME_EXE",
        r"E:\game\ccz\曹操传加强版V2.10.4c"
        r"\曹操传加强版V2.10.4c\Ekd5.exe",
    )
)


def snapshot(pid: int) -> dict[str, str]:
    return {
        hex(address): read_absolute(pid, address, size).hex()
        for address, size in (
            (0x0048B4C8, 4),
            (0x004AB020, 1),
            (0x004ABF9C, 4),
            (0x00497738, 4),
            (0x004AC63C, 1),
            (0x00500FFF, 1),
        )
    }


def main() -> None:
    with fast.HiddenGameSession(GAME) as game:
        time.sleep(2)
        write_absolute(game.pid, 0x004AC63C, b"\x03")
        print("before", snapshot(game.pid))
        fast.run_native_control(game.pid, ["real-load", "19"])
        fast.native_wake_game(game.pid, game.main_window, 1200)
        print("after-load", snapshot(game.pid))

        # Probe the game's own transition gate.  This is a diagnostic only;
        # no save data or job memory is modified.
        for value in (0, 1, 2, 3, 10):
            fast.native_mark_load_ready(game.pid, value)
            time.sleep(0.2)
            print("mark-ready", value, snapshot(game.pid))
        write_absolute(game.pid, 0x004AC63C, b"\x03")
        write_absolute(game.pid, 0x00497738, b"\0\0\0\0")
        print("gate-set", snapshot(game.pid))
        try:
            fast.native_dispatch_load_state(game.pid)
        except Exception as exc:
            print("process-state-error", repr(exc))
            import subprocess

            status = subprocess.run(
                [
                    str(fast.native_dir() / "ccz_injector.exe"),
                    str(game.pid),
                    str(fast.native_dir() / "ccz_control.dll"),
                    "status",
                ],
                capture_output=True,
                text=True,
                creationflags=getattr(
                    subprocess, "CREATE_NO_WINDOW", 0
                ),
            )
            print("process-state-status", status.stdout.strip())
        print("after-process", snapshot(game.pid))
        for timer_id in range(0, 16):
            ctypes.windll.user32.PostMessageW(
                game.main_window, 0x0113, timer_id, 0
            )
            time.sleep(0.15)
            current = snapshot(game.pid)
            if current != snapshot(game.pid):
                print("timer", timer_id, current)
            if current["0x4ab020"] == "00":
                print("timer-transition", timer_id, current)
                break
        fast.native_wake_game(game.pid, game.main_window, 3500)
        print("after-wake", snapshot(game.pid))
        print("jobs", fast.read_job_ids(game.pid))


if __name__ == "__main__":
    main()
