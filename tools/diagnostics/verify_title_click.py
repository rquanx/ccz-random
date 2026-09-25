from __future__ import annotations

import os
import time
from pathlib import Path

import cv2

import fast_randomizer as fast
from runtime_loader import install


def main() -> int:
    game_executable = Path(os.environ["CCZ_GAME_EXE"])
    screenshot = Path(__file__).resolve().parent / "title-click.png"
    with fast.HiddenGameSession(game_executable) as game:
        fast.native_background_click(
            game.main_window, 520, 112, 1, False
        )
        fast.native_wake_game(game.pid, game.main_window, 1800)
        install(fast.bundle_root())
        import task.CczReRandTask as task_module

        fast.patch_runtime(task_module, game.pid)
        runner = task_module.CczReRandTask(0)
        runner.initWind()
        frame = runner.wind.getMat()
        encoded, data = cv2.imencode(".png", frame)
        if encoded:
            data.tofile(screenshot)
            print(screenshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
