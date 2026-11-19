from __future__ import annotations
from tkinter import ttk

from ccz_randomizer.ui.window_position import centered_toplevel, show_centered
from ccz_randomizer.fixed_members import expand_rule_members
from ccz_randomizer.fixed_members import fixed_member_indices
from ccz_randomizer.entry_catalog import attach_fixed_entries
from ccz_randomizer.equipment_snapshot import serialize_equipment
from ccz_randomizer.workflow.result_snapshots import (
    skill_result_detail, result_detail_for_runner, build_history_result_snapshot,
)

import ctypes
import datetime as dt
import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import struct
import sys
import tempfile
import threading
import time
import traceback
from contextlib import contextmanager
from ctypes import wintypes
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

from ccz_randomizer.rules.reporting import job_rule_report

from ccz_randomizer.rules.config import (
    active_profile,
    default_rule_config,
    evaluate_job_rules,
    evaluate_skill_rules,
    load_rule_config,
    save_rule_config,
    skill_types_match,
    validate_rule_config,
)
from ccz_randomizer.rules.editor import show_rule_editor, show_toast
from ccz_randomizer.history import HistoryRepository
from ccz_randomizer.workflow.history_lifecycle import HistoryLifecycle
from ccz_randomizer.workflow.run_rules import capture_run_rules, load_run_rules
from ccz_randomizer.ui.history import show_history_window
from ccz_randomizer.ui.result_details import (
    decode_result_detail,
    encode_result_detail,
    format_result_detail,
)
from ccz_randomizer.support_diagnostics import (
    create_log_archive,
    inspect_environment,
    UploadCancelled,
    upload_log_archive,
)
from ccz_randomizer.diagnostics.runtime import (
    build_diagnostic_record,
    clear_diagnostic_context,
    environment_diagnostic,
    exception_diagnostic,
    start_diagnostic_run,
    update_diagnostic_context,
)
from ccz_randomizer.diagnostics.skill_storage import write_skill_evidence
from ccz_randomizer.runtime.log_retention import (
    RotatingTextWriter,
    cleanup_log_directory,
    trim_text_widget,
)
from ccz_randomizer.runtime.native_protocol import (
    PERSISTENT_NATIVE_ACTION_CODES, encode_native_request,
)
from ccz_randomizer.runtime.audio_recovery import (
    ProcessAudioMuteMonitor,
    restore_process_audio_sessions,
)
from ccz_randomizer.runtime.manual_repair import (
    ManualRepairResult,
    repair_normal_game_audio,
)
from ccz_randomizer.runtime.loader import install
from ccz_randomizer.runtime.skill_memory import (
    catalog_skill_name,
    format_profile_skill_name,
    normalize_skill_name,
    read_skill_memory,
)
from ccz_randomizer.runtime.s00_guard import (
    S00ScriptGuard,
    repair_game_s00,
)
from ccz_randomizer.runtime.scratch_save_guard import (
    ScratchSaveGuard,
    publish_candidate_save,
)
from ccz_randomizer.runtime.concurrent import (
    decode_concurrent_event,
    run_concurrent_workers,
    start_concurrent_worker_heartbeat,
)
from ccz_randomizer.runtime.window_capture import (
    WindowCaptureError,
    capture_window_with_fallbacks,
)
from ccz_randomizer.ui.member_panel import (
    render_member_text_panel as render_member_text_panel_image,
)
from ccz_randomizer.ui.concurrent_console import (
    ConcurrentConsoleState,
    build_console_render_signature,
    extract_result_image_path,
    format_round_heading,
    is_completion_console_line,
)
from ccz_randomizer.preferences import (
    acknowledge_first_use_notice,
    first_use_notice_acknowledged,
    load_compatibility_mode,
    load_concurrency,
    load_loop_random,
    load_prevent_sleep,
    save_random_runtime_settings,
)
from ccz_randomizer.game_versions import APP_DEFAULT_GAME_VERSION, DEFAULT_GAME_VERSION, current_game_version, activate_game_version, is_enhanced_game_version, VALID_GAME_VERSIONS
from ccz_randomizer.rule_members import rule_member_indices, validate_selected_members, validate_profile_members, required_data_collection
from ccz_randomizer.runtime.personnel_memory import read_personnel, validate_personnel_identity
from ccz_randomizer.runtime.job_talents import read_job_talents
from ccz_randomizer.recruitment_catalog import load_catalog, attach_recruitment
from ccz_randomizer.profile_updates import show_profile_update_dialog, startup_profile_check, profile_version_label
from ccz_randomizer.profiles import load_profile
from ccz_randomizer.workflow.randomization import (
    AcceptedResult,
    AttemptResult,
    run_random_workflow,
)
from ccz_randomizer.workflow.round_archive import (
    ensure_loop_disk_space,
    finalize_round,
    prepare_round_workspace,
    resolve_loop_run_stamp,
)


cv2 = None
np = None
Image = None
ImageDraw = None
ImageFont = None
_SKILL_SCORE_CATALOG = None
_SKILL_SCORE_CATALOG_LOCK = threading.Lock()
# Progress is deliberately coalesced. Rebuilding a Tk Text widget is much
# more expensive than receiving the worker line, especially with 15 slots.
CONCURRENT_CONSOLE_RENDER_INTERVAL_SECONDS = 0.35
CONCURRENT_CONSOLE_QUEUE_BATCH_SIZE = 250


def load_media_modules() -> None:
    global cv2, np, Image, ImageDraw, ImageFont
    if cv2 is not None:
        return
    import cv2 as cv2_module
    import numpy as numpy_module
    from PIL import Image as image_module
    from PIL import ImageDraw as image_draw_module
    from PIL import ImageFont as image_font_module

    cv2 = cv2_module
    np = numpy_module
    Image = image_module
    ImageDraw = image_draw_module
    ImageFont = image_font_module


GAME_EXE_NAME = "Ekd5.exe"
RANDOM_GAME_EXE_NAME = "Ekd5.ccz-fast-random.exe"
MEMORY_BASE = 0x00501000
JOB_OFFSET = load_profile().address("plannedJobArrayAddress") - MEMORY_BASE
LOAD_TRANSITION_ACTIVE_OFFSET = 0x004AB020 - MEMORY_BASE
LOAD_TRANSITION_STATE_OFFSET = 0x004ABF9C - MEMORY_BASE
TEAM_MEMBER_NUM = 7
JOB_POSITIONS_R0 = (0, 1, 6)
JOB_POSITIONS_R1 = (0, 1, 5, 6, 10, 11, 12)
R0_MEMORY_SIZE = 0x30000
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_TERMINATE = 0x0001
SYNCHRONIZE = 0x00100000
FILE_ATTRIBUTE_HIDDEN = 0x00000002
INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF
MIN_AVAILABLE_MEMORY_BYTES = 768 * 1024 * 1024
DESKTOP_ACCESS = 0x01CB
STARTF_USESHOWWINDOW = 0x00000001
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
CREATE_SUSPENDED = 0x00000004
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9
BM_CLICK = 0x00F5
SMTO_ABORTIFHUNG = 0x0002
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102
NATIVE_CONTROL_SEMAPHORE_NAME = "Local\\CCZFastNativeControlSlots"
NATIVE_CONTROL_DEFAULT_SLOTS = 6
NATIVE_CONTROL_RETRY_DELAY_SECONDS = 0.35
NATIVE_CONTROL_RETRY_ACTIONS = frozenset(
    {"wake", "list", "loadui", "openload", "real-load"}
)

OFFSCREEN_X = -3000
OFFSCREEN_Y = -3000
SOURCE_SAVE_NUMBER = 20
# The source save is the visible No.020 entry and SV020.E5S on disk.
SOURCE_TITLE_LIST_INDEX = 19
XU_CLIENT_POSITION = (369, 234)
CONFIRM_FIRST_CLIENT_POSITION = (297, 220)
TITLE_LOAD_CLIENT_POSITION = (512, 168)
NORMAL_RELOAD_FAILURES_BEFORE_COMPATIBILITY = 3
SECURITY_360_PROCESS_NAMES = frozenset(
    {
        "360doctor.exe",
        "360rp.exe",
        "360safe.exe",
        "360sd.exe",
        "360speedld.exe",
        "360tray.exe",
        "qhsafemain.exe",
        "qhsafetray.exe",
        "zhudongfangyu.exe",
    }
)
SECURITY_SOFTWARE_BLOCKED_EVENT = "@@CCZ_SECURITY_SOFTWARE_BLOCKED@@"
SECURITY_SOFTWARE_BLOCKED_MESSAGE = (
    "原生控制组件被安全软件拦截，请在隔离区恢复文件，"
    "并将工具目录加入信任后重试。"
)
def apply_equipment_profile(profile):
    global _EQUIPMENT_PROFILE
    _EQUIPMENT_PROFILE = profile
    data = profile.skills["displayRules"]["equipment"]
    for key in ("EQUIPMENT_OFFSET", "EQUIPMENT_SIZE", "EQUIPMENT_NAMES",
                "EQUIPMENT_CATEGORY_NAMES", "EQUIPMENT_CATEGORY_BY_NAME",
                "EQUIPMENT_SETS", "GOOD_EQUIPMENT_SKILL_MARKERS"):
        value = data[key]
        if key in ("EQUIPMENT_NAMES", "EQUIPMENT_CATEGORY_NAMES", "GOOD_EQUIPMENT_SKILL_MARKERS"):
            value = tuple(value)
        elif key == "EQUIPMENT_SETS":
            value = tuple((title, tuple(names)) for title, names in value)
        globals()[key] = value


from ccz_randomizer.profiles import load_profile as _load_equipment_profile
apply_equipment_profile(_load_equipment_profile())

from ccz_randomizer.jobs import JOB_MAP


TEAM_MEMBERS = (
    ("曹操", "ALL_ROUNDER", "WARRIOR"),
    ("夏侯惇", "WARRIOR", "ALL_ROUNDER"),
    ("曹仁", "ALL_ROUNDER", "WARRIOR"),
    ("夏侯渊", "MASTER", "ALL_ROUNDER"),
    ("乐进", "MASTER", "ALL_ROUNDER"),
    ("李典", "MASTER", "ALL_ROUNDER"),
    ("曹洪", "ALL_ROUNDER", "WARRIOR"),
)
INITIAL_TEAM_MEMBER_INDICES = (0, 1, 3)
INITIAL_TEAM_MEMBERS = tuple(
    TEAM_MEMBERS[index] for index in INITIAL_TEAM_MEMBER_INDICES
)


def initial_team_members(members):
    return tuple(members[index] for index in INITIAL_TEAM_MEMBER_INDICES)


@lru_cache(maxsize=1)
def canonical_skill_names() -> tuple[str, ...]:
    # 2.2 的运行时特技表已经扩展到 240 项。旧的
    # skill_dump_ascii.json 只有 2.10 的 135 项，且顺序不同，不能再
    # 用“数组下标对应模型”的方式匹配。
    return runtime_skill_catalog_names()


@lru_cache(maxsize=1)
def model_skill_by_name() -> dict[str, object]:
    """Load the legacy classifier by name, never by the old array index."""
    from models.CczModels import CCZ_MODELS

    return {
        normalize_skill_name(getattr(skill, "name", "")): skill
        for skill in CCZ_MODELS.skills
        if getattr(skill, "name", "")
    }


@lru_cache(maxsize=1)
def runtime_skill_catalog_rows() -> tuple[dict, ...]:
    from ccz_randomizer.profiles import load_profile
    rows = [dict(row, name=catalog_skill_name(row))
            for row in load_profile().skills["runtimeCatalog"]]
    rows.sort(key=lambda row: int(row["id"]))
    return tuple(rows)


def runtime_skill_catalog_names() -> tuple[str, ...]:
    return tuple(str(row["name"]) for row in runtime_skill_catalog_rows())


def load_member_skills_from_memory(
    task_module,
    pid: int,
    record_indices: tuple[int, ...],
    members,
    *, planned_job_ids=None,
):
    snapshot = (read_skill_memory(pid, record_indices) if planned_job_ids is None else
                read_skill_memory(pid, record_indices, planned_job_ids=planned_job_ids))
    from ccz_randomizer.rules.skill_scores import DEFAULT_SCORES, DEFAULT_TYPES

    models_by_name = model_skill_by_name()
    unknown_type = task_module.CczType.UNKNOWN
    unknown_skills = []
    for member, memory_member in zip(members, snapshot.members):
        skill_list = []
        for category, definitions in (
            ("personal", memory_member.personal),
            ("job", memory_member.job),
        ):
            for definition in definitions:
                matched = models_by_name.get(normalize_skill_name(definition.display_name))
                if matched is None:
                    matched = models_by_name.get(normalize_skill_name(definition.base_name))
                if matched is None:
                    canonical_name = ""
                    model = None
                    unknown_skills.append(
                        {
                            "member": member.name,
                            "category": category,
                            "internal_id": definition.internal_id,
                            "display_name": definition.display_name,
                            "base_name": definition.base_name,
                            "format_type": definition.format_type,
                            "parameter": definition.parameter,
                        }
                    )
                else:
                    canonical_name, model = getattr(matched, "name", definition.display_name), matched
                default_type = DEFAULT_TYPES.get(
                    definition.display_name,
                    DEFAULT_TYPES.get(definition.base_name, "ALL_ROUNDER"),
                )
                skill_list.append(
                    SimpleNamespace(
                        name=definition.display_name,
                        canonical_name=canonical_name,
                        score=float(
                            getattr(
                                model,
                                "score",
                                DEFAULT_SCORES.get(definition.display_name, 0.0),
                            )
                        ),
                        type=(
                            getattr(model, "type", unknown_type)
                            if model is not None
                            else default_type,
                        ),
                        mat=getattr(model, "mat", None),
                        memory_category=category,
                        internal_skill_id=definition.internal_id,
                        skill_format_type=definition.format_type,
                        skill_parameter=definition.parameter,
                    )
                )
        member.skillList = skill_list
    diagnostic_log(
        "skill_memory_resolved",
        pid=pid,
        record_array_base=f"0x{snapshot.record_array_base:08X}",
        rule_table_base=f"0x{snapshot.rule_table_base:08X}",
        direct_job_match=snapshot.direct_job_match,
        members=[
            {
                "name": member.name,
                "record_index": memory_member.record_index,
                "member_id": memory_member.member_id,
                "job_id": memory_member.job_id,
                "personal": [
                    skill.name
                    for skill in member.skillList
                    if skill.memory_category == "personal"
                ],
                "job": [
                    skill.name
                    for skill in member.skillList
                    if skill.memory_category == "job"
                ],
            }
            for member, memory_member in zip(members, snapshot.members)
        ],
        unknown_skills=unknown_skills,
    )
    return snapshot


def load_selected_rule_members(task_module, pid, rules):
    from ccz_randomizer.runtime.personnel_memory import read_rule_job_ids
    names = active_profile(rules)["threePerson"]["qualifiedMembers"]
    validate_selected_members(names)
    positions = tuple(rule_member_indices()[name] for name in names)
    ids = read_rule_job_ids(pid, positions)
    members = []
    for name, job_id in zip(names, ids):
        job_name, score, job_type = JOB_MAP[job_id]
        members.append(SimpleNamespace(name=name, job=SimpleNamespace(name=job_name, score=score, type=job_type)))
    load_member_skills_from_memory(task_module, pid, positions, members,
                                  planned_job_ids=dict(zip(positions, ids)))
    return tuple(members)


def skill_name_groups(task_module) -> tuple[set[str], set[str], set[str]]:
    from models.CczModels import CCZ_MODELS
    from ccz_randomizer.rules.skill_defaults import SKILL_DEFAULTS

    carry_names: set[str] = {
        name for name, _score, category, _kind in SKILL_DEFAULTS
        if category == "优质"
    }
    strong_names: set[str] = {
        name for name, _score, category, _kind in SKILL_DEFAULTS
        if category == "强力"
    }
    special_names: set[str] = {
        name for name, _score, category, _kind in SKILL_DEFAULTS
        if category == "特殊"
    }
    for skill in CCZ_MODELS.skills:
        name = getattr(skill, "name", "")
        if task_module.CczUtils.isSkillSpecial(skill):
            special_names.add(name)
        if task_module.CczUtils.isSkillImba(skill):
            strong_names.add(name)
        elif task_module.CczUtils.isSkillCarry(skill):
            carry_names.add(name)
    return carry_names, strong_names, special_names


def skill_score_catalog() -> tuple[tuple[str, float, str, str], ...]:
    global _SKILL_SCORE_CATALOG
    if _SKILL_SCORE_CATALOG is not None:
        return _SKILL_SCORE_CATALOG
    with _SKILL_SCORE_CATALOG_LOCK:
        if _SKILL_SCORE_CATALOG is not None:
            return _SKILL_SCORE_CATALOG
        previous_cwd = Path.cwd()
        try:
            install(bundle_root())
            import task.CczReRandTask as task_module
            from models.CczModels import CCZ_MODELS
        finally:
            os.chdir(previous_cwd)

        catalog = []
        from ccz_randomizer.rules.skill_defaults import SKILL_DEFAULTS

        models_by_name = model_skill_by_name()
        default_by_name = {
            normalize_skill_name(name): (score, category, kind)
            for name, score, category, kind in SKILL_DEFAULTS
        }
        for row in runtime_skill_catalog_rows():
            name = row["name"]
            skill = models_by_name.get(normalize_skill_name(name))
            if skill is None:
                skill = models_by_name.get(normalize_skill_name(row["baseName"]))
            if normalize_skill_name(name) in default_by_name:
                default_score, category, type_name = default_by_name[normalize_skill_name(name)]
            elif skill is None:
                default_score, category, type_name = default_by_name.get(
                    normalize_skill_name(name), (0.0, "其他", "ALL_ROUNDER")
                )
            elif task_module.CczUtils.isSkillSpecial(skill):
                default_score, category = 5.0, "特殊"
                type_name = getattr(getattr(skill, "type", None), "name", "ALL_ROUNDER")
            elif task_module.CczUtils.isSkillImba(skill):
                default_score, category = 2.0, "强力"
                type_name = getattr(getattr(skill, "type", None), "name", "ALL_ROUNDER")
            elif task_module.CczUtils.isSkillCarry(skill):
                default_score, category = 1.0, "优质"
                type_name = getattr(getattr(skill, "type", None), "name", "ALL_ROUNDER")
            else:
                default_score, category = 0.0, "其他"
                type_name = getattr(getattr(skill, "type", None), "name", "ALL_ROUNDER")
            if type_name not in {"ALL_ROUNDER", "WARRIOR", "MASTER", "NONE"}:
                type_name = "ALL_ROUNDER"
            catalog.append((name, default_score, category, type_name))
        _SKILL_SCORE_CATALOG = tuple(catalog)
        return _SKILL_SCORE_CATALOG


def _runtime_type_name(value) -> str:
    type_name = getattr(value, "name", value)
    type_name = str(type_name)
    return (
        type_name
        if type_name in {"ALL_ROUNDER", "WARRIOR", "MASTER"}
        else "ALL_ROUNDER"
    )


def effective_member_skill_names(rules: dict, members) -> list[str]:
    from ccz_randomizer.rules.skill_scores import migrate_skill_scores, DEFAULT_TYPES
    profile = active_profile(rules)
    migrate_skill_scores(profile)
    seven = profile["sevenPerson"]
    if not seven["skillTypeMatchingEnabled"]:
        return [
            skill.name
            for member in members
            for skill in member.skillList
        ]
    job_type_overrides = profile["jobScoring"]["jobTypeOverrides"]
    skill_type_overrides = seven["skillTypeOverrides"]
    normalized_skill_types = {
        normalize_skill_name(skill_name): skill_type
        for skill_name, skill_type in skill_type_overrides.items()
    }
    names: list[str] = []
    for member in members:
        job = getattr(member, "job", None)
        job_name = str(getattr(job, "name", ""))
        job_type = job_type_overrides.get(
            job_name,
            _runtime_type_name(getattr(job, "type", "ALL_ROUNDER")),
        )
        for skill in member.skillList:
            skill_type = skill_type_overrides.get(
                skill.name,
                normalized_skill_types.get(
                    normalize_skill_name(skill.name),
                    DEFAULT_TYPES.get(skill.name, _runtime_type_name(
                        getattr(skill, "type", "ALL_ROUNDER")
                    )),
                ),
            )
            if not skill_types_match(job_type, skill_type):
                continue
            names.append(skill.name)
    return names


def evaluate_task_skill_rules(
    rules: dict,
    task_module,
    members,
    job_average: float,
):
    carry_names, strong_names, special_names = skill_name_groups(task_module)
    for member in members:
        for skill in member.skillList:
            canonical_name = getattr(skill, "canonical_name", "")
            if not canonical_name:
                continue
            if canonical_name in carry_names:
                carry_names.add(skill.name)
            if canonical_name in strong_names:
                strong_names.add(skill.name)
            if canonical_name in special_names:
                special_names.add(skill.name)
    member_skills = {
        member.name: [skill.name for skill in member.skillList]
        for member in members
    }
    return evaluate_skill_rules(
        rules,
        job_average,
        member_skills,
        carry_names,
        strong_names,
        special_names,
        effective_member_skill_names(rules, members),
        qualification=active_profile(rules)["skillQualification"],
        effective_skills_by_member={m.name: effective_member_skill_names(rules, (m,)) for m in members},
    )






def collect_accepted_equipment_and_publish(runner, result_slot: int, round_index: int):
    # The live detail must be emitted after collection, just like history.
    # Still publish the saved result if collection fails; postprocess handles
    # that failure without discarding the game's successfully saved slot.
    try:
        return runner.collect_equipment()
    finally:
        detail = result_detail_for_runner(runner, result_slot, round_index)
        if detail is not None:
            print(encode_result_detail(detail))





kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)
WINDOW_DESKTOP = 0
RESULT_RUN_STAMP = ""
RESULT_ROOT: Path | None = None
RESULT_PANEL_DIR: Path | None = None
RESULT_GRID_FILE: Path | None = None
STOP_REQUESTED = False
STOP_FILE_PATH: Path | None = None
RESULT_BASE_DIR: Path | None = None
DIAGNOSTIC_LOG_PATH: Path | None = None
DIAGNOSTIC_LOG_WRITER: RotatingTextWriter | None = None
DIAGNOSTIC_SUMMARY_PATH: Path | None = None
DIAGNOSTIC_FAILURE_COUNTS: dict[str, int] = {}
DIAGNOSTIC_FAILURE_HISTORY: list[dict[str, object]] = []
DIAGNOSTIC_SUMMARY_FIELDS: dict[str, object] = {}
DIAGNOSTIC_LOCK = threading.Lock()
DIAGNOSTIC_SCREENSHOT_LIMIT = 10
DIAGNOSTIC_SCREENSHOT_TYPES: set[str] = set()
UNKNOWN_EQUIPMENT_EFFECTS: set[tuple[int, int]] = set()
SISHUI_REPAIR_UNAVAILABLE_MESSAGE = "此功能未完善，请联系作者"


def notify_sishui_repair_unavailable(parent, toast=show_toast) -> None:
    toast(parent, SISHUI_REPAIR_UNAVAILABLE_MESSAGE, 3200)
CWP_SKIPINVISIBLE = 0x0001
CWP_SKIPDISABLED = 0x0002
CWP_SKIPTRANSPARENT = 0x0004


class Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


class BitmapInfoHeader(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BitmapInfo(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BitmapInfoHeader),
        ("bmiColors", wintypes.DWORD * 3),
    ]


class ProcessEntry32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


class StartupInfo(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class ProcessInformation(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


class JobObjectBasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class JobObjectExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JobObjectBasicLimitInformation),
        ("IoInfo", IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
kernel32.ReadProcessMemory.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.GetExitCodeProcess.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.GetExitCodeProcess.restype = wintypes.BOOL
kernel32.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
kernel32.GetFileAttributesW.restype = wintypes.DWORD
kernel32.SetFileAttributesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
kernel32.SetFileAttributesW.restype = wintypes.BOOL
kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
kernel32.CreateJobObjectW.restype = wintypes.HANDLE
kernel32.SetInformationJobObject.argtypes = [
    wintypes.HANDLE,
    ctypes.c_int,
    ctypes.c_void_p,
    wintypes.DWORD,
]
kernel32.SetInformationJobObject.restype = wintypes.BOOL
kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
kernel32.CreateSemaphoreW.argtypes = [
    ctypes.c_void_p,
    ctypes.c_long,
    ctypes.c_long,
    wintypes.LPCWSTR,
]
kernel32.CreateSemaphoreW.restype = wintypes.HANDLE
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.ReleaseSemaphore.argtypes = [
    wintypes.HANDLE,
    ctypes.c_long,
    ctypes.POINTER(ctypes.c_long),
]
kernel32.ReleaseSemaphore.restype = wintypes.BOOL
user32.CreateDesktopW.restype = wintypes.HANDLE
user32.CreateDesktopW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_void_p,
]
user32.CloseDesktop.argtypes = [wintypes.HANDLE]
user32.CloseDesktop.restype = wintypes.BOOL
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
user32.PrintWindow.restype = wintypes.BOOL

gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [
    wintypes.HDC,
    ctypes.c_int,
    ctypes.c_int,
]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.GetDIBits.argtypes = [
    wintypes.HDC,
    wintypes.HBITMAP,
    wintypes.UINT,
    wintypes.UINT,
    ctypes.c_void_p,
    ctypes.POINTER(BitmapInfo),
    wintypes.UINT,
]
gdi32.GetDIBits.restype = ctypes.c_int
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL


class Tee:
    def __init__(self, *streams):
        self.streams = tuple(
            stream for stream in streams if stream is not None
        )

    def write(self, text: str) -> int:
        for stream in self.streams:
            try:
                stream.write(text)
                stream.flush()
            except (AttributeError, OSError, ValueError):
                continue
        return len(text)

    def flush(self) -> None:
        for stream in self.streams:
            try:
                stream.flush()
            except (AttributeError, OSError, ValueError):
                continue


def diagnostic_log(event: str, **fields) -> None:
    if DIAGNOSTIC_LOG_PATH is None or DIAGNOSTIC_LOG_WRITER is None:
        return
    record = {
        "time": dt.datetime.now().isoformat(timespec="milliseconds"),
        **build_diagnostic_record(event, **fields),
    }
    try:
        line = json.dumps(
            record,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        )
        with DIAGNOSTIC_LOCK:
            DIAGNOSTIC_LOG_WRITER.write(line + "\n")
            DIAGNOSTIC_LOG_WRITER.flush()
    except Exception:
        pass


@contextmanager
def diagnostic_timing(
    phase: str,
    *,
    result_slot: int | None = None,
    attempt: int | None = None,
    round_number: int | None = None,
    **fields,
):
    started = time.perf_counter()
    diagnostic_log(
        "timing_started",
        phase=phase,
        result_slot=result_slot,
        attempt=attempt,
        round_number=round_number,
        **fields,
    )
    try:
        yield
    except BaseException as exc:
        diagnostic_log(
            "timing_finished",
            phase=phase,
            result_slot=result_slot,
            attempt=attempt,
            round_number=round_number,
            elapsed_ms=round((time.perf_counter() - started) * 1000),
            outcome="error",
            error=repr(exc),
            **fields,
        )
        raise
    else:
        diagnostic_log(
            "timing_finished",
            phase=phase,
            result_slot=result_slot,
            attempt=attempt,
            round_number=round_number,
            elapsed_ms=round((time.perf_counter() - started) * 1000),
            outcome="ok",
            **fields,
        )


def diagnostic_error(
    event: str,
    exc: BaseException,
    *,
    game: object | None = None,
    **fields,
) -> str:
    details = exception_diagnostic(exc)
    if game is not None:
        try:
            pid = int(getattr(game, "pid", 0))
            hwnd = int(getattr(game, "main_window", 0))
            if pid:
                details["game_state"] = game_state_diagnostic(pid, hwnd)
                details["game_healthy"] = bool(game.is_healthy())
        except Exception as snapshot_exc:
            details["game_state_error"] = repr(snapshot_exc)
    diagnostic_log(event, failure=details, **fields)
    update_diagnostic_summary(
        status="failed",
        latest_failure={
            "event": event,
            "time": dt.datetime.now().isoformat(timespec="milliseconds"),
            "failure": details,
            "fields": fields,
        },
    )
    return str(details["error_id"])


def update_diagnostic_summary(
    *,
    status: str | None = None,
    latest_failure: dict[str, object] | None = None,
    **fields,
) -> None:
    if DIAGNOSTIC_SUMMARY_PATH is None:
        return
    with DIAGNOSTIC_LOCK:
        DIAGNOSTIC_SUMMARY_FIELDS.update(
            {key: value for key, value in fields.items() if value is not None}
        )
        if latest_failure is not None:
            failure = latest_failure.get("failure", {})
            fingerprint = (
                failure.get("fingerprint")
                if isinstance(failure, dict)
                else None
            )
            if fingerprint:
                DIAGNOSTIC_FAILURE_COUNTS[fingerprint] = (
                    DIAGNOSTIC_FAILURE_COUNTS.get(fingerprint, 0) + 1
                )
            DIAGNOSTIC_FAILURE_HISTORY.append(latest_failure)
            del DIAGNOSTIC_FAILURE_HISTORY[:-20]
        payload = {
            "schema": 1,
            "updated_at": dt.datetime.now().isoformat(
                timespec="milliseconds"
            ),
            "status": status,
            "failure_counts": dict(DIAGNOSTIC_FAILURE_COUNTS),
            "latest_failure": (
                DIAGNOSTIC_FAILURE_HISTORY[-1]
                if DIAGNOSTIC_FAILURE_HISTORY
                else None
            ),
            "recent_failures": list(DIAGNOSTIC_FAILURE_HISTORY),
            **DIAGNOSTIC_SUMMARY_FIELDS,
        }
        temporary = DIAGNOSTIC_SUMMARY_PATH.with_suffix(
            DIAGNOSTIC_SUMMARY_PATH.suffix + ".tmp"
        )
        try:
            temporary.write_text(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    default=str,
                    indent=2,
                ),
                encoding="utf-8",
            )
            os.replace(temporary, DIAGNOSTIC_SUMMARY_PATH)
        except Exception:
            temporary.unlink(missing_ok=True)


def is_running_as_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def file_diagnostic(path: Path) -> dict[str, object]:
    try:
        data = path.read_bytes()
        return {
            "path": str(path),
            "exists": True,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    except Exception as exc:
        return {
            "path": str(path),
            "exists": path.exists(),
            "error": repr(exc),
        }


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return source_root()


@lru_cache(maxsize=1)
def application_build_info() -> dict:
    fallback_version_path = source_root() / "VERSION"
    fallback_version = (
        fallback_version_path.read_text(encoding="utf-8").strip()
        if fallback_version_path.is_file()
        else "unknown"
    )
    fallback = {
        "version": fallback_version,
        "buildId": "development",
        "builtAt": "development",
        "sourceHash": "development",
        "gitCommit": "development",
        "gitDirty": True,
        "python": sys.version.split()[0],
    }
    if not getattr(sys, "frozen", False):
        return fallback

    path = Path(sys._MEIPASS) / "build_info.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return fallback
    if not isinstance(loaded, dict):
        return fallback
    return {**fallback, **loaded}


def build_version_text(info: dict | None = None) -> str:
    info = info or application_build_info()
    commit = str(info.get("gitCommit", "unknown"))
    if info.get("gitDirty"):
        commit += "+dirty"
    return (
        f"{info.get('version', 'unknown')} | "
        f"构建 {info.get('buildId', 'unknown')} | "
        f"源码 {commit}"
    )


@lru_cache(maxsize=1)
def application_changelog() -> tuple[dict[str, object], ...]:
    path = (
        Path(sys._MEIPASS) / "CHANGELOG.json"
        if getattr(sys, "frozen", False)
        else source_root() / "CHANGELOG.json"
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return ()
    if not isinstance(payload, list):
        return ()
    entries = []
    for raw_entry in payload:
        if not isinstance(raw_entry, dict):
            continue
        version = str(raw_entry.get("version", "")).strip()
        date = str(raw_entry.get("date", "")).strip()
        raw_changes = raw_entry.get("changes")
        if (
            not version
            or not date
            or not isinstance(raw_changes, list)
        ):
            continue
        changes = tuple(
            str(change).strip()
            for change in raw_changes
            if str(change).strip()
        )
        if not changes:
            continue
        entries.append(
            {
                "version": version,
                "date": date,
                "changes": changes,
            }
        )
    return tuple(entries)


def show_changelog_window(
    parent,
    entries: tuple[dict[str, object], ...] | None = None,
) -> None:
    import tkinter as tk
    from tkinter import ttk

    rows = application_changelog() if entries is None else entries
    dialog = centered_toplevel(parent)
    dialog.withdraw()
    dialog.title("版本更新记录")
    dialog.geometry("720x560")
    dialog.minsize(620, 460)
    dialog.transient(parent)

    header = tk.Frame(dialog, padx=18)
    header.pack(fill="x", pady=(16, 10))
    tk.Label(
        header,
        text="版本更新记录",
        font=("Microsoft YaHei UI", 13, "bold"),
        anchor="w",
    ).pack(fill="x")
    tk.Label(
        header,
        text="按版本查看新增功能、优化和问题修正。",
        fg="#666666",
        anchor="w",
    ).pack(fill="x", pady=(4, 0))

    body = tk.Frame(dialog, padx=18)
    body.pack(fill="both", expand=True)
    text = tk.Text(
        body,
        wrap="word",
        relief="solid",
        borderwidth=1,
        padx=16,
        pady=12,
        font=("Microsoft YaHei UI", 10),
        spacing3=5,
    )
    scrollbar = ttk.Scrollbar(
        body,
        orient="vertical",
        command=text.yview,
    )
    text.configure(yscrollcommand=scrollbar.set)
    text.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    text.tag_configure(
        "version",
        font=("Microsoft YaHei UI", 11, "bold"),
        foreground="#1f4e79",
        spacing1=12,
        spacing3=6,
    )
    text.tag_configure(
        "current",
        foreground="#9a5b18",
    )
    text.tag_configure(
        "change",
        lmargin1=10,
        lmargin2=28,
        spacing3=4,
    )
    current_version = str(
        application_build_info().get("version", "")
    ).strip()
    if rows:
        for entry in rows:
            version = str(entry["version"])
            heading = f"V{version}  {entry['date']}"
            tag = "current" if version == current_version else "version"
            if version == current_version:
                heading += "  当前版本"
            text.insert("end", heading + "\n", (tag, "version"))
            for change in entry["changes"]:
                text.insert("end", f"• {change}\n", "change")
    else:
        text.insert("end", "暂无可用的版本更新记录。")
    text.configure(state="disabled")

    footer = tk.Frame(dialog, padx=18, pady=14)
    footer.pack(fill="x")
    ttk.Button(
        footer,
        text="关闭",
        command=dialog.destroy,
        width=10,
    ).pack(side="right")

    dialog.update_idletasks()
    width = max(720, dialog.winfo_reqwidth())
    height = max(560, dialog.winfo_reqheight())
    dialog.geometry(f"{width}x{height}")
    show_centered(dialog)
    dialog.lift()
    dialog.grab_set()


def bind_version_changelog(version_label, parent) -> None:
    from ccz_randomizer.ui.tooltip import HoverTooltip
    version_label._changelog_tooltip = HoverTooltip(version_label, "双击查看更新日志")
    version_label.configure(cursor="hand2")
    version_label.bind(
        "<Double-Button-1>",
        lambda _event: show_changelog_window(parent),
    )


def bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "original"
    configured = os.environ.get("CCZ_RUNTIME_ROOT")
    if configured:
        candidate = Path(configured)
        return (candidate if candidate.is_absolute() else source_root() / candidate).resolve()
    return source_root().parent / "exe-analysis" / "tool.exe_extracted"


def source_root() -> Path:
    return Path(__file__).resolve().parents[1]


def source_entry_path() -> Path:
    return source_root() / "fast_randomizer.py"


def application_directory() -> Path:
    """Directory beside the EXE; profile updates live here for portability."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return source_root()


def native_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "native"
    return source_root() / "native"


def ui_asset_path(name: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / name
    return source_root() / "resources" / "app" / name


def native_control_error_hint(
    return_code: int,
    details: str = "",
) -> str:
    normalized_details = details.casefold()
    if "ntstatus=0xc000010a" in normalized_details:
        return (
            "\n后台游戏进程正在退出，工具将重新启动游戏后继续。"
        )
    if return_code == 2:
        if is_running_as_admin():
            return (
                "\n工具已使用管理员权限，但仍无法连接后台游戏。"
                "\n请先退出已经打开的 Ekd5.exe，再重新运行工具；"
                "如果仍然失败，请按安全软件拦截问题处理。"
            )
        return (
            "\n工具没有足够权限连接后台游戏。"
            "\n请关闭工具和 Ekd5.exe，然后右键本工具选择“以管理员身份运行”。"
        )
    if return_code in (3, 4, 9):
        return (
            "\n电脑的安全软件阻止了工具与后台游戏通信。"
            + native_control_security_steps()
        )
    if return_code in (5, 10):
        return (
            "\n电脑拒绝加载后台控制组件。最常见原因是 360、火绒、"
            "电脑管家、Windows 安全中心或单位安全软件进行了拦截。"
            + native_control_security_steps()
        )
    control_module_loaded = bool(
        re.search(r"remote_module=0x0*[1-9a-f][0-9a-f]*", normalized_details)
        and re.search(
            r"remote_export=0x0*[1-9a-f][0-9a-f]*",
            normalized_details,
        )
    )
    if return_code == 7 and control_module_loaded:
        return (
            "\n后台控制组件已加载，但本次操作未完成。"
            "工具将重新启动当前后台游戏实例后继续。"
        )
    if return_code in (6, 7, 8):
        return (
            "\n后台控制组件没有完整加载，文件可能被拦截、隔离或损坏。"
            + native_control_security_steps()
        )
    return (
        "\n后台游戏未能正常响应。请先关闭游戏和本工具后重试；"
        "若再次失败，请把普通日志和诊断日志一起发给工具作者。"
    )


def native_control_security_steps() -> str:
    steps = []
    if is_running_as_admin():
        steps.append("当前已使用管理员权限运行，无需再次尝试管理员模式。")
    else:
        steps.append(
            "关闭工具和 Ekd5.exe，右键本工具，选择“以管理员身份运行”。"
        )
    steps.extend(
        (
            "如果安装了 360、火绒或电脑管家，请打开拦截记录或隔离区，"
            "恢复被拦截的文件，并把整个游戏目录加入信任区。"
            "也可以暂时完全退出安全软件做一次验证；验证后请重新开启。",
            "打开“Windows 安全中心 > 病毒和威胁防护 > 保护历史记录”，"
            "允许与本工具、Ekd5.exe 或 ccz_control.dll 有关的拦截；"
            "必要时把整个游戏目录加入排除项。",
            "确认已经完整解压，并把工具放在游戏目录中运行；"
            "不要直接从压缩包、网盘预览目录或临时目录启动。",
            "如果是公司、学校或网吧电脑，可能启用了应用控制或终端防护策略，"
            "普通用户无法自行解除，需要联系电脑管理员放行。",
            "处理后关闭残留的工具和 Ekd5.exe，再重新运行。"
            "仍然失败时，请把普通日志和诊断日志一起发回。",
        )
    )
    return "\n请按顺序处理：\n" + "\n".join(
        f"{index}. {step}" for index, step in enumerate(steps, start=1)
    )


def missing_native_components_message(component_names: list[str]) -> str:
    return (
        "后台控制组件缺失，可能已被杀毒软件误报并隔离："
        + "、".join(component_names)
        + "。\n\n"
        "请打开 Windows 安全中心、360、火绒或电脑管家的"
        "保护历史记录/隔离区，恢复与本工具有关的文件，"
        "并把整个游戏目录加入信任区。\n"
        "处理完成后，请重新获取完整的工具程序并放到游戏目录运行。"
    )


def security_software_block_details(
    error: BaseException,
) -> dict[str, object] | None:
    pending = [error]
    visited: set[int] = set()
    paths: list[str] = []
    matched_error = ""
    while pending:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        message = str(current)
        if (
            getattr(current, "winerror", None) == 225
            or "[winerror 225]" in message.casefold()
        ):
            matched_error = message
            for attribute in ("filename", "filename2"):
                value = getattr(current, attribute, None)
                if value:
                    path = str(value)
                    if path not in paths:
                        paths.append(path)
        cause = getattr(current, "__cause__", None)
        context = getattr(current, "__context__", None)
        if cause is not None:
            pending.append(cause)
        if context is not None:
            pending.append(context)
    if not matched_error:
        return None
    return {
        "winerror": 225,
        "message": matched_error,
        "paths": paths,
    }


def encode_security_software_blocked_event(details: dict[str, object]) -> str:
    return SECURITY_SOFTWARE_BLOCKED_EVENT + json.dumps(
        details,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def decode_security_software_blocked_event(
    line: str,
) -> dict[str, object] | None:
    if not line.startswith(SECURITY_SOFTWARE_BLOCKED_EVENT):
        return None
    payload = json.loads(line[len(SECURITY_SOFTWARE_BLOCKED_EVENT) :])
    if not isinstance(payload, dict) or payload.get("winerror") != 225:
        raise ValueError("安全软件拦截事件格式无效")
    raw_paths = payload.get("paths", [])
    if not isinstance(raw_paths, list):
        raise ValueError("安全软件拦截路径格式无效")
    return {
        "winerror": 225,
        "message": str(payload.get("message", "")),
        "paths": [str(path) for path in raw_paths if str(path).strip()],
    }


def report_worker_exception(
    error: BaseException,
    log_file,
    blocked_details: dict[str, object] | None = None,
) -> None:
    details = (
        blocked_details
        if blocked_details is not None
        else security_software_block_details(error)
    )
    if details is None:
        traceback.print_exception(
            type(error),
            error,
            error.__traceback__,
        )
        return
    for path in details.get("paths", []):
        log_file.write(f"被安全软件拦截的文件：{path}\n")
    traceback.print_exception(
        type(error),
        error,
        error.__traceback__,
        file=log_file,
    )
    print(encode_security_software_blocked_event(details))


class NativeControlError(RuntimeError):
    def __init__(self, return_code: int, details: str = "") -> None:
        self.return_code = return_code
        self.details = details
        super().__init__(
            f"静默控件模块执行失败，代码 {return_code}"
            + (f"：{details}" if details else "")
            + native_control_error_hint(return_code, details)
        )


class PersistentNativeController:
    """Keep one injected controller alive for the lifetime of a game PID."""

    def __init__(self, pid: int) -> None:
        injector = native_dir() / "ccz_injector.exe"
        control_dll = native_dir() / "ccz_control.dll"
        self.pid = pid
        self.process = subprocess.Popen(
            [
                str(injector),
                "--server",
                str(pid),
                str(control_dll),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="ascii",
            errors="replace",
            bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        ready = self.process.stdout.readline() if self.process.stdout else ""
        if ready.strip() != "READY":
            stderr = (
                self.process.stderr.read().strip()
                if self.process.stderr
                else ""
            )
            return_code = self.process.poll() or 7
            self.close()
            raise NativeControlError(
                return_code,
                stderr or "持久化控件模块未就绪",
            )
        self._responses: queue.Queue[int] = queue.Queue()
        self._reader = threading.Thread(
            target=self._read_responses,
            name=f"ccz-native-{pid}",
            daemon=True,
        )
        self._reader.start()
        self._write_lock = threading.Lock()

    def _read_responses(self) -> None:
        stdout = self.process.stdout
        if stdout is None:
            return
        for line in stdout:
            try:
                self._responses.put(int(line.strip()))
            except ValueError:
                continue
        self._responses.put(-1)

    def execute(
        self,
        arguments: list[str],
        *,
        interruptible: bool = True,
    ) -> None:
        line = encode_native_request(arguments)
        started = time.perf_counter()
        with self._write_lock:
            if self.process.poll() is not None:
                raise NativeControlError(
                    self.process.returncode or 7,
                    "持久化控件进程已退出",
                )
            if self.process.stdin is None:
                raise NativeControlError(7, "持久化控件输入通道不可用")
            self.process.stdin.write(line)
            self.process.stdin.flush()
            while True:
                if interruptible and stop_is_requested():
                    self.close()
                    raise KeyboardInterrupt
                try:
                    result = self._responses.get(timeout=0.25)
                    break
                except queue.Empty:
                    if self.process.poll() is not None:
                        raise NativeControlError(
                            self.process.returncode or 7,
                            "持久化控件进程异常退出",
                        )
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        if result != 0:
            raise NativeControlError(
                result,
                f"持久化控件返回错误，耗时 {elapsed_ms} 毫秒",
            )
        if elapsed_ms >= 1000:
            diagnostic_log(
                "persistent_native_control_completed",
                pid=self.pid,
                action=arguments,
                elapsed_ms=elapsed_ms,
            )

    def close(self) -> None:
        process = getattr(self, "process", None)
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
        self.process = None


_PERSISTENT_CONTROLLERS: dict[int, PersistentNativeController] = {}
_PERSISTENT_CONTROLLERS_LOCK = threading.Lock()


def start_persistent_native_controller(pid: int) -> None:
    if os.environ.get("CCZ_DISABLE_PERSISTENT_NATIVE") == "1":
        return
    with _PERSISTENT_CONTROLLERS_LOCK:
        if pid in _PERSISTENT_CONTROLLERS:
            return
        try:
            _PERSISTENT_CONTROLLERS[pid] = PersistentNativeController(pid)
        except Exception as exc:
            diagnostic_error(
                "persistent_native_controller_start_failed",
                exc,
                pid=pid,
            )


def stop_persistent_native_controller(pid: int) -> None:
    with _PERSISTENT_CONTROLLERS_LOCK:
        controller = _PERSISTENT_CONTROLLERS.pop(pid, None)
    if controller is not None:
        controller.close()


class NativeControlTimeout(RuntimeError):
    pass


class InteractionNotTriggered(RuntimeError):
    """The game accepted background input without advancing randomization."""


class WindowCaptureUnavailable(InteractionNotTriggered):
    """All background capture methods failed for a game window region."""


class DirectReloadUnsupported(InteractionNotTriggered):
    """The current machine cannot safely reuse a running game instance."""


class NormalReloadUnsupported(InteractionNotTriggered):
    """The current game instance cannot complete the normal load workflow."""


class InspectionProcessError(RuntimeError):
    """A separate result-inspection game instance failed."""

    def __init__(
        self,
        stage: str,
        subprocess_returncode: int | None,
        details: str,
        *,
        timed_out: bool = False,
        child_log_path: Path | None = None,
        child_diagnostic_path: Path | None = None,
        child_stdout_path: Path | None = None,
        click_strategy: str | None = None,
        elapsed_seconds: float | None = None,
    ):
        self.stage = stage
        self.subprocess_returncode = subprocess_returncode
        self.details = details
        match = re.search(r"静默控件模块执行失败，代码\s+(-?\d+)", details)
        self.return_code = int(match.group(1)) if match else None
        self.inner_error_type = (
            "NativeControlError" if "NativeControlError" in details else None
        )
        self.native_timeout = timed_out or (
            "remote thread timed out" in details.casefold()
            or "响应超时" in details
        )
        self.child_log_path = child_log_path
        self.child_diagnostic_path = child_diagnostic_path
        self.child_stdout_path = child_stdout_path
        self.click_strategy = click_strategy
        self.elapsed_seconds = elapsed_seconds
        label = "初始三人能力检查" if stage == "initial" else "候选结果界面检查"
        super().__init__(label + "失败" + (f"：{details}" if details else ""))


def stop_is_requested() -> bool:
    return STOP_REQUESTED or (
        STOP_FILE_PATH is not None and STOP_FILE_PATH.exists()
    )


def check_stop_requested() -> None:
    if stop_is_requested():
        raise KeyboardInterrupt


def interruptible_sleep(seconds: float, interval: float = 0.05) -> None:
    remaining = max(0.0, seconds)
    while remaining > 0:
        check_stop_requested()
        sleep_seconds = min(interval, remaining)
        time.sleep(sleep_seconds)
        remaining -= sleep_seconds


@contextmanager
def critical_random_operation(name: str):
    marker_value = os.environ.get(
        "CCZ_CRITICAL_OPERATION_FILE",
        "",
    ).strip()
    marker = Path(marker_value) if marker_value else None
    if marker is not None:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(name, encoding="utf-8")
    try:
        yield
    finally:
        if marker is not None:
            marker.unlink(missing_ok=True)


def native_control_slot_count() -> int:
    configured = os.environ.get(
        "CCZ_NATIVE_CONTROL_CONCURRENCY",
        str(NATIVE_CONTROL_DEFAULT_SLOTS),
    ).strip()
    try:
        value = int(configured)
    except ValueError:
        value = NATIVE_CONTROL_DEFAULT_SLOTS
    return max(1, min(value, 32))


@contextmanager
def native_control_gate():
    """Limit cross-process DLL/window-control bursts on one machine."""
    slot_count = native_control_slot_count()
    semaphore = kernel32.CreateSemaphoreW(
        None,
        slot_count,
        slot_count,
        NATIVE_CONTROL_SEMAPHORE_NAME,
    )
    if not semaphore:
        diagnostic_log(
            "native_control_gate_unavailable",
            slot_count=slot_count,
            error=ctypes.WinError(ctypes.get_last_error()),
        )
        yield
        return

    acquired = False
    try:
        while True:
            result = kernel32.WaitForSingleObject(semaphore, 250)
            if result == WAIT_OBJECT_0:
                acquired = True
                break
            if result == WAIT_TIMEOUT:
                check_stop_requested()
                continue
            raise ctypes.WinError(ctypes.get_last_error())
        yield
    finally:
        if acquired:
            kernel32.ReleaseSemaphore(semaphore, 1, None)
        kernel32.CloseHandle(semaphore)


def _run_native_control_once(
    pid: int,
    arguments: list[str],
    *,
    interruptible: bool = True,
) -> None:
    injector = native_dir() / "ccz_injector.exe"
    control_dll = native_dir() / "ccz_control.dll"
    missing_components = [
        path.name
        for path in (injector, control_dll)
        if not path.is_file()
    ]
    if missing_components:
        raise FileNotFoundError(
            missing_native_components_message(missing_components)
        )
    action = arguments[0] if arguments else ""
    if action == "title-load":
        timeout = 8
    elif action in {
        "openload", "real-load", "dispatch-state",
        "silent-burst", "silent-burst-timed", "pulse-burst"
    }:
        timeout = 70
    else:
        timeout = 8
    command = [
        str(injector),
        str(pid),
        str(control_dll),
        *arguments,
    ]
    started = time.perf_counter()
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    deadline = time.perf_counter() + timeout
    while process.poll() is None:
        if interruptible and stop_is_requested():
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
            diagnostic_log(
                "native_control_cancelled",
                pid=pid,
                action=arguments,
                elapsed_ms=round(
                    (time.perf_counter() - started) * 1000
                ),
            )
            raise KeyboardInterrupt
        if time.perf_counter() >= deadline:
            process.kill()
            stdout, stderr = process.communicate()
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            diagnostic_log(
                "native_control_timeout",
                pid=pid,
                action=arguments,
                timeout_seconds=timeout,
                elapsed_ms=elapsed_ms,
                running_as_admin=is_running_as_admin(),
                windows=sys.getwindowsversion(),
                injector=file_diagnostic(injector),
                control_dll=file_diagnostic(control_dll),
                stdout=stdout.decode(errors="replace"),
                stderr=stderr.decode(errors="replace"),
            )
            raise NativeControlTimeout(
                "静默控件模块响应超时"
                + native_control_error_hint(-1)
            )
        time.sleep(0.05)
    stdout, stderr = process.communicate()
    result = subprocess.CompletedProcess(
        command,
        process.returncode,
        stdout,
        stderr,
    )
    if process.returncode is None:
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        raise RuntimeError(
            f"静默控件模块未返回退出状态，已等待 {elapsed_ms} 毫秒"
        )
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    if result.returncode != 0:
        stdout = result.stdout.decode(errors="replace").strip()
        details = result.stderr.decode(errors="replace").strip()
        diagnostic_log(
            "native_control_failed",
            pid=pid,
            action=arguments,
            return_code=result.returncode,
            elapsed_ms=elapsed_ms,
            stdout=stdout,
            stderr=details,
            running_as_admin=is_running_as_admin(),
            windows=sys.getwindowsversion(),
            executable=sys.executable,
            app_dir=app_dir(),
            temp_dir=tempfile.gettempdir(),
            injector=file_diagnostic(injector),
            control_dll=file_diagnostic(control_dll),
        )
        raise NativeControlError(result.returncode, details)
    if elapsed_ms >= 1000 or action in {
        "list",
        "openload",
        "real-load",
        "dispatch-state",
    }:
        diagnostic_log(
            "native_control_completed",
            pid=pid,
            action=arguments,
            elapsed_ms=elapsed_ms,
            stdout=result.stdout.decode(errors="replace").strip(),
            stderr=result.stderr.decode(errors="replace").strip(),
        )


def run_native_control(
    pid: int,
    arguments: list[str],
    *,
    interruptible: bool = True,
) -> None:
    action = arguments[0] if arguments else ""
    attempts = 2 if action in NATIVE_CONTROL_RETRY_ACTIONS else 1
    for attempt in range(attempts):
        try:
            with native_control_gate():
                with _PERSISTENT_CONTROLLERS_LOCK:
                    persistent = _PERSISTENT_CONTROLLERS.get(pid)
                if persistent is not None:
                    try:
                        persistent.execute(
                            arguments,
                            interruptible=interruptible,
                        )
                        return
                    except KeyboardInterrupt:
                        raise
                    except Exception as exc:
                        diagnostic_error(
                            "persistent_native_controller_failed",
                            exc,
                            pid=pid,
                            action=arguments,
                            attempt=attempt + 1,
                        )
                        stop_persistent_native_controller(pid)
                return _run_native_control_once(
                    pid,
                    arguments,
                    interruptible=interruptible,
                )
        except NativeControlError as exc:
            if (
                exc.return_code != 7
                or attempt + 1 >= attempts
            ):
                raise
            diagnostic_log(
                "native_control_retry",
                pid=pid,
                action=arguments,
                return_code=exc.return_code,
                attempt=attempt + 1,
                delay_seconds=NATIVE_CONTROL_RETRY_DELAY_SECONDS,
            )
            interruptible_sleep(NATIVE_CONTROL_RETRY_DELAY_SECONDS)


def native_silent_click(
    pid: int,
    hwnd: int,
    x: int,
    y: int,
    *,
    tail_delay_ms: int | None = None,
) -> None:
    action = "silent-click" if tail_delay_ms is None else "silent-click-timed"
    arguments = [action, str(hwnd), str(x), str(y)]
    if tail_delay_ms is not None:
        arguments.append(str(tail_delay_ms))
    run_native_control(pid, arguments)


def activate_save_list_item(pid: int, index: int) -> None:
    run_native_control(pid, ["list", str(index - 1)])


def native_background_click(
    hwnd: int,
    client_x: int,
    client_y: int,
    count: int,
    right: bool,
) -> None:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return
    try:
        run_native_control(
            pid.value,
            [
                "click",
                str(hwnd),
                str(client_x),
                str(client_y),
                str(count),
                "1" if right else "0",
            ],
        )
    except NativeControlTimeout as exc:
        # A modal window blocks the injected click call until it closes,
        # although the click itself has already been delivered.
        if "响应超时" in str(exc):
            diagnostic_log(
                "background_click_timeout_ignored",
                pid=pid.value,
                hwnd=hwnd,
                x=client_x,
                y=client_y,
                count=count,
                right=right,
            )
            return
        raise


def native_silent_click_burst(
    hwnd: int,
    client_x: int,
    client_y: int,
    count: int,
    *,
    down_delay_ms: int | None = None,
    up_delay_ms: int | None = None,
) -> None:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return
    if down_delay_ms is None and up_delay_ms is None:
        action = [
            "silent-burst",
            str(hwnd),
            str(client_x),
            str(client_y),
            str(count),
        ]
    else:
        action = [
            "silent-burst-timed",
            str(hwnd),
            str(client_x),
            str(client_y),
            str(count),
            str(55 if down_delay_ms is None else down_delay_ms),
            str(95 if up_delay_ms is None else up_delay_ms),
        ]
    run_native_control(pid.value, action)


def native_wake_game(pid: int, hwnd: int, duration_ms: int = 1500) -> None:
    run_native_control(
        pid,
        ["wake", str(hwnd), str(duration_ms)],
    )


def native_enable_acceleration(pid: int) -> None:
    run_native_control(pid, ["enable-acceleration"])


def native_direct_load(pid: int, slot: int) -> None:
    run_native_control(pid, ["load", str(slot)])


def native_end_dialog(pid: int, hwnd: int, result: int = 1) -> None:
    run_native_control(
        pid, ["end-dialog", str(hwnd), str(result)]
    )


def native_game_tick(pid: int) -> None:
    run_native_control(pid, ["tick"])


def native_process_load_state(pid: int) -> None:
    run_native_control(pid, ["process-state"])


def native_dispatch_load_state(pid: int) -> None:
    run_native_control(pid, ["dispatch-state"])


def native_mark_load_ready(pid: int, value: int = 0) -> None:
    run_native_control(pid, ["mark-ready", str(value)])


def native_load_dialog_item(pid: int, slot: int) -> None:
    run_native_control(pid, ["loadui", str(slot - 1), "0"])


def native_open_load_dialog(pid: int) -> subprocess.Popen:
    return subprocess.Popen(
        [
            str(native_dir() / "ccz_injector.exe"),
            str(pid),
            str(native_dir() / "ccz_control.dll"),
            "openload",
        ],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def find_process_ids(exe_name: str) -> tuple[int, ...]:
    matches = []
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot == wintypes.HANDLE(-1).value:
        return ()
    try:
        entry = ProcessEntry32()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return ()
        while True:
            if entry.szExeFile.casefold() == exe_name.casefold():
                matches.append(int(entry.th32ProcessID))
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                return tuple(matches)
    finally:
        kernel32.CloseHandle(snapshot)


def find_process_id(exe_name: str) -> int | None:
    matches = find_process_ids(exe_name)
    return matches[0] if matches else None


def process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    handle = kernel32.OpenProcess(
        SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION,
        False,
        pid,
    )
    if not handle:
        return False
    try:
        return kernel32.WaitForSingleObject(handle, 0) != 0
    finally:
        kernel32.CloseHandle(handle)


def process_exit_code(process_handle: int) -> int | None:
    if not process_handle:
        return None
    exit_code = wintypes.DWORD()
    if not kernel32.GetExitCodeProcess(
        process_handle,
        ctypes.byref(exit_code),
    ):
        return None
    return int(exit_code.value)


def running_process_names() -> set[str]:
    names: set[str] = set()
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot == wintypes.HANDLE(-1).value:
        return names
    try:
        entry = ProcessEntry32()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return names
        while True:
            names.add(entry.szExeFile.casefold())
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                return names
    finally:
        kernel32.CloseHandle(snapshot)


def detect_360_security_processes() -> tuple[str, ...]:
    matches = running_process_names().intersection(
        SECURITY_360_PROCESS_NAMES
    )
    return tuple(sorted(matches))


def available_physical_memory_bytes() -> int | None:
    status = MemoryStatusEx()
    status.dwLength = ctypes.sizeof(status)
    if not kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return int(status.ullAvailPhys)


def process_executable(pid: int) -> Path | None:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(
            handle, 0, buffer, ctypes.byref(size)
        ):
            return None
        return Path(buffer.value)
    finally:
        kernel32.CloseHandle(handle)


def locate_game_executable() -> Path:
    configured_game = os.environ.get("CCZ_GAME_EXE")
    if configured_game:
        configured_path = Path(configured_game)
        if configured_path.is_file():
            return configured_path

    local_game = app_dir() / GAME_EXE_NAME
    if local_game.is_file():
        return local_game

    pid = find_process_id(GAME_EXE_NAME)
    if pid is not None:
        running_game = process_executable(pid)
        if running_game is not None and running_game.is_file():
            return running_game

    raise FileNotFoundError(
        f"未找到 {GAME_EXE_NAME}。请把本工具放到游戏目录后运行。"
    )


def runtime_game_directory(game_executable: Path) -> Path:
    configured = os.environ.get("CCZ_GAME_RUNTIME_DIR", "").strip()
    if not configured:
        return game_executable.parent
    runtime_dir = Path(configured).resolve()
    if not runtime_dir.is_dir():
        raise FileNotFoundError(f"兼容模式运行目录不存在：{runtime_dir}")
    return runtime_dir


def prepare_random_game_executable(game_executable: Path) -> Path:
    source = game_executable.resolve()
    target = source.with_name(RANDOM_GAME_EXE_NAME)
    try:
        if target.is_file() and os.path.samefile(source, target):
            show_file(source)
    except OSError:
        pass
    target.unlink(missing_ok=True)
    shutil.copy2(source, target)
    hide_random_game_executable(target)
    return target


def show_file(path: Path) -> None:
    attributes = kernel32.GetFileAttributesW(str(path))
    if attributes == INVALID_FILE_ATTRIBUTES:
        raise ctypes.WinError(ctypes.get_last_error())
    if not attributes & FILE_ATTRIBUTE_HIDDEN:
        return
    if not kernel32.SetFileAttributesW(
        str(path),
        attributes & ~FILE_ATTRIBUTE_HIDDEN,
    ):
        raise ctypes.WinError(ctypes.get_last_error())


def hide_random_game_executable(path: Path) -> None:
    attributes = kernel32.GetFileAttributesW(str(path))
    if attributes == INVALID_FILE_ATTRIBUTES:
        raise ctypes.WinError(ctypes.get_last_error())
    if attributes & FILE_ATTRIBUTE_HIDDEN:
        return
    if not kernel32.SetFileAttributesW(
        str(path),
        attributes | FILE_ATTRIBUTE_HIDDEN,
    ):
        raise ctypes.WinError(ctypes.get_last_error())


def remove_random_game_executable(path: Path) -> None:
    if path.name.casefold() != RANDOM_GAME_EXE_NAME.casefold():
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        diagnostic_log(
            "random_game_executable_cleanup_failed",
            path=str(path),
            error=repr(exc),
        )


def terminate_random_game_instances(
    game_executable: Path,
) -> tuple[int, ...]:
    source = game_executable.resolve()
    target = source.with_name(RANDOM_GAME_EXE_NAME)
    expected_path = os.path.normcase(os.path.abspath(target))
    terminated = []
    errors = []
    for pid in find_process_ids(RANDOM_GAME_EXE_NAME):
        running_path = process_executable(pid)
        if running_path is None:
            continue
        if os.path.normcase(os.path.abspath(running_path)) != expected_path:
            continue
        handle = kernel32.OpenProcess(
            PROCESS_TERMINATE | SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            pid,
        )
        if not handle:
            errors.append(f"PID {pid}: 无法打开进程")
            continue
        try:
            if kernel32.WaitForSingleObject(handle, 0) != 0:
                if not kernel32.TerminateProcess(handle, 0):
                    errors.append(f"PID {pid}: 无法终止进程")
                    continue
                kernel32.WaitForSingleObject(handle, 5000)
            terminated.append(pid)
        finally:
            kernel32.CloseHandle(handle)
    remove_random_game_executable(target)
    if errors:
        raise RuntimeError("；".join(errors))
    return tuple(terminated)


def source_save_job_ids(save_path: Path) -> tuple[int, ...]:
    minimum_size = JOB_OFFSET + (max(JOB_POSITIONS_R1) + 1) * 4
    try:
        data = save_path.read_bytes()
    except OSError as exc:
        raise RuntimeError(
            "第20栏存档无法读取。\n\n"
            "请确认存档文件没有被其他程序占用，并检查游戏目录权限。"
        ) from exc
    if len(data) < max(R0_MEMORY_SIZE, minimum_size):
        raise RuntimeError(
            "第20栏存档文件不完整或版本不匹配。\n\n"
            "请进入游戏重新保存到第20栏，然后再开始随机。"
        )
    values = struct.unpack_from(
        f"<{max(JOB_POSITIONS_R1) + 1}I",
        data,
        JOB_OFFSET,
    )
    return tuple(values[index] for index in JOB_POSITIONS_R1)


def ensure_game_menu_ready(runner) -> None:
    if not getattr(runner, "wind", None):
        runner.initWind()


def save_result_via_game_menu(
    runner,
    slot: int,
) -> None:
    if not 1 <= slot <= 15:
        raise ValueError("结果存档槽位只能是第 1–15 号")
    ensure_game_menu_ready(runner)
    runner.saveAndConfirm(slot)


def save_file_signature(path: Path) -> tuple[int, int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    if not path.is_file() or stat.st_size <= 0:
        return None
    return stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def save_control_resource_snapshot() -> dict[str, int]:
    return {
        "available_memory_bytes": available_physical_memory_bytes(),
        "game_process_count": len(find_process_ids(GAME_EXE_NAME)),
        "tool_process_count": len(
            find_process_ids(Path(sys.executable).name)
        ),
    }


def start_save_list_control(
    pid: int,
    slot: int,
) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [
            str(native_dir() / "ccz_injector.exe"),
            str(pid),
            str(native_dir() / "ccz_control.dll"),
            "list",
            str(slot - 1),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def wait_for_game_menu_save(
    path: Path,
    previous_signature: tuple[int, int, int] | None,
    *,
    timeout: float = 5.0,
    interval: float = 0.05,
) -> tuple[int, int, int]:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        current_signature = save_file_signature(path)
        if (
            current_signature is not None
            and current_signature != previous_signature
        ):
            return current_signature
        time.sleep(interval)
    raise RuntimeError(
        f"游戏菜单保存后未检测到 {path.name} 写入，已停止发布该结果"
    )


def commit_qualified_result_save(
    runner,
    slot: int,
    target_path: Path,
    *,
    candidate_save: bytes | None = None,
) -> tuple[
    tuple[int, int, int] | None,
    tuple[int, int, int],
    str,
]:
    previous_signature = save_file_signature(target_path)
    if candidate_save is None:
        save_result_via_game_menu(runner, slot)
        saved_signature = wait_for_game_menu_save(
            target_path,
            previous_signature,
        )
        return previous_signature, saved_signature, "game_menu"

    publish_candidate_save(target_path, candidate_save)
    saved_signature = save_file_signature(target_path)
    if saved_signature is None:
        raise RuntimeError(f"{target_path.name} 发布后无法读取")
    return (
        previous_signature,
        saved_signature,
        "game_menu_candidate_copy",
    )


def drive_game_menu_save(
    pid: int,
    game: int,
    target_path: Path,
    slot: int,
    *,
    timeout: float = 25.0,
) -> tuple[int, int, int]:
    previous_signature = save_file_signature(target_path)
    recover_stale_windows(pid, game)
    activate_hidden_window(game)
    user32.PostMessageW(game, 0x0111, 101, 0)
    save_window = wait_list_dialog(pid, 3)
    if not save_window:
        raise RuntimeError("存档窗口未出现")

    activate_hidden_window(save_window)
    control_started = time.perf_counter()
    control = start_save_list_control(pid, slot)
    confirmation_clicks = 0
    control_error: NativeControlError | None = None
    control_output_collected = False
    control_stdout = ""
    control_stderr = ""
    control_forced_stop = False
    control_early_stopped = False
    diagnostic_log(
        "game_menu_save_interaction_started",
        pid=pid,
        result_slot=slot,
        save_path=target_path,
        save_window=save_window,
        control_pid=control.pid,
        previous_signature=previous_signature,
        **save_control_resource_snapshot(),
    )
    deadline = time.perf_counter() + timeout
    saved_signature = None
    try:
        while time.perf_counter() < deadline:
            check_stop_requested()
            visible_windows = visible_owned_windows(game)
            for alert, _title, _rect in visible_windows:
                if (
                    alert == save_window
                    or window_class(alert) != "#32770"
                    or user32.FindWindowExW(
                        alert, 0, "SysListView32", None
                    )
                ):
                    continue
                activate_hidden_window(alert)
                if click_leftmost_dialog_button(alert):
                    confirmation_clicks += 1

            current_signature = save_file_signature(target_path)
            if (
                current_signature is not None
                and current_signature != previous_signature
            ):
                saved_signature = current_signature

            return_code = control.poll()
            if (
                return_code is not None
                and return_code != 0
                and not control_output_collected
            ):
                stdout, stderr = control.communicate()
                control_output_collected = True
                control_stdout = stdout.decode(errors="replace").strip()
                control_stderr = stderr.decode(errors="replace").strip()
                control_error = NativeControlError(
                    return_code,
                    control_stderr or control_stdout,
                )
                details = control_error.details.casefold()
                if (
                    saved_signature is None
                    and "remote thread timed out" not in details
                ):
                    raise control_error

            remaining_alerts = [
                hwnd
                for hwnd, _title, _rect in visible_owned_windows(game)
                if hwnd != save_window
                and window_class(hwnd) == "#32770"
            ]
            if (
                saved_signature is not None
                and not remaining_alerts
            ):
                if control.poll() is None:
                    # The save file changed and the overwrite confirmation
                    # is gone. The helper may still be waiting for a remote
                    # thread to report completion; it is no longer needed
                    # to keep the game operation alive.
                    control_early_stopped = True
                    control_forced_stop = True
                    control.terminate()
                    try:
                        control.wait(timeout=0.25)
                    except subprocess.TimeoutExpired:
                        control.kill()
                        control.wait(timeout=1)
                break
            interruptible_sleep(0.08)
    finally:
        if control.poll() is None:
            control_forced_stop = True
            control.terminate()
            try:
                control.wait(timeout=1)
            except subprocess.TimeoutExpired:
                control.kill()
                control.wait(timeout=1)
        if not control_output_collected:
            stdout, stderr = control.communicate()
            control_output_collected = True
            control_stdout = stdout.decode(errors="replace").strip()
            control_stderr = stderr.decode(errors="replace").strip()

    if saved_signature is None:
        diagnostic_log(
            "game_menu_save_interaction_failed",
            pid=pid,
            result_slot=slot,
            save_path=target_path,
            control_return_code=control.returncode,
            confirmation_clicks=confirmation_clicks,
            elapsed_ms=round(
                (time.perf_counter() - control_started) * 1000
            ),
            error=repr(control_error) if control_error else "",
            control_forced_stop=control_forced_stop,
            control_stdout=control_stdout,
            control_stderr=control_stderr,
            **save_control_resource_snapshot(),
        )
        raise RuntimeError(
            f"游戏菜单保存后未检测到 SV{slot:03}.E5S 写入"
        )
    diagnostic_log(
        "game_menu_save_interaction_completed",
        pid=pid,
        result_slot=slot,
        save_path=target_path,
        previous_signature=previous_signature,
        saved_signature=saved_signature,
        control_return_code=control.returncode,
        control_timeout_observed=control_error is not None,
        control_forced_stop=control_forced_stop,
        control_early_stopped=control_early_stopped,
        control_stdout=control_stdout,
        control_stderr=control_stderr,
        confirmation_clicks=confirmation_clicks,
        elapsed_ms=round(
            (time.perf_counter() - control_started) * 1000
        ),
        **save_control_resource_snapshot(),
    )
    return saved_signature


def drive_game_menu_load(
    pid: int,
    game: int,
    save_path: Path,
    slot: int,
    *,
    timeout: float = 12.0,
    from_title: bool = False,
    fast_selection: bool = False,
) -> None:
    if slot < 1:
        raise ValueError("读取存档槽位必须大于 0")
    if not save_path.is_file():
        raise FileNotFoundError(f"未找到待读取存档：{save_path}")

    recover_stale_windows(pid, game)
    activate_hidden_window(game)
    if from_title:
        load_window = 0
        open_deadline = time.perf_counter() + min(timeout, 5.0)
        while time.perf_counter() < open_deadline:
            native_silent_click(
                pid,
                game,
                TITLE_LOAD_CLIENT_POSITION[0],
                TITLE_LOAD_CLIENT_POSITION[1],
                tail_delay_ms=300,
            )
            load_window = wait_list_dialog(pid, 1)
            if load_window:
                break
            interruptible_sleep(0.2)
    else:
        user32.PostMessageW(game, 0x0111, 102, 0)
        load_window = wait_list_dialog(pid, 3)
    if not load_window:
        raise RuntimeError("读取进度窗口未出现")

    activate_hidden_window(load_window)
    injector = native_dir() / "ccz_injector.exe"
    control_dll = native_dir() / "ccz_control.dll"
    control = subprocess.Popen(
        [
            str(injector),
            str(pid),
            str(control_dll),
            "turbo-list" if fast_selection else "list",
            str(slot - 1),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    deadline = time.perf_counter() + timeout
    try:
        while time.perf_counter() < deadline:
            check_stop_requested()
            for alert, _title, _rect in visible_owned_windows(game):
                if (
                    alert == load_window
                    or window_class(alert) != "#32770"
                    or user32.FindWindowExW(
                        alert, 0, "SysListView32", None
                    )
                ):
                    continue
                activate_hidden_window(alert)
                click_leftmost_dialog_button(alert)

            load_finished = (
                not user32.IsWindow(load_window)
                and user32.IsWindowEnabled(game)
            )
            if load_finished:
                if fast_selection and control.poll() is None:
                    # The remote thread restores input hooks before reporting
                    # completion. Never start random input while it still runs.
                    interruptible_sleep(0.02)
                    continue
                if (
                    control.poll() is not None
                    and control.returncode != 0
                ):
                    stdout, stderr = control.communicate()
                    raise NativeControlError(
                        control.returncode,
                        stderr.decode(errors="replace").strip()
                        or stdout.decode(errors="replace").strip(),
                    )
                if control.poll() is None:
                    # The game has closed the load dialog and re-enabled its
                    # main window. Memory verification happens immediately
                    # after this function, so do not wait for the injector's
                    # remote-thread cleanup to report completion.
                    control.terminate()
                    try:
                        control.wait(timeout=0.25)
                    except subprocess.TimeoutExpired:
                        control.kill()
                        control.wait(timeout=1)
                native_wake_game(pid, game, 80)
                diagnostic_log(
                    "game_menu_load_interaction_completed",
                    pid=pid,
                    slot=slot,
                    save_path=save_path,
                    fast_selection=fast_selection,
                )
                return
            if control.poll() is not None and control.returncode != 0:
                stdout, stderr = control.communicate()
                raise NativeControlError(
                    control.returncode,
                    stderr.decode(errors="replace").strip()
                    or stdout.decode(errors="replace").strip(),
                )
            interruptible_sleep(0.08)
    finally:
        if control.poll() is None:
            control.terminate()
            try:
                control.wait(timeout=1)
            except subprocess.TimeoutExpired:
                control.kill()
                control.wait(timeout=1)

    remaining = [
        (window_class(hwnd), window_text(hwnd))
        for hwnd in process_windows(pid)
    ]
    raise RuntimeError(
        f"第 {slot} 号存档未能完成游戏菜单读取；"
        f"残留窗口={remaining}"
    )


def ensure_directory_writable(directory: Path, label: str) -> None:
    probe = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix=".ccz-write-check-",
            dir=directory,
            delete=False,
        ) as handle:
            probe = Path(handle.name)
    except OSError as exc:
        raise RuntimeError(
            f"{label}无法写入。\n\n"
            "请将游戏放到普通文件夹，并确认当前用户拥有该目录的写入权限。"
        ) from exc
    finally:
        if probe is not None:
            probe.unlink(missing_ok=True)


def validate_start_environment(game_executable: Path) -> Path:
    game_executable = game_executable.resolve()
    if not game_executable.is_file():
        raise RuntimeError(
            f"未找到 {GAME_EXE_NAME}。\n\n"
            "请把本工具放到游戏目录下，再双击运行。"
        )
    available_memory = available_physical_memory_bytes()
    if (
        available_memory is not None
        and available_memory < MIN_AVAILABLE_MEMORY_BYTES
    ):
        available_mb = max(0, available_memory // (1024 * 1024))
        required_mb = MIN_AVAILABLE_MEMORY_BYTES // (1024 * 1024)
        raise RuntimeError(
            f"当前可用内存约 {available_mb} MB，无法安全启动随机。\n\n"
            f"请关闭其他占用内存的程序，确保至少有 {required_mb} MB "
            "可用内存后再试。"
        )

    game_dir = game_executable.parent
    save_dir = game_dir / "SV"
    source_save = save_dir / "SV020.E5S"
    if not source_save.is_file():
        raise RuntimeError(
            "未找到第20栏存档。\n\n"
            "请在许子将处完成配置，并在触发随机之前保存到第20栏。"
        )

    job_ids = source_save_job_ids(source_save)
    if any(job_ids):
        raise RuntimeError(
            "第20栏存档已经触发过随机，不能作为源存档。\n\n"
            "请重新读取配置完成但尚未随机的存档，"
            "在与许子将对话并选择第一项之前保存到第20栏。"
        )

    missing_native_components = [
        path.name
        for path in (
            native_dir() / "ccz_injector.exe",
            native_dir() / "ccz_control.dll",
        )
        if not path.is_file()
    ]
    if missing_native_components:
        raise RuntimeError(
            missing_native_components_message(missing_native_components)
        )
    if not bundle_root().is_dir():
        raise RuntimeError(
            "工具运行文件不完整，缺少运行组件。\n\n"
            "请重新获取完整的工具程序。"
        )

    ensure_directory_writable(game_dir, "游戏目录")
    ensure_directory_writable(save_dir, "存档目录")
    # Do not inspect every result slot here.  A read-only file in an unused
    # slot is unrelated to the selected run and used to block startup before
    # the actual target slots were known.  The game-menu save path verifies
    # the specific target after each result and reports a precise failure.

    if shutil.disk_usage(game_dir).free < 100 * 1024 * 1024:
        raise RuntimeError(
            "游戏所在磁盘剩余空间不足。\n\n"
            "请至少清理出 100 MB 可用空间后再开始随机。"
        )
    return source_save


class HiddenGameSession:
    def __init__(
        self,
        executable: Path,
        arguments: tuple[str, ...] = (),
        restarted: bool = False,
        announce: bool = True,
        working_directory: Path | None = None,
    ):
        self.executable = executable.resolve()
        self.arguments = arguments
        self.restarted = restarted
        self.announce = announce
        self.process = 0
        self.job = 0
        self.pid = 0
        self.main_window = 0
        self.foreground_before = 0
        self.desktop = 0
        self.launch_executable = self.executable
        self.working_directory = (
            working_directory.resolve()
            if working_directory is not None
            else self.executable.parent
        )
        self.audio_mute_monitor: ProcessAudioMuteMonitor | None = None
        self.use_isolated_desktop = (
            os.environ.get("CCZ_USE_ISOLATED_DESKTOP", "1") != "0"
        )
        self.background_render = (
            os.environ.get("CCZ_BACKGROUND_RENDER") == "1"
        )
        self.desktop_name = f"CCZFast_{os.getpid()}_{time.time_ns()}"

    def _raise_process_exited(self, stage: str) -> None:
        exit_code = process_exit_code(self.process)
        diagnostic_log(
            "game_process_exited",
            pid=self.pid,
            stage=stage,
            exit_code=exit_code,
            exit_code_hex=(
                f"0x{exit_code:08X}"
                if exit_code is not None
                else None
            ),
            executable=file_diagnostic(self.executable),
            working_directory=str(self.working_directory),
            isolated_desktop=self.use_isolated_desktop,
            desktop_name=self.desktop_name,
            main_window=self.main_window,
        )
        code_text = (
            f"{exit_code} (0x{exit_code:08X})"
            if exit_code is not None
            else "无法读取"
        )
        raise RuntimeError(
            "随机游戏实例启动后退出，"
            f"退出码：{code_text}，阶段：{stage}。"
        )

    def __enter__(self) -> "HiddenGameSession":
        global WINDOW_DESKTOP
        check_stop_requested()
        self.foreground_before = user32.GetForegroundWindow()
        if self.use_isolated_desktop:
            self.desktop = user32.CreateDesktopW(
                self.desktop_name,
                None,
                None,
                0,
                DESKTOP_ACCESS,
                None,
            )
            if not self.desktop:
                raise ctypes.WinError(ctypes.get_last_error())
            WINDOW_DESKTOP = self.desktop
        else:
            WINDOW_DESKTOP = 0
        startup = StartupInfo()
        startup.cb = ctypes.sizeof(startup)
        startup.dwFlags = STARTF_USESHOWWINDOW
        # The game does not enter its normal scene loop when Windows tells
        # it to start hidden.  The native guard is installed before resume
        # and moves every top-level game window off-screen, so request a
        # non-activating show while keeping the user's desktop untouched.
        startup.wShowWindow = SW_SHOWNOACTIVATE
        startup.lpDesktop = (
            self.desktop_name if self.use_isolated_desktop else None
        )
        process_info = ProcessInformation()
        command_parts = [f'"{self.executable}"']
        command_parts.extend(f'"{argument}"' for argument in self.arguments)
        command_line = ctypes.create_unicode_buffer(" ".join(command_parts))
        if not kernel32.CreateProcessW(
            str(self.launch_executable),
            command_line,
            None,
            None,
            False,
            CREATE_SUSPENDED,
            None,
            str(self.working_directory),
            ctypes.byref(startup),
            ctypes.byref(process_info),
        ):
            user32.CloseDesktop(self.desktop)
            self.desktop = 0
            WINDOW_DESKTOP = 0
            raise ctypes.WinError(ctypes.get_last_error())

        self.process = process_info.hProcess
        self.pid = int(process_info.dwProcessId)
        try:
            self.job = kernel32.CreateJobObjectW(None, None)
            if not self.job:
                raise ctypes.WinError(ctypes.get_last_error())
            limits = JobObjectExtendedLimitInformation()
            limits.BasicLimitInformation.LimitFlags = (
                JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            )
            if not kernel32.SetInformationJobObject(
                self.job,
                JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
                ctypes.byref(limits),
                ctypes.sizeof(limits),
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            if not kernel32.AssignProcessToJobObject(self.job, self.process):
                raise ctypes.WinError(ctypes.get_last_error())
            if (
                not self.use_isolated_desktop
                and os.environ.get("CCZ_DISABLE_GUARD") != "1"
            ):
                run_native_control(self.pid, ["guard"])
            if os.environ.get("CCZ_DISABLE_AUDIO_MUTE") != "1":
                self.audio_mute_monitor = ProcessAudioMuteMonitor(
                    self.pid,
                    process_is_alive=process_is_alive,
                    logger=diagnostic_log,
                )
                self.audio_mute_monitor.start()
                diagnostic_log(
                    "random_game_audio_mute_monitor_started",
                    pid=self.pid,
                )
            if kernel32.ResumeThread(process_info.hThread) == 0xFFFFFFFF:
                raise ctypes.WinError(ctypes.get_last_error())
        except BaseException:
            if self.audio_mute_monitor is not None:
                self.audio_mute_monitor.stop()
                self.audio_mute_monitor = None
            if self.process:
                kernel32.TerminateProcess(self.process, 1)
                kernel32.WaitForSingleObject(self.process, 3000)
                kernel32.CloseHandle(self.process)
                self.process = 0
            if self.job:
                kernel32.CloseHandle(self.job)
                self.job = 0
            if self.desktop:
                user32.CloseDesktop(self.desktop)
                self.desktop = 0
            WINDOW_DESKTOP = 0
            raise
        finally:
            kernel32.CloseHandle(process_info.hThread)

        deadline = time.perf_counter() + 15
        while time.perf_counter() < deadline:
            check_stop_requested()
            for hwnd in process_windows(self.pid, visible_only=False):
                if window_class(hwnd) == "SOUSOU":
                    self.main_window = hwnd
                    break
            if self.main_window:
                break
            if kernel32.WaitForSingleObject(self.process, 0) == 0:
                self._raise_process_exited("等待主窗口")
            interruptible_sleep(0.01)
        if not self.main_window:
            raise RuntimeError("静默游戏实例启动超时")

        if not user32.SetWindowPos(
            self.main_window,
            1,
            0
            if self.use_isolated_desktop or self.background_render
            else OFFSCREEN_X,
            0
            if self.use_isolated_desktop or self.background_render
            else OFFSCREEN_Y,
            646,
            489,
            SWP_NOACTIVATE | SWP_SHOWWINDOW,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if (
            window_process_id(user32.GetForegroundWindow()) == self.pid
            and self.foreground_before
            and user32.IsWindow(self.foreground_before)
        ):
            user32.SetForegroundWindow(self.foreground_before)
        interruptible_sleep(0.25)

        foreground_after = user32.GetForegroundWindow()
        if window_process_id(foreground_after) == self.pid:
            raise RuntimeError(
                "静默游戏抢占了前台窗口，已停止测试"
            )
        if kernel32.WaitForSingleObject(self.process, 0) == 0:
            self._raise_process_exited("主窗口初始化完成")
        start_persistent_native_controller(self.pid)
        if self.announce:
            print(
                f"隐藏游戏实例已{'重新' if self.restarted else ''}启动，"
                f"PID={self.pid}；"
                "游戏未取得前台，系统鼠标未被程序控制。"
            )
        return self

    def is_healthy(self) -> bool:
        return bool(
            self.process
            and kernel32.WaitForSingleObject(self.process, 0) != 0
            and self.main_window
            and user32.IsWindow(self.main_window)
        )

    def __exit__(self, exc_type, exc, tb) -> None:
        global WINDOW_DESKTOP
        if self.audio_mute_monitor is not None:
            self.audio_mute_monitor.stop()
            self.audio_mute_monitor = None
        if self.pid:
            stop_persistent_native_controller(self.pid)
        if self.process:
            if kernel32.WaitForSingleObject(self.process, 0) != 0:
                kernel32.TerminateProcess(self.process, 0)
                kernel32.WaitForSingleObject(self.process, 3000)
            kernel32.CloseHandle(self.process)
            self.process = 0
        if self.job:
            kernel32.CloseHandle(self.job)
            self.job = 0
        if self.desktop:
            user32.CloseDesktop(self.desktop)
            self.desktop = 0
        WINDOW_DESKTOP = 0


def read_memory(pid: int, offset: int, size: int) -> bytes:
    handle = kernel32.OpenProcess(
        PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid
    )
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        buffer = ctypes.create_string_buffer(size)
        count = ctypes.c_size_t()
        if not kernel32.ReadProcessMemory(
            handle,
            ctypes.c_void_p(MEMORY_BASE + offset),
            buffer,
            size,
            ctypes.byref(count),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if count.value != size:
            raise RuntimeError(f"游戏内存读取不完整：{count.value}/{size}")
        return buffer.raw
    finally:
        kernel32.CloseHandle(handle)


def read_job_ids(
    pid: int, positions: tuple[int, ...] = JOB_POSITIONS_R1
) -> tuple[int, ...]:
    size = (max(positions) + 1) * 4
    values = struct.unpack(
        f"<{size // 4}I", read_memory(pid, JOB_OFFSET, size)
    )
    return tuple(values[index] for index in positions)


def trigger_random_choice_click(
    pid: int,
    game: int,
    active_positions: tuple[int, ...],
    before: tuple[int, ...],
    interaction_attempt: int,
) -> tuple[int, ...]:
    check_stop_requested()
    try:
        native_silent_click(
            pid,
            game,
            CONFIRM_FIRST_CLIENT_POSITION[0],
            CONFIRM_FIRST_CLIENT_POSITION[1],
            tail_delay_ms=0,
        )
    except (NativeControlError, NativeControlTimeout) as exc:
        check_stop_requested()
        diagnostic_log(
            "fast_choice_click_failed",
            pid=pid,
            attempt=interaction_attempt,
            error=repr(exc),
        )
        native_silent_click(
            pid,
            game,
            CONFIRM_FIRST_CLIENT_POSITION[0],
            CONFIRM_FIRST_CLIENT_POSITION[1],
        )
        return read_job_ids(pid, active_positions)

    current = read_job_ids(pid, active_positions)
    check_stop_requested()
    if current != before and any(current):
        return current

    diagnostic_log(
        "fast_choice_click_no_change",
        pid=pid,
        attempt=interaction_attempt,
        jobs=current,
    )
    check_stop_requested()
    native_silent_click(
        pid,
        game,
        CONFIRM_FIRST_CLIENT_POSITION[0],
        CONFIRM_FIRST_CLIENT_POSITION[1],
    )
    return read_job_ids(pid, active_positions)


def read_equipment_records(pid: int) -> tuple[bytes, ...]:
    data = read_memory(pid, EQUIPMENT_OFFSET, EQUIPMENT_SIZE)
    groups = _EQUIPMENT_PROFILE.skills["displayRules"]["equipment"]["recordGroups"]
    records, offset = [], 0
    for group in groups:
        for _ in range(group["count"]):
            record = data[offset:offset + group["size"]]
            if len(record) != group["size"]:
                raise RuntimeError("宝物内存记录长度异常")
            records.append(record)
            offset += group["size"]
    return tuple(records)


def decode_equipment_effect(code: int, parameter: int) -> str:
    from ccz_randomizer.display_rules import render_equipment
    profile = _EQUIPMENT_PROFILE
    result = render_equipment(profile.skills["displayRules"], profile.skills["nameFormatting"], code, parameter)
    if result is not None:
        return result
    effect_key = (code, parameter)
    if effect_key not in UNKNOWN_EQUIPMENT_EFFECTS:
        UNKNOWN_EQUIPMENT_EFFECTS.add(effect_key)
        message = (
            f"发现未收录宝物特效 0x{code:02X}/0x{parameter:02X}；"
            "已记录诊断信息并继续运行"
        )
        print(message)
        diagnostic_log(
            "unknown_equipment_effect",
            code=code,
            parameter=parameter,
            display=f"0x{code:02X}/0x{parameter:02X}",
        )
    return f"未知特效(0x{code:02X}/0x{parameter:02X})"


def decode_equipment_records(
    records: tuple[bytes, ...],
) -> tuple[list[tuple[list[tuple[str, str]], str]], dict[str, str]]:
    if len(records) != len(EQUIPMENT_NAMES):
        raise RuntimeError(
            f"宝物记录数量异常：{len(records)}/{len(EQUIPMENT_NAMES)}"
        )
    equipment = _EQUIPMENT_PROFILE.skills["displayRules"]["equipment"]
    parameter_offsets = [g["parameterOffset"] for g in equipment["recordGroups"] for _ in range(g["count"])]
    categories = {name: [] for name in EQUIPMENT_CATEGORY_NAMES}
    effects = {}
    for index, (name, record) in enumerate(
        zip(EQUIPMENT_NAMES, records, strict=True)
    ):
        parameter = record[parameter_offsets[index]]
        effect = decode_equipment_effect(record[0], parameter)
        category = EQUIPMENT_CATEGORY_BY_NAME.get(name, equipment["defaultCategory"])
        categories[category].append((name, effect))
        effects[name] = effect
    return (
        [
            (categories[category], category)
            for category in EQUIPMENT_CATEGORY_NAMES
            if categories[category]
        ],
        effects,
    )


def build_equipment_specials(
    effects: dict[str, str],
) -> list[tuple[str, list[tuple[str, str]]]]:
    specials = [
        (
            title,
            [(name, effects[name]) for name in names if name in effects],
        )
        for title, names in EQUIPMENT_SETS
    ]
    specials.append(
        (
            "好东西",
            [
                (name, effect)
                for name, effect in effects.items()
                if any(
                    marker in effect
                    for marker in GOOD_EQUIPMENT_SKILL_MARKERS
                )
            ],
        )
    )
    return specials


def title_load_verified(
    pid: int,
    list_index: int,
    save_path: Path,
    timeout: float = 15.0,
) -> bool:
    expected = save_path.read_bytes()[:R0_MEMORY_SIZE]
    game = find_process_window_by_class(pid, "SOUSOU")
    if not game:
        raise RuntimeError("标题读档前未找到游戏主窗口")
    started = time.perf_counter()
    diagnostic_log(
        "title_load_start",
        pid=pid,
        list_index=list_index,
        save_path=save_path,
        expected_sha256=hashlib.sha256(expected).hexdigest(),
    )
    drive_game_menu_load(
        pid=pid,
        game=game,
        save_path=save_path,
        slot=list_index + 1,
        timeout=min(timeout, 12.0),
        from_title=True,
    )

    deadline = time.perf_counter() + timeout
    checks = 0
    while time.perf_counter() < deadline:
        check_stop_requested()
        checks += 1
        current = read_memory(pid, 0, R0_MEMORY_SIZE)
        transition_active = read_memory(
            pid,
            LOAD_TRANSITION_ACTIVE_OFFSET,
            1,
        )[0]
        transition_state = int.from_bytes(
            read_memory(
                pid,
                LOAD_TRANSITION_STATE_OFFSET,
                4,
            ),
            "little",
        )
        if (
            current == expected
            and transition_active == 0
            and transition_state == 0
        ):
            main_window = find_process_window_by_class(pid, "SOUSOU")
            closed_dialogs = []
            for hwnd in process_windows(pid):
                if (
                    window_class(hwnd) == "#32770"
                    and user32.FindWindowExW(
                        hwnd, 0, "SysListView32", None
                    )
                ):
                    user32.PostMessageW(hwnd, 0x0010, 0, 0)
                    closed_dialogs.append(hwnd)
            if main_window:
                user32.EnableWindow(main_window, True)
                try:
                    native_wake_game(pid, main_window, 80)
                except (NativeControlError, NativeControlTimeout) as exc:
                    diagnostic_log(
                        "title_load_ui_refresh_failed",
                        pid=pid,
                        main_window=main_window,
                        error=repr(exc),
                    )
            diagnostic_log(
                "title_load_verified",
                pid=pid,
                checks=checks,
                elapsed_ms=round(
                    (time.perf_counter() - started) * 1000
                ),
                memory_sha256=hashlib.sha256(current).hexdigest(),
                transition_active=transition_active,
                transition_state=transition_state,
                main_window=main_window,
                closed_dialogs=closed_dialogs,
            )
            return True
        interruptible_sleep(0.1)
    diagnostic_log(
        "title_load_timeout",
        pid=pid,
        checks=checks,
        elapsed_ms=round((time.perf_counter() - started) * 1000),
        process_alive=process_is_alive(pid),
    )
    return False


def normal_load_verified(
    pid: int,
    game: int,
    save_number: int,
    save_path: Path,
    load_action,
    timeout: float = 12.0,
) -> bool:
    """Load through the game's normal menu and verify the resulting memory."""
    expected = save_path.read_bytes()[:R0_MEMORY_SIZE]
    started = time.perf_counter()
    diagnostic_log(
        "normal_load_start",
        pid=pid,
        game_hwnd=game,
        save_number=save_number,
        save_path=save_path,
        expected_sha256=hashlib.sha256(expected).hexdigest(),
    )
    try:
        load_action(save_number)
    except Exception as exc:
        diagnostic_log(
            "normal_load_action_failed",
            pid=pid,
            game_hwnd=game,
            error=repr(exc),
            state=game_state_diagnostic(pid, game),
        )
        raise NormalReloadUnsupported(
            "同一游戏实例未能完成正常读档"
        ) from exc

    deadline = time.perf_counter() + timeout
    checks = 0
    while time.perf_counter() < deadline:
        check_stop_requested()
        checks += 1
        if not user32.IsWindow(game) or process_executable(pid) is None:
            diagnostic_log(
                "normal_load_process_exited",
                pid=pid,
                game_hwnd=game,
                checks=checks,
            )
            raise NormalReloadUnsupported(
                "正常读档过程中游戏进程退出"
            )
        try:
            current = read_memory(pid, 0, R0_MEMORY_SIZE)
        except OSError as exc:
            diagnostic_log(
                "normal_load_memory_read_failed",
                pid=pid,
                game_hwnd=game,
                checks=checks,
                error=repr(exc),
            )
            interruptible_sleep(0.05)
            continue
        if current == expected:
            diagnostic_log(
                "normal_load_verified",
                pid=pid,
                game_hwnd=game,
                checks=checks,
                elapsed_ms=round(
                    (time.perf_counter() - started) * 1000
                ),
                memory_sha256=hashlib.sha256(current).hexdigest(),
            )
            return True
        interruptible_sleep(0.05)

    diagnostic_log(
        "normal_load_verification_failed",
        pid=pid,
        game_hwnd=game,
        checks=checks,
        state=game_state_diagnostic(pid, game),
    )
    raise NormalReloadUnsupported(
        f"正常读档完成后，游戏内存与第 {save_number} 号存档不一致"
    )


def direct_load_verified(
    pid: int,
    slot_index: int,
    save_path: Path,
    timeout: float = 10.0,
) -> bool:
    expected = save_path.read_bytes()[:R0_MEMORY_SIZE]
    for attempt in range(1, 4):
        check_stop_requested()
        try:
            native_direct_load(pid, slot_index)
        except NativeControlTimeout as exc:
            print(f"游戏内原生直读返回延迟，改用内存确认：{exc}")
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            check_stop_requested()
            if read_memory(pid, 0, R0_MEMORY_SIZE) == expected:
                return True
            interruptible_sleep(0.1)
        print(f"第 {slot_index + 1} 号存档原生直读重试 {attempt}/3")
    return False


def initialize_result_output() -> tuple[Path, Path]:
    global RESULT_RUN_STAMP, RESULT_ROOT, RESULT_PANEL_DIR, RESULT_GRID_FILE
    # Dots keep the timestamp readable while remaining valid in Windows paths.
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H.%M.%S")
    configured_root = os.environ.get("CCZ_RESULT_BASE_DIR", "").strip()
    base_dir = (
        Path(configured_root)
        if configured_root
        else (RESULT_BASE_DIR or Path.cwd())
    )
    root = base_dir / "randResult"
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        root = app_dir() / "randResult"
    panel_dir = root / "panels" / stamp
    grid_file = root / f"{stamp}-random.png"
    duplicate = 2
    while panel_dir.exists() or grid_file.exists():
        unique_stamp = f"{stamp} ({duplicate})"
        panel_dir = root / "panels" / unique_stamp
        grid_file = root / f"{unique_stamp}-random.png"
        duplicate += 1
    panel_dir.mkdir(parents=True, exist_ok=False)
    RESULT_RUN_STAMP = panel_dir.name
    RESULT_ROOT = root
    RESULT_PANEL_DIR = panel_dir
    RESULT_GRID_FILE = grid_file
    return panel_dir, grid_file


def configure_result_output(
    panel_dir: Path,
    grid_file: Path,
    run_stamp: str,
) -> tuple[Path, Path]:
    global RESULT_RUN_STAMP, RESULT_ROOT, RESULT_PANEL_DIR, RESULT_GRID_FILE
    panel_dir.mkdir(parents=True, exist_ok=True)
    grid_file.parent.mkdir(parents=True, exist_ok=True)
    RESULT_RUN_STAMP = run_stamp
    RESULT_ROOT = grid_file.parent
    RESULT_PANEL_DIR = panel_dir
    RESULT_GRID_FILE = grid_file
    return panel_dir, grid_file


def relocate_result_output(round_dir: Path) -> Path:
    global RESULT_ROOT, RESULT_PANEL_DIR, RESULT_GRID_FILE
    assert RESULT_GRID_FILE is not None
    RESULT_ROOT = round_dir
    RESULT_PANEL_DIR = round_dir / "panels"
    RESULT_GRID_FILE = round_dir / RESULT_GRID_FILE.name
    return RESULT_GRID_FILE


def result_panel_dir() -> Path:
    if RESULT_PANEL_DIR is None:
        initialize_result_output()
    assert RESULT_PANEL_DIR is not None
    return RESULT_PANEL_DIR


def result_grid_path() -> Path:
    if RESULT_GRID_FILE is None:
        initialize_result_output()
    assert RESULT_GRID_FILE is not None
    return RESULT_GRID_FILE


@lru_cache(maxsize=16)
def result_font(size: int, bold: bool = False):
    load_media_modules()
    candidates = (
        Path("C:/Windows/Fonts/simsun.ttc"),
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def print_window_mat(
    hwnd: int,
    x: int = 0,
    y: int = 0,
    w: int = 0,
    h: int = 0,
    strip_client: bool = True,
    flags: int = 2,
) -> np.ndarray:
    load_media_modules()
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError(ctypes.get_last_error())
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        return np.empty((0, 0, 3), dtype=np.uint8)

    window_dc = user32.GetWindowDC(hwnd)
    if not window_dc:
        raise ctypes.WinError(ctypes.get_last_error())
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    previous = gdi32.SelectObject(memory_dc, bitmap)
    try:
        if not user32.PrintWindow(hwnd, memory_dc, flags):
            raise ctypes.WinError(ctypes.get_last_error())
        info = BitmapInfo()
        info.bmiHeader.biSize = ctypes.sizeof(BitmapInfoHeader)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = 0
        pixels = (ctypes.c_ubyte * (width * height * 4))()
        if not gdi32.GetDIBits(
            memory_dc,
            bitmap,
            0,
            height,
            pixels,
            ctypes.byref(info),
            0,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        image = np.frombuffer(pixels, dtype=np.uint8).reshape(
            height, width, 4
        )[:, :, :3].copy()
    finally:
        gdi32.SelectObject(memory_dc, previous)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(hwnd, window_dc)

    if strip_client:
        client_rect = wintypes.RECT()
        client_origin = Point()
        if (
            user32.GetClientRect(hwnd, ctypes.byref(client_rect))
            and user32.ClientToScreen(hwnd, ctypes.byref(client_origin))
        ):
            client_x = client_origin.x - rect.left
            client_y = client_origin.y - rect.top
            client_width = client_rect.right - client_rect.left
            client_height = client_rect.bottom - client_rect.top
            image = image[
                client_y : client_y + client_height,
                client_x : client_x + client_width,
            ]
    if w <= 0:
        w = image.shape[1] - x
    if h <= 0:
        h = image.shape[0] - y
    return image[y : y + h, x : x + w]


def render_member_text_panel(
    member_name: str,
    job_name: str,
    skills,
) -> np.ndarray:
    load_media_modules()
    return render_member_text_panel_image(
        member_name,
        job_name,
        skills,
        font_factory=result_font,
    )


def save_result_image(runner, equip_info, save_slot: int = 1) -> Path:
    from ccz_randomizer.ui.result_image import render_result_image
    load_media_modules()
    image = render_result_image(runner, equip_info, save_slot, result_font=result_font)
    output = result_panel_dir() / f"save{save_slot}.png"
    try:
        image.save(output, "PNG")
    finally:
        image.close()
    return output


def save_result_failure_image(save_slot: int, detail: str) -> Path:
    """Keep the result set complete when optional rendering fails."""
    load_media_modules()
    image = Image.new("RGB", (740, 1028), "#f5f5f5")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 739, 86), fill="#234f7d")
    draw.text(
        (28, 24),
        f"第 {save_slot} 号存档",
        font=result_font(28, bold=True),
        fill="white",
    )
    draw.text(
        (36, 132),
        "存档已保存",
        font=result_font(30, bold=True),
        fill="#173c61",
    )
    draw.text(
        (36, 190),
        "结果图生成失败，请查看本轮日志。",
        font=result_font(22),
        fill="#333333",
    )
    safe_detail = " ".join(str(detail).split())[:180]
    if safe_detail:
        draw.text(
            (36, 244),
            safe_detail,
            font=result_font(16),
            fill="#666666",
        )
    output = result_panel_dir() / f"save{save_slot}.png"
    image.save(output, "PNG")
    return output


def compose_result_grid(panel_paths: dict[int, Path]) -> Path:
    from ccz_randomizer.ui.result_grid import compose_result_panels
    output = result_grid_path()
    compose_result_panels(panel_paths, output)
    return output


def find_process_window(
    pid: int, title: str, visible_only: bool = True
) -> int:
    matches: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )

    @callback_type
    def callback(hwnd: int, _param: int) -> bool:
        window_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        if window_pid.value != pid:
            return True
        if visible_only and not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        title_buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buffer, length + 1)
        if title_buffer.value == title:
            matches.append(hwnd)
            return False
        return True

    if WINDOW_DESKTOP:
        user32.EnumDesktopWindows(WINDOW_DESKTOP, callback, 0)
    else:
        user32.EnumWindows(callback, 0)
    return matches[0] if matches else 0


def process_windows(pid: int, visible_only: bool = True) -> list[int]:
    matches: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )

    @callback_type
    def callback(hwnd: int, _param: int) -> bool:
        window_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        if window_pid.value != pid:
            return True
        if visible_only and not user32.IsWindowVisible(hwnd):
            return True
        matches.append(hwnd)
        return True

    if WINDOW_DESKTOP:
        user32.EnumDesktopWindows(WINDOW_DESKTOP, callback, 0)
    else:
        user32.EnumWindows(callback, 0)
    return matches


def window_process_id(hwnd: int) -> int:
    pid = wintypes.DWORD()
    if hwnd:
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def find_process_window_by_class(pid: int, class_name: str) -> int:
    for hwnd in process_windows(pid):
        if window_class(hwnd) == class_name:
            return hwnd
    return 0


def recover_stale_windows(pid: int, main_window: int = 0) -> int:
    closed_windows = []
    for hwnd in process_windows(pid, visible_only=False):
        if window_class(hwnd) == "#32770":
            user32.PostMessageW(hwnd, 0x0010, 0, 0)
            closed_windows.append(
                {
                    "hwnd": hwnd,
                    "title": window_text(hwnd),
                }
            )
    if closed_windows:
        print("已清理上轮残留窗口")
        deadline = time.perf_counter() + 1.5
        while time.perf_counter() < deadline:
            check_stop_requested()
            if not any(
                user32.IsWindow(row["hwnd"])
                # The game caches some dialogs (e.g. member information)
                # after hiding them. They need not be destroyed to load again.
                and user32.IsWindowVisible(row["hwnd"])
                for row in closed_windows
            ):
                break
            interruptible_sleep(0.05)
    if main_window and user32.IsWindow(main_window):
        user32.EnableWindow(main_window, True)
    diagnostic_log(
        "stale_game_windows_recovered",
        pid=pid,
        main_window=main_window,
        closed_windows=closed_windows,
        main_window_enabled=bool(
            main_window
            and user32.IsWindow(main_window)
            and user32.IsWindowEnabled(main_window)
        ),
    )
    return len(closed_windows)


def deepest_child_at(root: int, screen_x: int, screen_y: int) -> tuple[int, int, int]:
    target = root
    for _ in range(12):
        point = Point(screen_x, screen_y)
        user32.ScreenToClient(target, ctypes.byref(point))
        child = user32.ChildWindowFromPointEx(
            target,
            point,
            CWP_SKIPINVISIBLE | CWP_SKIPDISABLED | CWP_SKIPTRANSPARENT,
        )
        if not child or child == target:
            final_point = Point(screen_x, screen_y)
            user32.ScreenToClient(target, ctypes.byref(final_point))
            return target, final_point.x, final_point.y
        target = child
    final_point = Point(screen_x, screen_y)
    user32.ScreenToClient(target, ctypes.byref(final_point))
    return target, final_point.x, final_point.y


def window_class(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, len(buffer))
    return buffer.value


def activate_hidden_window(hwnd: int) -> None:
    return None


def focus_hidden_control(parent: int, control: int) -> None:
    return None


def post_click(root: int, screen_x: int, screen_y: int, count: int = 1, right=False) -> None:
    target, client_x, client_y = deepest_child_at(root, screen_x, screen_y)
    if not right and window_class(target) == "Button":
        for _ in range(count):
            check_stop_requested()
            user32.PostMessageW(target, 0x00F5, 0, 0)
            interruptible_sleep(0.12)
        return
    native_background_click(
        target, client_x, client_y, count, right
    )


def post_key_to_game(pid: int, key: str) -> None:
    virtual_keys = {
        "esc": 0x1B,
        "enter": 0x0D,
        "space": 0x20,
        "left": 0x25,
        "up": 0x26,
        "right": 0x27,
        "down": 0x28,
    }
    vk = virtual_keys.get(key.casefold())
    if vk is None and len(key) == 1:
        vk = ord(key.upper())
    if vk is None:
        return
    game = find_process_window_by_class(pid, "SOUSOU")
    target = user32.GetLastActivePopup(game) if game else 0
    if not target or not user32.IsWindowVisible(target):
        target = game
    if target:
        check_stop_requested()
        user32.PostMessageW(target, 0x0100, vk, 0)
        user32.PostMessageW(target, 0x0101, vk, 0)
        interruptible_sleep(0.15)


def enable_game_acceleration(pid: int) -> str:
    try:
        native_enable_acceleration(pid)
        return "native_state"
    except (NativeControlError, NativeControlTimeout) as exc:
        post_key_to_game(pid, "z")
        diagnostic_log(
            "acceleration_native_enable_failed",
            pid=pid,
            fallback="window_message",
            error=repr(exc),
        )
        return "window_message"


def visible_owned_windows(owner: int) -> list[tuple[int, str, tuple[int, int, int, int]]]:
    rows: list[tuple[int, str, tuple[int, int, int, int]]] = []
    owner_pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(owner, ctypes.byref(owner_pid))
    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )

    @callback_type
    def callback(hwnd: int, _param: int) -> bool:
        window_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        if (
            window_pid.value != owner_pid.value
            or hwnd == owner
            or not user32.IsWindowVisible(hwnd)
        ):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        title_buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buffer, length + 1)
        rect = wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            rows.append(
                (
                    hwnd,
                    title_buffer.value,
                    (rect.left, rect.top, rect.right, rect.bottom),
                )
            )
        return True

    if WINDOW_DESKTOP:
        user32.EnumDesktopWindows(WINDOW_DESKTOP, callback, 0)
    else:
        user32.EnumWindows(callback, 0)
    return rows


def wait_list_dialog(pid: int, timeout: float) -> int:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        check_stop_requested()
        for hwnd in process_windows(pid):
            if (
                window_class(hwnd) == "#32770"
                and user32.FindWindowExW(
                    hwnd, 0, "SysListView32", None
                )
            ):
                return hwnd
        interruptible_sleep(0.05)
    return 0


def window_text(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value.strip()


def game_state_diagnostic(
    pid: int,
    game: int,
    *,
    jobs: tuple[int, ...] = (),
    source_memory: bytes | None = None,
) -> dict[str, object]:
    windows = []
    for hwnd in process_windows(pid, visible_only=False):
        rect = wintypes.RECT()
        has_rect = bool(user32.GetWindowRect(hwnd, ctypes.byref(rect)))
        windows.append(
            {
                "hwnd": hwnd,
                "class": window_class(hwnd),
                "text": window_text(hwnd),
                "visible": bool(user32.IsWindowVisible(hwnd)),
                "enabled": bool(user32.IsWindowEnabled(hwnd)),
                "iconic": bool(user32.IsIconic(hwnd)),
                "rect": (
                    [rect.left, rect.top, rect.right, rect.bottom]
                    if has_rect
                    else None
                ),
            }
        )

    memory: dict[str, object] = {}
    try:
        current = read_memory(pid, 0, R0_MEMORY_SIZE)
        memory = {
            "size": len(current),
            "sha256": hashlib.sha256(current).hexdigest(),
            "source_equal": (
                current == source_memory
                if source_memory is not None
                else None
            ),
            "job_region": current[
                JOB_OFFSET : JOB_OFFSET + (max(JOB_POSITIONS_R1) + 1) * 4
            ].hex(),
        }
    except Exception as exc:
        memory = {"error": repr(exc)}

    foreground = user32.GetForegroundWindow()
    return {
        "pid": pid,
        "game_hwnd": game,
        "game_window_valid": bool(user32.IsWindow(game)),
        "game_window_visible": bool(user32.IsWindowVisible(game)),
        "game_window_enabled": bool(user32.IsWindowEnabled(game)),
        "game_window_iconic": bool(user32.IsIconic(game)),
        "last_active_popup": int(user32.GetLastActivePopup(game)) if game else 0,
        "foreground_hwnd": int(foreground),
        "foreground_pid": window_process_id(foreground),
        "jobs": list(jobs),
        "memory": memory,
        "windows": windows,
    }


def click_geometry_diagnostic(game: int) -> dict[str, object]:
    window_rect = wintypes.RECT()
    client_rect = wintypes.RECT()
    client_origin = Point(0, 0)
    has_window_rect = bool(
        user32.GetWindowRect(game, ctypes.byref(window_rect))
    )
    has_client_rect = bool(
        user32.GetClientRect(game, ctypes.byref(client_rect))
    )
    has_client_origin = bool(
        user32.ClientToScreen(game, ctypes.byref(client_origin))
    )
    try:
        dpi = int(user32.GetDpiForWindow(game))
    except (AttributeError, OSError):
        dpi = None
    return {
        "window_rect": (
            [
                window_rect.left,
                window_rect.top,
                window_rect.right,
                window_rect.bottom,
            ]
            if has_window_rect
            else None
        ),
        "client_rect": (
            [
                client_rect.left,
                client_rect.top,
                client_rect.right,
                client_rect.bottom,
            ]
            if has_client_rect
            else None
        ),
        "client_origin": (
            [client_origin.x, client_origin.y]
            if has_client_origin
            else None
        ),
        "dpi": dpi,
        "npc_client_position": list(XU_CLIENT_POSITION),
        "choice_client_position": list(CONFIRM_FIRST_CLIENT_POSITION),
    }


def interaction_failure_type(
    pid: int,
    state: dict[str, object],
    *,
    load_mode: str,
    reused_session: bool,
) -> str:
    if not process_is_alive(pid):
        return "interaction:process-exited"
    if not state.get("game_window_valid"):
        return "interaction:window-invalid"
    if not state.get("game_window_enabled"):
        popup = state.get("last_active_popup")
        for window in state.get("windows", []):
            if not isinstance(window, dict) or window.get("hwnd") != popup:
                continue
            return (
                "interaction:window-disabled:"
                f"{window.get('class', '')}:{window.get('text', '')}"
            )
        return "interaction:window-disabled:unknown-popup"
    session_type = "reused" if reused_session else "fresh"
    return f"interaction:no-change:{load_mode}:{session_type}"


def reserve_diagnostic_screenshot(error_type: str) -> bool:
    with DIAGNOSTIC_LOCK:
        if error_type in DIAGNOSTIC_SCREENSHOT_TYPES:
            return False
        if len(DIAGNOSTIC_SCREENSHOT_TYPES) >= DIAGNOSTIC_SCREENSHOT_LIMIT:
            return False
        DIAGNOSTIC_SCREENSHOT_TYPES.add(error_type)
        return True


def capture_interaction_failure(
    pid: int,
    game: int,
    error_type: str,
) -> str | None:
    if DIAGNOSTIC_LOG_PATH is None:
        return None
    if not reserve_diagnostic_screenshot(error_type):
        return None
    error_hash = hashlib.sha256(error_type.encode("utf-8")).hexdigest()[:12]
    output = DIAGNOSTIC_LOG_PATH.with_name(
        f"{DIAGNOSTIC_LOG_PATH.stem}_interaction_failure_"
        f"{error_hash}_{pid}_{time.time_ns()}.png"
    )
    try:
        image = print_window_mat(game, strip_client=False)
        if image.size == 0:
            raise RuntimeError("后台游戏窗口截图为空")
        load_media_modules()
        Image.fromarray(image[:, :, ::-1]).save(output, "PNG")
        return str(output)
    except Exception as exc:
        with DIAGNOSTIC_LOCK:
            DIAGNOSTIC_SCREENSHOT_TYPES.discard(error_type)
        diagnostic_log(
            "interaction_failure_capture_failed",
            pid=pid,
            hwnd=game,
            error_type=error_type,
            error=repr(exc),
        )
        return None


def click_leftmost_dialog_button(hwnd: int) -> bool:
    buttons: list[tuple[int, str, int]] = []
    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )

    @callback_type
    def callback(child: int, _param: int) -> bool:
        if (
            window_class(child) != "Button"
            or not user32.IsWindowVisible(child)
        ):
            return True
        rect = wintypes.RECT()
        if user32.GetWindowRect(child, ctypes.byref(rect)):
            buttons.append((rect.left, window_text(child), child))
        return True

    user32.EnumChildWindows(hwnd, callback, 0)
    if not buttons:
        return False
    preferred = ("是", "确定", "确认", "OK", "Yes")
    button = next(
        (
            child
            for _left, text, child in buttons
            if text in preferred
        ),
        min(buttons)[2],
    )
    print(
        "后台确认按钮: "
        + ", ".join(text or f"ID={user32.GetDlgCtrlID(child)}"
                    for _left, text, child in buttons)
    )
    result = wintypes.DWORD()
    return bool(
        user32.SendMessageTimeoutW(
            button,
            BM_CLICK,
            0,
            0,
            SMTO_ABORTIFHUNG,
            1500,
            ctypes.byref(result),
        )
    )


def finish_reused_load_confirmation(pid: int, game: int) -> bool:
    """Complete a delayed confirmation left by the direct-load path."""
    deadline = time.perf_counter() + 1.5
    dialog = 0
    while time.perf_counter() < deadline:
        check_stop_requested()
        for hwnd in process_windows(pid):
            if (
                window_class(hwnd) == "#32770"
                and window_text(hwnd) == "确认"
                and user32.IsWindowVisible(hwnd)
            ):
                dialog = hwnd
                break
        if dialog:
            break
        if user32.IsWindowEnabled(game):
            return False
        interruptible_sleep(0.05)

    if not dialog:
        diagnostic_log(
            "reused_load_not_ready",
            pid=pid,
            game_hwnd=game,
            game_enabled=bool(user32.IsWindowEnabled(game)),
            state=game_state_diagnostic(pid, game),
        )
        raise InteractionNotTriggered(
            "后台读档后游戏主窗口未恢复，且未找到确认窗口"
        )

    diagnostic_log(
        "reused_load_confirmation_found",
        pid=pid,
        game_hwnd=game,
        dialog_hwnd=dialog,
        game_enabled=bool(user32.IsWindowEnabled(game)),
    )
    if not click_leftmost_dialog_button(dialog):
        diagnostic_log(
            "reused_load_confirmation_click_failed",
            pid=pid,
            game_hwnd=game,
            dialog_hwnd=dialog,
        )
        raise InteractionNotTriggered("后台读档确认窗口未能关闭")

    close_deadline = time.perf_counter() + 3.0
    while time.perf_counter() < close_deadline:
        check_stop_requested()
        dialog_valid = bool(user32.IsWindow(dialog))
        game_enabled = bool(user32.IsWindowEnabled(game))
        if not dialog_valid and game_enabled:
            diagnostic_log(
                "reused_load_confirmation_closed",
                pid=pid,
                game_hwnd=game,
                dialog_hwnd=dialog,
            )
            return True
        if not dialog_valid and not game_enabled:
            if not user32.IsWindow(game) or not process_executable(pid):
                diagnostic_log(
                    "reused_load_process_exited",
                    pid=pid,
                    game_hwnd=game,
                    dialog_hwnd=dialog,
                )
                raise DirectReloadUnsupported(
                    "当前设备的后台快速读档会导致游戏退出"
                )
            diagnostic_log(
                "reused_load_owner_disabled",
                pid=pid,
                game_hwnd=game,
                dialog_hwnd=dialog,
                state=game_state_diagnostic(pid, game),
            )
            user32.EnableWindow(game, True)
            if user32.IsWindowEnabled(game):
                diagnostic_log(
                    "reused_load_owner_reenabled",
                    pid=pid,
                    game_hwnd=game,
                    dialog_hwnd=dialog,
                )
                return True
        interruptible_sleep(0.05)

    diagnostic_log(
        "reused_load_confirmation_close_timeout",
        pid=pid,
        game_hwnd=game,
        dialog_hwnd=dialog,
        dialog_valid=bool(user32.IsWindow(dialog)),
        game_enabled=bool(user32.IsWindowEnabled(game)),
    )
    raise InteractionNotTriggered("后台读档确认后游戏主窗口未恢复")


def bundled_random_s00() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "random_s00.eex"
    return source_root() / "resources" / "app" / "random_s00.eex"


def bundled_original_s00() -> Path:
    root = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else source_root()
    return root / "resources" / "app" / "2.2" / "original_s00.eex"


def repair_runtime_s00(
    game_executable: Path,
    event: str,
) -> None:
    original_script = bundled_original_s00()
    helper_script = bundled_random_s00()
    if not original_script.is_file() or not helper_script.is_file():
        raise FileNotFoundError("工具内缺少 S_00.eex 保护文件")
    result = repair_game_s00(
        game_executable.parent,
        original_script,
        helper_script,
    )
    diagnostic_log(
        event,
        active_script_repaired=result.active_script_repaired,
        stale_helper_replaced=result.stale_helper_replaced,
        transaction_recovered=result.transaction_recovered,
        root=file_diagnostic(game_executable.parent / "S_00.eex"),
        override=file_diagnostic(
            game_executable.parent / "RS" / "S_00.eex"
        ),
    )


def repair_runtime_scratch_save(
    game_executable: Path,
    event: str,
) -> None:
    guard = ScratchSaveGuard(game_executable.parent)
    recovered = guard.prepare()
    diagnostic_log(
        event,
        transaction_recovered=recovered,
        target=file_diagnostic(guard.target),
    )


def cleanup_random_runtime(
    game_executable: Path,
    event: str,
) -> None:
    errors = []
    terminated = ()
    try:
        terminated = terminate_random_game_instances(game_executable)
    except Exception as exc:
        errors.append(f"后台游戏关闭失败：{exc}")
        diagnostic_error(
            f"{event}_game_cleanup_failed",
            exc,
            game_executable=game_executable,
        )
    try:
        repair_runtime_s00(game_executable, f"{event}_s00_repair")
    except Exception as exc:
        errors.append(f"S_00 恢复失败：{exc}")
        diagnostic_error(
            f"{event}_s00_repair_failed",
            exc,
            game_executable=game_executable,
        )
    try:
        repair_runtime_scratch_save(
            game_executable,
            f"{event}_scratch_save_repair",
        )
    except Exception as exc:
        errors.append(f"第 16 号临时存档恢复失败：{exc}")
        diagnostic_error(
            f"{event}_scratch_save_repair_failed",
            exc,
            game_executable=game_executable,
        )
    diagnostic_log(
        event,
        game_executable=game_executable,
        terminated_random_pids=terminated,
    )
    if errors:
        raise RuntimeError("；".join(errors))


def write_cv_image(path: Path, image) -> None:
    load_media_modules()
    suffix = path.suffix or ".png"
    encoded, buffer = cv2.imencode(suffix, image)
    if not encoded:
        raise RuntimeError(f"结果图片编码失败：{path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer.tofile(str(path))


def decode_subprocess_output(output: bytes | str | None) -> str:
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    for encoding in ("utf-8", "gb18030"):
        try:
            return output.decode(encoding)
        except UnicodeDecodeError:
            continue
    return output.decode("utf-8", errors="replace")


def inspection_attempt_paths(
    output_dir: Path,
    attempt: int,
    slot: int | None = None,
) -> tuple[Path, Path, Path]:
    unique = f"{time.time_ns():x}"
    if DIAGNOSTIC_LOG_PATH is not None:
        base_stem = DIAGNOSTIC_LOG_PATH.stem.removesuffix("_diagnostic")
        prefix = DIAGNOSTIC_LOG_PATH.parent.resolve() / (
            f"{base_stem}_inspection_slot{slot or 0}_"
            f"attempt-{attempt}_{unique}"
        )
    else:
        prefix = output_dir.parent.resolve() / (
            f"{output_dir.name}-inspection-attempt-{attempt}-{unique}"
        )
    log_path = prefix.with_suffix(".log")
    return (
        log_path,
        prefix.with_name(prefix.name + "_diagnostic.jsonl"),
        log_path,
    )


def read_log_preview(path: Path, limit: int = 8000) -> str:
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text.strip()[-limit:]


def run_inspection_process_once(
    game_executable: Path,
    slot: int,
    output_dir: Path,
    job_score: float,
    *,
    force_injected_story_click: bool = False,
    attempt: int = 1,
) -> dict:
    output_dir = output_dir.resolve()
    started_at = time.perf_counter()
    click_strategy = (
        "injected_background_mouse"
        if force_injected_story_click
        else "post_message"
    )
    child_log_path, child_diagnostic_path, child_stdout_path = (
        inspection_attempt_paths(output_dir, attempt, slot)
    )
    if getattr(sys, "frozen", False):
        command = [
            sys.executable,
            "--inspect-slot",
            str(slot),
            "--inspect-output",
            str(output_dir),
            "--game-executable",
            str(game_executable),
            "--job-score",
            str(job_score),
        ]
    else:
        command = [
            sys.executable,
            str(source_entry_path()),
            "--inspect-slot",
            str(slot),
            "--inspect-output",
            str(output_dir),
            "--game-executable",
            str(game_executable),
            "--job-score",
            str(job_score),
        ]
    env = os.environ.copy()
    env["CCZ_USE_ISOLATED_DESKTOP"] = "1"
    env.pop("CCZ_BACKGROUND_RENDER", None)
    env.pop("CCZ_DISABLE_GUARD", None)
    if force_injected_story_click:
        env["CCZ_INSPECTION_FORCE_INJECTED_STORY_CLICK"] = "1"
    else:
        env.pop("CCZ_INSPECTION_FORCE_INJECTED_STORY_CLICK", None)
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("CCZ_INSPECTION_LOG_PATH", None)
    env["CCZ_INSPECTION_DIAGNOSTIC_PATH"] = str(child_diagnostic_path)
    env["CCZ_INSPECTION_ATTEMPT"] = str(attempt)
    env["CCZ_INSPECTION_CLICK_STRATEGY"] = click_strategy
    if DIAGNOSTIC_LOG_PATH is not None:
        env["CCZ_PARENT_DIAGNOSTIC_PATH"] = str(DIAGNOSTIC_LOG_PATH)
    diagnostic_log(
        "inspection_process_started",
        slot=slot,
        attempt=attempt,
        click_strategy=click_strategy,
        child_log_path=str(child_log_path),
        child_diagnostic_path=str(child_diagnostic_path),
        child_stdout_path=str(child_stdout_path),
    )
    child_stdout_path.parent.mkdir(parents=True, exist_ok=True)
    timed_out = False
    with child_stdout_path.open("wb") as stdout_stream:
        process = subprocess.Popen(
            command,
            cwd=str(game_executable.parent),
            env=env,
            stdout=stdout_stream,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        result_file = output_dir / "inspection.json"
        deadline = time.perf_counter() + 180
        while time.perf_counter() < deadline:
            if result_file.is_file():
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                break
            if process.poll() is not None:
                break
            time.sleep(0.2)
        if process.poll() is None:
            timed_out = True
            process.kill()
            process.wait()
        stdout_stream.flush()
    elapsed_seconds = round(time.perf_counter() - started_at, 3)
    if process.returncode != 0 or not result_file.is_file():
        detail = read_log_preview(child_stdout_path)
        error = InspectionProcessError(
            "full",
            process.returncode,
            detail,
            timed_out=timed_out,
            child_log_path=child_log_path,
            child_diagnostic_path=child_diagnostic_path,
            child_stdout_path=child_stdout_path,
            click_strategy=click_strategy,
            elapsed_seconds=elapsed_seconds,
        )
        diagnostic_log(
            "inspection_process_child_failed",
            slot=slot,
            attempt=attempt,
            child_pid=process.pid,
            child_returncode=process.returncode,
            timed_out=timed_out,
            elapsed_seconds=elapsed_seconds,
            click_strategy=click_strategy,
            child_log_path=str(child_log_path),
            child_diagnostic_path=str(child_diagnostic_path),
            child_stdout_path=str(child_stdout_path),
            output_preview=detail,
        )
        raise error
    result = json.loads(result_file.read_text(encoding="utf-8"))
    diagnostic_log(
        "inspection_process_completed",
        slot=slot,
        attempt=attempt,
        child_pid=process.pid,
        child_returncode=process.returncode,
        elapsed_seconds=elapsed_seconds,
        click_strategy=click_strategy,
        child_log_path=str(child_log_path),
        child_diagnostic_path=str(child_diagnostic_path),
        child_stdout_path=str(child_stdout_path),
    )
    return result


def run_inspection_process(
    game_executable: Path,
    slot: int,
    output_dir: Path,
    job_score: float,
) -> dict:
    last_error: RuntimeError | None = None
    for attempt in range(1, 3):
        try:
            return run_inspection_process_once(
                game_executable,
                slot,
                output_dir,
                job_score,
                force_injected_story_click=attempt > 1,
                attempt=attempt,
            )
        except RuntimeError as exc:
            last_error = exc
            diagnostic_log(
                "inspection_process_failed",
                slot=slot,
                attempt=attempt,
                error=repr(exc),
                click_strategy=getattr(exc, "click_strategy", None),
                child_log_path=str(getattr(exc, "child_log_path", "") or ""),
                child_diagnostic_path=str(
                    getattr(exc, "child_diagnostic_path", "") or ""
                ),
                child_stdout_path=str(
                    getattr(exc, "child_stdout_path", "") or ""
                ),
                elapsed_seconds=getattr(exc, "elapsed_seconds", None),
            )
            if attempt == 1:
                print("候选结果检查异常，正在自动重试一次")
                shutil.rmtree(output_dir, ignore_errors=True)
                output_dir.mkdir(parents=True, exist_ok=True)
                continue
            raise
    raise last_error or RuntimeError("候选结果检查失败")


def run_initial_inspection_process_once(
    game_executable: Path,
    slot: int,
    output_dir: Path,
    job_score: float,
) -> dict:
    if getattr(sys, "frozen", False):
        command = [
            sys.executable,
            "--inspect-initial-slot",
            str(slot),
            "--inspect-output",
            str(output_dir),
            "--game-executable",
            str(game_executable),
            "--job-score",
            str(job_score),
        ]
    else:
        command = [
            sys.executable,
            str(source_entry_path()),
            "--inspect-initial-slot",
            str(slot),
            "--inspect-output",
            str(output_dir),
            "--game-executable",
            str(game_executable),
            "--job-score",
            str(job_score),
        ]
    env = os.environ.copy()
    env["CCZ_USE_ISOLATED_DESKTOP"] = "1"
    env.pop("CCZ_BACKGROUND_RENDER", None)
    env.pop("CCZ_DISABLE_GUARD", None)
    env["PYTHONIOENCODING"] = "utf-8"
    process = subprocess.Popen(
        command,
        cwd=str(game_executable.parent),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    result_file = output_dir / "inspection.json"
    try:
        stdout, _ = process.communicate(timeout=90)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, _ = process.communicate()
        detail = decode_subprocess_output(stdout).strip()[-2000:]
        raise InspectionProcessError(
            "initial",
            process.returncode,
            detail or "检查进程运行超时",
            timed_out=True,
        )
    if process.returncode != 0 or not result_file.is_file():
        detail = decode_subprocess_output(stdout).strip()[-2000:]
        raise InspectionProcessError(
            "initial",
            process.returncode,
            detail,
        )
    return json.loads(result_file.read_text(encoding="utf-8"))


def run_initial_inspection_process(
    game_executable: Path,
    slot: int,
    output_dir: Path,
    job_score: float,
) -> dict:
    last_error: RuntimeError | None = None
    for attempt in range(1, 3):
        try:
            return run_initial_inspection_process_once(
                game_executable,
                slot,
                output_dir,
                job_score,
            )
        except RuntimeError as exc:
            last_error = exc
            diagnostic_log(
                "initial_inspection_process_failed",
                slot=slot,
                attempt=attempt,
                error=repr(exc),
            )
            if attempt == 1:
                print("初始三人能力检查异常，正在自动重试一次")
                shutil.rmtree(output_dir, ignore_errors=True)
                output_dir.mkdir(parents=True, exist_ok=True)
                continue
            raise
    raise last_error or RuntimeError("初始三人能力检查失败")


def run_candidate_inspection(
    game_executable: Path,
    slot: int,
    output_dir: Path,
    job_score: float,
    *,
    mode: str,
) -> dict | None:
    if mode not in {"three", "seven"}:
        raise ValueError(f"unsupported inspection mode: {mode}")
    inspect = (
        run_initial_inspection_process
        if mode == "three"
        else run_inspection_process
    )
    try:
        return inspect(
            game_executable,
            slot,
            output_dir,
            job_score,
        )
    except InspectionProcessError as exc:
        diagnostic_log(
            "candidate_inspection_abandoned",
            mode=mode,
            slot=slot,
            error=repr(exc),
            native_return_code=exc.return_code,
            native_timeout=exc.native_timeout,
        )
        return None


def inspection_background_click(
    pid: int,
    hwnd: int,
    client_x: int,
    client_y: int,
    *,
    right: bool = False,
) -> str:
    method = "injected_background_mouse"
    try:
        if right:
            native_background_click(hwnd, client_x, client_y, 1, True)
        else:
            native_silent_click(
                pid,
                hwnd,
                client_x,
                client_y,
                tail_delay_ms=120,
            )
    except (NativeControlError, NativeControlTimeout) as exc:
        method = "post_message_fallback"
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise
        post_click(
            hwnd,
            rect.left + client_x,
            rect.top + client_y,
            right=right,
        )
        diagnostic_log(
            "inspection_click_rect_fallback",
            pid=pid,
            hwnd=hwnd,
            client_point=(client_x, client_y),
            right=right,
            error=repr(exc),
        )
    diagnostic_log(
        "inspection_click_rect",
        pid=pid,
        hwnd=hwnd,
        client_point=(client_x, client_y),
        right=right,
        method=method,
    )
    return method


def trigger_seven_member_story(
    runner,
    pid: int,
    main_window: int,
    *,
    click_strategy: str,
) -> str:
    """Click Xu Zijiang again after randomization to start story progress."""
    del runner
    load_media_modules()
    before = print_window_mat(main_window)
    last_difference = 0.0
    for attempt in range(1, 4):
        check_stop_requested()
        method = "silent_click"
        try:
            native_silent_click(
                pid,
                main_window,
                XU_CLIENT_POSITION[0],
                XU_CLIENT_POSITION[1],
                tail_delay_ms=350,
            )
        except (NativeControlError, NativeControlTimeout) as exc:
            method = "injected_background_mouse"
            diagnostic_log(
                "inspection_story_npc_primary_click_failed",
                pid=pid,
                main_window=main_window,
                attempt=attempt,
                error=repr(exc),
            )
            native_background_click(
                main_window,
                XU_CLIENT_POSITION[0],
                XU_CLIENT_POSITION[1],
                1,
                False,
            )
        native_wake_game(pid, main_window, 800)
        interruptible_sleep(0.35)
        after = print_window_mat(main_window)
        if (
            before.shape == after.shape
            and before.size
            and after.size
        ):
            last_difference = float(
                np.mean(cv2.absdiff(before, after))
            )
        else:
            last_difference = 255.0
        diagnostic_log(
            "inspection_story_npc_clicked",
            pid=pid,
            main_window=main_window,
            attempt=attempt,
            client_point=list(XU_CLIENT_POSITION),
            method=method,
            frame_difference=round(last_difference, 3),
            requested_strategy=click_strategy,
            note="候选存档已完成随机，本次仅再次点击许子将触发剧情推进，无选项",
        )
        if last_difference >= 1.0:
            return method
        interruptible_sleep(0.3)
    raise RuntimeError(
        "候选存档再次点击许子将后画面没有变化，未能触发剧情推进"
    )


def persist_inspection_failure_screenshot(
    output_dir: Path,
    *,
    category: str,
    slot: int,
) -> str | None:
    diagnostic_value = os.environ.get(
        "CCZ_INSPECTION_DIAGNOSTIC_PATH", ""
    )
    if not diagnostic_value:
        return None
    diagnostic_path = Path(diagnostic_value)
    log_dir = diagnostic_path.parent
    parent_name = os.environ.get("CCZ_PARENT_DIAGNOSTIC_PATH", "")
    parent_stem = (
        Path(parent_name).stem.removesuffix("_diagnostic")
        if parent_name
        else diagnostic_path.stem.split("_inspection_", 1)[0]
    )
    safe_category = re.sub(r"[^a-z0-9_-]+", "_", category.casefold())
    pattern = f"{parent_stem}_inspection_failure_*.png"
    existing = list(log_dir.glob(pattern))
    if any(f"_{safe_category}_" in path.name for path in existing):
        return None
    if len(existing) >= DIAGNOSTIC_SCREENSHOT_LIMIT:
        return None
    source = output_dir / "people-window.png"
    if not source.is_file():
        source = output_dir / "after-jump.png"
    if not source.is_file():
        return None
    destination = log_dir / (
        f"{parent_stem}_inspection_failure_{safe_category}_"
        f"slot{slot}.png"
    )
    shutil.copyfile(source, destination)
    return str(destination)


def patch_inspection_runtime(task_module, pid: int, panel_dir: Path):
    from ccz_randomizer.runtime.inspection_adapter import patch_inspection_runtime as install_adapter
    return install_adapter(task_module, pid, panel_dir, services=sys.modules[__name__])



def wait_for_window_state(
    hwnd: int,
    *,
    exists: bool | None = None,
    enabled: bool | None = None,
    timeout: float = 3.0,
) -> bool:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        check_stop_requested()
        is_window = bool(hwnd and user32.IsWindow(hwnd))
        if exists is not None and is_window != exists:
            interruptible_sleep(0.05)
            continue
        if enabled is not None:
            if not is_window or bool(user32.IsWindowEnabled(hwnd)) != enabled:
                interruptible_sleep(0.05)
                continue
        return True
    return False


def find_dialog_button(hwnd: int, text: str) -> int:
    result = 0
    expected = "".join(
        character
        for character in text
        if character not in " &（）()"
    ).casefold()
    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )

    @callback_type
    def callback(child: int, _param: int) -> bool:
        nonlocal result
        child_text = "".join(
            character
            for character in window_text(child)
            if character not in " &（）()"
        ).casefold()
        if (
            window_class(child) == "Button"
            and (
                child_text == expected
                or child_text.startswith(expected)
            )
            and user32.IsWindowVisible(child)
            and user32.IsWindowEnabled(child)
        ):
            result = child
            return False
        return True

    user32.EnumChildWindows(hwnd, callback, 0)
    return result


def click_dialog_button(
    hwnd: int,
    text: str,
    *,
    pid: int | None = None,
    force_coordinate: bool = False,
) -> str:
    button = find_dialog_button(hwnd, text)
    if button and not force_coordinate:
        user32.SendMessageW(button, BM_CLICK, 0, 0)
        diagnostic_log(
            "dialog_button_click",
            hwnd=hwnd,
            button_hwnd=button,
            button_text=text,
            method="send_bm_click",
        )
        return "send_bm_click"

    if button and force_coordinate:
        screen_rect = wintypes.RECT()
        if user32.GetWindowRect(button, ctypes.byref(screen_rect)):
            click_pid = pid
            if click_pid is None:
                process_id = wintypes.DWORD()
                user32.GetWindowThreadProcessId(
                    button, ctypes.byref(process_id)
                )
                click_pid = int(process_id.value)
            if click_pid:
                point = Point(
                    (screen_rect.left + screen_rect.right) // 2,
                    (screen_rect.top + screen_rect.bottom) // 2,
                )
                user32.ScreenToClient(hwnd, ctypes.byref(point))
                diagnostic_log(
                    "dialog_button_click",
                    hwnd=hwnd,
                    button_hwnd=button,
                    button_text=text,
                    method="injected_dialog_button_mouse",
                    client_point=(point.x, point.y),
                    button_rect=(
                        screen_rect.left,
                        screen_rect.top,
                        screen_rect.right,
                        screen_rect.bottom,
                    ),
                )
                native_silent_click(
                    click_pid,
                    hwnd,
                    point.x,
                    point.y,
                    tail_delay_ms=120,
                )
                return "injected_dialog_button_mouse"

    fallback_rects = {
        "上一武将": (290, 350, 18, 56),
        "下一武将": (411, 350, 18, 56),
    }
    fallback = fallback_rects.get(text)
    if fallback and user32.IsWindow(hwnd):
        x, y, width, height = fallback
        rect = wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            point = Point(
                rect.left + x + width // 2,
                rect.top + y + height // 2,
            )
            user32.ScreenToClient(hwnd, ctypes.byref(point))
            click_pid = pid
            if click_pid is None:
                process_id = wintypes.DWORD()
                user32.GetWindowThreadProcessId(
                    hwnd, ctypes.byref(process_id)
                )
                click_pid = int(process_id.value)
            diagnostic_log(
                "dialog_button_click",
                hwnd=hwnd,
                button_hwnd=button,
                button_text=text,
                method="injected_dialog_fallback",
                client_point=(point.x, point.y),
                window_rect=(
                    rect.left,
                    rect.top,
                    rect.right,
                    rect.bottom,
                ),
            )
            if click_pid:
                native_silent_click(
                    click_pid,
                    hwnd,
                    point.x,
                    point.y,
                    tail_delay_ms=120,
                )
                return "injected_dialog_fallback"
            diagnostic_log(
                "dialog_button_click_pid_missing",
                hwnd=hwnd,
                button_text=text,
            )

    buttons = []
    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )

    @callback_type
    def collect(child: int, _param: int) -> bool:
        if window_class(child) == "Button":
            buttons.append(
                {
                    "hwnd": child,
                    "text": window_text(child),
                    "visible": bool(user32.IsWindowVisible(child)),
                    "enabled": bool(user32.IsWindowEnabled(child)),
                    "control_id": user32.GetDlgCtrlID(child),
                }
            )
        return True

    user32.EnumChildWindows(hwnd, collect, 0)
    diagnostic_log(
        "dialog_button_missing",
        hwnd=hwnd,
        expected_text=text,
        buttons=buttons,
    )
    raise RuntimeError(
        f"武将能力窗口未找到“{text}”按钮，也无法使用兼容方式切换。"
        "请把普通日志和诊断日志一起发给工具作者。"
    )


def dialog_has_text(hwnd: int, text: str) -> bool:
    found = False
    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )

    @callback_type
    def callback(child: int, _param: int) -> bool:
        nonlocal found
        if (
            user32.IsWindowVisible(child)
            and window_text(child) == text
        ):
            found = True
            return False
        return True

    user32.EnumChildWindows(hwnd, callback, 0)
    return found


def wait_for_dialog_text(hwnd: int, text: str, timeout: float = 3.0) -> bool:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        check_stop_requested()
        if user32.IsWindow(hwnd) and dialog_has_text(hwnd, text):
            return True
        interruptible_sleep(0.05)
    return False


def current_dialog_member(hwnd: int, member_names: tuple[str, ...]) -> str:
    for member_name in member_names:
        if dialog_has_text(hwnd, member_name):
            return member_name
    return ""


def find_member_dialog(pid: int, member_name: str) -> int:
    for hwnd in process_windows(pid):
        if (
            window_class(hwnd) == "#32770"
            and dialog_has_text(hwnd, member_name)
        ):
            return hwnd
    return 0


def find_any_member_dialog(
    pid: int, member_names: tuple[str, ...]
) -> tuple[int, str]:
    for hwnd in process_windows(pid):
        if window_class(hwnd) != "#32770":
            continue
        for member_name in member_names:
            if dialog_has_text(hwnd, member_name):
                return hwnd, member_name
    return 0, ""


def advance_people_info(
    pid: int,
    main_window: int,
    info_hwnd: int,
    current_name: str,
    expected_name: str,
    member_names: tuple[str, ...],
) -> int:
    for _ in range(3):
        if current_name != member_names[0]:
            user32.SendMessageW(info_hwnd, 0x001C, 1, 0)
            user32.SendMessageW(info_hwnd, 0x0006, 1, 0)
            user32.SendMessageW(info_hwnd, 0x0086, 1, 0)
            user32.SendMessageW(info_hwnd, 0x0007, 0, 0)
        click_dialog_button(info_hwnd, "下一武将", pid=pid)
        deadline = time.perf_counter() + 1.5
        while time.perf_counter() < deadline:
            check_stop_requested()
            expected_hwnd = find_member_dialog(pid, expected_name)
            if expected_hwnd:
                return expected_hwnd
            shown_name = current_dialog_member(info_hwnd, member_names)
            if shown_name and shown_name != current_name:
                raise RuntimeError(
                    f"武将顺序异常：应为{expected_name}，实际为{shown_name}"
                )
            interruptible_sleep(0.05)
        interruptible_sleep(0.2)
    shown_name = current_dialog_member(info_hwnd, member_names)
    raise RuntimeError(
        f"切换到{expected_name}失败，当前仍为{shown_name or '未知武将'}"
    )


def advance_people_info_in_game_order(
    pid: int,
    info_hwnd: int,
    current_name: str,
    member_names: tuple[str, ...],
    captured_names: set[str],
) -> tuple[int, str]:
    """Advance to the next distinct member without assuming roster order."""
    for attempt in range(3):
        click_method = click_dialog_button(
            info_hwnd,
            "下一武将",
            pid=pid,
            force_coordinate=attempt > 0,
        )
        diagnostic_log(
            "member_transition_click",
            pid=pid,
            hwnd=info_hwnd,
            attempt=attempt + 1,
            current_member=current_name,
            method=click_method,
        )
        deadline = time.perf_counter() + 2.0
        while time.perf_counter() < deadline:
            check_stop_requested()
            shown_name = current_dialog_member(info_hwnd, member_names)
            if (
                shown_name
                and shown_name != current_name
                and shown_name not in captured_names
            ):
                diagnostic_log(
                    "member_transition_observed",
                    pid=pid,
                    hwnd=info_hwnd,
                    attempt=attempt + 1,
                    current_member=current_name,
                    shown_member=shown_name,
                    method=click_method,
                )
                return info_hwnd, shown_name
            candidate_hwnd, candidate_name = find_any_member_dialog(
                pid, member_names
            )
            if (
                candidate_hwnd
                and candidate_name
                and candidate_name != current_name
                and candidate_name not in captured_names
            ):
                diagnostic_log(
                    "member_transition_observed",
                    pid=pid,
                    hwnd=candidate_hwnd,
                    attempt=attempt + 1,
                    current_member=current_name,
                    shown_member=candidate_name,
                    method=click_method,
                )
                return candidate_hwnd, candidate_name
            interruptible_sleep(0.05)
        diagnostic_log(
            "member_transition_click_no_change",
            pid=pid,
            hwnd=info_hwnd,
            attempt=attempt + 1,
            current_member=current_name,
            shown_member=current_dialog_member(
                info_hwnd, member_names
            ),
            method=click_method,
        )
        interruptible_sleep(0.2)
    shown_name = current_dialog_member(info_hwnd, member_names)
    raise RuntimeError(
        "切换到下一武将失败，"
        f"当前仍为{shown_name or current_name or '未知武将'}"
    )


def capture_roster_fallback_debug(
    pid: int,
    hwnd: int,
    stage: str,
) -> None:
    output_value = os.environ.get("CCZ_ROSTER_TEST_OUTPUT", "").strip()
    if not output_value:
        return
    output_dir = Path(output_value)
    output_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "stage": stage,
        "target_hwnd": hwnd,
        "target_valid": bool(hwnd and user32.IsWindow(hwnd)),
        "target_visible": bool(hwnd and user32.IsWindowVisible(hwnd)),
        "target_enabled": bool(hwnd and user32.IsWindowEnabled(hwnd)),
        "target_class": window_class(hwnd) if hwnd else "",
        "target_title": window_text(hwnd) if hwnd else "",
        "windows": [
            {
                "hwnd": candidate,
                "class": window_class(candidate),
                "title": window_text(candidate),
                "visible": bool(user32.IsWindowVisible(candidate)),
                "enabled": bool(user32.IsWindowEnabled(candidate)),
            }
            for candidate in process_windows(pid, visible_only=False)
        ],
    }
    with (output_dir / "roster-state.jsonl").open(
        "a", encoding="utf-8"
    ) as stream:
        stream.write(json.dumps(state, ensure_ascii=False) + "\n")
    if hwnd and user32.IsWindow(hwnd):
        try:
            write_cv_image(
                output_dir / f"{stage}.png",
                print_window_mat(hwnd, strip_client=False),
            )
        except Exception:
            pass


def wait_for_member_dialog_closed(hwnd: int, timeout: float = 2.0) -> bool:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        check_stop_requested()
        if (
            not user32.IsWindow(hwnd)
            or not user32.IsWindowVisible(hwnd)
            or window_text(hwnd) != "武将情报"
        ):
            return True
        interruptible_sleep(0.05)
    return False


def close_member_dialog(pid: int, main_window: int, info_hwnd: int) -> None:
    owner_hwnd = int(user32.GetWindow(info_hwnd, 4) or 0)

    def restore_owner() -> None:
        for hwnd in (owner_hwnd, main_window):
            if hwnd and user32.IsWindow(hwnd):
                user32.EnableWindow(hwnd, True)
        if owner_hwnd and user32.IsWindow(owner_hwnd):
            user32.ShowWindow(owner_hwnd, 5)
        diagnostic_log(
            "member_dialog_owner_restored",
            pid=pid,
            info_hwnd=info_hwnd,
            owner_hwnd=owner_hwnd,
            main_window=main_window,
            owner_valid=bool(owner_hwnd and user32.IsWindow(owner_hwnd)),
            main_window_enabled=bool(
                main_window and user32.IsWindowEnabled(main_window)
            ),
        )

    user32.PostMessageW(info_hwnd, 0x0010, 0, 0)
    if wait_for_member_dialog_closed(info_hwnd, timeout=2.0):
        restore_owner()
        return
    click_dialog_button(
        info_hwnd,
        "确定",
        pid=pid,
        force_coordinate=True,
    )
    if wait_for_member_dialog_closed(info_hwnd, timeout=2.0):
        restore_owner()
        return
    raise RuntimeError("武将能力窗口点击“确定”后未能关闭")


def ensure_people_roster_open(
    pid: int,
    main_window: int,
    runner,
    preferred_list_window: int = 0,
) -> int:
    """Reuse or reopen the roster without rediscovering the hidden game."""
    if preferred_list_window and user32.IsWindow(preferred_list_window):
        user32.EnableWindow(preferred_list_window, True)
        user32.ShowWindow(preferred_list_window, 5)
        diagnostic_log(
            "member_roster_fallback_reused",
            pid=pid,
            list_hwnd=preferred_list_window,
        )
        return preferred_list_window

    restore_deadline = time.perf_counter() + 1.5
    while time.perf_counter() < restore_deadline:
        check_stop_requested()
        runner.initPeopleWind()
        if runner.peopleWind.isInitSuccess():
            user32.EnableWindow(runner.peopleWind.hwnd, True)
            diagnostic_log(
                "member_roster_fallback_restored",
                pid=pid,
                list_hwnd=runner.peopleWind.hwnd,
            )
            return runner.peopleWind.hwnd
        interruptible_sleep(0.05)
    if not main_window or not user32.IsWindow(main_window):
        raise RuntimeError("列表备用路径中的后台游戏窗口已失效")

    diagnostic_log(
        "member_roster_fallback_open_start",
        pid=pid,
        main_window=main_window,
        main_window_enabled=bool(user32.IsWindowEnabled(main_window)),
        windows=[
            {
                "hwnd": hwnd,
                "class": window_class(hwnd),
                "title": window_text(hwnd),
                "visible": bool(user32.IsWindowVisible(hwnd)),
                "enabled": bool(user32.IsWindowEnabled(hwnd)),
            }
            for hwnd in process_windows(pid, visible_only=False)
        ],
    )
    for attempt in range(1, 4):
        native_wake_game(pid, main_window, 600)
        point = Point(138, 18)
        user32.ClientToScreen(main_window, ctypes.byref(point))
        post_click(main_window, point.x, point.y)
        deadline = time.perf_counter() + 2.0
        while time.perf_counter() < deadline:
            check_stop_requested()
            runner.initPeopleWind()
            if runner.peopleWind.isInitSuccess():
                user32.EnableWindow(runner.peopleWind.hwnd, True)
                diagnostic_log(
                    "member_roster_fallback_opened",
                    pid=pid,
                    list_hwnd=runner.peopleWind.hwnd,
                    attempt=attempt,
                )
                return runner.peopleWind.hwnd
            interruptible_sleep(0.05)
        diagnostic_log(
            "member_roster_fallback_open_retry",
            pid=pid,
            main_window=main_window,
            attempt=attempt,
        )
    raise RuntimeError("列表备用路径未能重新打开部队情报一览")


def open_uncaptured_member_from_roster(
    pid: int,
    main_window: int,
    runner,
    info_hwnd: int,
    member_names: tuple[str, ...],
    captured_names: set[str],
) -> tuple[int, str]:
    """Find an unread member from the roster without assuming row order."""
    list_hwnd = int(
        getattr(getattr(runner, "peopleWind", None), "hwnd", 0) or 0
    )
    capture_roster_fallback_debug(pid, list_hwnd, "before-close-list")
    capture_roster_fallback_debug(pid, info_hwnd, "before-close-info")
    close_member_dialog(pid, main_window, info_hwnd)
    capture_roster_fallback_debug(pid, list_hwnd, "after-close-list")
    observed: list[str] = []
    unread_rows = [
        index
        for index, name in enumerate(member_names)
        if name not in captured_names
    ]
    captured_rows = [
        index
        for index, name in enumerate(member_names)
        if name in captured_names
    ]
    for row_index in unread_rows + captured_rows:
        try:
            list_hwnd = ensure_people_roster_open(
                pid,
                main_window,
                runner,
                preferred_list_window=list_hwnd,
            )
        except RuntimeError as exc:
            diagnostic_log(
                "member_roster_fallback_list_unavailable",
                pid=pid,
                row_index=row_index,
                captured_members=sorted(captured_names),
                error=repr(exc),
            )
            continue
        diagnostic_log(
            "member_roster_fallback_click",
            pid=pid,
            row_index=row_index,
            list_hwnd=list_hwnd,
            captured_members=sorted(captured_names),
        )
        next_hwnd = 0
        shown_name = ""
        for click_method in ("list_window_command", "injected_row_click"):
            capture_roster_fallback_debug(
                pid,
                list_hwnd,
                f"row-{row_index}-{click_method}-before",
            )
            try:
                if click_method == "list_window_command":
                    run_native_control(
                        pid,
                        ["list-window", str(list_hwnd), str(row_index)],
                    )
                else:
                    native_background_click(
                        list_hwnd,
                        54,
                        129 + 60 * row_index,
                        1,
                        False,
                    )
                    native_wake_game(pid, main_window, 800)
            except (NativeControlError, NativeControlTimeout) as exc:
                diagnostic_log(
                    "member_roster_fallback_click_failed",
                    pid=pid,
                    row_index=row_index,
                    list_hwnd=list_hwnd,
                    method=click_method,
                    error=repr(exc),
                )
                continue
            deadline = time.perf_counter() + 3.0
            while time.perf_counter() < deadline:
                runner.initPeopleInfoWind()
                next_hwnd, shown_name = find_any_member_dialog(
                    pid, member_names
                )
                if next_hwnd:
                    break
                interruptible_sleep(0.05)
            if next_hwnd:
                break
            diagnostic_log(
                "member_roster_fallback_click_no_dialog",
                pid=pid,
                row_index=row_index,
                list_hwnd=list_hwnd,
                method=click_method,
            )
        if not next_hwnd:
            diagnostic_log(
                "member_roster_fallback_row_failed",
                pid=pid,
                row_index=row_index,
            )
            continue
        observed.append(shown_name)
        if shown_name not in captured_names:
            diagnostic_log(
                "member_roster_fallback_succeeded",
                pid=pid,
                row_index=row_index,
                info_hwnd=next_hwnd,
                shown_member=shown_name,
                captured_members=sorted(captured_names),
            )
            return next_hwnd, shown_name
        diagnostic_log(
            "member_roster_fallback_duplicate",
            pid=pid,
            row_index=row_index,
            info_hwnd=next_hwnd,
            shown_member=shown_name,
        )
        close_member_dialog(pid, main_window, next_hwnd)

    raise RuntimeError(
        "通过武将列表仍未找到尚未读取的武将；"
        f"已读取={sorted(captured_names)}，列表识别={observed}"
    )


def advance_seven_member_story(
    pid: int,
    main_window: int,
    *,
    rounds: int = 3,
    clicks_per_round: int = 80,
    first_round_down_delay_ms: int = 55,
    first_round_up_delay_ms: int = 80,
) -> bool:
    """Advance helper dialogue and the skipped-battle deployment screen."""
    for round_index in range(1, rounds + 1):
        check_stop_requested()
        if round_index == 1:
            native_silent_click_burst(
                main_window,
                360,
                400,
                clicks_per_round,
                down_delay_ms=first_round_down_delay_ms,
                up_delay_ms=first_round_up_delay_ms,
            )
            click_interval_ms = (
                first_round_down_delay_ms + first_round_up_delay_ms
            )
        else:
            native_silent_click_burst(
                main_window,
                360,
                400,
                clicks_per_round,
            )
            click_interval_ms = 150
        native_wake_game(pid, main_window, 500)
        interruptible_sleep(0.5)
        check_stop_requested()
        ready = seven_member_scene_ready(pid)
        diagnostic_log(
            "seven_member_story_progress",
            pid=pid,
            main_window=main_window,
            round=round_index,
            rounds=rounds,
            clicks=clicks_per_round,
            click_interval_ms=click_interval_ms,
            ready=ready,
        )
        if ready:
            diagnostic_log(
                "seven_member_story_ready",
                pid=pid,
                main_window=main_window,
                round=round_index,
            )
            return True
    failure_type = "seven-member-story:not-ready-after-three-batches"
    screenshot = capture_interaction_failure(
        pid,
        main_window,
        failure_type,
    )
    diagnostic_log(
        "seven_member_story_not_ready",
        pid=pid,
        main_window=main_window,
        rounds=rounds,
        clicks_per_round=clicks_per_round,
        scene_ready=False,
        state=game_state_diagnostic(pid, main_window),
        screenshot=screenshot,
    )
    return False


def wait_for_seven_member_scene(
    pid: int,
    *,
    timeout: float = 3.2,
) -> bool:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        check_stop_requested()
        if seven_member_scene_ready(pid):
            return True
        interruptible_sleep(0.05)
    return seven_member_scene_ready(pid)


def seven_member_scene_ready(pid: int) -> bool:
    try:
        state = read_memory(pid, 0, R0_MEMORY_SIZE)
    except OSError:
        return False
    if len(state) < 0x5830:
        return False
    if state[0x0FFF] != 1 or state[0x4F64:0x4F66] != b"\x01\x00":
        return False
    return all(
        any(state[offset : offset + 3])
        for offset in range(0x5800, 0x5815, 3)
    )


def capture_initial_member_panels(
    task_module,
    pid: int,
    main_window: int,
    runner,
) -> tuple:
    del main_window, runner
    check_stop_requested()
    members = initial_team_members(task_module.TEAM_MEMBER_LIST)
    load_member_skills_from_memory(
        task_module,
        pid,
        JOB_POSITIONS_R0,
        members,
    )
    panels = tuple(
        render_member_text_panel(
            member.name,
            str(getattr(getattr(member, "job", None), "name", "")),
            member.skillList,
        )
        for member in members
    )
    diagnostic_log(
        "initial_member_memory_inspection_completed",
        pid=pid,
        skills={
            member.name: [skill.name for skill in member.skillList]
            for member in members
        },
    )
    return panels, members


def inspect_initial_saved_slot(
    game_executable: Path,
    slot: int,
    output_dir: Path,
    job_score: float,
) -> int:
    load_media_modules()
    output_dir.mkdir(parents=True, exist_ok=True)
    install(bundle_root())
    import task.CczReRandTask as task_module

    save_path = (
        game_executable.parent / "SV" / f"SV{slot:03}.E5S"
    )
    if not save_path.is_file():
        raise FileNotFoundError(f"未找到结果存档 {save_path.name}")

    started_at = time.perf_counter()
    with HiddenGameSession(game_executable) as game:
        patch_inspection_runtime(
            task_module,
            game.pid,
            output_dir,
        )
        if not title_load_verified(game.pid, slot - 1, save_path):
            raise RuntimeError("结果存档未能完成后台读取")
        interruptible_sleep(0.8)
        runner = task_module.CczReRandTask(0)
        panels, members = capture_initial_member_panels(
            task_module,
            game.pid,
            game.main_window,
            runner,
        )

    panel_paths = []
    for index, panel in enumerate(panels):
        panel_path = output_dir / f"member-{index + 1}.png"
        write_cv_image(panel_path, panel)
        panel_paths.append(str(panel_path))
    diagnostic_log(
        "initial_member_inspection_completed",
        slot=slot,
        elapsed_seconds=round(time.perf_counter() - started_at, 3),
    )
    rules = load_rule_config(app_dir()).config
    skill_evaluation = evaluate_task_skill_rules(
        rules,
        task_module,
        members,
        job_score,
    )
    result = {
        "qualified": skill_evaluation.qualified,
        "reasons": list(skill_evaluation.reasons),
        "skills": [
            [skill.name for skill in member.skillList]
            for member in members
        ],
        "panels": panel_paths,
        "metrics": skill_evaluation.metrics,
    }
    (output_dir / "inspection.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0


def inspect_saved_slot(
    game_executable: Path,
    slot: int,
    output_dir: Path,
    job_score: float,
    member_index: int | None = None,
) -> int:
    output_dir = output_dir.resolve()
    started_at = time.perf_counter()
    game_for_diagnostics = None
    captured_names: set[str] = set()
    member_names: tuple[str, ...] = ()
    click_strategy = os.environ.get(
        "CCZ_INSPECTION_CLICK_STRATEGY",
        (
            "injected_background_mouse"
            if os.environ.get(
                "CCZ_INSPECTION_FORCE_INJECTED_STORY_CLICK"
            )
            == "1"
            else "post_message"
        ),
    )
    load_media_modules()
    output_dir.mkdir(parents=True, exist_ok=True)
    random_script = bundled_random_s00()
    original_script = bundled_original_s00()
    if not random_script.is_file() or not original_script.is_file():
        raise FileNotFoundError("工具内缺少随机流程辅助文件")
    manage_script = os.environ.get("CCZ_SKIP_S00") != "1"
    script_guard = (
        S00ScriptGuard(
            game_executable.parent,
            original_script,
            random_script,
        )
        if manage_script
        else None
    )
    repair_result = script_guard.prepare() if script_guard else None
    script_targets = (game_executable.parent / "RS" / "S_00.eex",)
    update_diagnostic_context(
        phase="inspection_prepare",
        result_slot=slot,
        inspection_mode="full",
        click_strategy=click_strategy,
    )
    diagnostic_log(
        "inspection_started",
        slot=slot,
        member_index=member_index,
        output_dir=str(output_dir),
        game_executable=file_diagnostic(game_executable),
        helper_script=file_diagnostic(random_script),
        script_targets=[
            file_diagnostic(target) for target in script_targets
        ],
        manage_script=manage_script,
        click_strategy=click_strategy,
        active_script_repaired=(
            repair_result.active_script_repaired if repair_result else False
        ),
        stale_helper_replaced=(
            repair_result.stale_helper_replaced
            if repair_result
            else False
        ),
    )
    try:
        if script_guard is not None:
            script_guard.install()
            diagnostic_log(
                "inspection_script_installed",
                targets=[
                    file_diagnostic(target) for target in script_targets
                ],
            )
        else:
            diagnostic_log(
                "inspection_script_install_skipped",
                reason="CCZ_SKIP_S00",
            )

        install(bundle_root())
        import task.CczReRandTask as task_module
        rules = load_rule_config(app_dir()).config
        diagnostic_log(
            "inspection_runtime_loaded",
            bundle_root=str(bundle_root()),
            active_rule=rules.get("activeProfile"),
        )

        if (
            member_index is None
            and os.environ.get("CCZ_PARALLEL_INSPECTION") == "1"
        ):
            processes = []
            env = os.environ.copy()
            env["CCZ_SKIP_S00"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            for index in range(TEAM_MEMBER_NUM):
                member_output = output_dir / f"worker-{index + 1}"
                if getattr(sys, "frozen", False):
                    command = [sys.executable]
                else:
                    command = [
                        sys.executable,
                        str(source_entry_path()),
                    ]
                command.extend(
                    [
                        "--inspect-slot",
                        str(slot),
                        "--inspect-member",
                        str(index),
                        "--inspect-output",
                        str(member_output),
                        "--game-executable",
                        str(game_executable),
                        "--job-score",
                        str(job_score),
                    ]
                )
                processes.append(
                    (
                        index,
                        member_output,
                        subprocess.Popen(
                            command,
                            cwd=str(game_executable.parent),
                            env=env,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            creationflags=getattr(
                                subprocess, "CREATE_NO_WINDOW", 0
                            ),
                        ),
                    )
                )
                time.sleep(0.35)
            worker_results = []
            for index, member_output, process in processes:
                try:
                    stdout, _ = process.communicate(timeout=150)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, _ = process.communicate()
                    raise RuntimeError(
                        f"第 {index + 1} 个武将检查超时"
                    )
                result_path = member_output / "member.json"
                if process.returncode != 0 or not result_path.is_file():
                    raise RuntimeError(
                        f"第 {index + 1} 个武将检查失败："
                        + decode_subprocess_output(stdout).strip()[-1200:]
                    )
                worker_results.append(
                    json.loads(result_path.read_text(encoding="utf-8"))
                )
            member_order = {
                member.name: index
                for index, member in enumerate(
                    task_module.TEAM_MEMBER_LIST
                )
            }
            result_names = [
                result["name"] for result in worker_results
            ]
            if set(result_names) != set(member_order):
                raise RuntimeError(
                    f"并行检查武将不完整：{result_names}"
                )
            worker_results.sort(
                key=lambda result: member_order[result["name"]]
            )
            job_ids = worker_results[0]["job_ids"]
            if any(result["job_ids"] != job_ids for result in worker_results):
                raise RuntimeError("并行检查读取到的兵种结果不一致")
            carry_names, strong_names, special_names = skill_name_groups(
                task_module
            )
            member_skills = {
                result["name"]: result["skills"]
                for result in worker_results
            }
            skill_evaluation = evaluate_skill_rules(
                rules,
                job_score,
                member_skills,
                carry_names,
                strong_names,
                special_names,
                [
                    skill
                    for result in worker_results
                    for skill in result["effective_skills"]
                ],
            )
            result = {
                "qualified": skill_evaluation.qualified,
                "reasons": list(skill_evaluation.reasons),
                "job_names": [
                    JOB_MAP[job_id][0] for job_id in job_ids
                ],
                "skills": [
                    worker_result["skills"]
                    for worker_result in worker_results
                ],
                "panels": [
                    worker_result["panel"]
                    for worker_result in worker_results
                ],
            }
            (output_dir / "inspection.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return 0

        save_path = (
            game_executable.parent / "SV" / f"SV{slot:03}.E5S"
        )
        if not save_path.is_file():
            raise FileNotFoundError(f"未找到候选存档 {save_path.name}")
        diagnostic_log(
            "inspection_candidate_ready",
            candidate_save=file_diagnostic(save_path),
        )

        with HiddenGameSession(game_executable) as game:
            game_for_diagnostics = game
            update_diagnostic_context(
                phase="inspection_game_started",
                game_pid=game.pid,
                game_hwnd=game.main_window,
            )
            diagnostic_log(
                "inspection_game_started",
                pid=game.pid,
                main_window=game.main_window,
                state=game_state_diagnostic(game.pid, game.main_window),
            )
            panels, click_info_button = patch_inspection_runtime(
                task_module, game.pid, output_dir
            )
            interruptible_sleep(1.2)
            update_diagnostic_context(phase="inspection_candidate_load")
            diagnostic_log(
                "inspection_candidate_load_started",
                pid=game.pid,
                slot=slot,
                candidate_save=file_diagnostic(save_path),
            )
            if not title_load_verified(game.pid, slot - 1, save_path):
                raise RuntimeError("候选存档未能完成后台读取")
            diagnostic_log(
                "inspection_candidate_load_verified",
                pid=game.pid,
                slot=slot,
                state=game_state_diagnostic(game.pid, game.main_window),
            )
            interruptible_sleep(0.8)
            before_jump_memory = read_memory(game.pid, 0, R0_MEMORY_SIZE)

            runner = task_module.CczReRandTask(0)
            runner.savePos = slot
            runner.initWind()
            update_diagnostic_context(phase="inspection_story_trigger")
            diagnostic_log(
                "inspection_randomized_candidate_confirmed",
                pid=game.pid,
                note="候选存档在主流程中已完成随机；检查流程不再选择随机选项",
            )
            acceleration_method = enable_game_acceleration(game.pid)
            diagnostic_log(
                "inspection_acceleration_enabled",
                pid=game.pid,
                key="z",
                method=acceleration_method,
                timing="before_story_trigger",
                note="进入剧情前启用加速",
            )
            trigger_seven_member_story(
                runner,
                game.pid,
                game.main_window,
                click_strategy=click_strategy,
            )
            native_wake_game(game.pid, game.main_window, 500)
            interruptible_sleep(0.3)
            update_diagnostic_context(phase="inspection_story_progress")
            accelerated = wait_for_seven_member_scene(game.pid)
            diagnostic_log(
                "inspection_accelerated_story_result",
                pid=game.pid,
                ready=accelerated,
                timeout_seconds=3.2,
            )
            if not accelerated:
                advance_seven_member_story(
                    game.pid,
                    game.main_window,
                )
            after_jump_path = output_dir / "after-jump.png"
            write_cv_image(
                after_jump_path,
                print_window_mat(game.main_window),
            )
            diagnostic_log(
                "inspection_story_progress_completed",
                pid=game.pid,
                screenshot=str(after_jump_path),
                state=game_state_diagnostic(game.pid, game.main_window),
            )
            update_diagnostic_context(phase="inspection_roster_open")
            diagnostic_log(
                "inspection_roster_open_started",
                pid=game.pid,
            )
            runner.openPeople()
            people_window_path = output_dir / "people-window.png"
            write_cv_image(
                people_window_path,
                print_window_mat(runner.peopleWind.hwnd),
            )
            diagnostic_log(
                "inspection_roster_opened",
                pid=game.pid,
                roster_hwnd=runner.peopleWind.hwnd,
                roster_initialized=runner.peopleWind.isInitSuccess(),
                screenshot=str(people_window_path),
                state=game_state_diagnostic(game.pid, game.main_window),
            )
            print(
                "候选检查窗口: "
                + "; ".join(
                    f"{window_class(hwnd)}|{window_text(hwnd)}"
                    for hwnd in process_windows(game.pid)
                )
            )
            job_ids = read_job_ids(game.pid, JOB_POSITIONS_R1)
            if any(job_id not in JOB_MAP for job_id in job_ids):
                raise RuntimeError(f"候选存档包含未知兵种编号：{job_ids}")
            diagnostic_log(
                "inspection_roster_snapshot",
                pid=game.pid,
                job_ids=list(job_ids),
                job_names=[JOB_MAP[job_id][0] for job_id in job_ids],
                windows=game_state_diagnostic(
                    game.pid, game.main_window
                ).get("windows", []),
            )
            for member, job_id in zip(
                task_module.TEAM_MEMBER_LIST, job_ids
            ):
                job_name, score, job_type = JOB_MAP[job_id]
                member.job = SimpleNamespace(
                    name=job_name,
                    score=score,
                    type=job_type,
                )
            memory_snapshot = read_skill_memory(
                game.pid,
                JOB_POSITIONS_R1,
            )
            memory_by_name = {
                member.name: memory_member
                for member, memory_member in zip(
                    task_module.TEAM_MEMBER_LIST,
                    memory_snapshot.members,
                )
            }
            members_to_read = (
                [
                    (
                        member_index,
                        task_module.TEAM_MEMBER_LIST[member_index],
                    )
                ]
                if member_index is not None
                else list(enumerate(task_module.TEAM_MEMBER_LIST))
            )
            member_names = tuple(
                item.name for item in task_module.TEAM_MEMBER_LIST
            )
            next_info_hwnd = 0
            next_shown_name = ""
            for index, member in members_to_read:
                requested_index = index
                if member_index is None and index > 0:
                    info_hwnd = next_info_hwnd
                    shown_name = next_shown_name
                else:
                    if (
                        not runner.peopleWind.hwnd
                        or not user32.IsWindow(runner.peopleWind.hwnd)
                    ):
                        runner.openPeople()
                    if not runner.peopleWind.isInitSuccess():
                        raise RuntimeError(
                            f"读取第 {index + 1} 个武将前，武将列表未能打开"
                        )
                    user32.EnableWindow(runner.peopleWind.hwnd, True)
                    runner.peopleWind.clickPeople(index)
                    info_hwnd = 0
                    shown_name = ""
                    deadline = time.perf_counter() + 10.0
                    while time.perf_counter() < deadline:
                        runner.initPeopleInfoWind()
                        info_hwnd, shown_name = find_any_member_dialog(
                            game.pid, member_names
                        )
                        if info_hwnd:
                            break
                        interruptible_sleep(0.05)
                if not info_hwnd:
                    diagnostic_log(
                        "inspection_member_open_failed",
                        pid=game.pid,
                        requested_index=requested_index,
                        captured_members=sorted(captured_names),
                        state=game_state_diagnostic(
                            game.pid, game.main_window
                        ),
                    )
                    raise RuntimeError(
                        f"第 {index + 1} 个武将能力窗口未能打开"
                    )
                member = next(
                    item
                    for item in task_module.TEAM_MEMBER_LIST
                    if item.name == shown_name
                )
                if member_index is None and member.name in captured_names:
                    raise RuntimeError(
                        f"重复读取武将能力面板：{member.name}"
                    )
                runner.peopleInfoWind._BaseWindow__hwnd = info_hwnd
                if not wait_for_window_state(
                    info_hwnd, exists=True, enabled=True, timeout=3.0
                ):
                    raise RuntimeError(
                        f"第 {index + 1} 个武将能力窗口不可用"
                    )
                if not wait_for_dialog_text(
                    info_hwnd, member.name, timeout=3.0
                ):
                    raise RuntimeError(
                        f"第 {index + 1} 个武将能力窗口人员不匹配"
                    )
                skill_list = []
                ui_slots = []
                for slot_index, skill_mat in enumerate(
                    runner.peopleInfoWind.getSkillMatList()
                ):
                    skill = task_module.CczUtils.getCczSkillWithMat(skill_mat)
                    ui_slots.append(
                        {
                            "slot": slot_index + 1,
                            "name": (
                                skill.name if skill is not None else None
                            ),
                        }
                    )
                    if skill is not None:
                        skill_list.append(skill)
                member.skillList = sorted(
                    skill_list,
                    key=lambda skill: skill.score,
                    reverse=True,
                )
                panel = runner.peopleInfoWind.getAllSkillMat()
                panels.append(panel.copy())
                captured_names.add(member.name)
                panel_index = (
                    member_names.index(member.name)
                    if member_index is None
                    else requested_index
                )
                write_cv_image(
                    output_dir / f"member-{panel_index + 1}.png",
                    panel,
                )
                diagnostic_log(
                    "inspection_member_captured",
                    pid=game.pid,
                    requested_index=requested_index,
                    panel_index=panel_index,
                    member=member.name,
                    job=member.job.name,
                    skills=[skill.name for skill in member.skillList],
                    captured_members=sorted(captured_names),
                    panel_path=str(
                        output_dir / f"member-{panel_index + 1}.png"
                    ),
                    info_hwnd=info_hwnd,
                )
                if member_index is not None:
                    memory_member = memory_by_name[member.name]
                    carry_count = 0
                    imba_count = 0
                    special_count = 0
                    effective_skills = effective_member_skill_names(
                        rules,
                        [member],
                    )
                    effective_remaining: dict[str, int] = {}
                    for effective_skill in effective_skills:
                        effective_remaining[effective_skill] = (
                            effective_remaining.get(effective_skill, 0) + 1
                        )
                    for skill in member.skillList:
                        if task_module.CczUtils.isSkillSpecial(skill):
                            special_count += 1
                        if not (
                            task_module.CczUtils.isSkillCarry(skill)
                            or task_module.CczUtils.isSkillImba(skill)
                        ):
                            continue
                        if effective_remaining.get(skill.name, 0) <= 0:
                            continue
                        effective_remaining[skill.name] -= 1
                        if task_module.CczUtils.isSkillImba(skill):
                            imba_count += 1
                        elif task_module.CczUtils.isSkillCarry(skill):
                            carry_count += 1
                    member_result = {
                        "index": requested_index,
                        "name": member.name,
                        "job_ids": job_ids,
                        "skills": [
                            skill.name for skill in member.skillList
                        ],
                        "ui_slots": ui_slots,
                        "memory_personal": [
                            {
                                "id": skill.internal_id,
                                "name": skill.display_name,
                                "base_name": skill.base_name,
                            }
                            for skill in memory_member.personal
                        ],
                        "memory_job": [
                            {
                                "id": skill.internal_id,
                                "name": skill.display_name,
                                "base_name": skill.base_name,
                            }
                            for skill in memory_member.job
                        ],
                        "panel": str(
                            output_dir / f"member-{panel_index + 1}.png"
                        ),
                        "carry_count": carry_count,
                        "imba_count": imba_count,
                        "special_count": special_count,
                        "effective_skills": effective_skills,
                    }
                    (output_dir / "member.json").write_text(
                        json.dumps(
                            member_result,
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                    return 0
                if len(captured_names) < TEAM_MEMBER_NUM:
                    diagnostic_log(
                        "member_transition_start",
                        pid=game.pid,
                        current_member=member.name,
                        captured_members=sorted(captured_names),
                        traversal_index=index,
                        hwnd=info_hwnd,
                    )
                    try:
                        if (
                            os.environ.get(
                                "CCZ_FORCE_ROSTER_FALLBACK"
                            )
                            == "1"
                        ):
                            diagnostic_log(
                                "member_transition_forced_roster_fallback",
                                pid=game.pid,
                                current_member=member.name,
                                captured_members=sorted(captured_names),
                            )
                            raise RuntimeError(
                                "测试模式强制使用武将列表备用路径"
                            )
                        (
                            next_info_hwnd,
                            next_shown_name,
                        ) = advance_people_info_in_game_order(
                            game.pid,
                            info_hwnd,
                            member.name,
                            member_names,
                            captured_names,
                        )
                    except RuntimeError as transition_error:
                        if (
                            os.environ.get(
                                "CCZ_DISABLE_ROSTER_FALLBACK"
                            )
                            == "1"
                        ):
                            raise
                        diagnostic_log(
                            "member_transition_roster_fallback",
                            pid=game.pid,
                            current_member=member.name,
                            captured_members=sorted(captured_names),
                            traversal_index=index,
                            hwnd=info_hwnd,
                            error=repr(transition_error),
                        )
                        try:
                            (
                                next_info_hwnd,
                                next_shown_name,
                            ) = open_uncaptured_member_from_roster(
                                game.pid,
                                game.main_window,
                                runner,
                                info_hwnd,
                                member_names,
                                captured_names,
                            )
                        except RuntimeError as roster_error:
                            diagnostic_log(
                                "member_roster_fallback_failed",
                                pid=game.pid,
                                current_member=member.name,
                                captured_members=sorted(captured_names),
                                traversal_index=index,
                                error=repr(roster_error),
                                state=game_state_diagnostic(
                                    game.pid, game.main_window
                                ),
                            )
                            raise
                    diagnostic_log(
                        "member_transition_succeeded",
                        pid=game.pid,
                        current_member=member.name,
                        shown_member=next_shown_name,
                        traversal_index=index + 1,
                        hwnd=next_info_hwnd,
                    )
            if (
                len(panels) != TEAM_MEMBER_NUM
                or captured_names != set(member_names)
            ):
                raise RuntimeError(
                    f"武将能力面板读取不完整：{sorted(captured_names)}"
                )
            skill_evaluation = evaluate_task_skill_rules(
                rules,
                task_module,
                task_module.TEAM_MEMBER_LIST,
                job_score,
            )
            result = {
                "qualified": skill_evaluation.qualified,
                "reasons": list(skill_evaluation.reasons),
                "job_names": [
                    JOB_MAP[job_id][0] for job_id in job_ids
                ],
                "skills": [
                    [skill.name for skill in member.skillList]
                    for member in task_module.TEAM_MEMBER_LIST
                ],
                "panels": [
                    str(output_dir / f"member-{index}.png")
                    for index in range(1, TEAM_MEMBER_NUM + 1)
                ],
                "metrics": skill_evaluation.metrics,
            }
            if member_index is None:
                evidence_path = write_skill_evidence(
                    output_dir / "skill-evidence.zip",
                    candidate_save=save_path.read_bytes(),
                    before_jump_memory=before_jump_memory,
                    after_render_memory=read_memory(
                        game.pid,
                        0,
                        R0_MEMORY_SIZE,
                    ),
                    metadata={
                        "slot": slot,
                        "job_ids": list(job_ids),
                        "job_names": result["job_names"],
                        "skills": result["skills"],
                        "qualified": result["qualified"],
                    },
                )
                result["skill_evidence"] = str(evidence_path)
            (output_dir / "inspection.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            diagnostic_log(
                "inspection_completed",
                slot=slot,
                qualified=result["qualified"],
                captured_members=sorted(captured_names),
                job_names=result["job_names"],
                result_path=str(output_dir / "inspection.json"),
                elapsed_seconds=round(
                    time.perf_counter() - started_at, 3
                ),
            )
        return 0
    except Exception as exc:
        initial_member_names = {member[0] for member in INITIAL_TEAM_MEMBERS}
        category = (
            "story_not_triggered_or_incomplete"
            if captured_names
            and captured_names.issubset(initial_member_names)
            and len(captured_names) <= len(initial_member_names)
            else "inspection_failure"
        )
        persisted_screenshot = persist_inspection_failure_screenshot(
            output_dir,
            category=category,
            slot=slot,
        )
        diagnostic_error(
            "inspection_failed",
            exc,
            game=game_for_diagnostics,
            slot=slot,
            category=category,
            click_strategy=click_strategy,
            captured_members=sorted(captured_names),
            expected_members=list(member_names),
            elapsed_seconds=round(time.perf_counter() - started_at, 3),
            screenshots={
                "after_jump": str(output_dir / "after-jump.png"),
                "people_window": str(output_dir / "people-window.png"),
                "persisted": persisted_screenshot,
            },
        )
        raise
    finally:
        if script_guard is not None:
            script_guard.restore()
        diagnostic_log(
            "inspection_script_restored",
            targets=[
                file_diagnostic(target) for target in script_targets
            ],
            elapsed_seconds=round(time.perf_counter() - started_at, 3),
        )


def patch_runtime(task_module, pid: int, three_person_mode: bool = False,
                  rules: dict | None = None, game_executable: Path | None = None) -> None:
    from ccz_randomizer.runtime.game_adapter import patch_runtime as install_adapter
    return install_adapter(task_module, pid, three_person_mode, rules, game_executable,
                           services=sys.modules[__name__])



def format_user_log(line: str) -> str:
    """Reduce the worker trace to user-facing progress information."""
    text = line.strip()
    if not text:
        return ""
    worker_match = re.match(r"^\[实例 (\d+)\]\s*(.*)$", text)
    if worker_match:
        formatted = format_user_log(worker_match.group(2))
        return (
            f"[实例 {worker_match.group(1)}] {formatted}"
            if formatted
            else ""
        )
    if text.startswith("工具版本："):
        return ""
    if text.startswith("环境处理提示："):
        return text.removeprefix("环境处理提示：").strip()
    if (
        text.startswith("R0 七人兵种筛选:")
        or text.startswith("R0 三人兵种筛选:")
    ):
        members, result = text.split("; 结果=", 1)
        members = members.split(":", 1)[1]
        return members.replace("; ", "，").strip()
    if "R1 特技内存快筛:" in text:
        return "" if text.endswith("通过") else "特技筛选：不合格"
    if text.startswith("用户进度:"):
        return ""
    if text.startswith("规则原因:"):
        return ""
    if text.startswith("规则提示："):
        return text
    if text.startswith("循环轮次开始："):
        return "\n" + text.replace("循环轮次开始：", "开始")
    if text.startswith("循环轮次完成："):
        return text.replace("循环轮次完成：", "")
    if text.startswith("循环轮次未完成结果："):
        return text.replace("循环轮次未完成结果：", "未完成结果已保留：")
    if text.startswith("循环轮次结果目录："):
        return ""
    if text.startswith("R1 七人特技内存读取:"):
        return "正在检查特技条件……"
    if text.startswith("所选人物兵种筛选通过，正在检查特技条件"):
        return "正在检查特技条件……"
    if text.startswith("========== 结果 "):
        parts = text.strip("= ").split("，", 1)
        attempt = parts[1].replace("原生随机第 ", "第 ").replace(
            " 轮", " 次尝试"
        )
        return f"\n{parts[0].replace('结果', '存档')}｜{attempt}"
    if "原生随机内存快筛流程 start" in text:
        return "正在执行随机流程……"
    if text.startswith("游戏原生随机已触发:"):
        return ""
    if text.startswith("第 ") and (
        "已由游戏原生保存" in text
        or "已通过游戏菜单保存" in text
    ):
        prefix = text.split("号", 1)[0] if "号" in text else text
        return f"{prefix}号存档已保存"
    if text.startswith(
        (
            "当前设备不兼容后台快速读档",
            "兼容模式：正在刷新后台游戏实例",
        )
    ):
        return ""
    if (
        text.startswith("第 ")
        and (
            "号存档已保存，但结果图生成失败" in text
        )
    ):
        return ""
    if text.startswith("宝物内存读取完成"):
        return ""
    if text.startswith("随机兵种已更新:"):
        return "随机结果已更新"
    if text.startswith("后台随机尝试"):
        return "正在触发随机……"
    if text.startswith(
        (
            "候选存档已由游戏原生保存",
            "候选存档已通过游戏菜单保存",
        )
    ):
        return ""
    if "平均分=" in text or "门槛=" in text:
        return ""
    if text.startswith("游戏将在独立后台桌面运行"):
        return "游戏将在后台运行，不占用当前鼠标和前台"
    if text.startswith("隐藏游戏实例已重新启动"):
        return "后台游戏异常，已重新启动"
    if text.startswith("隐藏游戏实例已启动"):
        return "后台游戏已启动"
    if text.startswith("游戏原生随机已触发"):
        return "已完成一次随机"
    if "个结果存档已全部保存；其中" in text:
        return text
    if text.startswith("Traceback"):
        return ""
    if text.startswith("  File "):
        return ""
    if text.startswith(("曹操传加强版", "默认生成", "游戏将在", "日志:", "本轮结果目录", "本轮总图路径")):
        return ""
    return ""


def activate_rule_profile(
    base_dir: Path,
    config: dict,
    profile_name: str,
) -> dict:
    updated = json.loads(json.dumps(config, ensure_ascii=False))
    if profile_name not in updated.get("profiles", {}):
        raise ValueError(f"规则不存在：{profile_name}")
    updated["activeProfile"] = profile_name
    normalized = validate_rule_config(updated)
    save_rule_config(base_dir, normalized)
    return normalized


def session_failure_requires_restart(
    game: HiddenGameSession, exc: BaseException
) -> bool:
    if isinstance(exc, InteractionNotTriggered):
        return True
    if not game.is_healthy():
        return True
    if isinstance(exc, InspectionProcessError):
        # Inspection runs in its own game process. Restarting the healthy
        # randomization process cannot repair an inspection-only failure.
        return False
    if isinstance(exc, NativeControlError):
        if "ntstatus=0xc000010a" in exc.details.casefold():
            return True
        # Restarting cannot change an OS or security-product policy.
        return exc.return_code not in {3, 4, 5, 6, 7, 8, 9, 10}
    if isinstance(exc, OSError) and getattr(exc, "winerror", None) in {299}:
        return True
    if not isinstance(exc, RuntimeError):
        return False
    message = str(exc)
    if any(
        text in message
        for text in (
            "已经包含随机结果",
            "不能作为源存档",
            "源存档在随机过程中被修改",
            "与保存时游戏内存不一致",
            "R0 原生保存与内存不一致",
        )
    ):
        return False
    return any(
        text in message
        for text in (
            "未找到游戏主窗口",
            "静默控件模块",
            "源存档读取失败",
            "后台读取",
            "连续 3 次点击许子将",
            "游戏原生保存",
            "读取进度窗口未出现",
            "静默游戏实例",
        )
    )


CURRENT_RUN_RULE_NOTICE = (
    "当前随机仍使用开始时的规则，新规则将在下次开始随机时生效。"
)


def serialize_rule_profile(profile: dict) -> str:
    return json.dumps(
        profile,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def current_run_rule_save_notice(
    config: dict,
    running_rule_name: str | None,
    running_rule_snapshot: str | None,
) -> str | None:
    if not running_rule_name or running_rule_snapshot is None:
        return None
    saved_profile = config.get("profiles", {}).get(running_rule_name)
    if saved_profile is None:
        return CURRENT_RUN_RULE_NOTICE
    if serialize_rule_profile(saved_profile) != running_rule_snapshot:
        return CURRENT_RUN_RULE_NOTICE
    return None


def gui_main() -> int:
    import tkinter as tk
    from tkinter import ttk
    from ccz_randomizer.ui import scrolled_text as scrolledtext
    from ccz_randomizer.ui import messages as messagebox
    from ccz_randomizer.ui.theme import FONT, setup_theme
    from ccz_randomizer.ui.inputs import TextEntry
    from ccz_randomizer.ui.searchable_combo import SelectionCombobox

    root = tk.Tk()
    root.withdraw()
    root.attributes("-alpha", 0.0)
    setup_theme(root)
    os.environ.setdefault("CCZ_GAME_VERSION", APP_DEFAULT_GAME_VERSION)
    try:
        activate_game_version(locate_game_executable())
    except (OSError, ValueError):
        pass  # Starting a run repeats file/environment checks and reports real failures.
    # Keep the product title stable across the night/build flavour; the
    # detailed game fingerprint remains available in diagnostics and logs.
    root.title("曹操传随机工具 · 2.20")
    root.geometry("980x680")
    root.minsize(760, 520)

    worker: subprocess.Popen[str] | None = None
    from ccz_randomizer.sleep_guard import SleepGuard
    sleep_guard = SleepGuard()
    running_rule_name: str | None = None
    running_rule_snapshot: str | None = None
    # Keep one queue per run.  A bounded queue provides back-pressure when a
    # worker emits a burst while Tk is busy rendering, and replacing it at the
    # start of a run prevents late lines from a stopped reader leaking into a
    # subsequent run.
    output_queue: queue.Queue[str] = queue.Queue(maxsize=20000)
    log_path: Path | None = None
    result_image_path: Path | None = None
    run_started_at = 0.0
    stop_file: Path | None = None
    active_game_executable: Path | None = None
    stop_requested_by_user = False
    last_formatted_line = ""
    security_blocked_details: dict[str, object] | None = None
    concurrent_console_state: ConcurrentConsoleState | None = None
    concurrent_console_rounds: dict[int, ConcurrentConsoleState] = {}
    concurrent_console_round_images: dict[int, Path] = {}
    concurrent_console_active_round = 1
    concurrent_console_finished = False
    concurrent_console_footer = ""
    concurrent_console_render_pending = False
    concurrent_console_last_render_at = 0.0
    concurrent_console_last_signature: tuple | None = None
    loop_var = tk.BooleanVar(value=load_loop_random(app_dir()))
    prevent_sleep_var = tk.BooleanVar(value=load_prevent_sleep(app_dir()))
    concurrency_var = tk.IntVar(value=load_concurrency(app_dir()))
    compatibility_mode_var = tk.BooleanVar(
        value=load_compatibility_mode(app_dir())
    )
    rule_load = load_rule_config(app_dir())
    current_rules = rule_load.config
    root._current_rule_profile = lambda: active_profile(current_rules)
    rule_profile_var = tk.StringVar(
        value=current_rules["activeProfile"]
    )

    def show_first_use_notice() -> None:
        if first_use_notice_acknowledged(app_dir()):
            return
        from ccz_randomizer.ui.first_use import show_first_use_prompt
        show_first_use_prompt(root,
            acknowledge=lambda: acknowledge_first_use_notice(app_dir()),
            on_beginner=start_onboarding,
            on_save_failed=lambda: messagebox.showwarning(
                "已读状态保存失败",
                "本机用户目录和游戏目录均无法保存已读状态。本次可继续使用，下次启动仍会显示提醒。",
                parent=root),
            on_exit=root.destroy)

    def selected_rule_member_count() -> int:
        """Return the number of people used by the active job filter rule."""
        try:
            profile = active_profile(current_rules)
            members = profile.get("threePerson", {}).get("qualifiedMembers", ())
            return len(tuple(member for member in members if str(member).strip()))
        except (AttributeError, TypeError):
            return 0

    outer = tk.Frame(root, padx=14, pady=12)
    outer.pack(fill="both", expand=True)

    info = tk.Frame(outer)
    info.pack(fill="x", pady=(0, 10))
    header = tk.Frame(info)
    header.pack(fill="x")
    version = str(application_build_info().get("version", "")).strip()
    from ccz_randomizer.ui.profile_status import ProfileStatus, ProfileStatusBadge
    from ccz_randomizer.profile_session import ProfileUpdateSession
    profile_badge = ProfileStatusBadge(header, ProfileStatus("checking", load_profile().manifest["catalogVersion"]))
    profile_badge.pack(side="right", padx=(0, 2))
    version_label = tk.Label(
        header,
        text=f"V{version}" if version else "",
        font=("Microsoft YaHei UI", 10),
        anchor="e",
        fg="#666666",
    )
    version_label.pack(side="right", padx=(12, 0))
    bind_version_changelog(version_label, root)

    def profile_activated():
        root.event_generate("<<RulesUpdated>>", when="tail")
        for window in root.winfo_children():
            if isinstance(window, tk.Toplevel):
                window.event_generate("<<ProfileUpdated>>", when="tail")

    profile_session = ProfileUpdateSession(root, application_directory(),
        is_idle=lambda: worker is None or worker.poll() is not None,
        display=profile_badge.set_status,
        notify=lambda text: show_toast(root, text, 4500),
        log_error=lambda error: diagnostic_error("profile_auto_update_failed", error),
        on_activated=profile_activated)
    help_popup: tk.Toplevel | None = None
    help_image: tk.PhotoImage | None = None

    tk.Label(
        header,
        text="请将本工具放置到游戏目录下，双击运行。",
        justify="left",
        anchor="w",
        fg="#444444",
    ).pack(side="left")
    first_line = tk.Frame(info)
    first_line.pack(fill="x", anchor="w")
    tk.Label(
        first_line,
        text="开始前请确认：已在许子将处完成配置，并将配置后的存档保存到",
        anchor="w",
        fg="#444444",
    ).pack(side="left")
    slot_help = tk.Label(
        first_line,
        text="第20栏",
        anchor="w",
        fg="#0563c1",
        cursor="hand2",
    )
    slot_help.pack(side="left")
    tk.Label(
        first_line,
        text="。",
        anchor="w",
        fg="#444444",
    ).pack(side="left")
    result_line = tk.Frame(info)
    result_line.pack(fill="x", anchor="w")
    tk.Label(
        result_line,
        text="合格结果会生成结果图并保存在 ",
        justify="left",
        anchor="w",
        fg="#444444",
    ).pack(side="left")
    result_dir_help = tk.Label(
        result_line,
        text="randResult",
        anchor="w",
        fg="#0563c1",
        cursor="hand2",
        underline=True,
    )
    result_dir_help.pack(side="left")
    tk.Label(result_line, text=" 目录。", anchor="w", fg="#444444").pack(side="left")

    def open_result_directory(_event=None) -> None:
        result_dir = Path(application_directory()) / "randResult"
        try:
            result_dir.mkdir(parents=True, exist_ok=True)
            os.startfile(str(result_dir))
        except OSError as exc:
            messagebox.showerror("无法打开结果目录", str(exc), parent=root)

    result_dir_help.bind("<Button-1>", open_result_directory)

    def show_slot_help(_event=None) -> None:
        nonlocal help_popup, help_image
        if help_popup is not None and help_popup.winfo_exists():
            return
        image_path = ui_asset_path("source_slot_20_help.png")
        if not image_path.is_file():
            return
        help_popup = tk.Toplevel(root)
        help_popup.overrideredirect(True)
        help_popup.attributes("-topmost", True)
        help_popup.configure(bg="#777777", padx=1, pady=1)
        help_image = tk.PhotoImage(file=str(image_path))
        tk.Label(
            help_popup,
            image=help_image,
            borderwidth=0,
        ).pack()
        help_popup.update_idletasks()
        x = slot_help.winfo_rootx()
        y = slot_help.winfo_rooty() + slot_help.winfo_height() + 4
        width = help_popup.winfo_reqwidth()
        height = help_popup.winfo_reqheight()
        x = min(x, root.winfo_screenwidth() - width - 8)
        y = min(y, root.winfo_screenheight() - height - 8)
        help_popup.geometry(f"+{max(8, x)}+{max(8, y)}")

    def hide_slot_help(_event=None) -> None:
        nonlocal help_popup, help_image
        if help_popup is not None:
            help_popup.destroy()
            help_popup = None
            help_image = None

    slot_help.bind("<Enter>", show_slot_help)
    slot_help.bind("<Leave>", hide_slot_help)

    settings_panel = tk.Frame(outer)
    settings_panel.pack(fill="x", pady=(0, 6))

    def persist_runtime_settings(_event=None) -> None:
        try:
            save_random_runtime_settings(
                app_dir(),
                loop_random=bool(loop_var.get()),
                concurrency=int(concurrency_var.get()),
                compatibility_mode=bool(compatibility_mode_var.get()),
                prevent_sleep=bool(prevent_sleep_var.get()),
            )
        except (OSError, ValueError, TypeError, tk.TclError):
            show_toast(root, "运行参数保存失败，请检查输入和工具目录。")

    runtime_settings_bar = tk.Frame(settings_panel)
    runtime_settings_bar.pack(fill="x")
    tk.Label(runtime_settings_bar, text="运行参数").pack(
        side="left", padx=(0, 8)
    )
    loop_check = ttk.Checkbutton(
        runtime_settings_bar,
        text="循环随机（每轮15个）",
        variable=loop_var,
        command=persist_runtime_settings,
    )
    loop_check.pack(side="left", padx=(0, 18))
    tk.Label(runtime_settings_bar, text="实例并发").pack(
        side="left", padx=(0, 4)
    )
    concurrency_entry = TextEntry(
        runtime_settings_bar,
        width=7,
        textvariable=concurrency_var,
        justify="center",
    )
    concurrency_entry.pack(side="left", padx=(0, 18))
    concurrency_entry.bind("<FocusOut>", persist_runtime_settings)
    concurrency_entry.bind("<Return>", persist_runtime_settings)
    compatibility_check = ttk.Checkbutton(
        runtime_settings_bar,
        text="兼容模式",
        variable=compatibility_mode_var,
        command=persist_runtime_settings,
    )
    compatibility_check.pack(side="left")
    prevent_sleep_check = ttk.Checkbutton(
        runtime_settings_bar, text="阻止系统睡眠",
        variable=prevent_sleep_var, command=persist_runtime_settings,
    )
    prevent_sleep_check.pack(side="left", padx=(16, 0))
    from ccz_randomizer.ui.experimental import experimental_tooltip
    experimental_tooltip(prevent_sleep_check,
        "仅在随机运行期间阻止因空闲自动睡眠，屏幕仍可正常熄灭。"
        "结束、停止或退出后恢复；不阻止手动睡眠、合盖或低电量保护。"
        )

    rule_settings_bar = tk.Frame(settings_panel)
    rule_settings_bar.pack(fill="x")
    tk.Label(rule_settings_bar, text="规则").pack(
        side="left",
        padx=(0, 6),
    )
    rule_profile_combo = SelectionCombobox(
        rule_settings_bar,
        search_label="搜索规则",
        textvariable=rule_profile_var,
        values=tuple(current_rules["profiles"]),
        state="readonly",
        width=24,
    )
    rule_profile_combo.pack(side="left", padx=(0, 8))
    rule_button = ttk.Button(rule_settings_bar, text="规则设置")
    rule_button.pack(side="left")
    recruit_button = ttk.Button(
        rule_settings_bar, text="历史记录", command=lambda: open_history()
    )
    recruit_button.pack(side="left", padx=(8, 0))
    from ccz_randomizer.ui.statistics import show_statistics_window
    statistics_button = ttk.Button(
        rule_settings_bar, text="数据统计",
        command=lambda: show_statistics_window(root, app_dir()),
    )
    statistics_button.pack(side="left", padx=(8, 0))
    experimental_tooltip(statistics_button,
        "查看随机次数、评分分布，以及兵种、特技和宝物特效的出现频率。")
    from ccz_randomizer.ui.effect_dictionary import show_effect_dictionary
    effects_button = ttk.Button(
        rule_settings_bar, text="特效手册", command=lambda: show_effect_dictionary(root)
    )
    effects_button.pack(side="left", padx=(8, 0))
    repair_button = ttk.Button(
        rule_settings_bar,
        text="常见问题",
    )
    repair_button.pack(side="left", padx=(8, 0))
    action_button = ttk.Button(
        rule_settings_bar,
        text="开始随机", style="Primary.TButton",
    )
    action_button.pack(side="right", padx=(8, 0))
    # ttk's default minimum width leaves excessive space around short CJK labels.
    for button in (rule_button, recruit_button, statistics_button, effects_button,
                   repair_button, action_button):
        button.configure(width=-1)

    def fit_rule_picker(event) -> None:
        # Keep the primary action readable at the supported minimum width.
        width = 14 if event.width < 850 else 24
        if int(rule_profile_combo.cget("width")) != width:
            rule_profile_combo.configure(width=width)
    rule_settings_bar.bind("<Configure>", fit_rule_picker)

    output = scrolledtext.ScrolledText(
        outer,
        # Chinese personnel lists have no whitespace boundary. Character
        # wrapping keeps expanded progress lines visible instead of clipping
        # the tail beyond the right edge of the window.
        wrap="char",
        font=(FONT, 10),
        state="disabled",
        bg="#fafafa",
        relief="solid",
        borderwidth=1,
    )
    output.pack(fill="both", expand=True)
    from ccz_randomizer.ui.text_links import TextLinks
    output_links = TextLinks(output)

    def split_names(value: str) -> list[str]:
        normalized = value.replace("，", ",").replace("；", ",")
        normalized = normalized.replace(";", ",").replace("\n", ",")
        return list(
            dict.fromkeys(
                item.strip() for item in normalized.split(",") if item.strip()
            )
        )

    def join_names(values) -> str:
        return "，".join(values)

    def open_rule_editor() -> None:
        def rules_saved(config: dict) -> None:
            nonlocal current_rules
            current_rules = config
            rule_profile_combo.configure(
                values=tuple(config["profiles"])
            )
            rule_profile_var.set(config["activeProfile"])
            root.event_generate("<<RulesUpdated>>", when="tail")

        def save_notice(config: dict) -> str | None:
            if worker is None or worker.poll() is not None:
                return None
            return current_run_rule_save_notice(
                config,
                running_rule_name,
                running_rule_snapshot,
            )

        show_rule_editor(
            root,
            app_dir(),
            current_rules,
            JOB_MAP,
            INITIAL_TEAM_MEMBERS,
            skill_score_catalog(),
            rules_saved,
            save_notice,
        )

    from ccz_randomizer.ui.sound_repair import create_sound_repair
    repair_game_sound = create_sound_repair(root, sys.modules[__name__])

    def open_storage_cleanup(parent: tk.Misc = root) -> None:
        from ccz_randomizer.ui.storage_cleanup import show_storage_cleanup
        show_storage_cleanup(
            parent, app_dir(),
            is_running=lambda: worker is not None and worker.poll() is None,
        )

    from ccz_randomizer.ui.support_controller import create_support_actions
    open_log_upload_progress, upload_latest_logs, open_unusable_diagnostics = create_support_actions(
        root, sys.modules[__name__])

    def start_onboarding() -> None:
        from ccz_randomizer.ui.onboarding import show_onboarding
        from ccz_randomizer.ui.usage_guide import show_usage_guide
        show_onboarding(outer, before=settings_panel, targets={
            "source": first_line, "rules": rule_profile_combo, "rule_editor": rule_button,
            "runtime": runtime_settings_bar, "start": action_button,
            "results": result_line, "history": recruit_button,
            "statistics": statistics_button, "help": repair_button,
            "effects": effects_button,
        }, open_help=show_usage_guide)

    def replay_onboarding(parent) -> None:
        # Return to the real main controls; don't leave a hidden modal menu.
        parent.destroy()
        start_onboarding()

    def open_repair_dialog() -> None:
        from ccz_randomizer.ui.audio_patch import show_audio_patch
        from ccz_randomizer.ui.growth_patch import show_growth_patch
        from ccz_randomizer.ui.usage_guide import show_usage_guide
        from ccz_randomizer.ui.support_menu import show_support_menu
        from ccz_randomizer.ui.effect_dictionary import show_effect_dictionary
        try:
            package_version = profile_version_label(application_directory())
        except Exception:
            package_version = "未知"
        show_support_menu(root, {
            "guide": show_usage_guide,
            "onboarding": replay_onboarding,
            "effects": show_effect_dictionary,
            "diagnostics": open_unusable_diagnostics,
            "sound": repair_game_sound,
            "growth_patch": lambda parent: show_growth_patch(parent, sys.modules[__name__],
                is_running=lambda: worker is not None and worker.poll() is None),
            "audio_patch": lambda parent: show_audio_patch(parent, sys.modules[__name__]),
            "logs": upload_latest_logs,
            "update": lambda parent: show_profile_update_dialog(parent, application_directory(), on_installed=profile_session.downloaded),
            "cleanup": open_storage_cleanup,
        }, package_version)

    def open_history() -> None:
        show_history_window(root, app_dir())

    def select_rule_profile(_event=None) -> None:
        nonlocal current_rules
        selected = rule_profile_var.get()
        previous = current_rules["activeProfile"]
        if selected == previous:
            return
        try:
            updated = activate_rule_profile(
                app_dir(),
                current_rules,
                selected,
            )
        except Exception as exc:
            rule_profile_var.set(previous)
            messagebox.showerror(
                "规则无法切换",
                f"无法使用所选规则。\n\n{exc}",
                parent=root,
            )
            return
        current_rules = updated
        root.event_generate("<<RulesUpdated>>", when="tail")

    def append(text: str) -> None:
        if not text:
            return
        output.configure(state="normal")
        output.insert("end", text + "\n")
        if trim_text_widget(output):
            output_links.prune()
        output.see("end")
        output.configure(state="disabled")

    def show_result_detail(detail: dict) -> None:
        from ccz_randomizer.ui.result_details import show_score_detail
        show_score_detail(root, detail)

    def show_concurrent_slot_detail(
        round_number: int,
        slot: int,
    ) -> None:
        from ccz_randomizer.ui.window_timer import window_after
        round_state = concurrent_console_rounds.get(round_number)
        if round_state is None or slot not in round_state.slots:
            return
        progress = round_state.slots[slot]
        dialog = centered_toplevel(root)
        dialog.title(f"存档{slot}运行明细")
        dialog.geometry("760x600")
        dialog.minsize(620, 440)
        dialog.transient(root)

        body = tk.Frame(dialog, padx=18, pady=16)
        body.pack(fill="both", expand=True)
        tk.Label(
            body,
            text=f"存档{slot}运行明细",
            font=("Microsoft YaHei UI", 13, "bold"),
            anchor="w",
        ).pack(fill="x")
        status_var = tk.StringVar()
        tk.Label(
            body,
            textvariable=status_var,
            font=("Microsoft YaHei UI", 10),
            fg="#555555",
            anchor="w",
        ).pack(fill="x", pady=(5, 12))

        history_text = scrolledtext.ScrolledText(
            body,
            wrap="word",
            font=("Microsoft YaHei UI", 10),
            bg="#ffffff",
            relief="solid",
            borderwidth=1,
            padx=12,
            pady=10,
        )
        history_text.pack(fill="both", expand=True)
        history_text.configure(state="disabled")

        actions = tk.Frame(body)
        actions.pack(fill="x", pady=(12, 0))
        ttk.Button(
            actions,
            text="关闭",
            width=10,
            command=dialog.destroy,
        ).pack(side="right")
        dialog.update_idletasks()
        displayed_history: tuple[object, ...] | None = None
        refresh_delay = 0.25

        def refresh_detail() -> None:
            nonlocal displayed_history, refresh_delay
            try:
                if not dialog.winfo_exists():
                    return
            except tk.TclError:
                return
            current_state = concurrent_console_rounds.get(round_number)
            if current_state is None or slot not in current_state.slots:
                return
            current = current_state.slots[slot]
            current_attempt = (
                f"第 {current.attempt} 次尝试"
                if current.attempt
                else "尚未开始尝试"
            )
            status_var.set(f"{current_attempt}　{current.stage}")
            attempt_signature = tuple(
                (
                    item.attempt,
                    item.member_summary,
                    (
                        item.detail.get("status"),
                        item.detail.get("label"),
                    )
                    if item.detail is not None
                    else None,
                )
                for item in current.attempts
            )
            display_signature = attempt_signature + (
                current.attempt,
                current.stage,
            )
            if display_signature != displayed_history:
                refresh_delay = 0.25
                displayed_history = display_signature
                history_text.configure(state="normal")
                history_text.delete("1.0", "end")
                history_text.tag_configure(
                    "attempt-heading",
                    font=("Microsoft YaHei UI", 10, "bold"),
                    spacing1=4,
                    spacing3=5,
                )
                if not current.attempts:
                    history_text.insert("end", "该存档尚未开始尝试。")
                for index, attempt in enumerate(
                    current.attempts,
                    start=1,
                ):
                    history_text.insert(
                        "end",
                        f"第 {attempt.attempt} 次尝试\n",
                        "attempt-heading",
                    )
                    if attempt.member_summary:
                        history_text.insert(
                            "end",
                            attempt.member_summary + "\n",
                        )
                    if attempt.detail is not None:
                        label = attempt.detail.get("label") or "未知"
                        history_text.insert("end", f"结果：{label}（")
                        tag = f"slot-score-{round_number}-{slot}-{index}"
                        history_text.insert("end", "点击查看详情", tag)
                        history_text.insert("end", "）\n\n")
                        history_text.tag_configure(
                            tag,
                            foreground="#0563c1",
                            underline=True,
                        )
                        history_text.tag_bind(
                            tag,
                            "<Button-1>",
                            lambda _event, value=attempt.detail: (
                                show_result_detail(value)
                            ),
                        )
                        history_text.tag_bind(
                            tag,
                            "<Enter>",
                            lambda _event: history_text.configure(
                                cursor="hand2"
                            ),
                        )
                        history_text.tag_bind(
                            tag,
                            "<Leave>",
                            lambda _event: history_text.configure(cursor=""),
                        )
                    elif attempt.attempt == current.attempt:
                        history_text.insert(
                            "end",
                            current.stage + "\n\n",
                        )
                    else:
                        history_text.insert("end", "等待结果\n\n")
                history_text.see("end")
                history_text.configure(state="disabled")
            else:
                # Keep the dialog responsive while active, but avoid waking
                # the Tk loop four times a second when nothing changed.
                refresh_delay = min(1.0, refresh_delay * 1.5)
            window_after(dialog, int(refresh_delay * 1000), refresh_detail)

        refresh_detail()
        show_centered(dialog)

    def recover_concurrent_result_image() -> Path | None:
        """Recover the latest image published by the current run.

        The worker can exit immediately after writing the image marker.  In
        that case the reader thread may not have delivered the marker before
        the GUI handles process exit, so use the result directory as the
        durable source of truth as well.
        """
        nonlocal result_image_path
        if result_image_path is not None and result_image_path.is_file():
            return result_image_path
        # During an active run only an explicit worker marker is authoritative;
        # directory recovery is reserved for the process-exit race.
        if worker is not None and not concurrent_console_finished:
            return None
        if run_started_at <= 0:
            return None
        try:
            executable = active_game_executable or locate_game_executable()
        except (FileNotFoundError, OSError, RuntimeError):
            return None
        result_root = executable.parent / "randResult"
        try:
            candidates = [
                path
                for path in result_root.glob("*-random.png")
                if path.is_file()
                and path.stat().st_mtime >= run_started_at - 5
            ]
        except (OSError, ValueError):
            return None
        if not candidates:
            return None
        try:
            result_image_path = max(
                candidates,
                key=lambda path: path.stat().st_mtime,
            )
        except OSError:
            return None
        if concurrent_console_state is not None:
            concurrent_console_round_images.setdefault(
                concurrent_console_active_round,
                result_image_path,
            )
        return result_image_path

    def render_concurrent_console(*, force: bool = False) -> bool:
        nonlocal concurrent_console_render_pending
        nonlocal concurrent_console_last_render_at
        nonlocal concurrent_console_last_signature
        if concurrent_console_state is None:
            concurrent_console_render_pending = False
            return False
        # Recover before computing the signature so the image link is rendered
        # even when the marker arrived after the worker exited.
        recover_concurrent_result_image()
        signature = build_console_render_signature(
            concurrent_console_rounds,
            concurrent_console_round_images,
            active_round=concurrent_console_active_round,
            footer=concurrent_console_footer,
            mode="three",
            loop_enabled=loop_var.get(),
        )
        if not force and signature == concurrent_console_last_signature:
            concurrent_console_render_pending = False
            return False
        now = time.monotonic()
        if (
            not force
            and concurrent_console_last_render_at
            and now - concurrent_console_last_render_at
            < CONCURRENT_CONSOLE_RENDER_INTERVAL_SECONDS
        ):
            concurrent_console_render_pending = True
            return False
        output.configure(state="normal")
        output_links.clear()
        output.delete("1.0", "end")
        output.insert("end", "曹操传随机工具 - 内存快筛版\n")
        version_text = str(
            application_build_info().get("version", "")
        ).strip()
        version_parts = version_text.split(".")
        if len(version_parts) == 3 and version_parts[1:] == ["0", "0"]:
            version_text = version_parts[0]
        output.insert(
            "end",
            f"工具版本：V{version_text}\n"
            f"兵种筛选范围：当前规则所选人物（{selected_rule_member_count()}人）\n"
            f"目标存档：1-{concurrent_console_state.result_count}\n"
            f"同时运行数量：{concurrent_console_state.concurrency}\n"
            f"循环随机：{'开启' if loop_var.get() else '关闭'}\n\n",
        )
        for round_number, round_state in sorted(
            concurrent_console_rounds.items()
        ):
            if loop_var.get():
                output.insert(
                    "end",
                    format_round_heading(round_number) + "\n",
                )
            for slot in round_state.visible_slots():
                progress = round_state.slots[slot]
                info_tag = f"concurrent-slot-info-{round_number}-{slot}"
                output.insert("end", "明细", info_tag)
                output_links.add(
                    info_tag,
                    lambda _event, value=(round_number, slot): (
                        show_concurrent_slot_detail(*value)
                    ),
                )
                output.insert("end", " ")
                if progress.attempt:
                    output.insert(
                        "end",
                        f"存档{slot}　第 {progress.attempt} 次尝试　"
                        f"{progress.stage}",
                    )
                else:
                    output.insert(
                        "end",
                        f"存档{slot}　{progress.stage}",
                    )
                if progress.detail is not None:
                    output.insert("end", "　")
                    score_tag = (
                        f"concurrent-slot-score-{round_number}-{slot}"
                    )
                    output.insert("end", "查看评分", score_tag)
                    output_links.add(
                        score_tag,
                        lambda _event, value=progress.detail: (
                            show_result_detail(value)
                        ),
                    )
                output.insert("end", "\n")
            round_image = concurrent_console_round_images.get(round_number)
            if (
                loop_var.get()
                and round_image is not None
                and round_image.is_file()
            ):
                tag = f"concurrent-result-image-{round_number}"
                output.insert("end", "点击查看结果图", tag)
                output.insert("end", "\n\n")
                output_links.add(
                    tag,
                    lambda _event, path=round_image: os.startfile(path),
                )
        if concurrent_console_footer:
            output.insert("end", concurrent_console_footer + "\n")
            final_image = concurrent_console_round_images.get(
                concurrent_console_active_round
            )
            if (
                final_image is not None
                and final_image.is_file()
                and (
                    not loop_var.get()
                    or concurrent_console_active_round
                    not in concurrent_console_rounds
                    or concurrent_console_finished
                )
            ):
                tag = "concurrent-final-result-image"
                output.insert("end", "点击查看结果图", tag)
                output.insert("end", "\n")
                output_links.add(
                    tag,
                    lambda _event, path=final_image: os.startfile(path),
                )
        output.see("end")
        output.configure(state="disabled")
        concurrent_console_last_signature = signature
        concurrent_console_last_render_at = now
        concurrent_console_render_pending = False
        return True

    def append_attempt_result(detail: dict) -> None:
        label = str(detail.get("label") or "未知")
        output.configure(state="normal")
        output.insert("end", f"结果：{label}（")
        tag = f"detail-link-{output.index('end')}"
        output.insert("end", "点击查看详情", tag)
        output.insert("end", "）\n")
        output_links.add(
            tag,
            lambda _event, value=detail: show_result_detail(value),
        )
        output.see("end")
        if trim_text_widget(output):
            output_links.prune()
        output.configure(state="disabled")

    def append_result_link() -> None:
        if result_image_path is None or not result_image_path.is_file():
            return
        try:
            if output.get("1.0", "end-1c").rstrip().endswith("点击查看结果图"):
                return
        except tk.TclError:
            return
        output.configure(state="normal")
        tag = f"result-link-{output.index('end')}"
        output.insert("end", "点击查看结果图", tag)
        output.insert("end", "\n")
        output_links.add(
            tag,
            lambda _event, path=result_image_path: os.startfile(path),
        )
        output.see("end")
        if trim_text_widget(output):
            output_links.prune()
        output.configure(state="disabled")

    def append_stopped_summary() -> None:
        output.configure(state="normal")
        output.insert("end", "\n本次流程已停止。\n")
        if result_image_path is not None and result_image_path.is_file():
            tag = f"result-link-{output.index('end')}"
            output.insert("end", "点击查看结果图", tag)
            output.insert("end", "\n")
            output_links.add(
                tag,
                lambda _event, path=result_image_path: os.startfile(path),
            )
        output.see("end")
        if trim_text_widget(output):
            output_links.prune()
        output.configure(state="disabled")

    def read_worker(pipe, target_queue: queue.Queue[str]) -> None:
        for line in iter(pipe.readline, ""):
            # Blocking here is intentional: it applies bounded back-pressure
            # instead of allowing an unbounded GUI queue to retain a whole
            # long-running session in memory.
            target_queue.put(line.rstrip("\r\n"))
        pipe.close()

    def poll_worker() -> None:
        from ccz_randomizer.ui.polling import poll_and_reschedule, report_poll_error
        poll_and_reschedule(
            poll_worker_once,
            lambda delay: root.after(delay, poll_worker),
            lambda error: report_poll_error(app_dir(), error),
        )

    def poll_worker_once() -> int:
        nonlocal worker, result_image_path, stop_file
        nonlocal stop_requested_by_user, last_formatted_line
        nonlocal running_rule_name, running_rule_snapshot
        nonlocal active_game_executable, security_blocked_details
        nonlocal concurrent_console_state, concurrent_console_rounds
        nonlocal concurrent_console_round_images
        nonlocal concurrent_console_active_round
        nonlocal concurrent_console_finished, concurrent_console_footer
        nonlocal concurrent_console_render_pending
        if worker is None or worker.poll() is not None:
            sleep_guard.close()
        console_dirty = False
        force_console_render = False
        worker_finished = False
        processed_line_count = 0
        while processed_line_count < CONCURRENT_CONSOLE_QUEUE_BATCH_SIZE:
            try:
                line = output_queue.get_nowait()
            except queue.Empty:
                break
            processed_line_count += 1
            display_line = line
            worker_prefix = ""
            worker_index: int | None = None
            event_round: int | None = None
            try:
                concurrent_event = decode_concurrent_event(line)
            except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
                concurrent_event = None
                diagnostic_log(
                    "concurrent_event_decode_failed",
                    line=line[:500],
                    error=repr(exc),
                )
            if concurrent_event is not None:
                worker_index, event_round, display_line = concurrent_event
            else:
                worker_match = re.match(r"^(\[实例 \d+\])\s*(.*)$", line)
                if worker_match:
                    worker_prefix = worker_match.group(1) + " "
                    display_line = worker_match.group(2)
                    worker_index = int(
                        re.search(r"\d+", worker_match.group(1)).group()
                    )
            try:
                blocked_event = decode_security_software_blocked_event(
                    display_line
                )
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                blocked_event = None
                diagnostic_log(
                    "security_software_blocked_event_decode_failed",
                    line=display_line[:500],
                    error=repr(exc),
                )
            if blocked_event is not None:
                security_blocked_details = blocked_event
                continue
            if (
                concurrent_console_state is not None
                and display_line.startswith("兼容模式多实例无法启动")
            ):
                for round_state in concurrent_console_rounds.values():
                    round_state.concurrency = 1
                concurrent_console_state.concurrency = 1
                console_dirty = True
            round_match = re.match(
                r"^并发轮次开始：第\s*(\d+)\s*轮$",
                display_line.strip(),
            )
            if concurrent_console_state is not None and round_match:
                concurrent_console_active_round = int(round_match.group(1))
                concurrent_console_state = (
                    concurrent_console_rounds.get(
                        concurrent_console_active_round
                    )
                    or ConcurrentConsoleState(
                        concurrent_console_state.result_count,
                        concurrent_console_state.concurrency,
                    )
                )
                concurrent_console_rounds[
                    concurrent_console_active_round
                ] = concurrent_console_state
                concurrent_console_footer = ""
                console_dirty = True
                continue
            image_candidate = extract_result_image_path(display_line)
            if image_candidate is not None and image_candidate.is_file():
                result_image_path = image_candidate
                if concurrent_console_state is not None:
                    concurrent_console_round_images[
                        event_round or concurrent_console_active_round
                    ] = image_candidate
                    console_dirty = True
            if (
                concurrent_console_state is not None
                and worker_index is not None
                and (
                    not stop_requested_by_user
                    or is_completion_console_line(display_line)
                )
                and concurrent_console_rounds.get(
                    event_round or concurrent_console_active_round,
                    concurrent_console_state,
                ).consume_line(
                    worker_index,
                    display_line,
                    history_line=format_user_log(display_line),
                )
            ):
                console_dirty = True
                continue
            try:
                result_detail = decode_result_detail(display_line)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                result_detail = None
                diagnostic_log(
                    "result_detail_decode_failed",
                    line=display_line[:300],
                    error=repr(exc),
                )
            if result_detail is not None:
                if concurrent_console_state is not None:
                    concurrent_console_rounds.get(
                        event_round or concurrent_console_active_round,
                        concurrent_console_state,
                    ).consume_result(
                        result_detail,
                        preserve_stopped=stop_requested_by_user,
                    )
                    console_dirty = True
                else:
                    append_attempt_result(result_detail)
                last_formatted_line = (
                    f"结果：{result_detail.get('label', '未知')}"
                )
                continue
            formatted = format_user_log(display_line)
            if formatted:
                if worker_prefix:
                    formatted = worker_prefix + formatted
                if (
                    formatted == "后台游戏已启动"
                    and last_formatted_line.endswith("号存档已保存")
                ):
                    formatted = "\n" + formatted
                append(formatted)
                last_formatted_line = formatted.strip()
        queue_batch_exhausted = (
            processed_line_count >= CONCURRENT_CONSOLE_QUEUE_BATCH_SIZE
            and not output_queue.empty()
        )
        if console_dirty:
            concurrent_console_render_pending = True
        if (
            concurrent_console_render_pending
            and concurrent_console_state is not None
        ):
            render_concurrent_console()
        if queue_batch_exhausted:
            return 1
        if worker is not None and worker.poll() is not None:
            code = worker.returncode
            worker = None
            worker_finished = True
            if concurrent_console_state is not None:
                # The concurrent worker can emit its final image marker just
                # before the GUI drains the pipe. Recover the published batch
                # image at shutdown so the result link is never lost.
                image_candidates = [
                    path
                    for path in (
                        (active_game_executable or locate_game_executable()).parent
                        / "randResult"
                    ).glob("*-random.png")
                    if path.is_file()
                    and path.stat().st_mtime >= run_started_at - 5
                ]
                if image_candidates:
                    final_image = max(
                        image_candidates,
                        key=lambda path: path.stat().st_mtime,
                    )
                    concurrent_console_round_images.setdefault(
                        concurrent_console_active_round,
                        final_image,
                    )
                    result_image_path = final_image
            try:
                cleanup_random_runtime(
                    active_game_executable or locate_game_executable(),
                    "gui_worker_exit_cleanup",
                )
            except Exception as exc:
                diagnostic_error("gui_worker_exit_cleanup_failed", exc)
            active_game_executable = None
            running_rule_name = None
            running_rule_snapshot = None
            action_button.configure(
                text="开始随机", style="Primary.TButton",
                command=start,
                state="normal",
            )
            rule_profile_combo.configure(state="readonly")
            rule_button.configure(state="normal")
            repair_button.configure(state="normal")
            loop_check.configure(state="normal")
            concurrency_entry.configure(state="normal")
            compatibility_check.configure(state="normal")
            prevent_sleep_check.configure(state="normal")
            stopped = stop_requested_by_user or code == 130
            if concurrent_console_state is not None:
                if stopped:
                    for round_state in concurrent_console_rounds.values():
                        round_state.mark_stopped()
                concurrent_console_finished = stopped or code == 0
                concurrent_console_footer = (
                    "本次流程已停止。"
                    if stopped
                    else (
                        "本次流程已完成。"
                        if code == 0
                        else "本次流程执行失败，详细信息已写入日志文件。"
                    )
                )
                console_dirty = True
                force_console_render = True
                # The pending render may have been consumed earlier in this
                # poll. The process-exit state is a new visible change and
                # must schedule its own final render, even with an empty queue.
                concurrent_console_render_pending = True
            elif stopped:
                append_stopped_summary()
            elif code == 0:
                append("本次流程已结束。")
                append_result_link()
            elif security_blocked_details is not None:
                append(SECURITY_SOFTWARE_BLOCKED_MESSAGE)
                show_toast(
                    root,
                    SECURITY_SOFTWARE_BLOCKED_MESSAGE,
                    8000,
                )
            else:
                append("本次流程执行失败，详细信息已写入日志文件。")
            if stop_file is not None:
                stop_file.unlink(missing_ok=True)
                stop_file = None
            stop_requested_by_user = False
        if (
            concurrent_console_render_pending
            and concurrent_console_state is not None
        ):
            render_concurrent_console(force=force_console_render)
        # In concurrent mode the final image marker can be consumed in the
        # same poll that observes process exit.  The full console render may
        # already have happened before the exit state was applied, so append
        # a durable final link after that render as a last publication step.
        if (
            worker_finished
            and concurrent_console_state is not None
            and concurrent_console_finished
            and result_image_path is not None
            and result_image_path.is_file()
        ):
            # The concurrent renderer already publishes one link per
            # completed round.  The durable post-exit append is only needed
            # when that render did not see the image marker in time; avoid
            # adding a second identical link after a normal stop.
            try:
                has_rendered_link = "点击查看结果图" in output.get("1.0", "end-1c")
            except tk.TclError:
                has_rendered_link = False
            if not has_rendered_link:
                append_result_link()
        return 100

    def start_random_worker() -> None:
        nonlocal output_queue
        nonlocal current_rules
        nonlocal worker, log_path, result_image_path, stop_file, run_started_at
        nonlocal stop_requested_by_user, last_formatted_line
        nonlocal running_rule_name, running_rule_snapshot
        nonlocal active_game_executable, security_blocked_details
        nonlocal concurrent_console_state, concurrent_console_rounds
        nonlocal concurrent_console_round_images
        nonlocal concurrent_console_active_round
        nonlocal concurrent_console_finished, concurrent_console_footer
        nonlocal concurrent_console_render_pending
        nonlocal concurrent_console_last_render_at
        nonlocal concurrent_console_last_signature
        if worker is not None:
            return
        # A previous reader may finish slightly after the process exits.  Give
        # that reader its own queue so its late EOF lines cannot be consumed by
        # this new run.
        output_queue = queue.Queue(maxsize=20000)
        try:
            game_executable = locate_game_executable()
            activate_game_version(game_executable)
            validate_start_environment(game_executable)
            cleanup_random_runtime(
                game_executable,
                "gui_start_cleanup",
            )
        except Exception as exc:
            messagebox.showerror(
                "无法开始随机",
                str(exc),
                parent=root,
            )
            return
        try:
            concurrency = int(concurrency_var.get())
        except (TypeError, ValueError):
            messagebox.showwarning(
                "同时运行数量设置",
                "同时运行数量必须是大于 0 的整数。",
                parent=root,
            )
            return
        if concurrency < 1:
            messagebox.showwarning(
                "同时运行数量设置",
                "同时运行数量必须大于 0。",
                parent=root,
            )
            return
        if not loop_var.get() and concurrency > 15:
            messagebox.showwarning(
                "同时运行数量设置",
                "非循环模式同时运行数量必须位于 1-15；"
                "循环模式可设置更高数量。",
                parent=root,
            )
            return
        persist_runtime_settings()
        compatibility_mode_enabled = bool(
            compatibility_mode_var.get()
        )
        active_game_executable = game_executable
        security_processes = detect_360_security_processes()
        if security_processes:
            show_toast(
                root,
                "检测到 360 安全软件，可能会影响后台随机。"
                "若运行异常，请退出 360 后重试。",
                5200,
            )
        latest_rules = load_rule_config(app_dir())
        current_rules = latest_rules.config
        rule_profile_combo.configure(
            values=tuple(current_rules["profiles"])
        )
        rule_profile_var.set(current_rules["activeProfile"])
        running_rule_name = current_rules["activeProfile"]
        running_rule_snapshot = serialize_rule_profile(
            current_rules["profiles"][running_rule_name]
        )
        if latest_rules.warning:
            messagebox.showwarning(
                "规则文件无法使用",
                latest_rules.warning,
                parent=root,
            )
        result_image_path = None
        stop_requested_by_user = False
        last_formatted_line = ""
        security_blocked_details = None
        env = os.environ.copy()
        capture_run_rules(current_rules, env)
        try:
            result_count = int(env.get("CCZ_RESULT_COUNT", "15"))
        except ValueError:
            result_count = 15
        result_count = min(15, max(1, result_count))
        if concurrency > 1:
            concurrent_console_state = ConcurrentConsoleState(
                result_count,
                concurrency,
            )
            concurrent_console_rounds = {1: concurrent_console_state}
            concurrent_console_round_images = {}
            concurrent_console_active_round = 1
            concurrent_console_finished = False
            concurrent_console_footer = ""
            concurrent_console_render_pending = True
            concurrent_console_last_render_at = 0.0
            concurrent_console_last_signature = None
            render_concurrent_console(force=True)
        else:
            concurrent_console_state = None
            concurrent_console_rounds = {}
            concurrent_console_round_images = {}
            concurrent_console_active_round = 1
            concurrent_console_finished = False
            concurrent_console_footer = ""
            concurrent_console_render_pending = False
            concurrent_console_last_render_at = 0.0
            concurrent_console_last_signature = None
            stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            append(f"\n========== 开始随机：{stamp} ==========")
            append(
                f"兵种筛选范围：当前规则所选人物（{selected_rule_member_count()}人）"
            )
            append("循环随机：" + ("开启" if loop_var.get() else "关闭"))
            append("环境检查：通过")
        stop_file = (
            app_dir()
            / "ccz_fast_logs"
            / f".stop-{os.getpid()}-{time.time_ns()}"
        )
        stop_file.parent.mkdir(parents=True, exist_ok=True)
        stop_file.unlink(missing_ok=True)
        env["CCZ_AUTOSTART"] = "1"
        env["CCZ_NO_PAUSE"] = "1"
        env["CCZ_STOP_FILE"] = str(stop_file)
        env["CCZ_RANDOM_MODE"] = "three"
        env["CCZ_GAME_VERSION"] = current_game_version()
        env["CCZ_PROFILE_DIRECTORY"] = load_profile().root.name
        env["CCZ_LOOP_RANDOM"] = "1" if loop_var.get() else "0"
        env["CCZ_CONCURRENT_MODE"] = "1"
        env["CCZ_CONCURRENT_COUNT"] = str(concurrency)
        env["CCZ_COMPATIBILITY_MODE"] = (
            "1" if compatibility_mode_enabled else "0"
        )
        # The experimental mode is hidden; ignore saved/inherited opt-ins.
        env["CCZ_TURBO_MODE"] = "0"
        env["CCZ_RUN_STAMP"] = dt.datetime.now().strftime(
            "%Y-%m-%d %H.%M.%S"
        )
        env["CCZ_HISTORY_RUN_ID"] = f"gui-{os.getpid()}-{time.time_ns()}"
        run_started_at = time.time()
        env["PYTHONIOENCODING"] = "utf-8"
        if getattr(sys, "frozen", False):
            command = [sys.executable, "--worker"]
        else:
            command = [sys.executable, str(source_entry_path()), "--worker"]
        try:
            if prevent_sleep_var.get():
                sleep_guard.start()
            worker = subprocess.Popen(
                command,
                cwd=str(app_dir()),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as exc:
            sleep_guard.close()
            diagnostic_error("gui_worker_start_failed", exc)
            messagebox.showerror("无法开始随机", str(exc), parent=root)
            return
        threading.Thread(
            target=read_worker,
            args=(worker.stdout, output_queue),
            daemon=True,
        ).start()
        action_button.configure(
            text="停止随机", style="Danger.TButton",
            command=stop,
            state="normal",
        )
        rule_profile_combo.configure(state="disabled")
        rule_button.configure(state="normal")
        repair_button.configure(state="disabled")
        loop_check.configure(state="disabled")
        concurrency_entry.configure(state="disabled")
        compatibility_check.configure(state="disabled")
        prevent_sleep_check.configure(state="disabled")

    def stop() -> None:
        nonlocal stop_requested_by_user
        nonlocal concurrent_console_footer
        nonlocal concurrent_console_render_pending
        if worker is not None and worker.poll() is None:
            target_worker = worker
            stop_requested_by_user = True
            action_button.configure(state="disabled")
            for round_state in concurrent_console_rounds.values():
                round_state.mark_stopping()
            if concurrent_console_state is not None:
                concurrent_console_footer = (
                    "正在停止随机并关闭后台实例……"
                )
                concurrent_console_render_pending = True
                render_concurrent_console(force=True)
            if stop_file is not None:
                stop_file.write_text("stop", encoding="ascii")
            # The runtime has a 20 second hard stop timeout.  Keep the GUI
            # fallback close to that bound so a stalled child cannot leave
            # the console in "正在停止" indefinitely.
            root.after(
                22000,
                lambda: force_stop_worker(target_worker),
            )

    def force_stop_worker(target_worker: subprocess.Popen[str]) -> None:
        if worker is not target_worker or target_worker.poll() is not None:
            return
        target_worker.terminate()
        # Do not block Tk's event loop while waiting for a child process.  A
        # short follow-up gives terminate a chance to finish and then kills
        # only if it is still alive; normal polling will render the final
        # stopped state as soon as the process exits.
        root.after(1000, lambda: force_kill_worker(target_worker))

    def force_kill_worker(target_worker: subprocess.Popen[str]) -> None:
        if worker is not target_worker or target_worker.poll() is not None:
            return
        try:
            target_worker.kill()
        except OSError:
            return
        try:
            cleanup_random_runtime(
                active_game_executable or locate_game_executable(),
                "gui_forced_stop_cleanup",
            )
        except Exception as exc:
            diagnostic_error("gui_forced_stop_cleanup_failed", exc)

    def close() -> None:
        try:
            save_random_runtime_settings(
                app_dir(),
                loop_random=bool(loop_var.get()),
                concurrency=int(concurrency_var.get()),
                compatibility_mode=bool(compatibility_mode_var.get()),
                prevent_sleep=bool(prevent_sleep_var.get()),
            )
        except (OSError, ValueError, TypeError, tk.TclError):
            pass
        if worker is not None and worker.poll() is None:
            if not messagebox.askyesno("确认退出", "随机仍在运行，确定停止并退出吗？"):
                return
            if stop_file is not None:
                stop_file.write_text("stop", encoding="ascii")
            try:
                worker.wait(timeout=50)
            except subprocess.TimeoutExpired:
                worker.terminate()
                try:
                    worker.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait(timeout=5)
        try:
            cleanup_random_runtime(
                active_game_executable or locate_game_executable(),
                "gui_close_cleanup",
            )
        except Exception as exc:
            diagnostic_error("gui_close_cleanup_failed", exc)
        root.destroy()

    from ccz_randomizer.ui.start_dependencies import StartDependencyCheck
    dependency_command = [sys.executable]
    if not getattr(sys, "frozen", False):
        dependency_command.append(str(source_entry_path()))
    start_dependencies = StartDependencyCheck(
        root, action_button, start_random_worker, dependency_command, bundle_root())

    def start() -> None:
        if worker is None:
            start_dependencies.request()

    action_button.configure(command=start)
    rule_button.configure(command=open_rule_editor)
    repair_button.configure(command=open_repair_dialog)
    rule_profile_combo.bind("<<ComboboxSelected>>", select_rule_profile)
    root.protocol("WM_DELETE_WINDOW", close)
    if rule_load.warning:
        root.after(
            150,
            lambda: messagebox.showwarning(
                "规则文件无法使用",
                rule_load.warning,
                parent=root,
            ),
        )
    from ccz_randomizer.profiles import PROFILE_LOAD_ERROR
    if PROFILE_LOAD_ERROR:
        root.after(500, lambda: messagebox.showwarning("数据包恢复", PROFILE_LOAD_ERROR, parent=root))
    root.after(100, show_first_use_notice)
    root.after(1500, profile_session.start)
    root.after(
        250,
        lambda: threading.Thread(
            target=skill_score_catalog,
            name="rule-catalog-preload",
            daemon=True,
        ).start(),
    )
    root.after(100, poll_worker)
    show_centered(root)
    try:
        root.mainloop()
    finally:
        sleep_guard.close()
    return 0


def main() -> int:
    global RESULT_BASE_DIR, DIAGNOSTIC_LOG_PATH, DIAGNOSTIC_LOG_WRITER
    global DIAGNOSTIC_SUMMARY_PATH, STOP_FILE_PATH
    os.environ.setdefault("CCZ_GAME_VERSION", APP_DEFAULT_GAME_VERSION)
    os.environ["CCZ_RANDOM_MODE"] = "three"
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    if os.environ.get("CCZ_CONCURRENT_WORKER"):
        start_concurrent_worker_heartbeat(sys.stdout)
    load_media_modules()
    if (
        os.environ.get("CCZ_CONCURRENT_MODE") == "1"
        and os.environ.get("CCZ_CONCURRENT_WORKER") is None
    ):
        game_executable = locate_game_executable()
        activate_game_version(game_executable)
        result_count = int(os.environ.get("CCZ_RESULT_COUNT", "15"))
        mode = os.environ.get("CCZ_RANDOM_MODE", "three")
        worker_count = int(os.environ.get("CCZ_CONCURRENT_COUNT", "2"))
        stop_file_value = os.environ.get("CCZ_STOP_FILE", "")
        history_base = Path(os.environ.get("CCZ_STATE_BASE_DIR") or app_dir())
        history_run_id = os.environ.setdefault(
            "CCZ_HISTORY_RUN_ID", f"concurrent-{os.getpid()}-{time.time_ns()}")
        history = HistoryLifecycle(HistoryRepository(history_base), history_run_id,
                                   expected_results=result_count)
        parent_rules = load_run_rules(app_dir(), os.environ).config
        capture_run_rules(parent_rules, os.environ)
        history.start_run(mode=mode, loop_random=os.environ.get("CCZ_LOOP_RANDOM") == "1",
                          rule_name=parent_rules["activeProfile"],
                          rule=active_profile(parent_rules), build=application_build_info())
        return run_concurrent_workers(
            history=history,
            game_executable=game_executable,
            result_count=result_count,
            mode=mode,
            stop_file=Path(stop_file_value) if stop_file_value else None,
            base_dir=app_dir(),
            worker_count=worker_count,
            loop_random=os.environ.get("CCZ_LOOP_RANDOM") == "1",
            compatibility_mode=(
                os.environ.get("CCZ_COMPATIBILITY_MODE") == "1"
            ),
        )
    configured_result_base = os.environ.get("CCZ_RESULT_BASE_DIR", "").strip()
    RESULT_BASE_DIR = (
        Path(configured_result_base)
        if configured_result_base
        else app_dir()
    )
    stop_file_value = os.environ.get("CCZ_STOP_FILE", "")
    stop_file = Path(stop_file_value) if stop_file_value else None
    STOP_FILE_PATH = stop_file

    app = app_dir()
    log_base = os.environ.get("CCZ_LOG_BASE_DIR", "").strip()
    log_dir = (
        Path(log_base) / "ccz_fast_logs"
        if log_base
        else app / "ccz_fast_logs"
    )
    log_dir.mkdir(parents=True, exist_ok=True)
    cleanup_result = cleanup_log_directory(log_dir)
    worker_suffix = (
        f"_worker{os.environ['CCZ_CONCURRENT_WORKER']}"
        if os.environ.get("CCZ_CONCURRENT_WORKER")
        else ""
    )
    log_path = log_dir / (
        f"fast_{dt.datetime.now():%Y%m%d_%H%M%S}{worker_suffix}.log"
    )
    DIAGNOSTIC_LOG_PATH = log_path.with_name(
        f"{log_path.stem}_diagnostic.jsonl"
    )
    DIAGNOSTIC_SUMMARY_PATH = log_path.with_name(
        f"{log_path.stem}_diagnostic_summary.json"
    )
    DIAGNOSTIC_FAILURE_COUNTS.clear()
    DIAGNOSTIC_FAILURE_HISTORY.clear()
    DIAGNOSTIC_SUMMARY_FIELDS.clear()
    log_file = RotatingTextWriter(log_path)
    DIAGNOSTIC_LOG_WRITER = RotatingTextWriter(DIAGNOSTIC_LOG_PATH)
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    sys.stdout = Tee(original_stdout, log_file)
    sys.stderr = Tee(original_stderr, log_file)

    ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    build_info = application_build_info()
    print("曹操传随机工具 - 内存快筛测试版")
    print(f"工具版本：{build_version_text(build_info)}")
    print("默认生成第 1-15 号结果存档；第 20 号存档仍作为源存档。")
    print("游戏将在独立后台桌面运行，不会占用当前鼠标或抢前台。")
    three_person_mode = os.environ.get("CCZ_RANDOM_MODE") == "three"
    loop_random = os.environ.get("CCZ_LOOP_RANDOM") == "1"
    script_guard: S00ScriptGuard | None = None
    scratch_guard: ScratchSaveGuard | None = None
    requested_run_stamp = os.environ.get(
        "CCZ_RUN_STAMP",
        dt.datetime.now().strftime("%Y-%m-%d %H.%M.%S"),
    )
    loop_run_stamp = (
        resolve_loop_run_stamp(app, requested_run_stamp)
        if loop_random
        else requested_run_stamp
    )
    run_id = start_diagnostic_run(
        phase="startup",
        random_mode="three" if three_person_mode else "seven",
        loop_random=loop_random,
    )
    print("循环随机：" + ("开启" if loop_random else "关闭"))
    print(f"日志: {log_path}")
    print(f"诊断日志: {DIAGNOSTIC_LOG_PATH}")
    rule_load = load_run_rules(app, os.environ)
    rules = rule_load.config
    active_rule_snapshot = active_profile(rules)
    active_rule_json = json.dumps(
        active_rule_snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    print(f"当前规则：{rules['activeProfile']}")
    if rule_load.warning:
        print(f"规则提示：{rule_load.warning}")
    state_base = os.environ.get("CCZ_STATE_BASE_DIR", "").strip()
    history_repository = HistoryRepository(
        Path(state_base) if state_base else app
    )
    history_run_id = os.environ.get("CCZ_HISTORY_RUN_ID", run_id)
    from ccz_randomizer.statistics import StatisticsRecorder
    statistics_recorder = StatisticsRecorder(
        Path(state_base) if state_base else app, run_id=history_run_id,
        rule_name=rules["activeProfile"], rule=active_rule_snapshot,
        mode="three" if three_person_mode else "seven",
        on_error=lambda error: diagnostic_log("statistics_collection_failed", error=repr(error)),
    )
    history_lifecycle = HistoryLifecycle(
        history_repository, history_run_id,
        owner=os.environ.get("CCZ_HISTORY_MANAGED") != "1")
    history_lifecycle.start_run(
        mode="three" if three_person_mode else "seven", loop_random=loop_random,
        rule_name=rules["activeProfile"], rule=active_rule_snapshot, build=build_info,
    )
    environment = environment_diagnostic(app, log_dir, tempfile.gettempdir())
    diagnostic_log(
        "worker_start",
        executable=sys.executable,
        app_dir=app,
        command_line=sys.argv,
        platform=sys.platform,
        build=build_info,
        random_mode="three" if three_person_mode else "seven",
        loop_random=loop_random,
        loop_run_stamp=loop_run_stamp if loop_random else None,
        rule_name=rules["activeProfile"],
        rule_config_sha256=hashlib.sha256(
            active_rule_json.encode("utf-8")
        ).hexdigest(),
        active_rule=active_rule_snapshot,
        rule_source=rule_load.source,
        rule_warning=rule_load.warning,
        run_id=run_id,
        environment=environment,
        available_memory_bytes=available_physical_memory_bytes(),
        detected_360_processes=detect_360_security_processes(),
        log_cleanup={
            "removed_files": cleanup_result.removed_files,
            "removed_bytes": cleanup_result.removed_bytes,
            "remaining_bytes": cleanup_result.remaining_bytes,
        },
    )
    update_diagnostic_summary(
        status="running",
        run_id=run_id,
        build=build_info,
        mode="three" if three_person_mode else "seven",
        loop_random=loop_random,
        rule_name=rules["activeProfile"],
        environment=environment,
        diagnostic_log=DIAGNOSTIC_LOG_PATH,
        regular_log=log_path,
    )

    try:
        update_diagnostic_context(phase="environment_check")
        game_executable = locate_game_executable()
        activate_game_version(game_executable)
        validate_profile_members(active_profile(rules))
        game_dir = runtime_game_directory(game_executable)
        original_script = bundled_original_s00()
        helper_script = bundled_random_s00()
        if not original_script.is_file() or not helper_script.is_file():
            raise FileNotFoundError("工具内缺少 S_00.eex 保护文件")
        script_guard = S00ScriptGuard(
            game_dir,
            original_script,
            helper_script,
        )
        scratch_guard = ScratchSaveGuard(game_dir)
        scratch_recovered = scratch_guard.prepare()
        diagnostic_log(
            "worker_start_scratch_save_repair",
            transaction_recovered=scratch_recovered,
            target=file_diagnostic(scratch_guard.target),
        )
        repair_result = script_guard.prepare()
        diagnostic_log(
            "worker_start_s00_repair",
            active_script_repaired=repair_result.active_script_repaired,
            stale_helper_replaced=(
                repair_result.stale_helper_replaced
            ),
            transaction_recovered=repair_result.transaction_recovered,
            root=file_diagnostic(game_dir / "S_00.eex"),
            override=file_diagnostic(
                game_dir / "RS" / "S_00.eex"
            ),
        )
        diagnostic_log(
            "runtime_files_ready",
            game_executable=file_diagnostic(game_executable),
            game_runtime_directory=str(game_dir),
            injector=file_diagnostic(native_dir() / "ccz_injector.exe"),
            control_dll=file_diagnostic(native_dir() / "ccz_control.dll"),
            source_bundle=str(bundle_root()),
        )
        if os.environ.get("CCZ_AUTOSTART") != "1":
            input("按回车启动静默测试...")
        source_save = game_dir / "SV" / "SV020.E5S"
        if not source_save.is_file():
            raise FileNotFoundError(
                "未找到第 20 号源存档 SV020.E5S"
            )
        if not three_person_mode:
            script_guard.install()
            diagnostic_log(
                "main_session_helper_script_installed",
                target=file_diagnostic(script_guard.override_target),
                helper=file_diagnostic(helper_script),
            )
        source_hash = hashlib.sha256(source_save.read_bytes()).hexdigest()
        update_diagnostic_context(phase="source_validation")
        diagnostic_log(
            "source_save_ready",
            path=source_save,
            size=source_save.stat().st_size,
            sha256=source_hash,
        )
        install(bundle_root())
        import task.CczReRandTask as task_module

        task_module.SAVE_NUM = 1
        support_probe = os.environ.get("CCZ_SUPPORT_PROBE") == "1"
        result_count = (
            15
            if loop_random
            else (1 if support_probe else int(os.environ.get("CCZ_RESULT_COUNT", "15")))
        )
        result_slot_start = 1 if support_probe else int(
            os.environ.get("CCZ_RESULT_SLOT_START", "1")
        )
        result_slot_list = os.environ.get(
            "CCZ_CONCURRENT_SLOT_LIST",
            "",
        ).strip()
        result_slots = (
            tuple(
                int(slot.strip())
                for slot in result_slot_list.split(",")
                if slot.strip()
            )
            if result_slot_list
            else None
        )
        progress_total = int(
            os.environ.get("CCZ_TOTAL_RESULT_COUNT", str(result_count))
        )
        if result_slot_start < 1 or (
            result_slot_start + result_count - 1 > 15
        ):
            raise ValueError("并发结果槽位必须位于第 1-15 号范围内")
        game: HiddenGameSession | None = None
        compatibility_restart_mode = support_probe
        consecutive_normal_reload_failures = 0
        session_generation = 0
        refresh_consumed_session = False

        def start_game_session(
            restarted: bool = False,
            announce: bool = True,
        ) -> HiddenGameSession:
            nonlocal session_generation
            check_stop_requested()
            update_diagnostic_context(phase="game_start")
            session = HiddenGameSession(
                game_executable,
                restarted=restarted,
                announce=announce,
                working_directory=game_dir,
            )
            session.__enter__()
            check_stop_requested()
            session_generation += 1
            update_diagnostic_context(
                pid=session.pid,
                game_hwnd=session.main_window,
                session_generation=session_generation,
            )
            try:
                diagnostic_log(
                    "game_session_restarted"
                    if restarted
                    else "game_session_started",
                    pid=session.pid,
                    hwnd=session.main_window,
                    session_generation=session_generation,
                )
                patch_runtime(
                    task_module,
                    session.pid,
                    three_person_mode=three_person_mode,
                    rules=rules,
                    game_executable=game_dir / GAME_EXE_NAME,
                )
            except BaseException as exc:
                if isinstance(exc, Exception):
                    diagnostic_error(
                        "game_session_setup_failed",
                        exc,
                        game=session,
                        restarted=restarted,
                        session_generation=session_generation,
                    )
                session.__exit__(None, None, None)
                raise
            return session

        def close_game_session(
            session: HiddenGameSession | None,
        ) -> None:
            if session is not None:
                session.__exit__(None, None, None)

        game = start_game_session()
        try:
            round_number = int(os.environ.get("CCZ_HISTORY_ROUND_NUMBER", "1"))
        except ValueError:
            round_number = 1
        try:
            while True:
                update_diagnostic_context(
                    phase="round_setup",
                    loop_round=round_number,
                    result_slot=None,
                    attempt=None,
                    recovery_attempt=None,
                )
                workspace = None
                expected_results = {}
                panel_paths: dict[int, Path] = {}
                postprocess_issues: dict[int, list[str]] = {}
                attempt_started_at: dict[tuple[int, int], float] = {}
                round_started_at = dt.datetime.now()
                history_round_id = history_lifecycle.start_round(
                    round_number,
                )
                if loop_random:
                    ensure_loop_disk_space(app)
                    workspace = prepare_round_workspace(
                        app,
                        loop_run_stamp,
                        round_number,
                    )
                    panel_dir, grid_file = configure_result_output(
                        workspace.panels_dir,
                        workspace.grid_file,
                        workspace.round_name,
                    )
                    print(f"循环轮次开始：第 {round_number} 轮")
                else:
                    panel_dir, grid_file = initialize_result_output()
                print(f"本轮结果目录：{panel_dir}")
                print(f"本轮总图路径：{grid_file}")

                def round_metadata(status_time: dt.datetime) -> dict:
                    return {
                        "mode": (
                            "three" if three_person_mode else "seven"
                        ),
                        "ruleName": rules["activeProfile"],
                        "toolVersion": build_version_text(build_info),
                        "build": build_info,
                        "startedAt": round_started_at.isoformat(
                            timespec="seconds"
                        ),
                        "finishedAt": status_time.isoformat(
                            timespec="seconds"
                        ),
                        "postProcessingIssues": {
                            str(slot): issues
                            for slot, issues in postprocess_issues.items()
                        },
                    }

                def archive_incomplete_round() -> Path | None:
                    if workspace is None:
                        return None
                    target = finalize_round(
                        workspace,
                        save_dir=game_dir / "SV",
                        completed_slots=expected_results,
                        expected_slots=range(
                            result_slot_start,
                            result_slot_start + result_count,
                        ),
                        metadata=round_metadata(dt.datetime.now()),
                        complete=False,
                    )
                    if target is None:
                        return None
                    final_grid = relocate_result_output(target)
                    print(f"循环轮次未完成结果：{target}")
                    if final_grid.is_file():
                        print(f"本轮总图路径：{final_grid}")
                    return target

                try:
                    def run_attempt(
                        result_slot: int,
                        _round_index: int,
                        loaded: bool,
                    ) -> AttemptResult:
                        nonlocal game, consecutive_normal_reload_failures
                        nonlocal refresh_consumed_session
                        check_stop_requested()
                        update_diagnostic_context(
                            phase="randomization",
                            result_slot=result_slot,
                            attempt=_round_index,
                            source_loaded=loaded,
                            recovery_attempt=None,
                            compatibility_mode=compatibility_restart_mode,
                        )
                        if refresh_consumed_session:
                            diagnostic_log(
                                "consumed_seven_member_session_refresh",
                                pid=game.pid,
                                result_slot=result_slot,
                                round_index=_round_index,
                            )
                            close_game_session(game)
                            game = start_game_session(
                                restarted=True,
                                announce=False,
                            )
                            refresh_consumed_session = False
                            loaded = False
                        if compatibility_restart_mode and loaded:
                            diagnostic_log(
                                "compatibility_restart_before_attempt",
                                pid=game.pid,
                                result_slot=result_slot,
                                round_index=_round_index,
                            )
                            print("兼容模式：正在刷新后台游戏实例")
                            close_game_session(game)
                            game = start_game_session(
                                restarted=True,
                                announce=False,
                            )
                            loaded = False
                        reused_session = loaded
                        runner = task_module.CczReRandTask(0)
                        runner._target_save_pos = result_slot
                        runner._source_loaded = loaded
                        try:
                            with diagnostic_timing(
                                "attempt_runner",
                                result_slot=result_slot,
                                attempt=_round_index,
                                round_number=(
                                    round_number if loop_random else None
                                ),
                                loaded=loaded,
                            ):
                                with statistics_recorder.attempt(
                                    runner, round_number=round_number,
                                    slot=result_slot, attempt=_round_index,
                                ) as statistical_result:
                                    accepted = runner.run()
                                    statistical_result["saved"] = bool(accepted)
                        finally:
                            if getattr(
                                runner,
                                "_session_consumed",
                                False,
                            ):
                                refresh_consumed_session = True
                            if getattr(
                                runner,
                                "_normal_load_succeeded",
                                False,
                            ):
                                consecutive_normal_reload_failures = 0
                        update_diagnostic_context(
                            source_loaded=bool(
                                getattr(runner, "_source_loaded", False)
                            ),
                            attempt_result=(
                                "accepted" if accepted else "rejected"
                            ),
                        )
                        return AttemptResult(
                            accepted=accepted,
                            source_loaded=bool(
                                getattr(runner, "_source_loaded", False)
                            )
                            and not refresh_consumed_session,
                            payload=runner,
                        )

                    def recover_session(
                        exc: BaseException,
                        result_slot: int,
                        round_index: int,
                    ) -> None:
                        nonlocal game, compatibility_restart_mode
                        nonlocal consecutive_normal_reload_failures
                        nonlocal refresh_consumed_session
                        check_stop_requested()
                        if isinstance(exc, NormalReloadUnsupported):
                            consecutive_normal_reload_failures += 1
                            diagnostic_log(
                                "normal_reload_failure_counted",
                                count=consecutive_normal_reload_failures,
                                threshold=(
                                    NORMAL_RELOAD_FAILURES_BEFORE_COMPATIBILITY
                                ),
                            )
                            if (
                                consecutive_normal_reload_failures
                                >= NORMAL_RELOAD_FAILURES_BEFORE_COMPATIBILITY
                            ):
                                compatibility_restart_mode = True
                                print(
                                    "当前设备无法稳定复用后台游戏，"
                                    "已自动切换兼容模式"
                                )
                        diagnostic_log(
                            "game_session_recovery",
                            pid=game.pid,
                            result_slot=result_slot,
                            round_index=round_index,
                            loop_round=(
                                round_number if loop_random else None
                            ),
                            error=repr(exc),
                        )
                        update_diagnostic_summary(
                            status="recovering",
                            pid=game.pid,
                            result_slot=result_slot,
                            attempt=round_index,
                            compatibility_mode=compatibility_restart_mode,
                        )
                        print(
                            "后台游戏运行异常，正在自动重新启动……"
                        )
                        check_stop_requested()
                        close_game_session(game)
                        check_stop_requested()
                        game = start_game_session(
                            restarted=True,
                            announce=True,
                        )
                        refresh_consumed_session = False
                        update_diagnostic_summary(
                            status="running",
                            pid=game.pid,
                            compatibility_mode=compatibility_restart_mode,
                        )

                    def attempt_started(
                        result_slot: int,
                        round_index: int,
                    ) -> None:
                        update_diagnostic_context(
                            phase="attempt_start",
                            result_slot=result_slot,
                            attempt=round_index,
                            recovery_attempt=None,
                        )
                        attempt_started_at[(result_slot, round_index)] = (
                            time.perf_counter()
                        )
                        diagnostic_log(
                            "attempt_started",
                            result_count=progress_total,
                        )
                        print(
                            f"========== 结果 {result_slot}/"
                            f"{progress_total}，原生随机第 "
                            f"{round_index} 轮 =========="
                        )

                    def accepted_result(
                        result: AcceptedResult,
                    ) -> None:
                        update_diagnostic_context(
                            phase="accepted_postprocess",
                            result_slot=result.result_slot,
                            attempt=result.round_index,
                        )
                        runner = result.payload
                        result_slot = result.result_slot
                        expected_results[result_slot] = True
                        check_stop_requested()
                        diagnostic_log(
                            "result_committed",
                            result_slot=result_slot,
                            round_index=result.round_index,
                            save_path=(
                                game_dir
                                / "SV"
                                / f"SV{result_slot:03}.E5S"
                            ),
                        )
                        with diagnostic_timing(
                            "accepted_collect_equipment",
                            result_slot=result_slot,
                            attempt=result.round_index,
                        ):
                            equip_info = collect_accepted_equipment_and_publish(
                                runner, result_slot, result.round_index)
                        check_stop_requested()
                        save_path = (
                            game_dir
                            / "SV"
                            / f"SV{result_slot:03}.E5S"
                        )
                        try:
                            snapshot = build_history_result_snapshot(
                                runner,
                                result_slot=result_slot,
                                accepted_attempt=result.round_index,
                                round_number=round_number,
                                equip_info=equip_info,
                                save_path=save_path,
                            )
                            with diagnostic_timing(
                                "accepted_write_history",
                                result_slot=result_slot,
                                attempt=result.round_index,
                            ):
                                history_repository.save_result(
                                    history_round_id,
                                    snapshot,
                                    save_path=save_path,
                                )
                        except Exception as history_exc:
                            print(f"第 {result_slot} 号存档的历史记录或备份保存失败，请查看日志")
                            diagnostic_error(
                                "history_result_write_failed",
                                history_exc,
                                game=game,
                                result_slot=result_slot,
                            )
                        with diagnostic_timing(
                            "accepted_render_panel",
                            result_slot=result_slot,
                            attempt=result.round_index,
                        ):
                            panel_paths[result_slot] = save_result_image(
                                runner,
                                equip_info,
                                result_slot,
                            )
                        with diagnostic_timing(
                            "accepted_render_grid",
                            result_slot=result_slot,
                            attempt=result.round_index,
                            panel_count=len(panel_paths),
                        ):
                            current_grid = compose_result_grid(panel_paths)
                        check_stop_requested()
                        print(
                            f"第 {result_slot} 号结果图已生成，"
                            f"总图已更新：{current_grid}"
                        )
                        diagnostic_log(
                            "accepted_postprocess_completed",
                            result_slot=result_slot,
                            panel_path=panel_paths[result_slot],
                            grid_path=current_grid,
                            history_round_id=history_round_id,
                        )

                    def accepted_result_error(
                        exc: BaseException,
                        result: AcceptedResult,
                    ) -> None:
                        result_slot = result.result_slot
                        try:
                            if history_repository.get_result(history_round_id, result_slot) is None:
                                save_path = game_dir / "SV" / f"SV{result_slot:03}.E5S"
                                snapshot = build_history_result_snapshot(
                                    result.payload, result_slot=result_slot,
                                    accepted_attempt=result.round_index, round_number=round_number,
                                    equip_info=None, save_path=save_path)
                                history_repository.save_result(history_round_id, snapshot, save_path=save_path)
                        except Exception as history_exc:
                            print(f"第 {result_slot} 号存档的历史记录或备份保存失败，请查看日志")
                            diagnostic_error("history_result_write_failed", history_exc,
                                             game=game, result_slot=result_slot)
                        issue = f"结果图处理失败：{exc}"
                        postprocess_issues.setdefault(
                            result_slot, []
                        ).append(issue)
                        diagnostic_error(
                            "accepted_postprocess_failed",
                            exc,
                            game=game,
                            result_slot=result_slot,
                            round_index=result.round_index,
                        )
                        print(
                            f"第 {result_slot} 号存档已保存，"
                            "但结果图生成失败；将继续处理下一个存档"
                        )
                        try:
                            panel_paths[result_slot] = (
                                save_result_failure_image(
                                    result_slot,
                                    str(exc),
                                )
                            )
                            compose_result_grid(panel_paths)
                        except Exception as fallback_exc:
                            postprocess_issues[result_slot].append(
                                f"备用结果图生成失败：{fallback_exc}"
                            )
                            diagnostic_error(
                                "fallback_result_image_failed",
                                fallback_exc,
                                game=game,
                                result_slot=result_slot,
                            )

                    def attempt_error(
                        exc: BaseException,
                        result_slot: int,
                        round_index: int,
                        recovery_attempt: int,
                        source_loaded: bool,
                        will_recover: bool,
                    ) -> None:
                        check_stop_requested()
                        started = attempt_started_at.get(
                            (result_slot, round_index)
                        )
                        update_diagnostic_context(
                            phase="attempt_failed",
                            result_slot=result_slot,
                            attempt=round_index,
                            recovery_attempt=recovery_attempt,
                            source_loaded=source_loaded,
                        )
                        diagnostic_error(
                            "attempt_failed",
                            exc,
                            game=game,
                            will_recover=will_recover,
                            compatibility_mode=compatibility_restart_mode,
                            normal_reload_failure_count=(
                                consecutive_normal_reload_failures
                            ),
                            attempt_elapsed_ms=(
                                round(
                                    (time.perf_counter() - started) * 1000
                                )
                                if started is not None
                                else None
                            ),
                        )

                    def attempt_finished(
                        result_slot: int,
                        round_index: int,
                        attempt: AttemptResult,
                    ) -> None:
                        started = attempt_started_at.pop(
                            (result_slot, round_index), None
                        )
                        diagnostic_log(
                            "attempt_finished",
                            result_slot=result_slot,
                            round_index=round_index,
                            accepted=attempt.accepted,
                            source_loaded=attempt.source_loaded,
                            elapsed_ms=(
                                round(
                                    (time.perf_counter() - started) * 1000
                                )
                                if started is not None
                                else None
                            ),
                        )
                        detail = result_detail_for_runner(
                            attempt.payload,
                            result_slot,
                            round_index,
                        )
                        if detail is not None and not attempt.accepted:
                            print(encode_result_detail(detail))

                    run_random_workflow(
                        result_count=result_count,
                        run_attempt=run_attempt,
                        recover_session=recover_session,
                        should_recover=(
                            lambda exc: (
                                check_stop_requested(),
                                session_failure_requires_restart(game, exc),
                            )[1]
                        ),
                        on_attempt_started=attempt_started,
                        on_accepted=accepted_result,
                        on_accepted_error=accepted_result_error,
                        on_attempt_error=attempt_error,
                        on_attempt_finished=attempt_finished,
                        check_stop=check_stop_requested,
                        result_slot_start=result_slot_start,
                        result_slots=result_slots,
                    )
                    if panel_paths:
                        print(
                            f"{result_count} 个存档结果图已完成："
                            f"{result_grid_path()}"
                        )

                    if (
                        hashlib.sha256(source_save.read_bytes()).hexdigest()
                        != source_hash
                    ):
                        raise RuntimeError(
                            "第 20 号源存档在随机过程中被修改"
                        )
                    if not loop_random:
                        history_lifecycle.finish_round(
                            history_round_id,
                            "completed",
                        )
                except KeyboardInterrupt:
                    history_lifecycle.finish_round(
                        history_round_id,
                        "stopped",
                    )
                    archive_incomplete_round()
                    raise
                except Exception:
                    history_lifecycle.finish_round(
                        history_round_id,
                        "failed",
                    )
                    raise

                if not loop_random:
                    break

                assert workspace is not None
                try:
                    completed_dir = finalize_round(
                        workspace,
                        save_dir=game_dir / "SV",
                        completed_slots=expected_results,
                        expected_slots=range(
                            result_slot_start,
                            result_slot_start + result_count,
                        ),
                        metadata=round_metadata(dt.datetime.now()),
                        complete=True,
                    )
                except Exception:
                    history_lifecycle.finish_round(
                        history_round_id,
                        "failed",
                    )
                    raise
                assert completed_dir is not None
                final_grid = relocate_result_output(completed_dir)
                history_lifecycle.finish_round(
                    history_round_id,
                    "completed",
                )
                print(
                    f"循环轮次完成：第 {round_number} 轮已完成，"
                    "共保存15个存档"
                )
                print(f"循环轮次结果目录：{completed_dir}")
                print(f"本轮总图路径：{final_grid}")
                diagnostic_log(
                    "loop_round_completed",
                    round_number=round_number,
                    path=completed_dir,
                )
                round_number += 1
                check_stop_requested()
        finally:
            close_game_session(game)
        if not loop_random:
            if postprocess_issues:
                print(
                    f"{result_count} 个结果存档已全部保存；"
                    f"其中 {len(postprocess_issues)} 个存档的"
                    "结果图存在异常，详情请查看日志。"
                )
            else:
                print(f"{result_count} 个结果存档已全部保存。")
        history_lifecycle.finish_run("completed")
        update_diagnostic_summary(
            status="completed",
            completed_results=len(expected_results),
            result_count=result_count,
        )
        return 0
    except KeyboardInterrupt:
        history_lifecycle.finish_run("stopped")
        update_diagnostic_context(phase="stopped")
        diagnostic_log("worker_stopped", reason="keyboard_interrupt")
        update_diagnostic_summary(status="stopped")
        print("测试已中断。")
        return 130
    except Exception as exc:
        history_lifecycle.finish_run("failed")
        update_diagnostic_context(phase="worker_failed")
        blocked_details = security_software_block_details(exc)
        diagnostic_error(
            "worker_failed",
            exc,
            game=locals().get("game"),
            security_software_blocked=blocked_details is not None,
            blocked_paths=(
                blocked_details.get("paths", [])
                if blocked_details is not None
                else []
            ),
        )
        if isinstance(exc, NativeControlError):
            for message_line in str(exc).splitlines():
                if message_line.strip():
                    print(f"环境处理提示：{message_line}")
        report_worker_exception(exc, log_file, blocked_details)
        return 1
    finally:
        update_diagnostic_context(phase="worker_exit")
        game_executable_for_cleanup = locals().get("game_executable")
        if isinstance(game_executable_for_cleanup, Path):
            try:
                terminated_pids = terminate_random_game_instances(
                    game_executable_for_cleanup
                )
                diagnostic_log(
                    "worker_exit_game_cleanup",
                    terminated_random_pids=terminated_pids,
                )
            except Exception as cleanup_exc:
                diagnostic_error(
                    "worker_exit_game_cleanup_failed",
                    cleanup_exc,
                )
        if script_guard is not None:
            try:
                script_guard.restore()
                diagnostic_log(
                    "main_session_helper_script_restored",
                    target=str(script_guard.override_target),
                    root=file_diagnostic(
                        script_guard.game_dir / "S_00.eex"
                    ),
                )
            except Exception as restore_exc:
                diagnostic_error(
                    "main_session_helper_script_restore_failed",
                    restore_exc,
                    target=str(script_guard.override_target),
                )
        if scratch_guard is not None:
            try:
                recovered = scratch_guard.restore()
                diagnostic_log(
                    "worker_exit_scratch_save_restored",
                    transaction_recovered=recovered,
                    target=str(scratch_guard.target),
                )
            except Exception as restore_exc:
                diagnostic_error(
                    "worker_exit_scratch_save_restore_failed",
                    restore_exc,
                    target=str(scratch_guard.target),
                )
        statistics_recorder.close()
        diagnostic_log("worker_exit")
        clear_diagnostic_context(
            "pid",
            "game_hwnd",
            "result_slot",
            "attempt",
            "recovery_attempt",
        )
        if (
            stop_file is not None
            and os.environ.get("CCZ_CONCURRENT_WORKER") is None
        ):
            stop_file.unlink(missing_ok=True)
        STOP_FILE_PATH = None
        if os.environ.get("CCZ_NO_PAUSE") != "1":
            try:
                input("按回车退出...")
            except EOFError:
                pass
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        log_file.close()
        if DIAGNOSTIC_LOG_WRITER is not None:
            DIAGNOSTIC_LOG_WRITER.close()
            DIAGNOSTIC_LOG_WRITER = None


def run_inspection_cli_with_diagnostics(
    stage: str,
    operation,
) -> int:
    global DIAGNOSTIC_LOG_PATH, DIAGNOSTIC_LOG_WRITER
    global DIAGNOSTIC_SUMMARY_PATH
    log_value = os.environ.get("CCZ_INSPECTION_LOG_PATH", "")
    diagnostic_value = os.environ.get(
        "CCZ_INSPECTION_DIAGNOSTIC_PATH", ""
    )
    log_path = Path(log_value) if log_value else None
    diagnostic_path = Path(diagnostic_value) if diagnostic_value else None
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    log_writer = RotatingTextWriter(log_path) if log_path else None
    if diagnostic_path:
        DIAGNOSTIC_LOG_PATH = diagnostic_path
        DIAGNOSTIC_LOG_WRITER = RotatingTextWriter(diagnostic_path)
    DIAGNOSTIC_SUMMARY_PATH = None
    start_diagnostic_run(
        run_type="inspection_child",
        inspection_stage=stage,
        inspection_attempt=os.environ.get("CCZ_INSPECTION_ATTEMPT", "1"),
        click_strategy=os.environ.get(
            "CCZ_INSPECTION_CLICK_STRATEGY", "post_message"
        ),
        parent_diagnostic_path=os.environ.get(
            "CCZ_PARENT_DIAGNOSTIC_PATH", ""
        ),
        process_id=os.getpid(),
    )
    if log_writer is not None:
        sys.stdout = Tee(original_stdout, log_writer)
        sys.stderr = Tee(original_stderr, log_writer)
    diagnostic_log(
        "inspection_child_started",
        stage=stage,
        argv=sys.argv,
        cwd=str(Path.cwd()),
        process_id=os.getpid(),
    )
    inspect_code = 1
    try:
        inspect_code = int(operation())
        diagnostic_log(
            "inspection_child_completed",
            stage=stage,
            return_code=inspect_code,
        )
    except Exception as exc:
        diagnostic_error(
            "inspection_child_failed",
            exc,
            stage=stage,
        )
        traceback.print_exc()
        inspect_code = 1
    finally:
        diagnostic_log(
            "inspection_child_exiting",
            stage=stage,
            return_code=inspect_code,
        )
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        if log_writer is not None:
            log_writer.close()
        if DIAGNOSTIC_LOG_WRITER is not None:
            DIAGNOSTIC_LOG_WRITER.close()
        DIAGNOSTIC_LOG_PATH = None
        DIAGNOSTIC_LOG_WRITER = None
    return inspect_code


def run_cli() -> int:
    if "--benchmark-ui" in sys.argv:
        from ccz_randomizer.diagnostics.ui_benchmark import run_request
        return run_request(Path(sys.argv[sys.argv.index("--benchmark-ui") + 1]))
    if "--diagnose-runtime" in sys.argv:
        from ccz_randomizer.diagnostics.dependencies import probe_runtime
        index = sys.argv.index("--diagnose-runtime")
        Path(sys.argv[index + 1]).write_text(
            json.dumps(probe_runtime(bundle_root()), ensure_ascii=False), encoding="utf-8")
        return 0
    if "--smoke-startup" in sys.argv:
        return 0
    if "--smoke-windowed-output" in sys.argv:
        with open(os.devnull, "w", encoding="utf-8") as sink:
            Tee(sys.stdout, sink).write("ok")
        return 0
    if "--smoke-imports" in sys.argv:
        load_media_modules()
        catalog = skill_score_catalog()
        if not catalog:
            return 1
        return 0
    if "--smoke-changelog" in sys.argv:
        version = str(application_build_info().get("version", "")).strip()
        return (
            0
            if any(
                str(entry.get("version", "")) == version
                for entry in application_changelog()
            )
            else 1
        )
    if "--inspect-initial-slot" in sys.argv:
        slot_index = sys.argv.index("--inspect-initial-slot")
        output_index = sys.argv.index("--inspect-output")
        game_index = sys.argv.index("--game-executable")
        score_index = (
            sys.argv.index("--job-score")
            if "--job-score" in sys.argv
            else -1
        )
        return run_inspection_cli_with_diagnostics(
            "initial",
            lambda: inspect_initial_saved_slot(
                Path(sys.argv[game_index + 1]),
                int(sys.argv[slot_index + 1]),
                Path(sys.argv[output_index + 1]),
                float(sys.argv[score_index + 1])
                if score_index >= 0
                else 0.0,
            ),
        )
    if "--inspect-slot" in sys.argv:
        slot_index = sys.argv.index("--inspect-slot")
        output_index = sys.argv.index("--inspect-output")
        game_index = sys.argv.index("--game-executable")
        score_index = (
            sys.argv.index("--job-score")
            if "--job-score" in sys.argv
            else -1
        )
        member_index = (
            sys.argv.index("--inspect-member")
            if "--inspect-member" in sys.argv
            else -1
        )
        return run_inspection_cli_with_diagnostics(
            "full",
            lambda: inspect_saved_slot(
                Path(sys.argv[game_index + 1]),
                int(sys.argv[slot_index + 1]),
                Path(sys.argv[output_index + 1]),
                float(sys.argv[score_index + 1]) if score_index >= 0 else 0.0,
                (
                    int(sys.argv[member_index + 1])
                    if member_index >= 0
                    else None
                ),
            ),
        )
    if "--worker" in sys.argv:
        exit_code = main()
        if (
            getattr(sys, "frozen", False)
            and os.environ.get("CCZ_CONCURRENT_MODE") == "1"
            and os.environ.get("CCZ_CONCURRENT_WORKER") is None
        ):
            # The frozen coordinator can retain third-party runtime threads
            # after all workers and sandboxes have been closed.  Flush the
            # final result path before ending this dedicated child process.
            for stream in (sys.stdout, sys.stderr):
                flush = getattr(stream, "flush", None)
                if flush is None:
                    continue
                try:
                    flush()
                except (BrokenPipeError, OSError, ValueError):
                    pass
            os._exit(exit_code)
        return exit_code
    return gui_main()


if __name__ == "__main__":
    raise SystemExit(run_cli())
