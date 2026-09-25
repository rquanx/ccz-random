from __future__ import annotations

import os
from pathlib import Path

from capstone import Cs, CS_ARCH_X86, CS_MODE_32


GAME = Path(
    os.environ.get(
        "CCZ_GAME_EXE",
        r"E:\game\ccz\曹操传加强版V2.10.4c"
        r"\曹操传加强版V2.10.4c\Ekd5.exe",
    )
)


def main() -> None:
    data = GAME.read_bytes()
    base = 0x00400000
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = False
    for address in (0x0042383C, 0x0043BFD4, 0x0042C223, 0x0044F058):
        offset = address - base
        print(f"\n### {address:#010x}")
        for instruction in md.disasm(data[offset : offset + 0x180], address):
            print(
                f"{instruction.address:08X} "
                f"{instruction.mnemonic:<8} {instruction.op_str}"
            )


if __name__ == "__main__":
    main()
