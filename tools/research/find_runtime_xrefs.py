from __future__ import annotations

import os
import time
from pathlib import Path

from capstone import CS_ARCH_X86, CS_MODE_32, CS_OP_IMM, Cs

import fast_randomizer as fast
from tools.diagnostics.inspect_live_code import read_process


GAME = Path(
    os.environ.get(
        "CCZ_GAME_EXE",
        r"E:\game\ccz\曹操传加强版V2.10.4c"
        r"\曹操传加强版V2.10.4c\Ekd5.exe",
    )
)
TEXT_START = 0x00401000
TEXT_END = 0x00485000
TARGETS = {
    0x004024E6,
    0x0040E326,
    0x0042BF54,
    0x0042BF8A,
    0x0042BF90,
    0x0042BFB8,
    0x0042C09E,
    0x00404C7D,
}


def main() -> None:
    with fast.HiddenGameSession(GAME) as session:
        time.sleep(2)
        code = read_process(session.pid, TEXT_START, TEXT_END - TEXT_START)
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        md.detail = True
        md.skipdata = True

        print("direct control-flow references")
        for instruction in md.disasm(code, TEXT_START):
            if (
                instruction.mnemonic.startswith(("call", "j"))
                and instruction.operands
                and instruction.operands[0].type == CS_OP_IMM
                and instruction.operands[0].imm in TARGETS
            ):
                print(
                    f"{instruction.address:08X} "
                    f"{instruction.mnemonic:8} {instruction.op_str}"
                )

        print("\nraw rel32 references")
        for offset in range(len(code) - 5):
            opcode = code[offset]
            if opcode not in (0xE8, 0xE9):
                continue
            source = TEXT_START + offset
            displacement = int.from_bytes(
                code[offset + 1 : offset + 5], "little", signed=True
            )
            target = source + 5 + displacement
            if target in TARGETS:
                print(
                    f"{source:08X} "
                    f"{'call' if opcode == 0xE8 else 'jmp ':8} {target:08X}"
                )


if __name__ == "__main__":
    main()
