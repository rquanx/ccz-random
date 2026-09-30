from __future__ import annotations

import ctypes
import os
import time
from pathlib import Path

import fast_randomizer as fast
from runtime_loader import install
from tools.diagnostics.trace_original_flow import read_absolute
from full_randomizer_normal_load import trigger_random


GAME = Path(
    os.environ.get(
        "CCZ_GAME_EXE",
        r"E:\game\ccz\曹操传加强版V2.10.4c"
        r"\曹操传加强版V2.10.4c\Ekd5.exe",
    )
)
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_WRITE = 0x0020


def write_absolute(pid: int, address: int, data: bytes) -> None:
    handle = fast.kernel32.OpenProcess(
        fast.PROCESS_QUERY_INFORMATION
        | PROCESS_VM_OPERATION
        | PROCESS_VM_WRITE,
        False,
        pid,
    )
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        buffer = ctypes.create_string_buffer(data)
        count = ctypes.c_size_t()
        if not fast.kernel32.WriteProcessMemory(
            handle,
            ctypes.c_void_p(address),
            buffer,
            len(data),
            ctypes.byref(count),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        fast.kernel32.CloseHandle(handle)


def main() -> None:
    with fast.HiddenGameSession(GAME) as game:
        source_save = GAME.parent / "SV" / "SV020.E5S"
        if not fast.title_load_verified(
            game.pid,
            fast.SOURCE_TITLE_LIST_INDEX,
            source_save,
        ):
            raise RuntimeError("原生随机测试读取第20号源存档失败")

        install(fast.bundle_root())
        import task.CczReRandTask as task_module

        before = fast.read_job_ids(game.pid)
        after = trigger_random(
            game.pid,
            game.main_window,
            fast.JOB_POSITIONS_R0,
        )
        print(f"jobs={before}->{after}")
        if after == before or not any(after):
            raise RuntimeError("原生读档状态恢复后仍未触发随机")


if __name__ == "__main__":
    main()
