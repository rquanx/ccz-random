from __future__ import annotations

import ctypes
import os
import subprocess
import time
from pathlib import Path

import fast_randomizer as fast
from inspect_live_code import disassemble


def main() -> None:
    game = Path(os.environ["CCZ_GAME_EXE"])
    with fast.HiddenGameSession(game) as session:
        time.sleep(1)
        result = subprocess.run(
            [
                str(fast.native_dir() / "ccz_injector.exe"),
                str(session.pid),
                str(fast.native_dir() / "ccz_control.dll"),
                "wndproc",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        address = int(result.stdout.strip())
        print(f"wndproc={address:#010x}")
        disassemble(session.pid, address, 4096)


if __name__ == "__main__":
    main()
