from __future__ import annotations

import ctypes
import os
import subprocess
import time
from ctypes import wintypes
from pathlib import Path

import cv2
from capstone import CS_ARCH_X86, CS_MODE_32, Cs

import fast_randomizer as fast
from runtime_loader import install


GAME = Path(
    os.environ.get(
        "CCZ_GAME_EXE",
        r"E:\game\ccz\曹操传加强版V2.10.4c"
        r"\曹操传加强版V2.10.4c\Ekd5.exe",
    )
)


def wait_for_game_window(pid: int, timeout: float = 15) -> int:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        hwnd = fast.find_process_window_by_class(pid, "SOUSOU")
        if hwnd:
            return hwnd
        time.sleep(0.05)
    raise RuntimeError("游戏窗口启动超时")


def read_runtime_globals(pid: int) -> dict[str, int]:
    values = {}
    handle = fast.kernel32.OpenProcess(
        fast.PROCESS_QUERY_INFORMATION | fast.PROCESS_VM_READ,
        False,
        pid,
    )
    try:
        for name, address, size in (
            ("loaded", 0x00500FFF, 1),
            ("active", 0x004AB020, 1),
            ("state", 0x0048B4C8, 4),
            ("flags", 0x004ABF9C, 4),
            ("branch", 0x00497738, 4),
        ):
            buffer = ctypes.create_string_buffer(size)
            count = ctypes.c_size_t()
            fast.kernel32.ReadProcessMemory(
                handle,
                ctypes.c_void_p(address),
                buffer,
                size,
                ctypes.byref(count),
            )
            values[name] = int.from_bytes(buffer.raw, "little")
    finally:
        fast.kernel32.CloseHandle(handle)
    return values


def read_absolute(pid: int, address: int, size: int) -> bytes:
    handle = fast.kernel32.OpenProcess(
        fast.PROCESS_QUERY_INFORMATION | fast.PROCESS_VM_READ,
        False,
        pid,
    )
    try:
        buffer = ctypes.create_string_buffer(size)
        count = ctypes.c_size_t()
        if not fast.kernel32.ReadProcessMemory(
            handle,
            ctypes.c_void_p(address),
            buffer,
            size,
            ctypes.byref(count),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return buffer.raw
    finally:
        fast.kernel32.CloseHandle(handle)


def dump_code(pid: int, address: int, size: int) -> str:
    decoder = Cs(CS_ARCH_X86, CS_MODE_32)
    decoder.skipdata = True
    return "\n".join(
        f"{instruction.address:08X}  "
        f"{instruction.mnemonic:8} {instruction.op_str}"
        for instruction in decoder.disasm(
            read_absolute(pid, address, size), address
        )
    )


def main() -> None:
    if fast.find_process_id(fast.GAME_EXE_NAME) is not None:
        raise RuntimeError("请先关闭已运行的游戏")
    trace_path = GAME.parent / "ccz_random_trace.log"
    trace_path.unlink(missing_ok=True)
    dialog_trace_path = GAME.parent / "ccz_dialog_trace.log"
    dialog_trace_path.unlink(missing_ok=True)
    previous_foreground = fast.user32.GetForegroundWindow()
    cursor = fast.Point()
    fast.user32.GetCursorPos(ctypes.byref(cursor))
    save_1 = GAME.parent / "SV" / "SV001.E5S"
    save_20 = GAME.parent / "SV" / "SV020.E5S"
    save_1_original = save_1.read_bytes() if save_1.exists() else None
    save_1.write_bytes(save_20.read_bytes())
    process = subprocess.Popen(
        [str(GAME)],
        cwd=str(GAME.parent),
    )
    try:
        wait_for_game_window(process.pid)
        time.sleep(3)
        install(fast.bundle_root())
        import task.CczReRandTask as task_module

        runner = task_module.CczReRandTask(0)
        runner.initWind()
        print(f"globals_before={read_runtime_globals(process.pid)}")
        fast.run_native_control(process.pid, ["trace-dialog"])
        fast.run_native_control(process.pid, ["trace-load"])
        game_rect = wintypes.RECT()
        fast.user32.GetWindowRect(
            runner.wind.hwnd, ctypes.byref(game_rect)
        )
        dialog = 0
        for _attempt in range(5):
            fast.user32.SetForegroundWindow(runner.wind.hwnd)
            fast.user32.SetCursorPos(
                game_rect.left + 530, game_rect.top + 220
            )
            fast.user32.mouse_event(0x0002, 0, 0, 0, 0)
            fast.user32.mouse_event(0x0004, 0, 0, 0, 0)
            dialog = fast.wait_list_dialog(process.pid, 1)
            if dialog:
                break
        if not dialog:
            raise RuntimeError("读取进度窗口未出现")
        fast.run_native_control(process.pid, ["reallist", "0"])
        deadline = time.perf_counter() + 5
        confirmation = 0
        while time.perf_counter() < deadline:
            for hwnd in fast.process_windows(process.pid):
                if hwnd != dialog and fast.user32.GetDlgItem(hwnd, 6):
                    confirmation = hwnd
                    break
            if confirmation:
                break
            time.sleep(0.05)
        if not confirmation:
            raise RuntimeError("读档确认窗口未出现")
        yes = fast.user32.GetDlgItem(confirmation, 6)
        rect = wintypes.RECT()
        if yes and fast.user32.GetWindowRect(yes, ctypes.byref(rect)):
            fast.user32.SetForegroundWindow(confirmation)
            fast.user32.SetCursorPos(
                (rect.left + rect.right) // 2,
                (rect.top + rect.bottom) // 2,
            )
            fast.user32.mouse_event(0x0002, 0, 0, 0, 0)
            fast.user32.mouse_event(0x0004, 0, 0, 0, 0)
        else:
            fast.click_leftmost_dialog_button(confirmation)
        time.sleep(1)
        fast.native_wake_game(process.pid, runner.wind.hwnd, 2500)
        runner.initWind()
        cv2.imencode(".png", runner.wind.getMat())[1].tofile(
            Path(__file__).with_name("trace-original-after-load.png")
        )
        print(
            "windows="
            + repr(
                [
                    (
                        fast.window_class(hwnd),
                        fast.window_text(hwnd),
                        bool(fast.user32.IsWindowVisible(hwnd)),
                    )
                    for hwnd in fast.process_windows(
                        process.pid, visible_only=False
                    )
                ]
            )
        )
        loaded_memory = fast.read_memory(
            process.pid, 0, fast.R0_MEMORY_SIZE
        )
        source_save = (
            GAME.parent / "SV" / "SV020.E5S"
        ).read_bytes()[: fast.R0_MEMORY_SIZE]
        print(
            "save_memory_diff="
            + str(
                sum(
                    left != right
                    for left, right in zip(
                        loaded_memory, source_save
                    )
                )
            )
        )
        print(f"globals_after={read_runtime_globals(process.pid)}")
        print(f"before={fast.read_job_ids(process.pid)}")
        fast.run_native_control(process.pid, ["trace-random"])
        state_base = 0x0048B000
        state_size = 0x85000
        before_npc = read_absolute(
            process.pid, state_base, state_size
        )
        runner.initWind()
        print(
            "clickNpc="
            + str(
                runner.wind.clickNpc(
                    task_module.CczNpc.R0_XUZIJIANG
                )
            )
        )
        time.sleep(1)
        after_npc = read_absolute(
            process.pid, state_base, state_size
        )
        print(
            "cursor_after_npc="
            + repr(
                tuple(
                    int.from_bytes(
                        read_absolute(process.pid, address, 4),
                        "little",
                        signed=True,
                    )
                    for address in (0x004B2C68, 0x004B2C6C)
                )
            )
        )
        Path("choice-before.bin").write_bytes(before_npc)
        Path("choice-menu.bin").write_bytes(after_npc)
        npc_diff = [
            state_base + index
            for index, (left, right) in enumerate(
                zip(before_npc, after_npc)
            )
            if left != right
        ]
        print(
            "npc_diff="
            + ",".join(hex(value) for value in npc_diff[:200])
        )
        print(
            "choose="
            + str(runner.wind.chooseRSelect(1))
        )
        Path("choice-after.bin").write_bytes(
            read_absolute(process.pid, state_base, state_size)
        )
        time.sleep(1)
        print(
            "cursor_after_choice="
            + repr(
                tuple(
                    int.from_bytes(
                        read_absolute(process.pid, address, 4),
                        "little",
                        signed=True,
                    )
                    for address in (0x004B2C68, 0x004B2C6C)
                )
            )
        )
        print(f"after={fast.read_job_ids(process.pid)}")
        Path("choice-runtime-code.txt").write_text(
            dump_code(process.pid, 0x00429870, 0x800),
            encoding="utf-8",
        )
        if trace_path.exists():
            print(trace_path.read_text("utf-16-le"))
        else:
            print("no trace")
    finally:
        fast.user32.SetCursorPos(cursor.x, cursor.y)
        if previous_foreground and fast.user32.IsWindow(previous_foreground):
            fast.user32.SetForegroundWindow(previous_foreground)
        process.terminate()
        try:
            process.wait(3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        if save_1_original is None:
            save_1.unlink(missing_ok=True)
        else:
            save_1.write_bytes(save_1_original)


if __name__ == "__main__":
    main()
