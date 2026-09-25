from __future__ import annotations

import os
import subprocess
import time
import ctypes
from ctypes import wintypes
from pathlib import Path

import cv2

import fast_randomizer as fast
from runtime_loader import install


def child_controls(hwnd: int) -> list[tuple[int, str, str, int]]:
    rows: list[tuple[int, str, str, int]] = []
    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )

    @callback_type
    def callback(child: int, _param: int) -> bool:
        rows.append(
            (
                child,
                fast.window_class(child),
                fast.window_text(child),
                fast.user32.GetDlgCtrlID(child),
            )
        )
        return True

    fast.user32.EnumChildWindows(hwnd, callback, 0)
    return rows


def read_globals(pid: int) -> dict[str, int]:
    addresses = {
        "loaded": (0x00500FFF, 1),
        "active": (0x004AB020, 1),
        "state": (0x0048B4C8, 4),
        "flags": (0x004ABF9C, 4),
        "branch": (0x00497738, 4),
    }
    handle = fast.kernel32.OpenProcess(
        fast.PROCESS_QUERY_INFORMATION | fast.PROCESS_VM_READ, False, pid
    )
    try:
        result = {}
        for name, (address, size) in addresses.items():
            buffer = ctypes.create_string_buffer(size)
            count = ctypes.c_size_t()
            fast.kernel32.ReadProcessMemory(
                handle,
                ctypes.c_void_p(address),
                buffer,
                size,
                ctypes.byref(count),
            )
            result[name] = int.from_bytes(buffer.raw[:size], "little")
        return result
    finally:
        fast.kernel32.CloseHandle(handle)


def main() -> int:
    game_executable = Path(os.environ["CCZ_GAME_EXE"])
    with fast.RandomScenarioSession(game_executable.parent):
        with fast.HiddenGameSession(game_executable) as game:
            install(fast.bundle_root())
            import task.CczReRandTask as task_module

            fast.patch_runtime(task_module, game.pid)
            runner = task_module.CczReRandTask(0)
            runner.initWind()
            print(f"globals_before={read_globals(game.pid)}")
            game_window = runner.wind.hwnd
            fast.activate_hidden_window(game_window)
            fast.user32.PostMessageW(game_window, 0x0111, 102, 0)
            dialog = fast.wait_list_dialog(game.pid, 3)
            if not dialog:
                raise RuntimeError("读取进度窗口未出现")

            injector = fast.native_dir() / "ccz_injector.exe"
            control_dll = fast.native_dir() / "ccz_control.dll"
            process = subprocess.Popen(
                [
                    str(injector),
                    str(game.pid),
                    str(control_dll),
                    "loadui",
                    "19",
                    "0",
                ],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            completed_at = None
            for tick in range(15):
                windows = [
                    (hwnd, fast.window_class(hwnd), fast.window_text(hwnd))
                    for hwnd in fast.process_windows(
                        game.pid, visible_only=False
                    )
                ]
                dialogs = {
                    hwnd: child_controls(hwnd)
                    for hwnd, class_name, _title in windows
                    if class_name == "#32770"
                }
                if process.poll() is not None and completed_at is None:
                    completed_at = tick
                print(
                    f"tick={tick} injector={process.poll()} "
                    f"jobs={fast.read_job_ids(game.pid)} windows={windows} "
                    f"dialogs={dialogs}"
                )
                if completed_at is not None and tick >= completed_at + 2:
                    break
                time.sleep(1)
            if process.poll() is None:
                process.kill()
                process.wait()
            runner.initWind()
            print(f"globals_after={read_globals(game.pid)}")
            try:
                frame = runner.wind.getMat()
                cv2.imencode(".png", frame)[1].tofile(
                    Path(__file__).with_name("diagnose-after-load.png")
                )
                print("captured=diagnose-after-load.png")
            except Exception as exc:
                print(f"capture_error={type(exc).__name__}: {exc}")
            left, top, _right, _bottom = runner.wind.getRect()
            for name, x, y in (
                ("npc", left + 372, top + 280),
                ("choice", left + 370, top + 264),
            ):
                target, client_x, client_y = fast.deepest_child_at(
                    runner.wind.hwnd, x, y
                )
                print(
                    f"{name}_target={target} "
                    f"class={fast.window_class(target)} "
                    f"client=({client_x},{client_y})"
                )
            fast.native_background_click(
                runner.wind.hwnd, 372, 280, 1, False
            )
            time.sleep(0.5)
            fast.native_background_click(
                runner.wind.hwnd, 370, 264, 1, False
            )
            time.sleep(1)
            print(
                "direct_client_jobs="
                f"{fast.read_job_ids(game.pid)}"
            )
            print(f"startRand={runner.startRand()}")
            print(f"random_jobs={fast.read_job_ids(game.pid)}")
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
