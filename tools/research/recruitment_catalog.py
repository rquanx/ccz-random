"""Extract the audited R_99 stage-to-recruit assignments from 2.2."""
from __future__ import annotations

import re
import struct

from ccz_randomizer.profiles import load_profile
_RULES = load_profile().script_rules
STAGE_CONDITION = bytes.fromhex(_RULES["stageCondition"])
ASSIGN_PREFIX = bytes.fromhex(_RULES["assignPrefix"])
ASSIGN_MIDDLE = bytes.fromhex(_RULES["assignMiddle"])
STAGE_EXTRAS = {int(k): bytes.fromhex(v) for k, v in _RULES["stageExtras"].items()}


def extract_stage_recruits(script: bytes) -> tuple[dict, ...]:
    marker = "可招募人物根据关卡赋值".encode("gb18030") + b"\0"
    marker_offset = script.find(marker)
    if marker_offset >= 0:
        cursor = marker_offset + len(marker)
        if cursor + 2 > len(script):
            raise ValueError("招募关卡容器不完整")
        length = struct.unpack_from("<H", script, cursor)[0]
        if cursor + 2 + length > len(script):
            raise ValueError("招募关卡容器不完整")
        script = script[cursor + 2:cursor + 2 + length]
    result = []
    seen = set()
    for match in re.finditer(re.escape(STAGE_CONDITION), script):
        cursor = match.end()
        if cursor + 6 > len(script):
            raise ValueError("招募关卡头不完整")
        stage, size = struct.unpack_from("<IH", script, cursor)
        body = script[cursor + 6:cursor + 6 + size]
        if len(body) != size or body[-2:] != b"\0\0":
            raise ValueError("招募关卡赋值块长度不匹配")
        records = []
        offset = 0
        slots = set()
        extra_seen = False
        while offset < size - 2:
            extra = STAGE_EXTRAS.get(stage)
            if extra and body[offset:offset + len(extra)] == extra and not extra_seen:
                offset += len(extra)
                extra_seen = True
                continue
            row = body[offset:offset+26]
            if len(row) != 26 or row[:8] != ASSIGN_PREFIX or row[12:22] != ASSIGN_MIDDLE:
                raise ValueError("招募关卡包含未识别的条件，需重新核实")
            slot = struct.unpack_from("<I", row, 8)[0]
            record = struct.unpack_from("<I", row, 22)[0]
            if not 610 <= slot <= 618 or not 0 <= record < 1024:
                raise ValueError("招募人物编号越界")
            if slot in slots or record in records:
                raise ValueError("重复招募槽位或人物")
            slots.add(slot)
            records.append(record)
            offset += 26
        if offset != size - 2:
            raise ValueError("招募关卡赋值块长度不匹配")
        if stage in seen:
            raise ValueError("重复招募关卡")
        seen.add(stage)
        result.append({"stageId": stage, "recordIndices": records})
    if not result:
        raise ValueError("未找到招募关卡赋值")
    return tuple(result)
