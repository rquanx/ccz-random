from __future__ import annotations

import os
import time
from pathlib import Path

import fast_randomizer as fast
from diagnose_dialog_load import child_controls


GAME = Path(
    r"E:\game\ccz\曹操传加强版V2.10.4c"
    r"\曹操传加强版V2.10.4c\Ekd5.exe"
)


def main() -> None:
    os.environ["CCZ_USE_ISOLATED_DESKTOP"] = "1"
    with fast.HiddenGameSession(GAME) as game:
        process = fast.native_open_load_dialog(game.pid)
        time.sleep(2)
        windows = [
            (hwnd, fast.window_class(hwnd), fast.window_text(hwnd))
            for hwnd in fast.process_windows(game.pid, visible_only=False)
        ]
        print(f"windows={windows}")
        for hwnd, class_name, _title in windows:
            if class_name == "#32770":
                print(f"dialog={hwnd} controls={child_controls(hwnd)}")
        process.kill()
        process.wait()


if __name__ == "__main__":
    main()
