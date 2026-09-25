from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from pathlib import Path

import cv2

import fast_randomizer as fast
from runtime_loader import install


LOAD_SAVE_FUNCTION = 0x0041888D
PROCESS_ALL_NEEDED = (
    0x0002  # PROCESS_CREATE_THREAD
    | 0x0400  # PROCESS_QUERY_INFORMATION
    | 0x0008  # PROCESS_VM_OPERATION
    | 0x0020  # PROCESS_VM_WRITE
    | 0x0010  # PROCESS_VM_READ
)
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x04

fast.kernel32.VirtualAllocEx.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_size_t,
    wintypes.DWORD,
    wintypes.DWORD,
]
fast.kernel32.VirtualAllocEx.restype = ctypes.c_void_p
fast.kernel32.VirtualFreeEx.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_size_t,
    wintypes.DWORD,
]
fast.kernel32.WriteProcessMemory.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
fast.kernel32.CreateRemoteThread.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
]
fast.kernel32.CreateRemoteThread.restype = wintypes.HANDLE


def remote_load(pid: int, slot: int) -> int:
    handle = fast.kernel32.OpenProcess(PROCESS_ALL_NEEDED, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        thread = fast.kernel32.CreateRemoteThread(
            handle,
            None,
            0,
            ctypes.c_void_p(LOAD_SAVE_FUNCTION),
            ctypes.c_void_p(slot),
            0,
            None,
        )
        if not thread:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            wait = fast.kernel32.WaitForSingleObject(thread, 15000)
            if wait != 0:
                raise RuntimeError(f"游戏原生读档函数等待失败: {wait}")
            result = wintypes.DWORD()
            fast.kernel32.GetExitCodeThread(thread, ctypes.byref(result))
            return int(result.value)
        finally:
            fast.kernel32.CloseHandle(thread)
    finally:
        fast.kernel32.CloseHandle(handle)


def main() -> int:
    game_executable = Path(os.environ["CCZ_GAME_EXE"])
    screenshot = Path(__file__).resolve().parent / "direct-load-slot20.png"
    with fast.HiddenGameSession(game_executable) as game:
        fast.native_direct_load(game.pid, 19)
        print("native_direct_load=success")
        fast.native_wake_game(game.pid, game.main_window, 3000)
        time.sleep(1)
        print(f"jobs={fast.read_job_ids(game.pid)}")

        install(fast.bundle_root())
        import task.CczReRandTask as task_module

        fast.patch_runtime(task_module, game.pid)
        runner = task_module.CczReRandTask(0)
        runner.initWind()
        frame = runner.wind.getMat()
        encoded, data = cv2.imencode(".png", frame)
        if encoded:
            data.tofile(screenshot)
            print(f"screenshot={screenshot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
