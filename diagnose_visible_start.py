from __future__ import annotations

import ctypes
import os
import subprocess
import time
from pathlib import Path

import fast_randomizer as fast
from trace_original_flow import read_absolute, wait_for_game_window


GAME = Path(
    os.environ.get(
        "CCZ_GAME_EXE",
        r"E:\game\ccz\曹操传加强版V2.10.4c"
        r"\曹操传加强版V2.10.4c\Ekd5.exe",
    )
)


def state(pid: int) -> list[str]:
    return [
        read_absolute(pid, address, size).hex()
        for address, size in (
            (0x0048B4C8, 4),
            (0x004AB020, 1),
            (0x004ABF9C, 4),
            (0x00497738, 4),
            (0x004AC63C, 1),
        )
    ]


def main() -> None:
    previous = fast.user32.GetForegroundWindow()
    process = subprocess.Popen([str(GAME)], cwd=str(GAME.parent))
    try:
        hwnd = wait_for_game_window(process.pid)
        time.sleep(1)
        fast.user32.SetWindowPos(
            hwnd,
            1,
            -3000,
            -3000,
            646,
            489,
            0x0010 | 0x0004 | 0x0040,
        )
        time.sleep(2)
        print("before", state(process.pid))
        fast.run_native_control(process.pid, ["real-load", "19"])
        print("after", state(process.pid))
        fast.native_wake_game(process.pid, hwnd, 4000)
        print("wake", state(process.pid))
    finally:
        process.terminate()
        try:
            process.wait(3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        if previous and fast.user32.IsWindow(previous):
            fast.user32.SetForegroundWindow(previous)


if __name__ == "__main__":
    main()
