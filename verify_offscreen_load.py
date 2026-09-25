from __future__ import annotations

import ctypes
import os
import time
from pathlib import Path

import cv2

import fast_randomizer as fast
from runtime_loader import install


def cursor_position() -> tuple[int, int]:
    point = fast.Point()
    fast.user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def main() -> int:
    game_executable = Path(os.environ["CCZ_GAME_EXE"])
    screenshot = Path(__file__).resolve().parent / "offscreen-slot20.png"
    foreground_before = fast.user32.GetForegroundWindow()
    cursor_before = cursor_position()

    with fast.HiddenGameSession(game_executable) as game:
        install(fast.bundle_root())
        import task.CczReRandTask as task_module

        fast.patch_runtime(task_module, game.pid)
        runner = task_module.CczReRandTask(0)
        runner.initWind()
        if not runner.wind.isInitSuccess():
            raise RuntimeError("游戏窗口初始化失败")
        runner.loadAndConfirm(20)
        time.sleep(1.5)
        jobs = fast.read_job_ids(game.pid)
        frame = runner.wind.getMat()
        if frame is None or frame.size == 0:
            raise RuntimeError("存档载入后截图为空")
        encoded, data = cv2.imencode(".png", frame)
        if not encoded:
            raise RuntimeError("截图编码失败")
        data.tofile(screenshot)

        foreground_after = fast.user32.GetForegroundWindow()
        cursor_after = cursor_position()
        print(f"pid={game.pid}")
        print(f"jobs={jobs}")
        print(f"foreground={foreground_before}->{foreground_after}")
        print(f"cursor={cursor_before}->{cursor_after}")
        print(f"screenshot={screenshot}")
        if fast.window_process_id(foreground_after) == game.pid:
            raise RuntimeError("测试期间游戏取得了前台窗口")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
