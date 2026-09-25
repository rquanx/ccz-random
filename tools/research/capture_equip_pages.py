from __future__ import annotations

import os
import time
from pathlib import Path

import cv2

import fast_randomizer as fast
from runtime_loader import install


def save_window(window, output: Path) -> None:
    frame = window.getMat()
    encoded, data = cv2.imencode(".png", frame)
    if not encoded:
        raise RuntimeError(f"无法编码截图：{output}")
    data.tofile(output)


def main() -> int:
    game_executable = Path(os.environ["CCZ_GAME_EXE"]).resolve()
    install(fast.bundle_root())
    import task.CczReRandTask as task_module

    with fast.HiddenGameSession(game_executable) as game:
        fast.patch_runtime(task_module, game.pid)
        runner = task_module.CczReRandTask(0)
        save_path = game_executable.parent / "SV" / "SV001.E5S"
        if not fast.title_load_verified(game.pid, 0, save_path):
            raise RuntimeError("无法读取第 1 号存档")
        time.sleep(0.8)
        runner.initWind()
        save_window(
            runner.wind, Path(__file__).with_name("equip-main-before.png")
        )
        for _attempt in range(3):
            fast.native_wake_game(game.pid, game.main_window, 800)
            runner.openEquip()
            time.sleep(0.8)
            runner.initEquipWind()
            if runner.equipWind.isInitSuccess():
                break
        if not runner.equipWind.isInitSuccess():
            raise RuntimeError("无法打开宝物图鉴")
        save_window(
            runner.equipWind, Path(__file__).with_name("equip-page-1.png")
        )
        left, top, _right, _bottom = runner.equipWind.getRect()
        target, client_x, client_y = fast.deepest_child_at(
            runner.equipWind.hwnd, left + 856, top + 672
        )
        print(
            "scroll-target",
            target,
            fast.window_class(target),
            client_x,
            client_y,
        )
        fast.user32.PostMessageW(target, 0x0115, 3, 0)
        fast.user32.PostMessageW(runner.equipWind.hwnd, 0x0115, 3, 0)
        fast.post_click(
            runner.equipWind.hwnd, left + 856, top + 672
        )
        time.sleep(0.8)
        save_window(
            runner.equipWind, Path(__file__).with_name("equip-page-2.png")
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
