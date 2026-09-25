from __future__ import annotations

import struct
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


LEGACY_SKILL_OFFSET = 0x6800
LEGACY_RECORD_SIZE = 8
LEGACY_RECORD_COUNT = 42


@dataclass(frozen=True)
class SkillObservation:
    save_number: int
    member_index: int
    slot_index: int
    model_id: int
    confidence: float


def read_legacy_records(data: bytes) -> tuple[tuple[int, int, int, int], ...]:
    end = LEGACY_SKILL_OFFSET + LEGACY_RECORD_COUNT * LEGACY_RECORD_SIZE
    if len(data) < end:
        raise ValueError(
            f"存档长度不足：需要至少 0x{end:X} 字节，实际 0x{len(data):X}"
        )
    return tuple(
        struct.unpack_from(
            "<4H",
            data,
            LEGACY_SKILL_OFFSET + index * LEGACY_RECORD_SIZE,
        )
        for index in range(LEGACY_RECORD_COUNT)
    )


def stable_direct_offsets(
    saves: dict[int, bytes],
    observations: Iterable[SkillObservation],
    *,
    value_size: int,
) -> dict[tuple[int, int], tuple[int, ...]]:
    if value_size not in (1, 2, 4):
        raise ValueError("value_size 只支持 1、2、4")
    grouped: dict[tuple[int, int], list[SkillObservation]] = {}
    for observation in observations:
        if observation.save_number not in saves:
            continue
        grouped.setdefault(
            (observation.member_index, observation.slot_index), []
        ).append(observation)

    unpackers = {1: "<B", 2: "<H", 4: "<I"}
    result: dict[tuple[int, int], tuple[int, ...]] = {}
    for key, items in grouped.items():
        if len(items) < 3:
            continue
        max_length = min(len(saves[item.save_number]) for item in items)
        candidates = []
        for offset in range(0, max_length - value_size + 1, value_size):
            if all(
                struct.unpack_from(
                    unpackers[value_size],
                    saves[item.save_number],
                    offset,
                )[0]
                == item.model_id
                for item in items
            ):
                candidates.append(offset)
        result[key] = tuple(candidates)
    return result


def summarize_changed_ranges(
    before: bytes,
    after: bytes,
    *,
    merge_gap: int = 8,
) -> tuple[tuple[int, int], ...]:
    changed = [
        index
        for index, (left, right) in enumerate(zip(before, after))
        if left != right
    ]
    if len(before) != len(after):
        changed.extend(range(min(len(before), len(after)), max(len(before), len(after))))
    if not changed:
        return ()

    ranges = []
    start = previous = changed[0]
    for offset in changed[1:]:
        if offset - previous > merge_gap:
            ranges.append((start, previous + 1))
            start = offset
        previous = offset
    ranges.append((start, previous + 1))
    return tuple(ranges)


def load_numbered_saves(
    save_dir: Path,
    save_numbers: Sequence[int],
) -> dict[int, bytes]:
    saves = {}
    for number in save_numbers:
        path = save_dir / f"SV{number:03}.E5S"
        if path.is_file():
            saves[number] = path.read_bytes()
    return saves


def write_skill_evidence(
    output: Path,
    *,
    candidate_save: bytes,
    before_jump_memory: bytes,
    after_render_memory: bytes,
    metadata: dict,
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as archive:
        archive.writestr(
            "metadata.json",
            json.dumps(metadata, ensure_ascii=False, indent=2),
        )
        archive.writestr("candidate-save.bin", candidate_save)
        archive.writestr("before-jump-memory.bin", before_jump_memory)
        archive.writestr("after-render-memory.bin", after_render_memory)
    return output


def read_skill_evidence(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        return {
            "metadata": json.loads(
                archive.read("metadata.json").decode("utf-8")
            ),
            "candidate_save": archive.read("candidate-save.bin"),
            "before_jump_memory": archive.read("before-jump-memory.bin"),
            "after_render_memory": archive.read("after-render-memory.bin"),
        }
