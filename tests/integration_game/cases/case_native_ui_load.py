from __future__ import annotations

import ctypes
import os
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


def click_confirmation(pid: int, excluded: set[int]) -> bool:
    for hwnd in fast.process_windows(pid, visible_only=False):
        if hwnd in excluded or fast.window_class(hwnd) != "#32770":
            continue
        button = fast.user32.GetDlgItem(hwnd, 6)
        if not button:
            button = fast.user32.GetDlgItem(hwnd, 1)
        if button:
            fast.user32.SendMessageW(button, 0x00F5, 0, 0)
            return True
    return False


def cursor() -> tuple[int, int]:
    point = fast.Point()
    fast.user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def main() -> None:
    before_cursor = cursor()
    before_foreground = fast.user32.GetForegroundWindow()
    with fast.HiddenGameSession(GAME) as game:
        time.sleep(2)
        print("initial", state(game.pid))
        fast.run_native_control(
            game.pid,
            [
                "silent-click",
                str(game.main_window),
                "530",
                "220",
            ],
        )
        dialog = fast.wait_list_dialog(game.pid, 5)
        print("dialog", dialog)
        if not dialog:
            raise RuntimeError("原生读档窗口未打开")
        fast.run_native_control(game.pid, ["reallist", "19"])
        deadline = time.perf_counter() + 8
        while time.perf_counter() < deadline:
            click_confirmation(game.pid, {game.main_window, dialog})
            if (
                not fast.user32.IsWindow(dialog)
                and fast.user32.IsWindowEnabled(game.main_window)
            ):
                break
            time.sleep(0.05)
        time.sleep(2)
        print("loaded", state(game.pid), fast.read_job_ids(game.pid))
        print(
            "desktop",
            before_cursor,
            cursor(),
            before_foreground,
            fast.user32.GetForegroundWindow(),
        )


if __name__ == "__main__":
    main()
