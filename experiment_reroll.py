from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

from runtime_loader import install


EXTRACTED_ROOT = Path(
    r"C:\Users\91658\Documents\Codex\2026-09-18\hi\work"
    r"\exe-analysis\tool.exe_extracted"
)
MEMORY_BASE = 0x00501000
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
kernel32.ReadProcessMemory.restype = wintypes.BOOL


def read_region(pid: int, offset: int, size: int) -> bytes:
    handle = kernel32.OpenProcess(
        PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid
    )
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        buffer = ctypes.create_string_buffer(size)
        count = ctypes.c_size_t()
        if not kernel32.ReadProcessMemory(
            handle,
            ctypes.c_void_p(MEMORY_BASE + offset),
            buffer,
            size,
            ctypes.byref(count),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return buffer.raw[: count.value]
    finally:
        kernel32.CloseHandle(handle)


def job_names(task, count: int) -> list[str]:
    task.initPeopleWind()
    mats = task.peopleWind.getJobMatList(count)
    return [
        getattr(task_module.CczUtils.getCczJobWithMat(mat), "name", "UNKNOWN")
        for mat in mats
    ]


if __name__ == "__main__":
    pid = int(sys.argv[1])
    install(EXTRACTED_ROOT)
    import task.CczReRandTask as task_module
    from window.BaseWindow import BaseWindow

    def set_foreground(self) -> None:
        ctypes.windll.user32.ShowWindow(self.hwnd, 9)
        ctypes.windll.user32.SetForegroundWindow(self.hwnd)
        time.sleep(0.15)

    BaseWindow.setForeground = set_foreground

    task = task_module.CczReRandTask(0)
    task.savePos = 1
    task.is2_08 = False

    print("load slot 20")
    task.closePeopleWindow()
    task.loadR0Sv()
    for round_no in range(1, 4):
        started = time.perf_counter()
        task.startRand()
        task.openPeople()
        time.sleep(0.5)
        names = job_names(task, 3)
        memory = read_region(pid, 0x2F40, 0x2B0)
        print(
            f"round={round_no} jobs={names} "
            f"memory={memory[:32].hex()} elapsed={time.perf_counter()-started:.2f}s"
        )
        task.closePeopleWindow()
