from __future__ import annotations

import os
import time
from pathlib import Path

import fast_randomizer as fast
from test_direct_native_random import write_absolute
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


def main() -> None:
    save_1 = GAME.parent / "SV" / "SV001.E5S"
    save_20 = GAME.parent / "SV" / "SV020.E5S"
    original = save_1.read_bytes()
    save_1.write_bytes(save_20.read_bytes())
    try:
        with fast.HiddenGameSession(GAME) as game:
            time.sleep(2)
            fast.run_native_control(game.pid, ["real-load", "0"])
            print("after-load", state(game.pid))
            fast.run_native_control(game.pid, ["dump-contexts"])
            print(
                Path(os.environ.get("TEMP", "."), "ccz_thread_contexts.log")
                .read_text(errors="replace")
            )
            write_absolute(game.pid, 0x004AC63C, b"\x03")
            fast.run_native_control(
                game.pid,
                [
                    "click",
                    str(game.main_window),
                    "10",
                    "10",
                    "1",
                    "0",
                ],
            )
            time.sleep(1)
            print("after-probe-click", state(game.pid))
            fast.native_wake_game(game.pid, game.main_window, 3000)
            print("after-wake", state(game.pid))
            fast.run_native_control(game.pid, ["trace-random"])
            fast.run_native_control(
                game.pid, ["frame-click", "372", "280"]
            )
            time.sleep(0.8)
            print("after-npc", state(game.pid), fast.read_job_ids(game.pid))
            fast.run_native_control(
                game.pid, ["frame-click", "370", "264"]
            )
            time.sleep(1.5)
            print("after-choice", state(game.pid), fast.read_job_ids(game.pid))
    finally:
        save_1.write_bytes(original)


if __name__ == "__main__":
    main()
