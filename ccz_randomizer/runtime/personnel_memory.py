"""Read personnel records without assuming which units can be recruited."""
from __future__ import annotations

import struct
from ccz_randomizer.profiles import load_profile

PLANNED_JOB_ARRAY_ADDRESS = load_profile().address("plannedJobArrayAddress")

from ccz_randomizer.runtime.skill_memory import (
    ProcessMemoryReader, RECORD_ARRAY_BASE_POINTER_ADDRESS, RECORD_SIZE,
    read_skill_memory,
)


def decode_personnel_record(record: bytes, index: int) -> tuple[str, int, int]:
    if len(record) != RECORD_SIZE:
        raise ValueError("人物记录长度错误")
    if struct.unpack_from("<I", record)[0] != 0x1000 + index:
        raise ValueError(f"人物记录 {index} 标识与预期不一致")
    name = record[8:17].split(b"\0", 1)[0].decode("gb18030")
    if not name or not name.isprintable():
        raise ValueError(f"人物记录 {index} 名称无效")
    return name, struct.unpack_from("<I", record, 4)[0], record[0x2B]


def validate_personnel_identity(pid, expected, *, reader_factory=ProcessMemoryReader):
    """Reject an old save's roster before rolling or committing a result."""
    with reader_factory(pid) as reader:
        base = struct.unpack("<I", reader.read(RECORD_ARRAY_BASE_POINTER_ADDRESS, 4))[0]
        data = reader.read(base, (max(expected.values()) + 1) * RECORD_SIZE)
    for name, index in expected.items():
        actual, _member_id, _job = decode_personnel_record(data[index*RECORD_SIZE:(index+1)*RECORD_SIZE], index)
        if actual != name:
            raise ValueError(f"源存档人物与当前游戏版本不匹配：{name} 的位置读到 {actual}。请用当前游戏重新准备第 20 栏源存档")


def read_rule_job_ids(pid, positions, *, reader_factory=ProcessMemoryReader):
    """Fast screening uses the same effective jobs as the personnel preview."""
    from ccz_randomizer.recruitment_catalog import load_catalog
    FIXED_JOB_INDICES = frozenset(p["recordIndex"] for p in load_catalog() if p["fixedConfiguration"])

    positions = tuple(positions)
    if not positions:
        return ()
    if any(type(i) is not int or not 0 <= i < 1024 for i in positions):
        raise ValueError("人物记录编号无效")
    with reader_factory(pid) as reader:
        size = max(positions) + 1
        jobs = struct.unpack(f"<{size}I", reader.read(PLANNED_JOB_ARRAY_ADDRESS, size * 4))
        fixed = FIXED_JOB_INDICES.intersection(positions)
        current = {}
        if fixed:
            base = struct.unpack("<I", reader.read(RECORD_ARRAY_BASE_POINTER_ADDRESS, 4))[0]
            for index in fixed:
                record = reader.read(base + index * RECORD_SIZE, RECORD_SIZE)
                current[index] = decode_personnel_record(record, index)[2]
        return tuple(current[i] if i in current else jobs[i] for i in positions)


def read_personnel(pid: int, indices, *, planned=False, fixed_indices=(), reader_factory=ProcessMemoryReader) -> list[dict]:
    positions = tuple(indices)
    if not positions or any(type(i) is not int or not 0 <= i < 1024 for i in positions):
        raise ValueError("人物记录编号须位于已验证的 0–1023 范围内")
    if len(set(positions)) != len(positions):
        raise ValueError("人物记录编号重复")
    with reader_factory(pid) as reader:
        base = struct.unpack("<I", reader.read(RECORD_ARRAY_BASE_POINTER_ADDRESS, 4))[0]
        data = reader.read(base, (max(positions) + 1) * RECORD_SIZE)
        jobs = struct.unpack(f"<{max(positions)+1}I", reader.read(PLANNED_JOB_ARRAY_ADDRESS, (max(positions)+1)*4)) if planned else ()
    fixed = frozenset(fixed_indices)
    planned_jobs = {index: (data[index * RECORD_SIZE + 0x2B] if index in fixed else jobs[index])
                    for index in positions} if planned else None
    snapshot = read_skill_memory(pid, positions, reader_factory=reader_factory, planned_job_ids=planned_jobs)
    if snapshot.record_array_base != base:
        raise RuntimeError("读取期间人物表变化，请在游戏静止时重试")
    result = []
    for member in snapshot.members:
        index = member.record_index
        name, member_id, job_id = decode_personnel_record(data[index*RECORD_SIZE:(index+1)*RECORD_SIZE], index)
        effective_job = planned_jobs[index] if planned_jobs is not None else job_id
        if member_id != member.member_id or effective_job != member.job_id:
            raise RuntimeError("读取期间人物数据变化，请重试")
        result.append({
            "recordIndex": index, "memberId": member_id, "name": name,
            "jobId": effective_job, "currentJobId": job_id,
            "jobTalents": [skill.display_name for skill in member.job],
            "personalTalents": [skill.display_name for skill in member.personal],
            "availabilityVerified": False,
        })
    return result
