from __future__ import annotations

import os
import struct
import time
from pathlib import Path

from capstone import CS_ARCH_X86, CS_MODE_32, Cs

import fast_randomizer as fast


CODE_BASE = 0x00400000
CODE_SIZE = 0x00180000
JOB_ADDRESS = fast.MEMORY_BASE + fast.JOB_OFFSET


def main() -> None:
    game = Path(os.environ["CCZ_GAME_EXE"])
    with fast.HiddenGameSession(game) as session:
        time.sleep(2)
        code = fast.read_memory(
            session.pid,
            CODE_BASE - fast.MEMORY_BASE,
            CODE_SIZE,
        )
        for label, value in (
            ("job address", JOB_ADDRESS),
            ("job offset", fast.JOB_OFFSET),
            ("memory base", fast.MEMORY_BASE),
        ):
            pattern = struct.pack("<I", value)
            raw_hits = []
            cursor = 0
            while True:
                cursor = code.find(pattern, cursor)
                if cursor < 0:
                    break
                raw_hits.append(CODE_BASE + cursor)
                cursor += 1
            print(label, [f"{address:#010x}" for address in raw_hits])

        md = Cs(CS_ARCH_X86, CS_MODE_32)
        md.skipdata = True
        instructions = list(md.disasm(code, CODE_BASE))
        references = [
            instruction
            for instruction in instructions
            if any(
                needle in instruction.op_str.casefold()
                for needle in ("503f40", "0x2f40", "501000")
            )
        ]
        for reference in references:
            print(
                f"{reference.address:08X}  "
                f"{reference.mnemonic:8} {reference.op_str}"
            )
        print("context around job offset:")
        for instruction in md.disasm(
            code[0x15E20:0x15F20],
            CODE_BASE + 0x15E20,
        ):
            print(
                f"{instruction.address:08X}  "
                f"{instruction.mnemonic:8} {instruction.op_str}"
            )


if __name__ == "__main__":
    main()
