from __future__ import annotations

import ctypes
import struct
from dataclasses import dataclass
from ctypes import wintypes
from typing import Callable, Iterable
from ccz_randomizer.profiles import load_profile
from ccz_randomizer.profile_context import current_context

_PROFILE = load_profile()
RECORD_ARRAY_BASE_POINTER_ADDRESS = _PROFILE.address("recordArrayBasePointerAddress")
SKILL_RULE_TABLE_POINTER_ADDRESS = _PROFILE.address("SKILL_RULE_TABLE_POINTER_ADDRESS")
DIRECT_JOB_MATCH_FLAG_ADDRESS = _PROFILE.address("DIRECT_JOB_MATCH_FLAG_ADDRESS")
SKILL_NAME_TABLE_ADDRESS = _PROFILE.address("SKILL_NAME_TABLE_ADDRESS")
ABILITY_SHORT_NAMES_ADDRESS = _PROFILE.address("ABILITY_SHORT_NAMES_ADDRESS")
ALL_ABILITY_NAME_ADDRESS = _PROFILE.address("ALL_ABILITY_NAME_ADDRESS")
ABILITY_NAMES_ADDRESS = _PROFILE.address("ABILITY_NAMES_ADDRESS")
STRATEGY_NAMES_ADDRESS = _PROFILE.address("STRATEGY_NAMES_ADDRESS")

RECORD_SIZE = int(_PROFILE.memory_layout.get("recordSize", 0x48))
MEMBER_ID_OFFSET = int(_PROFILE.memory_layout.get("recordIdOffset", 0x04))
JOB_ID_OFFSET = int(_PROFILE.memory_layout.get("recordJobOffset", 0x2B))
SKILL_RULE_COUNT = _PROFILE.address("SKILL_RULE_COUNT")
SKILL_RULE_STRIDE = _PROFILE.address("SKILL_RULE_STRIDE")
SKILL_NAME_RECORD_SIZE = _PROFILE.address("SKILL_NAME_RECORD_SIZE")
STRATEGY_RECORD_SIZE = _PROFILE.address("STRATEGY_RECORD_SIZE")

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
    rule_table: bytes = b""


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


def format_skill_name(base_name, format_type, parameter, *, ability_short_names,
                      ability_names, all_ability_name, strategy_name=""):
    from ccz_randomizer.display_rules import render_skill
    tables = dict(ability_short_names=ability_short_names, ability_names=ability_names,
                  all_ability_name=all_ability_name)
    return render_skill(current_context().skills["displayRules"], tables, base_name,
                        format_type, parameter, strategy_name)


def catalog_skill_name(row: dict, data=None) -> str:
    rules = (data or current_context().skills)["displayRules"]
    return rules["catalogOverrides"].get(row["name"], row["name"])


def format_profile_skill_name(base_name: str, format_type: int, parameter: int) -> str:
    return format_skill_name(base_name, format_type, parameter,
                             **current_context().skills["nameFormatting"])


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
    planned_job_ids: dict[int, int] | None = None,
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
            job_id = (planned_job_ids or {}).get(record_index, record[JOB_ID_OFFSET])
            if type(job_id) is not int or not 0 <= job_id <= 255:
                raise ValueError(f"人物 {record_index} 的预生成兵种编号无效")
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
        rule_table=rule_table,
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


def normalize_skill_name(name: str) -> str:
    from ccz_randomizer.display_rules import normalize_name
    return normalize_name(current_context().skills["displayRules"], name)
