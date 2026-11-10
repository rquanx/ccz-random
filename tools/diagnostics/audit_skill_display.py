"""Compare tool names to the game's original x86 formatter, without injection.

Requires the optional diagnostic-only unicorn package. No emulator is bundled
with the app. Captures a private title-screen process; never loads/writes saves.
Only the formatter addresses verified for 2.20-1104-night are supported.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import time


class NativeSkillFormatter:
    def __init__(self, image):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
        from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX

        self.sp, self.ax = UC_X86_REG_ESP, UC_X86_REG_EAX
        self.cx, self.dx = UC_X86_REG_ECX, UC_X86_REG_EDX
        self.uc = Uc(UC_ARCH_X86, UC_MODE_32)
        self.uc.mem_map(0x400000, 0x110000)
        self.uc.mem_write(0x400000, image)
        self.uc.mem_map(0x1000000, 0x10000)
        self.uc.mem_map(0x2000000, 0x10000)
        # The only external call is wsprintfA; emulate its string output.
        self.uc.mem_write(0x4862C0, struct.pack('<I', 0x2000000))
        self.uc.mem_write(0x2000000, b'\xc3')
        self.uc.hook_add(UC_HOOK_CODE, self._printf, begin=0x2000000, end=0x2000000)

    def _string(self, address):
        return bytes(self.uc.mem_read(address, 256)).split(b'\0', 1)[0]

    def _printf(self, uc, _address, _size, _context):
        stack = uc.reg_read(self.sp)
        dest, fmt, *args = struct.unpack('<8I', uc.mem_read(stack + 4, 32))
        values = iter(args)

        def substitute(match):
            if match[0] == b'%%':
                return b'%'
            value = next(values)
            if match[0] == b'%s':
                return self._string(value)
            return str(value if value < 0x80000000 else value - 0x100000000).encode()

        result = re.sub(rb'%s|%d|%%', substitute, self._string(fmt))
        uc.mem_write(dest, result + b'\0')
        uc.reg_write(self.ax, len(result))

    def name(self, base, format_type, parameter):
        uc = self.uc
        raw = base.encode('gb18030')
        if len(raw) > 15:
            raise ValueError('游戏特技名超出 15 字节')
        uc.mem_write(0x2001000, raw.ljust(15, b'\0') + bytes([format_type]))
        uc.mem_write(0x2002000, b'\0' * 256)
        uc.mem_write(0x1000000, b'\0' * 0x10000)
        stack = 0x100F000
        uc.mem_write(stack, struct.pack('<4I', 0x2000100, 0x2002000, 0x2001000, parameter))
        uc.reg_write(self.sp, stack)
        uc.emu_start(0x418D97, 0x2000100, count=10000)
        return self._string(0x2002000).decode('gb18030').strip()

    def effect_suffix(self, code, parameter):
        uc = self.uc
        uc.mem_write(0x1000000, b'\0' * 0x10000)
        uc.mem_write(0x2002000, b'\0' * 256)
        uc.mem_write(0x100F000, struct.pack('<I', 0x2000100))
        for register, value in ((self.sp, 0x100F000), (self.ax, code),
                                (self.cx, parameter), (self.dx, 0x2002000)):
            uc.reg_write(register, value)
        uc.emu_start(0x460509, 0x2000100, count=10000)
        return self._string(uc.reg_read(self.cx)).decode('gb18030').strip()


def audit(game: Path, output: Path):
    from ccz_randomizer.app import HiddenGameSession
    from ccz_randomizer.profiles import load_profile
    from ccz_randomizer.runtime.skill_memory import ProcessMemoryReader, read_skill_memory, format_skill_name

    with HiddenGameSession(game, announce=False) as session:
        time.sleep(1)
        with ProcessMemoryReader(session.pid) as memory:
            image = memory.read(0x400000, 0x110000)
        live = read_skill_memory(session.pid, [0])

    def table(address, stride, count):
        return [image[address - 0x400000 + index * stride:].split(b'\0', 1)[0].decode('gb18030')
                for index in range(count)]

    native = NativeSkillFormatter(image)
    tables = dict(ability_names=table(0x486ADB, 5, 8),
                  ability_short_names=table(0x48EC6A, 3, 6),
                  all_ability_name=table(0x48B3E1, 0, 1)[0])
    source_rows = [dict(id=s.internal_id, baseName=s.base_name, formatType=s.format_type,
                        parameter=s.parameter) for s in live.catalog]
    editor_rows = load_profile().skills['runtimeCatalog']
    strategies = {str(row['parameter']): table(0x4A3E77 + row['parameter'] * 97, 0, 1)[0]
                  for row in [*source_rows, *editor_rows] if row['formatType'] == 7}
    differences = []

    def render(rows):
        result = []
        for row in rows:
            base, kind, parameter = row['baseName'], row['formatType'], row['parameter']
            expected = native.name(base, kind, parameter)
            actual = format_skill_name(base, kind, parameter,
                                       strategy_name=strategies.get(str(parameter), ''), **tables)
            if expected != actual:
                differences.append(dict(row, gameName=expected, toolName=actual))
            result.append(dict(row, name=expected))
        return result

    suffixes = {f'{code:02x}': [native.effect_suffix(code, parameter) for parameter in range(256)]
                for code in (0x1C, 0x51, 0x66, 0x6E, 0x70, 0x7A, 0x7B, 0x7C)}
    report = dict(source='Ekd5.exe 2.20-1104-night, native formatters 0x418D97 / 0x460509 (emulated)',
                  sourceSha256=hashlib.sha256(game.read_bytes()).hexdigest(), tables=tables,
                  strategyNames=strategies, catalog=render(source_rows), editorCatalog=render(editor_rows),
                  differences=differences, effectSuffixes=suffixes)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"Live: {len(source_rows)}; editor: {len(editor_rows)}; mismatches: {len(differences)}")
    return not differences


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--unicorn-path', type=Path)
    args = parser.parse_args()
    if args.unicorn_path:
        sys.path.insert(0, str(args.unicorn_path.resolve()))
    return 0 if audit(args.game, args.output) else 1


if __name__ == '__main__':
    raise SystemExit(main())
