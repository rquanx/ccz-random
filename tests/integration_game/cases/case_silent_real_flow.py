from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import fast_randomizer as fast
from runtime_loader import install
from tools.diagnostics.trace_original_flow import read_absolute


GAME = Path(
    os.environ.get(
        "CCZ_GAME_EXE",
        r"E:\game\ccz\曹操传加强版V2.10.4c"
        r"\曹操传加强版V2.10.4c\Ekd5.exe",
    )
)


def main() -> None:
    save_1 = GAME.parent / "SV" / "SV001.E5S"
    save_20 = GAME.parent / "SV" / "SV020.E5S"
    save_1_original = save_1.read_bytes()
    save_1.write_bytes(save_20.read_bytes())
    try:
        run_test()
    finally:
        save_1.write_bytes(save_1_original)


def run_test() -> None:
    with fast.HiddenGameSession(GAME) as game:
        install(fast.bundle_root())
        import task.CczReRandTask as task_module

        fast.patch_runtime(task_module, game.pid)
        runner = task_module.CczReRandTask(0)
        runner.initWind()
        if not runner.wind.isInitSuccess():
            raise RuntimeError("游戏窗口初始化失败")
        time.sleep(2)
        print("load slot20")
        load_process = fast.native_open_load_dialog(game.pid)
        dialog = fast.wait_list_dialog(game.pid, 5)
        if not dialog:
            load_process.kill()
            raise RuntimeError("后台读档窗口未打开")
        fast.native_load_dialog_item(game.pid, 1)
        try:
            load_process.wait(15)
        except subprocess.TimeoutExpired:
            load_process.kill()
            load_process.wait()
            raise RuntimeError("后台原生读档入口未返回")
        print(
            "post-load windows="
            + repr(
                [
                    (hwnd, fast.window_class(hwnd), fast.window_text(hwnd))
                    for hwnd in fast.process_windows(
                        game.pid, visible_only=False
                    )
                ]
            )
        )
        fast.native_wake_game(game.pid, runner.wind.hwnd, 5000)
        loaded_memory = fast.read_memory(
            game.pid, 0, fast.R0_MEMORY_SIZE
        )
        Path("loaded-row0-memory.bin").write_bytes(loaded_memory)
        time.sleep(2)
        if not game.use_isolated_desktop:
            import cv2

            runner.initWind()
            if runner.wind.isInitSuccess():
                cv2.imencode(".png", runner.wind.getMat())[1].tofile(
                    Path(__file__).with_name(
                        "silent-real-after-load.png"
                    )
                )
        print(f"loaded jobs={fast.read_job_ids(game.pid)}")
        def state() -> dict[str, str]:
            return {
                hex(address): read_absolute(
                    game.pid, address, size
                ).hex()
                for address, size in (
                    (0x00492FBC, 4),
                    (0x00496F48, 4),
                    (0x00498058, 4),
                    (0x0049CEE0, 4),
                    (0x004B2C68, 4),
                    (0x004B2C6C, 4),
                )
            }
        print(f"loaded state={state()}")
        def game_click(x: int, y: int) -> None:
            fast.native_background_click(
                game.main_window, x, y, 1, False
            )

        game_click(372, 280)
        time.sleep(1)
        print(f"after npc state={state()}")
        game_click(370, 264)
        time.sleep(2)
        print(f"random jobs={fast.read_job_ids(game.pid)}")
        print(f"random state={state()}")


if __name__ == "__main__":
    main()
