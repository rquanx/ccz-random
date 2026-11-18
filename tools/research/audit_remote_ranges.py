"""Verify equipment range IDs against 1104 native geometry and skill records."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import time

from ccz_randomizer.runtime.skill_memory import ProcessMemoryReader, read_skill_memory
from tests.helpers.desktop import background_desktop
from tests.helpers.game_copy import isolated_game_copy


# Descriptive geometry names, not invented official job or skill names.
GEOMETRY_NAMES = {
    0: '十字1格', 1: '九宫', 2: '菱形2格', 3: '菱形2～3格',
    4: '菱形2～4格', 5: '十字1～2格', 6: '菱形1～2格',
    8: '菱形4～5格', 9: '十字2格', 13: '菱形1～4格',
    14: '3格外框·窄边', 15: '3格外框·去角', 16: '菱形3格',
    17: '菱形3～4格', 18: '菱形3～5格', 22: '方环3～4格·削角',
    23: '斜角1格', 24: '斜角1～2格', 25: '2格外框·去角',
    26: '菱形2～3格·轴向限2格', 27: '斜角2格', 28: '八方向2格',
    30: '十字3格', 31: '十字2～3格', 32: '九宫·加斜角2格',
    33: '菱形1～5格', 34: '方环3～5格·削角', 35: '方环2～3格·削角',
    36: '方形1～2格', 37: '菱形3～6格·轴向限5格',
}


def audit(source, output):
    digest = hashlib.sha256((source / 'Ekd5.exe').read_bytes()).hexdigest()
    if digest != 'aece85339ff48c24e8d783d2d65766e8c9f7be00bd7389d38a8cad8f7cbd95a5':
        raise ValueError('游戏版本不是已核对的1104夜版')
    with isolated_game_copy(source) as game, background_desktop() as startup:
        process = subprocess.Popen([str(game / 'Ekd5.exe')], cwd=game, startupinfo=startup)
        try:
            time.sleep(2)
            catalog = read_skill_memory(process.pid, [0]).catalog
            names = {row.parameter: row.base_name.removeprefix('远距攻击 ')
                     for row in catalog if 159 <= row.internal_id <= 164}
            # Descriptive names derived from the actual symmetric coordinate sets.
            names.update(GEOMETRY_NAMES)
            names.update({10: '全地图', 11: '不追加范围'})
            with ProcessMemoryReader(process.pid) as memory:
                dispatch = memory.read(0x436599, 15)
                bounds = memory.read(0x43657E, 0x2A)
                special10 = memory.read(0x437D10, 0x49)
                axis_expansion = memory.read(0x436692, 0x5D)
                if dispatch.hex() != '3c0b74c5720248488b148500144d00':
                    raise ValueError('范围表分派代码不匹配')
                rows = []
                for parameter, name in sorted(names.items()):
                    if parameter in (10, 11):
                        rows.append(dict(parameter=parameter, name=name,
                                         nameSource='native special branch'))
                        continue
                    index = parameter if parameter < 11 else parameter - 2
                    pointer, = struct.unpack('<I', memory.read(0x4D1400 + index * 4, 4))
                    raw = memory.read(pointer, 512)
                    pairs = []
                    for offset in range(0, 512, 2):
                        pair = list(raw[offset:offset+2])
                        if pair == [255, 255]:
                            break
                        pairs.append(pair)
                    else:
                        raise ValueError('范围坐标缺少终止标记')
                    rows.append(dict(parameter=parameter, name=name, pointer=hex(pointer), pairs=pairs,
                                     bytes=raw[:2*len(pairs)+2].hex(),
                                     nameSource='geometry' if parameter in GEOMETRY_NAMES else 'native skill definition'))
        finally:
            process.terminate()
            process.wait(timeout=15)
    output.write_text(json.dumps(dict(source='1104 isolated title-screen process, private desktop, read-only',
        executableSha256=digest, dispatchAddress='0x436599', dispatchBytes=dispatch.hex(),
        boundsAddress='0x43657e', boundsBytes=bounds.hex(),
        special10Address='0x437d10', special10Bytes=special10.hex(),
        axisExpansionAddress='0x436692', axisExpansionBytes=axis_expansion.hex(),
        tableAddress='0x4D1400', entries=rows), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('game', type=Path)
    parser.add_argument('--output', type=Path, default=Path('tests/fixtures/remote_ranges_1104.json'))
    args = parser.parse_args()
    audit(args.game, args.output)
