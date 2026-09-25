from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import fast_randomizer as fast
from trace_original_flow import read_absolute
from runtime_loader import install


GAME = Path(
    os.environ.get(
        "CCZ_GAME_EXE",
        r"E:\game\ccz\曹操传加强版V2.10.4c"
        r"\曹操传加强版V2.10.4c\Ekd5.exe",
    )
)


def main() -> None:
    run_test()


def run_test() -> None:
    save_1 = GAME.parent / "SV" / "SV001.E5S"
    save_20 = GAME.parent / "SV" / "SV020.E5S"
    original = save_1.read_bytes()
    save_1.write_bytes(save_20.read_bytes())
    try:
        with fast.HiddenGameSession(GAME) as game:
            time.sleep(2)
            fast.run_native_control(game.pid, ["real-load", "0"])
            fast.native_wake_game(
                game.pid, game.main_window, 1500
            )
            for _ in range(5):
                state = read_absolute(game.pid, 0x0048B4C8, 4)
                active = read_absolute(game.pid, 0x004AB020, 1)
                print(
                    f"post-load state={state.hex()} active={active.hex()} "
                    + repr(
                        [
                            (
                                fast.window_class(hwnd),
                                fast.window_text(hwnd),
                            )
                            for hwnd in fast.process_windows(
                                game.pid, visible_only=False
                            )
                        ]
                    )
                )
                if state == b"\x01\x00\x00\x00":
                    break
                fast.native_game_tick(game.pid)
                fast.native_wake_game(game.pid, game.main_window, 1000)
                time.sleep(0.3)

            try:
                fast.native_process_load_state(game.pid)
            except RuntimeError as exc:
                print(f"process-state-return={exc}")
                status = subprocess.run(
                    [
                        str(fast.native_dir() / "ccz_injector.exe"),
                        str(game.pid),
                        str(fast.native_dir() / "ccz_control.dll"),
                        "status",
                    ],
                    capture_output=True,
                    text=True,
                    creationflags=getattr(
                        subprocess, "CREATE_NO_WINDOW", 0
                    ),
                )
                print(f"process-state-raw={status.stdout.strip()}")
            print(
                "after-process-state="
                + repr(
                    {
                        hex(address): read_absolute(
                            game.pid, address, size
                        ).hex()
                        for address, size in (
                            (0x00492FBC, 4),
                            (0x00496F48, 4),
                            (0x00498058, 4),
                            (0x0049CEE0, 4),
                            (0x004AB020, 1),
                            (0x0048B4C8, 4),
                            (0x00497738, 4),
                            (0x004AC63C, 1),
                        )
                    }
                )
            )
            install(fast.bundle_root())
            import task.CczReRandTask as task_module

            fast.patch_runtime(task_module, game.pid)
            runner = task_module.CczReRandTask(0)
            runner.initWind()
            before = fast.read_job_ids(game.pid)
            print(f"loaded jobs={before}")
            print(
                "loaded state="
                + repr(
                    {
                        hex(address): read_absolute(
                            game.pid, address, size
                        ).hex()
                        for address, size in (
                            (0x00492FBC, 4),
                            (0x00496F48, 4),
                            (0x00498058, 4),
                            (0x0049CEE0, 4),
                            (0x00500FFF, 1),
                            (0x004AB020, 1),
                            (0x0048B4C8, 4),
                            (0x00497738, 4),
                            (0x004AC63C, 1),
                        )
                    }
                )
            )

            print(
                "npc="
                + str(
                    runner.wind.clickNpc(
                        task_module.CczNpc.R0_XUZIJIANG
                    )
                )
            )
            time.sleep(0.8)
            print("choice=" + str(runner.wind.chooseRSelect(1)))
            time.sleep(2)
            after = fast.read_job_ids(game.pid)
            print(f"random jobs={after}")
            if after == before or not any(after):
                raise RuntimeError("独立桌面点击未触发真实随机")
    finally:
        save_1.write_bytes(original)


if __name__ == "__main__":
    main()
