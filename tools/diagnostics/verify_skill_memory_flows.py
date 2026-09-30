from __future__ import annotations

import argparse
import ctypes
import functools
import json
import os
import shutil
import struct
import time
from pathlib import Path

import fast_randomizer as fast
from rule_config import active_profile, default_rule_config
from runtime_loader import install
from tests.helpers.game_backup import GameFileBackup
from tools.project_paths import ARTIFACTS_DIR


CURRENT_MEMBER_INDEX_ADDRESS = 0x004B7504
CURRENT_RECORD_POINTER_ADDRESS = 0x00500E28
RECORD_SIZE = 0x48
MEMBER_ID_OFFSET = 0x04
JOB_ID_OFFSET = 0x2B
JOB_LEVEL_OFFSET = 0x2C
RECORD_ARRAY_BASE_POINTER_ADDRESS = 0x004CEA00
SKILL_RULE_TABLE_POINTER_ADDRESS = 0x00500C3B
DIRECT_JOB_MATCH_FLAG_ADDRESS = 0x00505F68
SKILL_RULE_COUNT = 0xFF
SKILL_RULE_STRIDE = 8


def read_absolute(pid: int, address: int, size: int) -> bytes:
    handle = fast.kernel32.OpenProcess(
        fast.PROCESS_QUERY_INFORMATION | fast.PROCESS_VM_READ,
        False,
        pid,
    )
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        buffer = ctypes.create_string_buffer(size)
        count = ctypes.c_size_t()
        if not fast.kernel32.ReadProcessMemory(
            handle,
            ctypes.c_void_p(address),
            buffer,
            size,
            ctypes.byref(count),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if count.value != size:
            raise RuntimeError(
                f"绝对地址内存读取不完整：{count.value}/{size}"
            )
        return buffer.raw
    finally:
        fast.kernel32.CloseHandle(handle)


def sample_detail_memory(pid: int) -> dict[str, object]:
    started = time.perf_counter_ns()
    member_index = struct.unpack(
        "<I",
        read_absolute(pid, CURRENT_MEMBER_INDEX_ADDRESS, 4),
    )[0]
    record_pointer = struct.unpack(
        "<I",
        read_absolute(pid, CURRENT_RECORD_POINTER_ADDRESS, 4),
    )[0]
    record = read_absolute(pid, record_pointer, RECORD_SIZE)
    elapsed_ns = time.perf_counter_ns() - started
    return {
        "member_index": member_index,
        "record_pointer": f"0x{record_pointer:08X}",
        "member_id": struct.unpack_from("<I", record, MEMBER_ID_OFFSET)[0],
        "job_id": record[JOB_ID_OFFSET],
        "record_hex": record.hex(),
        "memory_read_ms": round(elapsed_ns / 1_000_000, 4),
    }


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


def resolve_skill_ids_from_memory_tables(
    *,
    record_pointer: int,
    record: bytes,
    record_array_base: int,
    rule_table: bytes,
    direct_job_match: bool,
) -> dict[str, list[int]]:
    record_index = (record_pointer - record_array_base) // RECORD_SIZE
    job_id = record[JOB_ID_OFFSET]

    personal = []
    job = []
    for skill_id in range(SKILL_RULE_COUNT):
        offset = skill_id * SKILL_RULE_STRIDE
        required_records = struct.unpack_from("<HHH", rule_table, offset)
        if record_index in required_records:
            personal.append(skill_id)
        entry_job = rule_table[offset + 6]
        if job_rule_matches(entry_job, job_id, direct_job_match):
            job.append(skill_id)

    return {
        "personal": list(dict.fromkeys(personal)),
        "job": list(dict.fromkeys(job)),
    }


def run(mode: str, game_executable: Path) -> dict[str, object]:
    game_dir = game_executable.parent
    output_dir = ARTIFACTS_DIR / "skill-memory-flow-verify"
    output_dir.mkdir(parents=True, exist_ok=True)

    install(fast.bundle_root())
    import task.CczReRandTask as task_module
    from models.CczModels import CCZ_MODELS
    from window.CczWindow import CczPeopleInfoWindow

    rules = default_rule_config()
    profile = active_profile(rules)
    profile["sevenPerson"]["lowMinSkillScore"] = 0.0
    profile["sevenPerson"]["mediumMinSkillScore"] = 0.0
    model_ids = {
        skill.name: index for index, skill in enumerate(CCZ_MODELS.skills)
    }
    samples: list[dict[str, object]] = []
    memory_samples: list[dict[str, object]] = []
    phase_stats: dict[str, dict[str, float | int]] = {}
    phase_spans: list[dict[str, float | str]] = []
    run_started_ns = 0
    restored_functions: list[tuple[object, str, object]] = []
    pre_ui_direct_snapshot: dict[str, object] | None = None
    pre_roster_direct_snapshot: dict[str, object] | None = None
    original_get_skill_mats = CczPeopleInfoWindow.getSkillMatList
    original_get_all_skill_mat = CczPeopleInfoWindow.getAllSkillMat
    current_pid = 0

    def record_phase(name: str, started_ns: int, finished_ns: int) -> None:
        elapsed_ms = (finished_ns - started_ns) / 1_000_000
        stats = phase_stats.setdefault(
            name,
            {"calls": 0, "total_ms": 0.0},
        )
        stats["calls"] += 1
        stats["total_ms"] += elapsed_ms
        if run_started_ns:
            phase_spans.append(
                {
                    "name": name,
                    "start_ms": round(
                        (started_ns - run_started_ns) / 1_000_000,
                        3,
                    ),
                    "end_ms": round(
                        (finished_ns - run_started_ns) / 1_000_000,
                        3,
                    ),
                    "duration_ms": round(elapsed_ms, 3),
                }
            )

    def install_timed_wrapper(owner, attribute: str, phase_name: str) -> None:
        original = getattr(owner, attribute)

        @functools.wraps(original)
        def wrapped(*args, **kwargs):
            started_ns = time.perf_counter_ns()
            try:
                return original(*args, **kwargs)
            finally:
                record_phase(
                    phase_name,
                    started_ns,
                    time.perf_counter_ns(),
                )

        restored_functions.append((owner, attribute, original))
        setattr(owner, attribute, wrapped)

    def capture_direct_snapshot(
        pid: int,
        positions: tuple[int, ...],
    ) -> dict[str, object]:
        record_array_base = struct.unpack(
            "<I",
            read_absolute(pid, RECORD_ARRAY_BASE_POINTER_ADDRESS, 4),
        )[0]
        rule_table_base = struct.unpack(
            "<I",
            read_absolute(pid, SKILL_RULE_TABLE_POINTER_ADDRESS, 4),
        )[0]
        rule_table = read_absolute(
            pid,
            rule_table_base,
            SKILL_RULE_COUNT * SKILL_RULE_STRIDE + 2,
        )
        direct_job_match = bool(
            read_absolute(pid, DIRECT_JOB_MATCH_FLAG_ADDRESS, 1)[0]
        )
        members = []
        started_ns = time.perf_counter_ns()
        for member_index, record_index in enumerate(positions):
            record_pointer = (
                record_array_base + record_index * RECORD_SIZE
            )
            record = read_absolute(pid, record_pointer, RECORD_SIZE)
            members.append(
                {
                    "member_index": member_index,
                    "record_index": record_index,
                    "member_id": struct.unpack_from(
                        "<I",
                        record,
                        MEMBER_ID_OFFSET,
                    )[0],
                    "job_id": record[JOB_ID_OFFSET],
                    "resolved": resolve_skill_ids_from_memory_tables(
                        record_pointer=record_pointer,
                        record=record,
                        record_array_base=record_array_base,
                        rule_table=rule_table,
                        direct_job_match=direct_job_match,
                    ),
                }
            )
        elapsed_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
        return {
            "record_array_base": f"0x{record_array_base:08X}",
            "rule_table_base": f"0x{rule_table_base:08X}",
            "direct_job_match": direct_job_match,
            "elapsed_ms": round(elapsed_ms, 4),
            "members": members,
        }

    def install_pre_ui_wrapper(
        owner,
        attribute: str,
        phase_name: str,
        positions: tuple[int, ...],
    ) -> None:
        original = getattr(owner, attribute)

        @functools.wraps(original)
        def wrapped(*args, **kwargs):
            nonlocal pre_ui_direct_snapshot
            pre_ui_direct_snapshot = capture_direct_snapshot(
                current_pid,
                positions,
            )
            started_ns = time.perf_counter_ns()
            try:
                return original(*args, **kwargs)
            finally:
                record_phase(
                    phase_name,
                    started_ns,
                    time.perf_counter_ns(),
                )

        restored_functions.append((owner, attribute, original))
        setattr(owner, attribute, wrapped)

    def probed_get_skill_mats(window):
        before = sample_detail_memory(current_pid)
        capture_started = time.perf_counter_ns()
        mats = original_get_skill_mats(window)
        capture_finished = time.perf_counter_ns()
        capture_ns = capture_finished - capture_started
        record_phase(
            "skill_slot_capture_and_match",
            capture_started,
            capture_finished,
        )
        after = sample_detail_memory(current_pid)
        slots = []
        for slot_index, mat in enumerate(mats):
            skill = task_module.CczUtils.getCczSkillWithMat(mat)
            slots.append(
                {
                    "slot": slot_index + 1,
                    "category": (
                        "personal" if slot_index < 3 else "job"
                    ),
                    "model_id": (
                        model_ids.get(skill.name)
                        if skill is not None
                        else None
                    ),
                    "name": skill.name if skill is not None else None,
                }
            )
        samples.append(
            {
                "sequence": len(samples),
                "before_capture": before,
                "after_capture": after,
                "capture_and_template_match_ms": round(
                    capture_ns / 1_000_000,
                    4,
                ),
                "slots": slots,
            }
        )
        return mats

    def probed_get_all_skill_mat(window):
        started_ns = time.perf_counter_ns()
        try:
            return original_get_all_skill_mat(window)
        finally:
            record_phase(
                "member_panel_capture",
                started_ns,
                time.perf_counter_ns(),
            )

    for attribute, phase_name in (
        ("title_load_verified", "source_save_load"),
        ("trigger_random_choice_click", "random_choice_click"),
        ("native_direct_save", "native_save"),
        ("wait_for_seven_member_scene", "seven_scene_fast_wait"),
        ("advance_seven_member_story", "seven_story_fallback"),
        ("advance_people_info", "three_detail_switch"),
        ("advance_people_info_in_game_order", "seven_detail_switch"),
        ("normal_load_verified", "normal_save_load"),
    ):
        install_timed_wrapper(fast, attribute, phase_name)
    original_memory_loader = fast.load_member_skills_from_memory

    @functools.wraps(original_memory_loader)
    def probed_memory_loader(
        task_module_arg,
        pid_arg,
        record_indices,
        members,
    ):
        started_ns = time.perf_counter_ns()
        try:
            snapshot = original_memory_loader(
                task_module_arg,
                pid_arg,
                record_indices,
                members,
            )
        finally:
            record_phase(
                "skill_memory_resolution",
                started_ns,
                time.perf_counter_ns(),
            )
        for member, memory_member in zip(members, snapshot.members):
            memory_samples.append(
                {
                    "record_index": memory_member.record_index,
                    "member_id": memory_member.member_id,
                    "job_id": memory_member.job_id,
                    "name": member.name,
                    "personal": [
                        {
                            "internal_id": skill.internal_skill_id,
                            "name": skill.name,
                            "canonical_name": skill.canonical_name,
                        }
                        for skill in member.skillList
                        if skill.memory_category == "personal"
                    ],
                    "job": [
                        {
                            "internal_id": skill.internal_skill_id,
                            "name": skill.name,
                            "canonical_name": skill.canonical_name,
                        }
                        for skill in member.skillList
                        if skill.memory_category == "job"
                    ],
                }
            )
        return snapshot

    restored_functions.append(
        (fast, "load_member_skills_from_memory", original_memory_loader)
    )
    fast.load_member_skills_from_memory = probed_memory_loader
    if mode == "three":
        install_pre_ui_wrapper(
            fast,
            "capture_initial_member_panels",
            "three_member_inspection",
            fast.JOB_POSITIONS_R0,
        )
    else:
        install_pre_ui_wrapper(
            fast,
            "trigger_seven_member_story",
            "seven_story_trigger",
            fast.JOB_POSITIONS_R1,
        )

    previous_accept_first = os.environ.get("CCZ_TEST_ACCEPT_FIRST")
    os.environ["CCZ_TEST_ACCEPT_FIRST"] = "1"
    started = time.perf_counter()
    try:
        with GameFileBackup(game_dir):
            game_session = fast.HiddenGameSession(game_executable)
            game_start_started_ns = time.perf_counter_ns()
            with game_session as game:
                game_start_finished_ns = time.perf_counter_ns()
                record_phase(
                    "game_start",
                    game_start_started_ns,
                    game_start_finished_ns,
                )
                current_pid = game.pid
                fast.patch_runtime(
                    task_module,
                    game.pid,
                    three_person_mode=mode == "three",
                    rules=rules,
                )
                CczPeopleInfoWindow.getSkillMatList = probed_get_skill_mats
                CczPeopleInfoWindow.getAllSkillMat = probed_get_all_skill_mat
                install_timed_wrapper(
                    task_module.CczReRandTask,
                    "checkPeopleAtR0",
                    "job_filter",
                )
                original_open_people = task_module.CczReRandTask.openPeople

                @functools.wraps(original_open_people)
                def probed_open_people(self, *args, **kwargs):
                    nonlocal pre_roster_direct_snapshot
                    if pre_roster_direct_snapshot is None:
                        positions = (
                            fast.JOB_POSITIONS_R0
                            if mode == "three"
                            else fast.JOB_POSITIONS_R1
                        )
                        pre_roster_direct_snapshot = capture_direct_snapshot(
                            current_pid,
                            positions,
                        )
                    started_ns = time.perf_counter_ns()
                    try:
                        return original_open_people(self, *args, **kwargs)
                    finally:
                        record_phase(
                            "open_roster",
                            started_ns,
                            time.perf_counter_ns(),
                        )

                restored_functions.append(
                    (
                        task_module.CczReRandTask,
                        "openPeople",
                        original_open_people,
                    )
                )
                task_module.CczReRandTask.openPeople = probed_open_people
                runner = task_module.CczReRandTask(0)
                runner._target_save_pos = 16
                runner._source_loaded = False
                run_started_ns = time.perf_counter_ns()
                accepted = runner.run()
                run_finished_ns = time.perf_counter_ns()
                record_phase(
                    "runner_total",
                    run_started_ns,
                    run_finished_ns,
                )
                skill_detail = getattr(
                    runner,
                    "_skill_evaluation_detail",
                    None,
                )
                panel_paths = []
                for index, panel in enumerate(
                    getattr(runner, "_member_panels", ()),
                    start=1,
                ):
                    panel_path = (
                        output_dir / f"{mode}-member-{index}.png"
                    )
                    fast.write_cv_image(panel_path, panel)
                    panel_paths.append(str(panel_path))
                result_image = ""
                if accepted:
                    equipment_started_ns = time.perf_counter_ns()
                    equip_info = runner.collect_equipment()
                    record_phase(
                        "equipment_collection",
                        equipment_started_ns,
                        time.perf_counter_ns(),
                    )
                    rendered_result = fast.save_result_image(
                        runner,
                        equip_info,
                        16,
                    )
                    copied_result = output_dir / f"{mode}-result.png"
                    shutil.copy2(rendered_result, copied_result)
                    result_image = str(copied_result)
                record_array_base = struct.unpack(
                    "<I",
                    read_absolute(
                        game.pid,
                        RECORD_ARRAY_BASE_POINTER_ADDRESS,
                        4,
                    ),
                )[0]
                rule_table_base = struct.unpack(
                    "<I",
                    read_absolute(
                        game.pid,
                        SKILL_RULE_TABLE_POINTER_ADDRESS,
                        4,
                    ),
                )[0]
                rule_table = read_absolute(
                    game.pid,
                    rule_table_base,
                    SKILL_RULE_COUNT * SKILL_RULE_STRIDE + 2,
                )
                direct_job_match = bool(
                    read_absolute(
                        game.pid,
                        DIRECT_JOB_MATCH_FLAG_ADDRESS,
                        1,
                    )[0]
                )
                direct_resolutions = []
                seen_indices = set()
                for sample in samples:
                    memory = sample["before_capture"]
                    member_index = memory["member_index"]
                    if member_index in seen_indices:
                        continue
                    seen_indices.add(member_index)
                    record_pointer = int(
                        str(memory["record_pointer"]),
                        16,
                    )
                    record = bytes.fromhex(str(memory["record_hex"]))
                    resolved = resolve_skill_ids_from_memory_tables(
                        record_pointer=record_pointer,
                        record=record,
                        record_array_base=record_array_base,
                        rule_table=rule_table,
                        direct_job_match=direct_job_match,
                    )
                    expected_personal = [
                        slot["model_id"]
                        for slot in sample["slots"][:3]
                        if slot["model_id"] is not None
                    ]
                    expected_job = [
                        slot["model_id"]
                        for slot in sample["slots"][3:]
                        if slot["model_id"] is not None
                    ]
                    direct_resolutions.append(
                        {
                            "member_index": member_index,
                            "member_id": memory["member_id"],
                            "resolved": resolved,
                            "ui_model_ids": {
                                "personal": expected_personal,
                                "job": expected_job,
                            },
                            "matches_ui": (
                                resolved["personal"] == expected_personal
                                and resolved["job"] == expected_job
                            ),
                        }
                    )
                members = [
                    {
                        "name": member.name,
                        "job": getattr(member.job, "name", ""),
                        "skills": [
                            skill.name for skill in member.skillList
                        ],
                    }
                    for member in getattr(runner, "_team_members", ())
                ]
    finally:
        CczPeopleInfoWindow.getSkillMatList = original_get_skill_mats
        CczPeopleInfoWindow.getAllSkillMat = original_get_all_skill_mat
        for owner, attribute, original in reversed(restored_functions):
            setattr(owner, attribute, original)
        if previous_accept_first is None:
            os.environ.pop("CCZ_TEST_ACCEPT_FIRST", None)
        else:
            os.environ["CCZ_TEST_ACCEPT_FIRST"] = previous_accept_first

    result = {
        "mode": mode,
        "accepted": accepted,
        "sample_count": len(memory_samples),
        "unique_member_indices": sorted(
            sample["record_index"] for sample in memory_samples
        ),
        "expected_count": 3 if mode == "three" else 7,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "phase_stats": {
            name: {
                "calls": stats["calls"],
                "total_ms": round(float(stats["total_ms"]), 3),
            }
            for name, stats in phase_stats.items()
        },
        "phase_spans": phase_spans,
        "pre_ui_direct_snapshot": pre_ui_direct_snapshot,
        "pre_roster_direct_snapshot": pre_roster_direct_snapshot,
        "direct_memory_resolution": {
            "record_array_base": f"0x{record_array_base:08X}",
            "rule_table_base": f"0x{rule_table_base:08X}",
            "direct_job_match": direct_job_match,
            "members": direct_resolutions,
            "all_match_ui": bool(direct_resolutions) and all(
                item["matches_ui"] for item in direct_resolutions
            ),
        },
        "members": members,
        "skill_detail": skill_detail,
        "panel_paths": panel_paths,
        "result_image": result_image,
        "memory_samples": memory_samples,
        "samples": samples,
    }
    output_path = output_dir / f"{mode}.json"
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"输出：{output_path}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("three", "seven"))
    parser.add_argument(
        "--game-exe",
        type=Path,
        default=Path(
            r"E:\game\ccz\曹操传加强版V2.10.4c"
            r"\曹操传加强版V2.10.4c\Ekd5.exe"
        ),
    )
    args = parser.parse_args()
    result = run(args.mode, args.game_exe)
    expected_indices = (
        list(fast.JOB_POSITIONS_R0)
        if args.mode == "three"
        else list(fast.JOB_POSITIONS_R1)
    )
    if result["unique_member_indices"] != sorted(expected_indices):
        raise RuntimeError(
            f"{args.mode} 流程索引不完整："
            f"{result['unique_member_indices']}，预期 {expected_indices}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
