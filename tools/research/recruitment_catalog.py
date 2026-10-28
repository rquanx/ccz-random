"""Extract the audited R_99 stage-to-recruit assignments from 2.2."""
from __future__ import annotations

import re
import struct

STAGE_CONDITION = bytes.fromhex("010079005200040004006d02000056000000520000000400")
ASSIGN_PREFIX = bytes.fromhex("7700510002000400")
ASSIGN_MIDDLE = bytes.fromhex("53000200520000000400")


def extract_stage_recruits(script: bytes) -> tuple[dict, ...]:
    marker = "可招募人物根据关卡赋值".encode("gb18030") + b"\0"
    marker_offset = script.find(marker)
    if marker_offset >= 0:
        cursor = marker_offset + len(marker)
        length = struct.unpack_from("<H", script, cursor)[0]
        script = script[cursor + 2:cursor + 2 + length]
    result = []
    seen = set()
    for match in re.finditer(re.escape(STAGE_CONDITION), script):
        cursor = match.end()
        stage, size = struct.unpack_from("<IH", script, cursor)
        body = script[cursor + 6:cursor + 6 + size]
        if len(body) != size or body[-2:] != b"\0\0" or (size - 2) % 26:
            raise ValueError("招募关卡赋值块长度不匹配")
        records = []
        for offset in range(0, size - 2, 26):
            row = body[offset:offset+26]
            if row[:8] != ASSIGN_PREFIX or row[12:22] != ASSIGN_MIDDLE:
                raise ValueError("招募关卡包含未识别的条件，需重新核实")
            slot = struct.unpack_from("<I", row, 8)[0]
            record = struct.unpack_from("<I", row, 22)[0]
            if not 610 <= slot <= 618 or not 0 <= record < 1024:
                raise ValueError("招募人物编号越界")
            records.append(record)
        if stage in seen:
            raise ValueError("重复招募关卡")
        seen.add(stage)
        result.append({"stageId": stage, "recordIndices": records})
    if not result:
        raise ValueError("未找到招募关卡赋值")
    return tuple(result)
