from __future__ import annotations

import ctypes
import os
import time
from pathlib import Path

import fast_randomizer as fast
from tools.diagnostics.trace_original_flow import read_absolute


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
        source_save = GAME.parent / "SV" / "SV020.E5S"
        print("initial", state(game.pid))
        if not fast.title_load_verified(
            game.pid,
            fast.SOURCE_TITLE_LIST_INDEX,
            source_save,
        ):
            raise RuntimeError("静默读取第20号源存档失败")
        print("loaded", state(game.pid), fast.read_job_ids(game.pid))
        after_cursor = cursor()
        after_foreground = fast.user32.GetForegroundWindow()
        print(
            "desktop",
            before_cursor,
            after_cursor,
            before_foreground,
            after_foreground,
        )
        if after_cursor != before_cursor:
            raise RuntimeError("静默读档移动了系统鼠标")
        if after_foreground != before_foreground:
            raise RuntimeError("静默读档抢占了前台窗口")


if __name__ == "__main__":
    main()
