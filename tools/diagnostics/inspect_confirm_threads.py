import os
import subprocess
import time
from pathlib import Path
from ctypes import byref, wintypes

import fast_randomizer as fast

GAME = Path(
    r"E:\game\ccz\曹操传加强版V2.10.4c"
    r"\曹操传加强版V2.10.4c\Ekd5.exe"
)


def main() -> None:
    os.environ["CCZ_USE_ISOLATED_DESKTOP"] = "1"
    with fast.HiddenGameSession(GAME) as game:
        child = subprocess.Popen(
            [
                str(fast.native_dir() / "ccz_injector.exe"),
                str(game.pid),
                str(fast.native_dir() / "ccz_control.dll"),
                "real-load",
                "19",
            ],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        deadline = time.time() + 10
        while time.time() < deadline and child.poll() is None:
            rows = []
            for hwnd in fast.process_windows(game.pid, visible_only=False):
                if fast.window_class(hwnd) == "#32770":
                    thread = wintypes.DWORD()
                    fast.user32.GetWindowThreadProcessId(
                        hwnd, byref(thread)
                    )
                    rows.append(
                        (hwnd, thread.value, fast.window_text(hwnd))
                    )
            print(rows, flush=True)
            time.sleep(0.25)
        if child.poll() is None:
            child.kill()
            child.wait()


if __name__ == "__main__":
    main()
