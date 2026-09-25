from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import fast_randomizer as fast


GAME = Path(
    os.environ.get(
        "CCZ_GAME_EXE",
        r"E:\game\ccz\曹操传加强版V2.10.4c"
        r"\曹操传加强版V2.10.4c\Ekd5.exe",
    )
)


def inject(game: fast.HiddenGameSession, *args: str) -> int:
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
        timeout=20,
    )
    print("inject", args, result.returncode, result.stdout.strip())
    return result.returncode


def main() -> None:
    trace = GAME.parent / "ccz_random_trace.log"
    trace.unlink(missing_ok=True)
    with fast.HiddenGameSession(GAME) as game:
        time.sleep(2)
        for address in ("0x0042BF90", "0x0042C223", "0x0044F058"):
            inject(game, "trace-address", address, "1")
            inject(game, "real-load", "19")
            inject(game, "wake", str(game.main_window), "5000")
            time.sleep(0.5)
            print(address, "trace:")
            print(trace.read_text(encoding="utf-16-le", errors="replace")[-5000:])
            trace.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
