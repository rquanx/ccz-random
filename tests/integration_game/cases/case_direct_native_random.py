from __future__ import annotations

import ctypes
import os
import time
from pathlib import Path

import fast_randomizer as fast
from runtime_loader import install
from trace_original_flow import read_absolute


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
        time.sleep(2)
        fast.native_direct_load(game.pid, 19)
        flags = int.from_bytes(
            read_absolute(game.pid, 0x004ABF9C, 4), "little"
        )
        print(
            "after_load="
            + repr(
                {
                    "active": read_absolute(
                        game.pid, 0x004AB020, 1
                    ).hex(),
                    "state": read_absolute(
                        game.pid, 0x0048B4C8, 4
                    ).hex(),
                    "flags": hex(flags),
                    "jobs": fast.read_job_ids(game.pid),
                }
            )
        )
        write_absolute(game.pid, 0x004AB020, b"\0")
        write_absolute(
            game.pid,
            0x004ABF9C,
            (flags & ~8).to_bytes(4, "little"),
        )
        fast.native_wake_game(game.pid, game.main_window, 1500)

        install(fast.bundle_root())
        import task.CczReRandTask as task_module

        fast.patch_runtime(task_module, game.pid)
        runner = task_module.CczReRandTask(0)
        runner.initWind()
        before = fast.read_job_ids(game.pid)
        for event_type, event_value in (
            (0, 0),
            (0, 0),
            (1, 1),
            (0, 0),
        ):
            fast.run_native_control(
                game.pid,
                ["event", str(event_type), str(event_value)],
            )
            print(
                f"event={event_type},{event_value}; "
                f"jobs={fast.read_job_ids(game.pid)}; "
                f"flags={read_absolute(game.pid, 0x004ABF9C, 4).hex()}"
            )
            time.sleep(0.4)
        result = any(fast.read_job_ids(game.pid))
        after = fast.read_job_ids(game.pid)
        print(f"startRand={result}; jobs={before}->{after}")
        if not result or after == before or not any(after):
            raise RuntimeError("原生读档状态恢复后仍未触发随机")


if __name__ == "__main__":
    main()
