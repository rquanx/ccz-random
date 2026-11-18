"""Record the verified 1104 equipment range table on a private desktop."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import time

from ccz_randomizer.runtime.skill_memory import ProcessMemoryReader
from tests.helpers.desktop import background_desktop
from tests.helpers.game_copy import isolated_game_copy


def audit(source, output):
    digest = hashlib.sha256((source / 'Ekd5.exe').read_bytes()).hexdigest()
    if digest != 'aece85339ff48c24e8d783d2d65766e8c9f7be00bd7389d38a8cad8f7cbd95a5':
        raise ValueError('游戏版本不是已核对的1104夜版')
    with isolated_game_copy(source) as game, background_desktop() as startup:
        process = subprocess.Popen([str(game / 'Ekd5.exe')], cwd=game, startupinfo=startup)
        try:
            time.sleep(2)
            with ProcessMemoryReader(process.pid) as memory:
                table = memory.read(0x40CEE9, 12 * 4)
                branch = memory.read(0x46226C, 15)
                # Native equipment suffix dispatch: code 0x33 indexes this table.
                if branch.hex() != '041a3c337509ff348de9ce4000eb18':
                    raise ValueError('原生穿透范围分派代码不匹配')
                rows = []
                for parameter, (pointer,) in enumerate(struct.iter_unpack('<I', table)):
                    raw = memory.read(pointer, 32).split(b'\0', 1)[0]
                    rows.append(dict(parameter=parameter, pointer=hex(pointer),
                                     bytes=raw.hex(), name=raw.decode('gb18030')))
        finally:
            process.terminate()
            process.wait(timeout=15)
    data = dict(source='1104 title-screen read-only memory; private desktop; isolated game copy',
                executableSha256=digest, tableAddress='0x40CEE9',
                dispatchAddress='0x46226C', dispatchBytes=branch.hex(), entries=rows)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('game', type=Path)
    parser.add_argument('--output', type=Path, default=Path('tests/fixtures/equipment_ranges_1104.json'))
    args = parser.parse_args()
    audit(args.game, args.output)
