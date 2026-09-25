from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from pathlib import Path

import cv2

import fast_randomizer as fast


GAME = Path(
    os.environ.get(
        "CCZ_GAME_EXE",
        r"E:\game\ccz\曹操传加强版V2.10.4c"
        r"\曹操传加强版V2.10.4c\Ekd5.exe",
    )
)

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2


def real_click(x: int, y: int) -> None:
    fast.user32.SetCursorPos(x, y)
    time.sleep(0.15)
    fast.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.12)
    fast.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.5)


def main() -> None:
    os.environ["CCZ_DISABLE_GUARD"] = "1"
    trace_path = GAME.parent / "ccz_random_trace.log"
    trace_path.unlink(missing_ok=True)
    with fast.HiddenGameSession(GAME) as session:
        fast.install(fast.bundle_root())
        import task.CczReRandTask as task_module

        fast.patch_runtime(task_module, session.pid)
        task = task_module.CczReRandTask(0)
        task.initWind()
        if not task.wind.isInitSuccess():
            raise RuntimeError("游戏窗口初始化失败")
        task.loadR0Sv()
        before = fast.read_job_ids(session.pid)
        print(f"random before={before}")
        cv2.imencode(".png", task.wind.getMat())[1].tofile(
            Path(__file__).with_name("trace-before.png")
        )
        fast.run_native_control(session.pid, ["trace-random"])

        cursor = fast.Point()
        fast.user32.GetCursorPos(ctypes.byref(cursor))
        previous = fast.user32.GetForegroundWindow()
        hwnd = task.wind.hwnd
        fast.user32.SetWindowLongW(
            hwnd,
            -20,
            fast.user32.GetWindowLongW(hwnd, -20) & ~0x00080000,
        )
        fast.user32.SetWindowPos(
            hwnd,
            HWND_TOPMOST,
            0,
            0,
            646,
            489,
            SWP_SHOWWINDOW,
        )
        fast.user32.SetForegroundWindow(hwnd)
        fast.user32.SetActiveWindow(hwnd)
        fast.user32.SetFocus(hwnd)
        time.sleep(0.7)
        try:
            real_click(356 + 16, 251 + 29)
            cv2.imencode(".png", task.wind.getMat())[1].tofile(
                Path(__file__).with_name("trace-after-npc.png")
            )
            real_click(240 + 130, 255 + 9)
            time.sleep(2)
            cv2.imencode(".png", task.wind.getMat())[1].tofile(
                Path(__file__).with_name("trace-after-choice.png")
            )
        finally:
            fast.user32.SetCursorPos(cursor.x, cursor.y)
            if previous and fast.user32.IsWindow(previous):
                fast.user32.SetForegroundWindow(previous)
            fast.user32.SetWindowPos(
                hwnd,
                HWND_NOTOPMOST,
                fast.OFFSCREEN_X,
                fast.OFFSCREEN_Y,
                646,
                489,
                SWP_SHOWWINDOW,
            )
        after = fast.read_job_ids(session.pid)
        print(f"random after={after}")
        print(trace_path.read_text("utf-16") if trace_path.exists() else "no trace")


if __name__ == "__main__":
    main()
