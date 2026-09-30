from __future__ import annotations

import ctypes
import re
import struct
from dataclasses import dataclass
from ctypes import wintypes
from typing import Callable, Iterable


RECORD_ARRAY_BASE_POINTER_ADDRESS = 0x004CEA00
SKILL_RULE_TABLE_POINTER_ADDRESS = 0x00500C3B
DIRECT_JOB_MATCH_FLAG_ADDRESS = 0x00505F68
SKILL_NAME_TABLE_ADDRESS = 0x004CC600
ABILITY_SHORT_NAMES_ADDRESS = 0x0048EC6A
ALL_ABILITY_NAME_ADDRESS = 0x0048B3E1
ABILITY_NAMES_ADDRESS = 0x00486ADB
STRATEGY_NAMES_ADDRESS = 0x004A3E77

RECORD_SIZE = 0x48
MEMBER_ID_OFFSET = 0x04
JOB_ID_OFFSET = 0x2B
SKILL_RULE_COUNT = 0xFF
SKILL_RULE_STRIDE = 8
SKILL_NAME_RECORD_SIZE = 16
STRATEGY_RECORD_SIZE = 0x61

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010


@dataclass(frozen=True)
class SkillDefinition:
    internal_id: int
    display_name: str
    base_name: str
    format_type: int
    parameter: int


@dataclass(frozen=True)
class MemberSkillMemory:
    record_index: int
    member_id: int
    job_id: int
    personal: tuple[SkillDefinition, ...]
    job: tuple[SkillDefinition, ...]

    @property
    def all_skills(self) -> tuple[SkillDefinition, ...]:
        return self.personal + self.job


@dataclass(frozen=True)
class SkillMemorySnapshot:
    record_array_base: int
    rule_table_base: int
    direct_job_match: bool
    catalog: tuple[SkillDefinition, ...]
    members: tuple[MemberSkillMemory, ...]


class ProcessMemoryReader:
    def __init__(self, pid: int):
        self.pid = pid
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        self._kernel32.OpenProcess.restype = wintypes.HANDLE
        self._kernel32.ReadProcessMemory.argtypes = [
            wintypes.HANDLE,
            wintypes.LPCVOID,
            wintypes.LPVOID,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self._kernel32.ReadProcessMemory.restype = wintypes.BOOL
        self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel32.CloseHandle.restype = wintypes.BOOL
        self._handle = None

    def __enter__(self) -> ProcessMemoryReader:
        self._handle = self._kernel32.OpenProcess(
            PROCESS_QUERY_INFORMATION | PROCESS_VM_READ,
            False,
            self.pid,
        )
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None

    def read(self, address: int, size: int) -> bytes:
        if not self._handle:
            raise RuntimeError("游戏内存读取器尚未打开")
        buffer = ctypes.create_string_buffer(size)
        count = ctypes.c_size_t()
        if not self._kernel32.ReadProcessMemory(
            self._handle,
            ctypes.c_void_p(address),
            buffer,
            size,
            ctypes.byref(count),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if count.value != size:
            raise RuntimeError(
                f"游戏绝对地址内存读取不完整：{count.value}/{size}"
            )
        return buffer.raw


def _decode_c_string(data: bytes) -> str:
    return data.split(b"\0", 1)[0].decode("gb18030", errors="replace")


def _read_u32(read: Callable[[int, int], bytes], address: int) -> int:
    return struct.unpack("<I", read(address, 4))[0]


def normalized_job_id(job_id: int) -> int:
    if job_id < 0x3C:
        return job_id // 3
    if job_id < 0x50:
        return job_id - 0x28
    return 0x28


def job_rule_matches(entry_job: int, job_id: int, direct_match: bool) -> bool:
    if direct_match:
        return entry_job == job_id
    return (
        normalized_job_id(entry_job) == normalized_job_id(job_id)
        and entry_job <= job_id
    )


def resolve_skill_ids(
    *,
    record_index: int,
    job_id: int,
    rule_table: bytes,
    direct_job_match: bool,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    personal = []
    for skill_id in range(SKILL_RULE_COUNT):
        offset = skill_id * SKILL_RULE_STRIDE
        assigned_records = struct.unpack_from("<HHH", rule_table, offset)
        if record_index in assigned_records:
            personal.append(skill_id)

    job = []
    for skill_id in range(SKILL_RULE_COUNT):
        offset = skill_id * SKILL_RULE_STRIDE
        entry_job = rule_table[offset + 6]
        if job_rule_matches(entry_job, job_id, direct_job_match):
            job.append(skill_id)
    return tuple(personal), tuple(job)


def _ability_mask_name(
    parameter: int,
    ability_names: tuple[str, ...],
    all_ability_name: str,
    count: int,
) -> str:
    mask = parameter & ((1 << count) - 1)
    if mask == (1 << count) - 1:
        return all_ability_name
    return "".join(
        ability_names[index]
        for index in range(count)
        if mask & (1 << index)
    )


def format_skill_name(
    base_name: str,
    format_type: int,
    parameter: int,
    *,
    ability_short_names: tuple[str, ...],
    ability_names: tuple[str, ...],
    all_ability_name: str,
    strategy_name: str = "",
) -> str:
    if format_type == 0:
        return base_name
    if format_type == 1:
        return f"{base_name} +{parameter}"
    if format_type == 2:
        return f"{base_name} +{parameter}%"
    if format_type == 3:
        return f"{base_name} -{parameter}%"
    if format_type == 4:
        return f"{base_name} {parameter}%"
    if format_type == 5:
        return f"{base_name} {parameter}"
    if format_type == 6:
        source_index, target_mask = divmod(parameter, 16)
        if target_mask in (0, 15):
            source_index -= 1
            target_mask += 16
        target_name = _ability_mask_name(
            target_mask,
            ability_short_names,
            all_ability_name,
            5,
        )
        source_name = (
            ability_short_names[source_index]
            if source_index < len(ability_short_names)
            else str(source_index)
        )
        return f"{base_name} {source_name}→{target_name}"
    if format_type == 7:
        return f"{base_name} {strategy_name or parameter}"
    if format_type == 8:
        ability_name = (
            ability_names[parameter]
            if parameter < len(ability_names)
            else str(parameter)
        )
        return f"{base_name} {ability_name}"
    if format_type in (9, 10):
        ability_name = _ability_mask_name(
            parameter,
            ability_short_names,
            all_ability_name,
            5 if format_type == 9 else 6,
        )
        return f"{base_name} {ability_name}"
    return base_name


def _read_null_strings(data: bytes, limit: int) -> tuple[str, ...]:
    values = []
    offset = 0
    while offset < len(data) and len(values) < limit:
        end = data.find(b"\0", offset)
        if end < 0:
            break
        values.append(data[offset:end].decode("gb18030", errors="replace"))
        offset = end + 1
    return tuple(values)


def read_skill_memory(
    pid: int,
    record_indices: Iterable[int],
    *,
    reader_factory: Callable[[int], object] = ProcessMemoryReader,
) -> SkillMemorySnapshot:
    positions = tuple(record_indices)
    if not positions:
        raise ValueError("至少需要一个武将记录索引")

    with reader_factory(pid) as memory:
        read = memory.read
        record_array_base = _read_u32(
            read, RECORD_ARRAY_BASE_POINTER_ADDRESS
        )
        rule_table_base = _read_u32(
            read, SKILL_RULE_TABLE_POINTER_ADDRESS
        )
        rule_table = read(
            rule_table_base,
            SKILL_RULE_COUNT * SKILL_RULE_STRIDE,
        )
        direct_job_match = bool(read(DIRECT_JOB_MATCH_FLAG_ADDRESS, 1)[0])
        records = read(
            record_array_base,
            (max(positions) + 1) * RECORD_SIZE,
        )
        name_records = read(
            SKILL_NAME_TABLE_ADDRESS,
            SKILL_RULE_COUNT * SKILL_NAME_RECORD_SIZE,
        )
        ability_short_names = _read_null_strings(
            read(ABILITY_SHORT_NAMES_ADDRESS, 32),
            6,
        )
        ability_names = _read_null_strings(
            read(ABILITY_NAMES_ADDRESS, 48),
            8,
        )
        all_ability_name = _decode_c_string(
            read(ALL_ABILITY_NAME_ADDRESS, 16)
        )

        raw_members = []
        for record_index in positions:
            record = records[
                record_index * RECORD_SIZE :
                (record_index + 1) * RECORD_SIZE
            ]
            member_id = struct.unpack_from("<I", record, MEMBER_ID_OFFSET)[0]
            job_id = record[JOB_ID_OFFSET]
            personal_ids, job_ids = resolve_skill_ids(
                record_index=record_index,
                job_id=job_id,
                rule_table=rule_table,
                direct_job_match=direct_job_match,
            )
            raw_members.append(
                (record_index, member_id, job_id, personal_ids, job_ids)
            )

        definitions: dict[int, SkillDefinition] = {}
        strategy_names: dict[int, str] = {}
        for skill_id in range(SKILL_RULE_COUNT):
            offset = skill_id * SKILL_NAME_RECORD_SIZE
            name_record = name_records[offset : offset + SKILL_NAME_RECORD_SIZE]
            base_name = _decode_c_string(name_record[:15])
            format_type = name_record[15]
            parameter = rule_table[
                skill_id * SKILL_RULE_STRIDE + SKILL_RULE_STRIDE - 1
            ]
            strategy_name = ""
            if format_type == 7:
                if parameter not in strategy_names:
                    strategy_names[parameter] = _decode_c_string(
                        read(
                            STRATEGY_NAMES_ADDRESS
                            + parameter * STRATEGY_RECORD_SIZE,
                            STRATEGY_RECORD_SIZE,
                        )
                    )
                strategy_name = strategy_names[parameter]
            definitions[skill_id] = SkillDefinition(
                internal_id=skill_id,
                display_name=format_skill_name(
                    base_name,
                    format_type,
                    parameter,
                    ability_short_names=ability_short_names,
                    ability_names=ability_names,
                    all_ability_name=all_ability_name,
                    strategy_name=strategy_name,
                ),
                base_name=base_name,
                format_type=format_type,
                parameter=parameter,
            )

    return SkillMemorySnapshot(
        record_array_base=record_array_base,
        rule_table_base=rule_table_base,
        direct_job_match=direct_job_match,
        catalog=tuple(
            definitions[skill_id] for skill_id in range(SKILL_RULE_COUNT)
        ),
        members=tuple(
            MemberSkillMemory(
                record_index=record_index,
                member_id=member_id,
                job_id=job_id,
                personal=tuple(definitions[item] for item in personal_ids),
                job=tuple(definitions[item] for item in job_ids),
            )
            for (
                record_index,
                member_id,
                job_id,
                personal_ids,
                job_ids,
            ) in raw_members
        ),
    )


_IGNORED_NAME_CHARACTERS = re.compile(
    r"[\s\-—－_()（）:：+＋%％]"
)


def normalize_skill_name(name: str) -> str:
    normalized = str(name).strip()
    if normalized.startswith("能力替换"):
        normalized = normalized.replace("→", "替")
    elif normalized.startswith("能力辅助"):
        normalized = normalized.replace("→", "辅")
    return _IGNORED_NAME_CHARACTERS.sub("", normalized)
