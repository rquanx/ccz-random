from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import fast_randomizer as fast
from trace_original_flow import read_absolute


GAME = Path(
    os.environ.get(
        "CCZ_GAME_EXE",
        r"E:\game\ccz\曹操传加强版V2.10.4c"
        r"\曹操传加强版V2.10.4c\Ekd5.exe",
    )
)


def injector(game: fast.HiddenGameSession, *args: str) -> None:
    result = subprocess.run(
        [
            str(fast.native_dir() / "ccz_injector.exe"),
            str(game.pid),
            str(fast.native_dir() / "ccz_control.dll"),
            *args,
        ],
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        timeout=70,
    )
    print(args, result.returncode, result.stdout.strip(), result.stderr.strip())


def main() -> None:
    log = GAME.parent / "ccz_random_trace.log"
    if log.exists():
        log.unlink()
    with fast.HiddenGameSession(GAME) as game:
        time.sleep(2)
        injector(game, "trace-address", "0x004AC63C", "2")
        fast.run_native_control(game.pid, ["real-load", "19"])
        print(
            "state",
            read_absolute(game.pid, 0x0048B4C8, 4).hex(),
            read_absolute(game.pid, 0x004AB020, 1).hex(),
            read_absolute(game.pid, 0x004ABF9C, 4).hex(),
            read_absolute(game.pid, 0x00497738, 4).hex(),
            read_absolute(game.pid, 0x004AC63C, 1).hex(),
        )
        time.sleep(4)
        if log.exists():
            print(
                log.read_text(encoding="utf-16-le", errors="replace")
                [-20000:]
            )
        else:
            print("trace-log-missing")


if __name__ == "__main__":
    main()
