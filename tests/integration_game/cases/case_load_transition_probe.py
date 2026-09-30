from __future__ import annotations

import os
import time
from pathlib import Path

import fast_randomizer as fast
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
        current = snapshot(game.pid)
        if current["0x48b4c8"] != "01000000":
            raise RuntimeError(f"读档状态未进入游戏场景：{current}")
        if any(fast.read_job_ids(game.pid)):
            raise RuntimeError("第20号源存档读档后兵种状态异常")


if __name__ == "__main__":
    main()
