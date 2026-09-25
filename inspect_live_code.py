from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from pathlib import Path

from capstone import CS_ARCH_X86, CS_MODE_32, Cs

import fast_randomizer as fast


PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400


def read_process(pid: int, address: int, size: int) -> bytes:
    handle = fast.kernel32.OpenProcess(
        PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid
    )
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
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
        return buffer.raw[: count.value]
    finally:
        fast.kernel32.CloseHandle(handle)


def disassemble(pid: int, address: int, size: int = 512) -> None:
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    print(f"\n### {address:#010x}")
    for instruction in md.disasm(read_process(pid, address, size), address):
        print(
            f"{instruction.address:08X}  "
            f"{instruction.mnemonic:8} {instruction.op_str}"
        )
        if instruction.mnemonic.startswith("ret") and instruction.address > address + 16:
            break


def main() -> None:
    game = Path(os.environ["CCZ_GAME_EXE"])
    with fast.HiddenGameSession(game) as session:
        time.sleep(2)
        for address in (
            0x004103C0,
            0x00410480,
            0x00416D30,
            0x004105FD,
            0x00410870,
            0x004109A0,
            0x00413A80,
            0x00413B00,
            0x004192C0,
            0x00419340,
            0x00417EEA,
            0x004180C1,
            0x0041811F,
            0x004180F9,
            0x0041839A,
            0x0046CFC0,
            0x0046D080,
            0x00429880,
            0x0040DF80,
            0x0042BFC0,
            0x0040E2F0,
            0x0040B84C,
            0x00405696,
            0x0041C460,
            0x00465392,
            0x0041888D,
            0x004189C0,
            0x004189DA,
            0x0040B922,
            0x0040531A,
            0x00425FE3,
            0x00416ABC,
            0x004260E9,
            0x0046931E,
            0x00426075,
            0x004261D8,
            0x00429877,
            0x00429906,
            0x00429B68,
            0x00429D47,
            0x0042C56B,
            0x0042C223,
            0x0044F058,
            0x0042383C,
            0x0043BFD4,
            0x00482718,
            0x0040684D,
            0x0044D0AF,
            0x0044D2CA,
            0x0044A3F6,
            0x0044A971,
            0x00440F00,
            0x004261F4,
            0x0047C173,
            0x0042B841,
            0x0042B851,
            0x0042B700,
            0x0042B800,
            0x0042B81B,
            0x0042B900,
            0x0042BF00,
            0x0042BF90,
            0x0042BD00,
            0x0042BD60,
            0x0042BE00,
            0x0042C000,
            0x0042C1E0,
            0x0042C3F0,
            0x0040D500,
            0x0040D7D0,
            0x0040F100,
            0x0040F144,
            0x0040F1A0,
            0x0040F2A0,
            0x0041C2A0,
            0x0041C460,
            0x0044F1A0,
        ):
            disassemble(session.pid, address)
        vtable = read_process(session.pid, 0x00486668, 128)
        print("\n### vtable")
        for index in range(0, len(vtable), 4):
            target = int.from_bytes(vtable[index : index + 4], "little")
            print(f"{index // 4:02d}: {target:#010x}")


if __name__ == "__main__":
    main()
