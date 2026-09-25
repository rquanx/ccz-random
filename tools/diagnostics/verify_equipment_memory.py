from __future__ import annotations

import json
import os
from pathlib import Path

import fast_randomizer as randomizer
from tools.project_paths import EQUIPMENT_DATA_DIR


KNOWN_OCR_ERRORS = {
    "24:11",
    "33:09",
    "35:12",
    "4a:1c",
}


def save_records(data: bytes) -> tuple[bytes, ...]:
    first = tuple(
        data[0x54D8 + index * 4 : 0x54DC + index * 4]
        for index in range(46)
    )
    second = tuple(
        data[0x5590 + index * 8 : 0x5598 + index * 8]
        for index in range(24)
    )
    return first + second


def main() -> int:
    game_root = Path(
        os.environ.get(
            "CCZ_GAME_ROOT",
            "E:/game/ccz/曹操传加强版V2.10.4c/曹操传加强版V2.10.4c",
        )
    )
    observed = json.loads(
        (EQUIPMENT_DATA_DIR / "equip_effect_map.json").read_text(
            encoding="utf-8"
        )
    )
    mismatches = []
    for key, expected in observed.items():
        code, parameter = (int(part, 16) for part in key.split(":"))
        actual = randomizer.decode_equipment_effect(code, parameter)
        if actual != expected and key not in KNOWN_OCR_ERRORS:
            mismatches.append((key, expected, actual))
    if mismatches:
        raise RuntimeError(f"特效文字映射不一致：{mismatches[:10]}")

    decoded_slots = 0
    observed_codes = set()
    for slot in range(1, 16):
        save_path = game_root / "SV" / f"SV{slot:03}.E5S"
        records = save_records(save_path.read_bytes())
        equip_info, effects = randomizer.decode_equipment_records(records)
        count = sum(len(items) for items, _category in equip_info)
        if count != 70 or len(effects) != 70:
            raise RuntimeError(
                f"第 {slot} 号存档宝物数量异常：{count}/{len(effects)}"
            )
        observed_codes.update(record[0] for record in records)
        decoded_slots += 1

    mapped_codes = {int(key[:2], 16) for key in observed}
    missing_codes = observed_codes - mapped_codes
    if missing_codes:
        raise RuntimeError(
            "存在未标定的特效代码："
            + ", ".join(f"0x{code:02X}" for code in sorted(missing_codes))
        )
    print(
        f"验证通过：{decoded_slots} 个存档、"
        f"{decoded_slots * 70} 条宝物记录、"
        f"{len(observed_codes)} 个特效代码。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
