from __future__ import annotations

import ctypes
import datetime as dt
import hashlib
import json
import os
import queue
import shutil
import subprocess
import struct
import sys
import tempfile
import threading
import time
import traceback
from ctypes import wintypes
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

from ccz_randomizer.rules.config import (
    active_profile,
    default_rule_config,
    evaluate_job_rules,
    evaluate_skill_rules,
    load_rule_config,
    save_rule_config,
    validate_rule_config,
)
from ccz_randomizer.rules.editor import show_rule_editor
from ccz_randomizer.diagnostics.skill_storage import write_skill_evidence
from ccz_randomizer.runtime.loader import install
from ccz_randomizer.workflow.randomization import (
    AcceptedResult,
    AttemptResult,
    run_random_workflow,
    validate_reloaded_jobs,
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
MEMORY_BASE = 0x00501000
JOB_OFFSET = 0x2F40
SKILL_OFFSET = 0x6800
SKILL_RECORD_SIZE = 8
SKILLS_PER_MEMBER = 6
TEAM_MEMBER_NUM = 7
JOB_POSITIONS_R0 = (0, 1, 6)
JOB_POSITIONS_R1 = (0, 1, 5, 6, 10, 11, 12)
R0_MEMORY_SIZE = 0x30000
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
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
OFFSCREEN_X = -3000
OFFSCREEN_Y = -3000
SOURCE_SAVE_NUMBER = 20
# The source save is the visible No.020 entry and SV020.E5S on disk.
SOURCE_TITLE_LIST_INDEX = 19
XU_CLIENT_POSITION = (369, 234)
CONFIRM_FIRST_CLIENT_POSITION = (297, 220)
EQUIPMENT_OFFSET = 0x54D8
EQUIPMENT_SIZE = 376
EQUIPMENT_NAMES = (
    "雌雄双剑", "倚天剑", "青釭剑", "古锭刀", "青龙偃月刀",
    "丈八蛇矛", "方天画戟", "龙胆枪", "李广之弓", "吕布之弓",
    "龙渊剑", "流星锤", "双鞭", "霸王枪", "青冥剑",
    "开山斧", "双戟", "龙骑枪", "金火罐车", "白羽扇",
    "五火神焰扇", "芭蕉扇", "圣者宝剑", "七星剑", "镜铠",
    "黄金铠", "白银铠", "龙鳞铠", "连环铠", "霸王乌金甲",
    "蚩尤战甲", "兽面吞云铠", "亮银甲", "青云羽衣", "短打劲装",
    "凤凰羽衣", "飞龙斗袍", "青龙战袍", "天仙洞衣", "鹤氅",
    "国士无双袍", "漆黑道袍", "名士华服", "虎豹嘶风铠", "上将铠",
    "贯日袍", "白银盾", "风神盾", "淮南子", "风车轮",
    "诸葛巾", "精铁盔", "的卢", "绝影", "赤兔",
    "爪黄飞电", "照夜玉狮子", "飞刀", "孟德新书", "六韬",
    "三略", "太平清领书", "遁甲天书", "孙子兵法", "青囊书",
    "玉玺", "青龙宝玉", "朱雀宝玉", "玄武宝玉", "白虎宝玉",
)
EQUIPMENT_CATEGORY_NAMES = (
    "剑", "佩剑", "刀", "枪", "弓", "炮车", "扇", "法剑",
    "铠甲", "衣服", "辅助",
)
EQUIPMENT_CATEGORY_BY_NAME = {
    **{name: "剑" for name in ("倚天剑", "雌雄双剑", "青冥剑")},
    **{name: "佩剑" for name in ("青釭剑", "龙渊剑")},
    **{
        name: "刀"
        for name in ("古锭刀", "青龙偃月刀", "流星锤", "双鞭", "双戟")
    },
    **{
        name: "枪"
        for name in (
            "丈八蛇矛", "方天画戟", "龙胆枪", "霸王枪", "开山斧",
            "龙骑枪",
        )
    },
    **{name: "弓" for name in ("李广之弓", "吕布之弓")},
    "金火罐车": "炮车",
    **{name: "扇" for name in ("白羽扇", "五火神焰扇", "芭蕉扇")},
    **{name: "法剑" for name in ("圣者宝剑", "七星剑")},
    **{
        name: "铠甲"
        for name in (
            "镜铠", "黄金铠", "白银铠", "龙鳞铠", "连环铠",
            "霸王乌金甲", "蚩尤战甲", "兽面吞云铠", "亮银甲",
            "虎豹嘶风铠", "上将铠",
        )
    },
    **{
        name: "衣服"
        for name in (
            "青云羽衣", "短打劲装", "凤凰羽衣", "飞龙斗袍",
            "青龙战袍", "天仙洞衣", "鹤氅", "国士无双袍",
            "漆黑道袍", "名士华服", "贯日袍",
        )
    },
}
EQUIPMENT_SETS = (
    ("追击套装", ("倚天剑", "太平清领书", "古锭刀", "黄金铠", "绝影")),
    ("传承套装", ("凤凰羽衣", "遁甲天书", "爪黄飞电", "流星锤")),
    ("吕布套装", ("方天画戟", "吕布之弓", "兽面吞云铠", "赤兔")),
    ("诸葛亮套装", ("白羽扇", "鹤氅", "诸葛巾")),
    ("赵云套装", ("龙胆枪", "亮银甲", "照夜玉狮子")),
    ("刘备套装", ("雌雄双剑", "的卢")),
    ("关羽套装", ("青龙偃月刀", "青龙战袍", "赤兔")),
    ("张飞套装", ("丈八蛇矛",)),
)
GOOD_EQUIPMENT_SKILL_MARKERS = (
    "未知", "特效", "二次行动", "免疫", "自动使用", "唯我独尊",
    "神魔附体5", "强化成长-全能力", "自动提升全能力",
    "提升周围-全能力", "如履平地", "纵横无阻", "破甲攻击",
)
ABILITY_MASK_NAMES = {
    0x05: "攻精",
    0x06: "防精",
    0x09: "攻爆",
    0x0A: "防爆",
    0x12: "防士",
    0x15: "攻精士",
    0x18: "爆士",
    0x2A: "防爆移",
    0x30: "士移",
    0x3F: "全能力",
}
STRATEGY_NAMES = {
    1: "烈火",
    3: "火龙",
    13: "风龙",
    20: "诱惑",
    31: "谎报",
    33: "毒烟",
    35: "定身",
    37: "封咒",
    79: "狂雷",
    80: "雷阵",
}
FIXED_EQUIPMENT_EFFECTS = {
    0x29: "突击先手",
    0x2A: "如履平地",
    0x2C: "中毒破士",
    0x2D: "麻痹破爆",
    0x2E: "封策破精",
    0x31: "致命一击ALL",
    0x36: "引导攻击",
    0x37: "策略随心",
    0x3B: "策略模仿",
    0x40: "防御远距攻击",
    0x41: "防御特殊攻击",
    0x42: "主动连击",
    0x46: "自动使用-粟",
    0x47: "束缚破攻",
    0x48: "削铁如泥ALL",
    0x49: "异常攻击",
    0x4F: "策略免疫",
    0x50: "百战不殆",
    0x53: "策略穿透",
    0x5A: "二次行动",
    0x5B: "纵横无阻",
    0x5D: "穿越偷袭",
    0x5E: "破坏状态攻击",
    0x61: "唯我独尊",
    0x62: "策略连击",
    0x6A: "反击成双",
    0x6C: "学会策略",
    0x75: "特效屏蔽",
    0x76: "拓展范围",
}
FORMATTED_EQUIPMENT_EFFECTS = {
    0x1A: ("恢复HP状态", "%", 0),
    0x1D: ("迅捷之勇", "%", 0),
    0x1F: ("破甲攻击", "%", 1),
    0x20: ("提升攻击力+", "%", 0),
    0x21: ("提升防御力+", "%", 0),
    0x22: ("提升精神力+", "%", 0),
    0x23: ("辅爆强连+", "%", 0),
    0x24: ("辅士猛击+", "%", 0),
    0x25: ("HP上限+", "%", 0),
    0x2B: ("混乱攻击", "%", 0),
    0x30: ("昭威奋烈", "", 0),
    0x32: ("远距攻击", "", 0),
    0x35: ("增伤强命+", "%", 0),
    0x38: ("强化元素策略", "%", 0),
    0x39: ("节约MP-", "%", 0),
    0x3C: ("辅助妨碍策略+", "%", 0),
    0x3D: ("辅助攻击格挡", "%", 0),
    0x3E: ("辅助策略格挡", "%", 0),
    0x3F: ("辅助全格挡", "%", 0),
    0x43: ("减轻策略损伤-", "%", 0),
    0x44: ("MP防御+", "", 0),
    0x4A: ("步兵克制", "%", 0),
    0x4B: ("盾反破防", "%", 0),
    0x4C: ("状态强化", "", 0),
    0x4D: ("疾风迅雷", "", 0),
    0x4E: ("绝对克制", "%", 0),
    0x52: ("治愈光环", "%", 0),
    0x54: ("属性增伤", "%", 0),
    0x56: ("奇正相生", "%", 0),
    0x57: ("骑马克制", "%", 0),
    0x58: ("援护攻击", "", 0),
    0x59: ("反弹伤害异常", "%", 0),
    0x5C: ("神魔附体", "", 0),
    0x5F: ("冲锋再动", "%", 0),
    0x60: ("物理减伤", "%", 0),
    0x63: ("同仇敌忾", "", 0),
    0x64: ("众志成城", "%", 0),
    0x65: ("吸血攻击", "%", 0),
    0x68: ("回马强反", "%", 0),
    0x69: ("一夫当关", "%", 0),
    0x6B: ("怀恨必中", "%", 0),
    0x6D: ("鬼神之勇", "%", 0),
    0x71: ("万夫莫敌", "%", 0),
    0x72: ("限制伤害", "", 0),
    0x73: ("转移伤害", "%", 0),
}

JOB_MAP = {
    0: ("群雄", 8, "ALL_ROUNDER"),
    3: ("轻步兵", 6, "WARRIOR"),
    6: ("弓兵", 5, "WARRIOR"),
    9: ("轻骑兵", 5, "WARRIOR"),
    12: ("弓骑兵", 5, "WARRIOR"),
    15: ("轻炮车", 8, "WARRIOR"),
    18: ("游侠", 6, "WARRIOR"),
    21: ("山贼", 4, "WARRIOR"),
    24: ("策士", 7, "MASTER"),
    27: ("医师", 7, "MASTER"),
    30: ("道士", 7, "MASTER"),
    33: ("骑策士", 7, "ALL_ROUNDER"),
    36: ("女侍", 4, "MASTER"),
    39: ("刀兵", 6, "WARRIOR"),
    42: ("枪兵", 4, "WARRIOR"),
    45: ("先锋兵", 5, "WARRIOR"),
    48: ("水贼", 4, "WARRIOR"),
    51: ("轻战车", 6, "WARRIOR"),
    54: ("重骑兵", 6, "WARRIOR"),
    57: ("校尉", 6, "ALL_ROUNDER"),
    60: ("西凉骑", 5, "WARRIOR"),
    61: ("勇将", 9, "WARRIOR"),
    62: ("游牧骑", 9, "WARRIOR"),
    63: ("驯兽师", 7, "WARRIOR"),
    64: ("杀手", 7, "WARRIOR"),
    65: ("都督", 9, "ALL_ROUNDER"),
    66: ("咒术师", 9, "MASTER"),
    67: ("玉龙军", 9, "ALL_ROUNDER"),
    68: ("辎重队", 9, "ALL_ROUNDER"),
    69: ("神羿骑", 7, "WARRIOR"),
    70: ("机关", 7, "WARRIOR"),
    71: ("名将", 9, "ALL_ROUNDER"),
    72: ("皇帝", 10, "ALL_ROUNDER"),
    73: ("虎豹骑", 9, "WARRIOR"),
    74: ("穿杨手", 7, "WARRIOR"),
    75: ("虎贲军", 8, "WARRIOR"),
    76: ("力士", 8, "WARRIOR"),
    77: ("云川卫", 8, "WARRIOR"),
    78: ("宿卫骑", 9, "WARRIOR"),
    79: ("魔王", 12, "ALL_ROUNDER"),
}

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


def skill_name_groups(task_module) -> tuple[set[str], set[str], set[str]]:
    from models.CczModels import CCZ_MODELS

    carry_names: set[str] = set()
    strong_names: set[str] = set()
    special_names: set[str] = set()
    for skill in CCZ_MODELS.skills:
        if task_module.CczUtils.isSkillSpecial(skill):
            special_names.add(skill.name)
        if task_module.CczUtils.isSkillImba(skill):
            strong_names.add(skill.name)
        elif task_module.CczUtils.isSkillCarry(skill):
            carry_names.add(skill.name)
    return carry_names, strong_names, special_names


def skill_score_catalog() -> tuple[tuple[str, float, str], ...]:
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
        seen = set()
        for skill in CCZ_MODELS.skills:
            if skill.name in seen:
                continue
            seen.add(skill.name)
            if task_module.CczUtils.isSkillSpecial(skill):
                default_score, category = 5.0, "特殊"
            elif task_module.CczUtils.isSkillImba(skill):
                default_score, category = 2.0, "强力"
            elif task_module.CczUtils.isSkillCarry(skill):
                default_score, category = 1.0, "优质"
            else:
                default_score, category = 0.0, "其他"
            catalog.append((skill.name, default_score, category))
        _SKILL_SCORE_CATALOG = tuple(catalog)
        return _SKILL_SCORE_CATALOG


def effective_member_skill_names(task_module, members) -> list[str]:
    names: list[str] = []
    for member in members:
        for skill in member.skillList:
            if (
                member.cczType == task_module.CczType.WARRIOR
                and skill.type == task_module.CczType.MASTER
            ) or (
                member.cczType == task_module.CczType.MASTER
                and skill.type == task_module.CczType.WARRIOR
            ):
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
        effective_member_skill_names(task_module, members),
    )


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)
WINDOW_DESKTOP = 0
RESULT_RUN_STAMP = ""
RESULT_ROOT: Path | None = None
RESULT_PANEL_DIR: Path | None = None
RESULT_GRID_FILE: Path | None = None
STOP_REQUESTED = False
RESULT_BASE_DIR: Path | None = None
DIAGNOSTIC_LOG_PATH: Path | None = None
DIAGNOSTIC_LOCK = threading.Lock()
UNKNOWN_EQUIPMENT_EFFECTS: set[tuple[int, int]] = set()
CWP_SKIPINVISIBLE = 0x0001
CWP_SKIPDISABLED = 0x0002
CWP_SKIPTRANSPARENT = 0x0004


class Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


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
    if DIAGNOSTIC_LOG_PATH is None:
        return
    record = {
        "time": dt.datetime.now().isoformat(timespec="milliseconds"),
        "event": event,
        **fields,
    }
    try:
        line = json.dumps(
            record,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        )
        with DIAGNOSTIC_LOCK:
            with DIAGNOSTIC_LOG_PATH.open(
                "a", encoding="utf-8", newline="\n"
            ) as file:
                file.write(line + "\n")
    except Exception:
        pass


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


def bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "original"
    return source_root().parent / "exe-analysis" / "tool.exe_extracted"


def source_root() -> Path:
    return Path(__file__).resolve().parents[1]


def source_entry_path() -> Path:
    return source_root() / "fast_randomizer.py"


def native_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "native"
    return source_root() / "native"


def ui_asset_path(name: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / name
    return source_root() / "resources" / "app" / name


def native_control_error_hint(return_code: int) -> str:
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


class NativeControlError(RuntimeError):
    def __init__(self, return_code: int, details: str = "") -> None:
        self.return_code = return_code
        self.details = details
        super().__init__(
            f"静默控件模块执行失败，代码 {return_code}"
            + (f"：{details}" if details else "")
            + native_control_error_hint(return_code)
        )


class NativeControlTimeout(RuntimeError):
    pass


class InteractionNotTriggered(RuntimeError):
    """The game accepted background input without advancing randomization."""


def run_native_control(pid: int, arguments: list[str]) -> None:
    injector = native_dir() / "ccz_injector.exe"
    control_dll = native_dir() / "ccz_control.dll"
    if not injector.is_file() or not control_dll.is_file():
        raise FileNotFoundError("静默控件模块缺失")
    timeout = 70 if arguments and arguments[0] in {
        "openload", "real-load", "dispatch-state", "title-load",
        "silent-burst", "pulse-burst"
    } else 8
    command = [
        str(injector),
        str(pid),
        str(control_dll),
        *arguments,
    ]
    started = time.perf_counter()
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
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
            stdout=(exc.stdout or b"").decode(errors="replace"),
            stderr=(exc.stderr or b"").decode(errors="replace"),
        )
        raise NativeControlTimeout(
            "静默控件模块响应超时"
            + native_control_error_hint(-1)
        ) from exc
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
    diagnostic_log(
        "native_control_completed",
        pid=pid,
        action=arguments,
        elapsed_ms=elapsed_ms,
        stdout=result.stdout.decode(errors="replace").strip(),
        stderr=result.stderr.decode(errors="replace").strip(),
    )


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
) -> None:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return
    run_native_control(
        pid.value,
        [
            "silent-burst",
            str(hwnd),
            str(client_x),
            str(client_y),
            str(count),
        ],
    )


def native_wake_game(pid: int, hwnd: int, duration_ms: int = 1500) -> None:
    run_native_control(
        pid,
        ["wake", str(hwnd), str(duration_ms)],
    )


def native_direct_load(pid: int, slot: int) -> None:
    run_native_control(pid, ["load", str(slot)])


def native_direct_save(pid: int, slot: int) -> None:
    run_native_control(pid, ["save", str(slot)])


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


def find_process_id(exe_name: str) -> int | None:
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot == wintypes.HANDLE(-1).value:
        return None
    try:
        entry = ProcessEntry32()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return None
        while True:
            if entry.szExeFile.casefold() == exe_name.casefold():
                return int(entry.th32ProcessID)
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                return None
    finally:
        kernel32.CloseHandle(snapshot)


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
    if find_process_id(GAME_EXE_NAME) is not None:
        raise RuntimeError(
            "检测到游戏正在运行。\n\n"
            "请先关闭游戏，再点击“开始随机”。"
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

    missing_components = [
        path.name
        for path in (
            native_dir() / "ccz_injector.exe",
            native_dir() / "ccz_control.dll",
        )
        if not path.is_file()
    ]
    if not bundle_root().is_dir():
        missing_components.append("运行组件")
    if missing_components:
        raise RuntimeError(
            "工具运行文件不完整，缺少："
            + "、".join(missing_components)
            + "。\n\n请重新获取完整的工具程序。"
        )

    ensure_directory_writable(game_dir, "游戏目录")
    ensure_directory_writable(save_dir, "存档目录")
    read_only_saves = []
    for slot in range(1, 16):
        target = save_dir / f"SV{slot:03}.E5S"
        attributes = (
            getattr(target.stat(), "st_file_attributes", 0)
            if target.exists()
            else 0
        )
        if attributes & 0x1:
            read_only_saves.append(str(slot))
    if read_only_saves:
        raise RuntimeError(
            "以下结果存档被设置为只读，无法覆盖："
            + "、".join(read_only_saves)
            + "。\n\n请取消这些存档文件的“只读”属性后重试。"
        )

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
        self.use_isolated_desktop = (
            os.environ.get("CCZ_USE_ISOLATED_DESKTOP", "1") != "0"
        )
        self.background_render = (
            os.environ.get("CCZ_BACKGROUND_RENDER") == "1"
        )
        self.desktop_name = f"CCZFast_{os.getpid()}_{time.time_ns()}"

    def __enter__(self) -> "HiddenGameSession":
        global WINDOW_DESKTOP
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
            str(self.executable),
            command_line,
            None,
            None,
            False,
            CREATE_SUSPENDED,
            None,
            str(self.executable.parent),
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
                try:
                    run_native_control(self.pid, ["mute-audio"])
                    diagnostic_log("game_audio_muted", pid=self.pid)
                except Exception as exc:
                    diagnostic_log(
                        "game_audio_mute_failed",
                        pid=self.pid,
                        error=repr(exc),
                    )
                    if isinstance(exc, NativeControlError):
                        raise
                    print(
                        "提示：后台游戏静音设置未生效，"
                        "本次运行可能仍会有游戏声音。"
                    )
            if kernel32.ResumeThread(process_info.hThread) == 0xFFFFFFFF:
                raise ctypes.WinError(ctypes.get_last_error())
        except Exception:
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
            for hwnd in process_windows(self.pid, visible_only=False):
                if window_class(hwnd) == "SOUSOU":
                    self.main_window = hwnd
                    break
            if self.main_window:
                break
            if kernel32.WaitForSingleObject(self.process, 0) == 0:
                raise RuntimeError("静默游戏实例启动后立即退出")
            time.sleep(0.01)
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
        time.sleep(0.25)

        foreground_after = user32.GetForegroundWindow()
        if window_process_id(foreground_after) == self.pid:
            raise RuntimeError(
                "静默游戏抢占了前台窗口，已停止测试"
            )
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
    try:
        native_silent_click(
            pid,
            game,
            CONFIRM_FIRST_CLIENT_POSITION[0],
            CONFIRM_FIRST_CLIENT_POSITION[1],
            tail_delay_ms=0,
        )
    except (NativeControlError, NativeControlTimeout) as exc:
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
    if current != before and any(current):
        return current

    diagnostic_log(
        "fast_choice_click_no_change",
        pid=pid,
        attempt=interaction_attempt,
        jobs=current,
    )
    native_silent_click(
        pid,
        game,
        CONFIRM_FIRST_CLIENT_POSITION[0],
        CONFIRM_FIRST_CLIENT_POSITION[1],
    )
    return read_job_ids(pid, active_positions)


def read_skill_ids(pid: int, skill_count: int) -> tuple[tuple[int, ...], ...]:
    size = TEAM_MEMBER_NUM * SKILLS_PER_MEMBER * SKILL_RECORD_SIZE
    data = read_memory(pid, SKILL_OFFSET, size)
    members = []
    for member_index in range(TEAM_MEMBER_NUM):
        skill_ids = []
        for skill_index in range(SKILLS_PER_MEMBER):
            offset = (
                member_index * SKILLS_PER_MEMBER + skill_index
            ) * SKILL_RECORD_SIZE
            skill_id = struct.unpack_from("<H", data, offset)[0]
            if skill_id < skill_count:
                skill_ids.append(skill_id)
        members.append(tuple(skill_ids))
    return tuple(members)


def read_equipment_records(pid: int) -> tuple[bytes, ...]:
    data = read_memory(pid, EQUIPMENT_OFFSET, EQUIPMENT_SIZE)
    records = [
        data[index * 4 : (index + 1) * 4]
        for index in range(46)
    ]
    second_offset = 46 * 4
    records.extend(
        data[
            second_offset + index * 8 :
            second_offset + (index + 1) * 8
        ]
        for index in range(24)
    )
    if len(records) != len(EQUIPMENT_NAMES) or any(
        len(record) not in (4, 8) for record in records
    ):
        raise RuntimeError("宝物内存记录长度异常")
    return tuple(records)


def decode_equipment_effect(code: int, parameter: int) -> str:
    fixed = FIXED_EQUIPMENT_EFFECTS.get(code)
    if fixed is not None:
        return fixed

    formatted = FORMATTED_EQUIPMENT_EFFECTS.get(code)
    if formatted is not None:
        prefix, suffix, adjustment = formatted
        return f"{prefix}{parameter + adjustment}{suffix}"

    if code in (0x1C, 0x51, 0x66, 0x6E, 0x7A):
        mask_name = ABILITY_MASK_NAMES.get(parameter)
        if mask_name is None:
            return f"能力组合0x{parameter:02X}"
        prefixes = {
            0x1C: "HP辅助",
            0x51: "提升周围",
            0x66: "自动提升",
            0x6E: "MP辅助",
            0x7A: "忽视能力",
        }
        separator = "" if code == 0x1C and parameter in (0x05, 0x09) else "-"
        if code == 0x66 and parameter == 0x3F:
            separator = ""
        return f"{prefixes[code]}{separator}{mask_name}"

    if code == 0x33:
        return {
            4: "穿透攻击-两格",
            7: "穿透攻击-三格",
            9: "穿透攻击-横扫",
        }.get(parameter, f"穿透攻击-{parameter}")
    if code == 0x70:
        return {
            4: "弱点攻击-爆发",
            5: "弱点攻击-士气",
        }.get(parameter, f"弱点攻击-{parameter}")
    if code in (0x77, 0x78, 0x79):
        strategy = STRATEGY_NAMES.get(parameter, f"策略编号{parameter}")
        prefix = {
            0x77: "攻击追加",
            0x78: "策略先手",
            0x79: "策略反击",
        }[code]
        return f"{prefix}-{strategy}"
    if code == 0x7B:
        return {
            0x02: "能力辅助-攻-防",
            0x11: "能力辅助-防-攻",
            0x22: "能力辅助-精-防",
            0x33: "能力辅助-爆-攻防",
            0x45: "能力辅助-士-攻精",
        }.get(parameter, f"能力辅助-0x{parameter:02X}")
    if code == 0x7C:
        return {
            0x04: "能力替换-攻-精",
            0x10: "能力替换-攻-士",
            0x11: "能力替换-防-攻",
            0x14: "能力替换-防-精",
            0x22: "能力替换-精-防",
        }.get(parameter, f"能力替换-0x{parameter:02X}")
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
    categories = {name: [] for name in EQUIPMENT_CATEGORY_NAMES}
    effects = {}
    for index, (name, record) in enumerate(
        zip(EQUIPMENT_NAMES, records, strict=True)
    ):
        parameter = record[2] if index < 46 else record[4]
        effect = decode_equipment_effect(record[0], parameter)
        category = EQUIPMENT_CATEGORY_BY_NAME.get(name, "辅助")
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
    started = time.perf_counter()
    diagnostic_log(
        "title_load_start",
        pid=pid,
        list_index=list_index,
        save_path=save_path,
        expected_sha256=hashlib.sha256(expected).hexdigest(),
    )
    try:
        run_native_control(pid, ["title-load", str(list_index)])
    except NativeControlTimeout as exc:
        # The load dialog can keep the injected call blocked after the
        # save has already been copied. Verify the resulting memory instead
        # of treating that transport timeout as a failed load.
        print(f"标题读档调用返回延迟，改用内存确认：{exc}")
        diagnostic_log(
            "title_load_transport_error",
            pid=pid,
            error=repr(exc),
        )

    deadline = time.perf_counter() + timeout
    checks = 0
    while time.perf_counter() < deadline:
        checks += 1
        current = read_memory(pid, 0, R0_MEMORY_SIZE)
        if current == expected:
            diagnostic_log(
                "title_load_verified",
                pid=pid,
                checks=checks,
                elapsed_ms=round(
                    (time.perf_counter() - started) * 1000
                ),
                memory_sha256=hashlib.sha256(current).hexdigest(),
            )
            return True
        time.sleep(0.1)
    diagnostic_log(
        "title_load_timeout",
        pid=pid,
        checks=checks,
        elapsed_ms=round((time.perf_counter() - started) * 1000),
        process_alive=find_process_id(GAME_EXE_NAME) == pid,
    )
    return False


def direct_load_verified(
    pid: int,
    slot_index: int,
    save_path: Path,
    timeout: float = 10.0,
) -> bool:
    expected = save_path.read_bytes()[:R0_MEMORY_SIZE]
    for attempt in range(1, 4):
        try:
            native_direct_load(pid, slot_index)
        except NativeControlTimeout as exc:
            print(f"游戏内原生直读返回延迟，改用内存确认：{exc}")
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            if read_memory(pid, 0, R0_MEMORY_SIZE) == expected:
                return True
            time.sleep(0.1)
        print(f"第 {slot_index + 1} 号存档原生直读重试 {attempt}/3")
    return False


def initialize_result_output() -> tuple[Path, Path]:
    global RESULT_RUN_STAMP, RESULT_ROOT, RESULT_PANEL_DIR, RESULT_GRID_FILE
    # Dots keep the timestamp readable while remaining valid in Windows paths.
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H.%M.%S")
    root = (RESULT_BASE_DIR or Path.cwd()) / "randResult"
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
        if not user32.PrintWindow(hwnd, memory_dc, 2):
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


def save_result_image(runner, equip_info, save_slot: int = 1) -> Path:
    load_media_modules()
    width, height = 740, 1028
    # These coordinates match the original result image: the two blue
    # separators are at x=132/133 and x=334/335, with the equipment split
    # at x=536/537.
    left_width, special_width = 132, 202
    equipment_width = width - left_width - special_width
    body_font = result_font(12)
    heading_font = result_font(13)
    # Keep all body text on the same font object and size. Smaller separately
    # rasterized fonts made the left roster and skill list visibly thinner and
    # harder to read than the equipment columns.
    small_font = body_font
    member_font = body_font
    roster_font = body_font
    roster_job_font = body_font
    line_height = 20

    probe = Image.new("RGB", (1, 1))
    probe_draw = ImageDraw.Draw(probe)

    def wrap_text(text: str, font, max_width: int) -> list[str]:
        text = str(text)
        if not text:
            return [""]
        lines = []
        current = ""
        for character in text:
            candidate = current + character
            if (
                current
                and probe_draw.textlength(candidate, font=font) > max_width
            ):
                lines.append(current)
                current = character
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines

    def special_item_texts(item) -> list[str]:
        if isinstance(item, str):
            return [item]
        if isinstance(item, (list, tuple)):
            if (
                len(item) == 2
                and isinstance(item[0], str)
                and isinstance(item[1], str)
            ):
                return [f"{item[0]}: {item[1]}"]
            if (
                len(item) == 2
                and isinstance(item[0], str)
                and isinstance(item[1], (list, tuple, set))
            ):
                result = [f"{item[0]}:"]
                for child in item[1]:
                    result.extend(special_item_texts(child))
                return result
            result = []
            for child in item:
                result.extend(special_item_texts(child))
            return result
        return [str(item)]

    special_palette = (
        (0, 0, 255),
        (255, 0, 0),
        (128, 0, 128),
        (0, 128, 0),
        (255, 0, 255),
        (0, 128, 128),
        (0, 128, 255),
        (149, 80, 30),
        (255, 0, 0),
    )
    special_blocks = []
    special_line_count = 0
    for index, (title, items) in enumerate(
        getattr(runner, "_equip_specials", ())
    ):
        block = [
            (
                line,
                heading_font,
                special_palette[index % len(special_palette)],
            )
            for line in wrap_text(
                f"{title}:", heading_font, special_width - 8
            )
        ]
        for item in items:
            for item_text in special_item_texts(item):
                for line in wrap_text(
                    item_text,
                    body_font,
                    special_width - 8,
                ):
                    block.append(
                        (
                            line,
                            body_font,
                            special_palette[index % len(special_palette)],
                        )
                    )
        block.append(("", body_font, (0, 0, 0)))
        special_blocks.append(block)
        special_line_count += len(block)

    category_blocks = []
    for items, type_name in equip_info or ():
        block = [
            (line, heading_font)
            for line in wrap_text(
                f"{type_name}:", heading_font, equipment_width // 2 - 6
            )
        ]
        for equip_name, skill_name in items:
            block.extend(
                (line, body_font)
                for line in wrap_text(
                    f"{equip_name}: {skill_name}",
                    body_font,
                    equipment_width // 2 - 6,
                )
            )
        block.append(("", body_font))
        category_blocks.append(block)

    equipment_columns = [[], []]
    equipment_lengths = [0, 0]
    for block in sorted(category_blocks, key=len, reverse=True):
        column = 0 if equipment_lengths[0] <= equipment_lengths[1] else 1
        equipment_columns[column].append(block)
        equipment_lengths[column] += len(block)

    image = Image.new("RGB", (width, height), (232, 228, 222))
    draw = ImageDraw.Draw(image)

    def draw_crisp(position, text, font, fill) -> None:
        # Render the glyph mask without subpixel anti-aliasing. This keeps the
        # small Chinese text readable after the 5x3 result image is viewed
        # scaled down.
        x, y = position
        bbox = tuple(int(value) for value in draw.textbbox((0, 0), text, font=font))
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        if width <= 0 or height <= 0:
            return
        mask = Image.new("1", (width, height), 0)
        ImageDraw.Draw(mask).text(
            (-bbox[0], -bbox[1]), text, font=font, fill=1
        )
        ink = Image.new("RGB", mask.size, fill)
        image.paste(
            ink,
            (round(x + bbox[0]), round(y + bbox[1])),
            mask,
        )

    # The old tool used the exact primary colors below.  Keeping them exact
    # matters because the result grid is also used as a visual report.
    red = (255, 0, 0)
    blue = (0, 0, 255)
    # A flat neutral background keeps the small bitmap-style text crisp.
    draw.rectangle((2, 2, left_width - 1, height - 2), fill=(211, 211, 211))
    draw.rectangle((1, 1, width - 2, height - 2), outline=red, width=3)
    draw.line((left_width, 0, left_width, height), fill=blue, width=2)
    draw.line(
        (left_width + special_width, 0, left_width + special_width, height),
        fill=blue,
        width=2,
    )
    equipment_mid = left_width + special_width + (equipment_width - 1) // 2
    draw.line(
        (equipment_mid, 0, equipment_mid, height),
        fill=blue,
        width=2,
    )

    # The original report puts the seven-person roster at the top, then uses
    # seven 130px detail sections beginning at y=98.
    detail_top = 98
    member_height = 130
    rendered_members = getattr(runner, "_team_members", ())
    member_panels = getattr(runner, "_member_panels", ())
    recognized_job_names = getattr(runner, "_job_names", ())
    three_person_mode = bool(
        getattr(runner, "_three_person_mode", False)
    )
    report_members = (
        INITIAL_TEAM_MEMBERS if three_person_mode else TEAM_MEMBERS
    )
    for index, (job_id, member) in enumerate(
        zip(runner._r0_job_ids, report_members)
    ):
        job_name = (
            recognized_job_names[index]
            if index < len(recognized_job_names)
            else JOB_MAP[job_id][0]
        )
        # Roster list in the upper two-column strip.
        roster_x = 4 if index < 7 else 68
        roster_y = 1 + (index % 7) * 14
        draw_crisp(
            (roster_x, roster_y),
            member[0],
            font=roster_font,
            fill=(0, 0, 0),
        )
        roster_job_width = draw.textlength(job_name, font=roster_job_font)
        draw_crisp(
            (left_width - 3 - roster_job_width, roster_y),
            job_name,
            font=roster_job_font,
            fill=(0, 0, 0),
        )
        top = detail_top + index * member_height
        draw.line(
            (2, top, left_width - 1, top),
            fill=(255, 255, 255),
            width=2,
        )
        if index < len(member_panels):
            panel = member_panels[index]
            if isinstance(panel, np.ndarray):
                panel = Image.fromarray(cv2.cvtColor(panel, cv2.COLOR_BGR2RGB))
            elif isinstance(panel, (str, Path)):
                with Image.open(panel) as source:
                    panel = source.convert("RGB")
            else:
                panel = panel.convert("RGB")
            if panel.size != (130, 130):
                panel = panel.resize((130, 130), Image.Resampling.NEAREST)
            image.paste(panel, (2, top))
            member_job_text = f"{member[0]}-{job_name}"
            member_job_width = draw.textlength(member_job_text, font=small_font)
            draw.rectangle(
                (2, top + 112, left_width - 1, top + 129),
                fill=(211, 211, 211),
            )
            draw_crisp(
                (left_width - 3 - member_job_width, top + 112),
                member_job_text,
                font=small_font,
                fill=(128, 0, 0),
            )
            continue
        live_member = (
            rendered_members[index]
            if index < len(rendered_members)
            else None
        )
        live_skills = list(getattr(live_member, "skillList", ()))
        detail_lines = [("个人天赋:", 0)]
        detail_lines.extend(
            (str(getattr(skill, "name", skill)), 12)
            for skill in live_skills[:3]
        )
        detail_lines.append(("兵种技能:", 0))
        detail_lines.extend(
            (str(getattr(skill, "name", skill)), 12)
            for skill in live_skills[3:6]
        )
        detail_y = top + 3
        title_y = top + 112
        for detail, indent in detail_lines:
            for line in wrap_text(
                detail,
                small_font,
                left_width - 10 - indent,
            ):
                if detail_y + 14 > title_y:
                    break
                draw_crisp(
                    (5 + indent, detail_y),
                    line,
                    font=small_font,
                    fill=(0, 0, 0),
                )
                detail_y += 14
            if detail_y + 14 > title_y:
                break
        member_job_text = f"{member[0]}-{job_name}"
        member_job_width = draw.textlength(member_job_text, font=small_font)
        draw_crisp(
            (left_width - 3 - member_job_width, title_y),
            member_job_text,
            font=small_font,
            fill=(128, 0, 0),
        )

    special_y = 2
    if three_person_mode:
        draw_crisp(
            (left_width + 4, special_y),
            "初始3人模式",
            font=heading_font,
            fill=(0, 0, 255),
        )
        special_y += line_height
    for block in special_blocks:
        for text, font, color in block:
            draw_crisp(
                (left_width + 2, special_y),
                text,
                font=font,
                fill=color,
            )
            special_y += line_height

    equipment_column_width = equipment_width // 2
    for column_index, blocks in enumerate(equipment_columns):
        x = left_width + special_width + column_index * equipment_column_width
        y = 2
        for block in blocks:
            for text, font in block:
                draw_crisp(
                    (x + 2, y),
                    text,
                    font=font,
                    fill=(0, 0, 0),
                )
                y += line_height

    draw_crisp(
        (4, height - 19),
        f"save{save_slot}",
        font=heading_font,
        fill=red,
    )

    output = result_panel_dir() / f"save{save_slot}.png"
    image.save(output, "PNG")
    return output


def compose_result_grid(panel_paths: dict[int, Path]) -> Path:
    load_media_modules()
    panel_width, panel_height = 740, 1028
    grid = Image.new(
        "RGB", (panel_width * 5, panel_height * 3), (235, 233, 228)
    )
    for slot, panel_path in sorted(panel_paths.items()):
        if not panel_path.is_file():
            continue
        with Image.open(panel_path) as source:
            panel = source.convert("RGB")
        if panel.size != (panel_width, panel_height):
            panel = panel.resize(
                (panel_width, panel_height), Image.Resampling.LANCZOS
            )
        index = slot - 1
        grid.paste(
            panel,
            ((index % 5) * panel_width, (index // 5) * panel_height),
        )
    output = result_grid_path()
    temporary = output.with_suffix(".tmp.png")
    grid.save(temporary, "PNG")
    os.replace(temporary, output)
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


def recover_stale_windows(pid: int) -> None:
    closed = False
    for hwnd in process_windows(pid):
        if window_class(hwnd) == "#32770":
            user32.PostMessageW(hwnd, 0x0010, 0, 0)
            closed = True
    if closed:
        print("已清理上轮残留窗口")
        time.sleep(0.8)


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
            user32.PostMessageW(target, 0x00F5, 0, 0)
            time.sleep(0.12)
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
        user32.PostMessageW(target, 0x0100, vk, 0)
        user32.PostMessageW(target, 0x0101, vk, 0)
        time.sleep(0.15)


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
        for hwnd in process_windows(pid):
            if (
                window_class(hwnd) == "#32770"
                and user32.FindWindowExW(
                    hwnd, 0, "SysListView32", None
                )
            ):
                return hwnd
        time.sleep(0.05)
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


def capture_interaction_failure(pid: int, game: int) -> str | None:
    if DIAGNOSTIC_LOG_PATH is None:
        return None
    output = DIAGNOSTIC_LOG_PATH.with_name(
        f"{DIAGNOSTIC_LOG_PATH.stem}_interaction_failure_"
        f"{pid}_{time.time_ns()}.png"
    )
    try:
        image = print_window_mat(game, strip_client=False)
        if image.size == 0:
            raise RuntimeError("后台游戏窗口截图为空")
        load_media_modules()
        Image.fromarray(image[:, :, ::-1]).save(output, "PNG")
        return str(output)
    except Exception as exc:
        diagnostic_log(
            "interaction_failure_capture_failed",
            pid=pid,
            hwnd=game,
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


def bundled_random_s00() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "random_s00.eex"
    return source_root() / "resources" / "app" / "random_s00.eex"


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


def run_inspection_process_once(
    game_executable: Path,
    slot: int,
    output_dir: Path,
    job_score: float,
) -> dict:
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
            return json.loads(result_file.read_text(encoding="utf-8"))
        if process.poll() is not None:
            break
        time.sleep(0.2)
    if process.poll() is None:
        process.kill()
    stdout, _ = process.communicate()
    if process.returncode != 0 or not result_file.is_file():
        detail = decode_subprocess_output(stdout).strip()[-2000:]
        raise RuntimeError(
            "候选结果界面检查失败"
            + (f"：{detail}" if detail else "")
        )
    return json.loads(result_file.read_text(encoding="utf-8"))


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
            )
        except RuntimeError as exc:
            last_error = exc
            diagnostic_log(
                "inspection_process_failed",
                slot=slot,
                attempt=attempt,
                error=repr(exc),
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
        raise RuntimeError("初始三人能力检查超时")
    if process.returncode != 0 or not result_file.is_file():
        detail = decode_subprocess_output(stdout).strip()[-2000:]
        raise RuntimeError(
            "初始三人能力检查失败"
            + (f"：{detail}" if detail else "")
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


def patch_inspection_runtime(task_module, pid: int, panel_dir: Path):
    from window.BaseWindow import BaseWindow
    from window.CczWindow import CczPeopleWindow

    panels: list[np.ndarray] = []

    def get_hwnd_by_name(self, window_name: str) -> None:
        self._BaseWindow__hwnd = find_process_window(pid, window_name)

    def no_foreground(self) -> None:
        return None

    def background_click_rect(
        self, x: int, y: int, w: int, h: int, rightClick: bool = False
    ) -> None:
        if not self.hwnd or not user32.IsWindow(self.hwnd):
            return
        rect = wintypes.RECT()
        if not user32.GetWindowRect(self.hwnd, ctypes.byref(rect)):
            return
        post_click(
            self.hwnd,
            rect.left + x + w // 2,
            rect.top + y + h // 2,
            right=rightClick,
        )

    def window_mat(
        self,
        x: int = 0,
        y: int = 0,
        w: int = 0,
        h: int = 0,
        toGray: bool = False,
    ):
        mat = print_window_mat(
            self.hwnd, x, y, w, h, strip_client=False
        )
        if toGray:
            task_module.CvUtils.transNotBlackToWhite(mat, 100)
        return mat

    def click_people(self, index: int) -> None:
        run_native_control(
            pid, ["list-window", str(self.hwnd), str(index)]
        )
        time.sleep(0.6)

    def open_people(self) -> None:
        self.initWind()
        if not self.wind.isInitSuccess():
            raise RuntimeError("候选检查阶段未找到游戏主窗口")
        for attempt in range(1, 5):
            self.initPeopleWind()
            if self.peopleWind.isInitSuccess():
                return
            native_wake_game(pid, self.wind.hwnd, 600)
            point = Point(138, 18)
            user32.ClientToScreen(self.wind.hwnd, ctypes.byref(point))
            post_click(self.wind.hwnd, point.x, point.y)
            deadline = time.perf_counter() + 3.0
            while time.perf_counter() < deadline:
                time.sleep(0.15)
                self.initPeopleWind()
                if self.peopleWind.isInitSuccess():
                    print(f"候选武将列表第 {attempt} 次尝试打开成功")
                    return
            print(f"候选武将列表第 {attempt}/4 次尝试未打开")
            native_silent_click_burst(self.wind.hwnd, 360, 400, 12)
            native_wake_game(pid, self.wind.hwnd, 800)
        windows = [
            {
                "class": window_class(hwnd),
                "title": window_text(hwnd),
                "visible": bool(user32.IsWindowVisible(hwnd)),
                "enabled": bool(user32.IsWindowEnabled(hwnd)),
            }
            for hwnd in process_windows(pid, visible_only=False)
        ]
        raise RuntimeError(
            "候选存档的武将列表连续4次未能打开；"
            f"当前窗口={windows}"
        )

    def click_info_button(hwnd: int, from_right: int) -> None:
        buttons: list[tuple[int, int]] = []
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )

        @callback_type
        def callback(child: int, _param: int) -> bool:
            if window_class(child) == "Button":
                rect = wintypes.RECT()
                if user32.GetWindowRect(child, ctypes.byref(rect)):
                    buttons.append((rect.left, child))
            return True

        user32.EnumChildWindows(hwnd, callback, 0)
        if len(buttons) < from_right:
            raise RuntimeError("武将能力窗口按钮不完整")
        buttons.sort()
        target_button = buttons[-from_right]
        user32.PostMessageW(target_button[1], BM_CLICK, 0, 0)

    BaseWindow.setForeground = no_foreground
    BaseWindow._BaseWindow__getHwndbyName = get_hwnd_by_name
    BaseWindow.clickRect = background_click_rect
    BaseWindow.moveMouseToEnd = no_foreground
    BaseWindow.getMat = window_mat
    CczPeopleWindow.clickPeople = click_people
    task_module.KeyboardUtils.tapKey = lambda key: post_key_to_game(pid, key)
    task_module.CczReRandTask.openPeople = open_people
    return panels, click_info_button


def wait_for_window_state(
    hwnd: int,
    *,
    exists: bool | None = None,
    enabled: bool | None = None,
    timeout: float = 3.0,
) -> bool:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        is_window = bool(hwnd and user32.IsWindow(hwnd))
        if exists is not None and is_window != exists:
            time.sleep(0.05)
            continue
        if enabled is not None:
            if not is_window or bool(user32.IsWindowEnabled(hwnd)) != enabled:
                time.sleep(0.05)
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


def click_dialog_button(hwnd: int, text: str) -> None:
    button = find_dialog_button(hwnd, text)
    if button:
        user32.SendMessageW(button, BM_CLICK, 0, 0)
        return

    fallback_rects = {
        "上一武将": (290, 350, 18, 56),
        "下一武将": (411, 350, 18, 56),
    }
    fallback = fallback_rects.get(text)
    if fallback and user32.IsWindow(hwnd):
        x, y, width, height = fallback
        rect = wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            diagnostic_log(
                "dialog_button_coordinate_fallback",
                hwnd=hwnd,
                button_text=text,
                window_rect=(
                    rect.left,
                    rect.top,
                    rect.right,
                    rect.bottom,
                ),
            )
            post_click(
                hwnd,
                rect.left + x + width // 2,
                rect.top + y + height // 2,
            )
            return

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
        if user32.IsWindow(hwnd) and dialog_has_text(hwnd, text):
            return True
        time.sleep(0.05)
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
        click_dialog_button(info_hwnd, "下一武将")
        deadline = time.perf_counter() + 1.5
        while time.perf_counter() < deadline:
            expected_hwnd = find_member_dialog(pid, expected_name)
            if expected_hwnd:
                return expected_hwnd
            shown_name = current_dialog_member(info_hwnd, member_names)
            if shown_name and shown_name != current_name:
                raise RuntimeError(
                    f"武将顺序异常：应为{expected_name}，实际为{shown_name}"
                )
            time.sleep(0.05)
        time.sleep(0.2)
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
    for _ in range(3):
        click_dialog_button(info_hwnd, "下一武将")
        deadline = time.perf_counter() + 2.0
        while time.perf_counter() < deadline:
            shown_name = current_dialog_member(info_hwnd, member_names)
            if (
                shown_name
                and shown_name != current_name
                and shown_name not in captured_names
            ):
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
                return candidate_hwnd, candidate_name
            time.sleep(0.05)
        time.sleep(0.2)
    shown_name = current_dialog_member(info_hwnd, member_names)
    raise RuntimeError(
        "切换到下一武将失败，"
        f"当前仍为{shown_name or current_name or '未知武将'}"
    )


def close_member_dialog(pid: int, main_window: int, info_hwnd: int) -> None:
    button = find_dialog_button(info_hwnd, "确定")
    if button:
        control_id = user32.GetDlgCtrlID(button)
        user32.SendMessageW(
            info_hwnd,
            0x0111,
            control_id,
            button,
        )
    if wait_for_window_state(info_hwnd, exists=False, timeout=1.5):
        return
    native_end_dialog(pid, info_hwnd)
    if not wait_for_window_state(info_hwnd, exists=False, timeout=3.0):
        raise RuntimeError("武将能力窗口未能关闭")


def capture_initial_member_panels(
    task_module,
    pid: int,
    main_window: int,
    runner,
) -> tuple:
    member_names = tuple(member[0] for member in INITIAL_TEAM_MEMBERS)
    info_hwnd = 0
    for attempt in range(1, 5):
        runner.openPeople()
        if runner.peopleWind.isInitSuccess():
            break
        native_wake_game(pid, main_window, 600)
        time.sleep(0.2)
    else:
        raise RuntimeError("初始三人检查未能打开武将列表")
    try:
        run_native_control(
            pid,
            ["list-window", str(runner.peopleWind.hwnd), "0"],
        )
        time.sleep(0.6)
        deadline = time.perf_counter() + 8.0
        shown_name = ""
        while time.perf_counter() < deadline:
            runner.initPeopleInfoWind()
            info_hwnd, shown_name = find_any_member_dialog(
                pid, member_names
            )
            if info_hwnd:
                break
            time.sleep(0.05)
        if not info_hwnd:
            raise RuntimeError("初始三人检查未能打开曹操能力窗口")

        panels = []
        members = initial_team_members(task_module.TEAM_MEMBER_LIST)
        for index, expected_name in enumerate(member_names):
            shown_name = current_dialog_member(info_hwnd, member_names)
            if shown_name != expected_name:
                raise RuntimeError(
                    "初始三人能力窗口顺序不一致："
                    f"应为{expected_name}，实际为{shown_name or '未知武将'}"
                )
            runner.peopleInfoWind._BaseWindow__hwnd = info_hwnd
            if not wait_for_window_state(
                info_hwnd, exists=True, enabled=True, timeout=3.0
            ):
                raise RuntimeError(
                    f"{expected_name}能力窗口不可用"
                )
            skill_list = []
            for skill_mat in runner.peopleInfoWind.getSkillMatList():
                skill = task_module.CczUtils.getCczSkillWithMat(skill_mat)
                if skill is not None:
                    skill_list.append(skill)
            members[index].skillList = sorted(
                skill_list,
                key=lambda skill: skill.score,
                reverse=True,
            )
            panel = runner.peopleInfoWind.getAllSkillMat()
            if panel is None or not getattr(panel, "size", 0):
                raise RuntimeError(
                    f"{expected_name}能力信息未能读取"
                )
            panels.append(panel.copy())
            diagnostic_log(
                "initial_member_panel_captured",
                pid=pid,
                member=expected_name,
                index=index,
                shape=getattr(panel, "shape", None),
                skills=[skill.name for skill in members[index].skillList],
            )
            if index + 1 < len(member_names):
                info_hwnd = advance_people_info(
                    pid,
                    main_window,
                    info_hwnd,
                    expected_name,
                    member_names[index + 1],
                    member_names,
                )
        return tuple(panels), members
    finally:
        if info_hwnd and user32.IsWindow(info_hwnd):
            close_member_dialog(pid, main_window, info_hwnd)
        people_hwnd = getattr(
            getattr(runner, "peopleWind", None), "hwnd", 0
        )
        if people_hwnd and user32.IsWindow(people_hwnd):
            runner.closePeopleWindow()
            time.sleep(0.3)
        current_main = find_process_window_by_class(pid, "SOUSOU")
        if current_main:
            try:
                native_wake_game(pid, current_main, 500)
            except RuntimeError as exc:
                diagnostic_log(
                    "initial_member_cleanup_wake_failed",
                    pid=pid,
                    error=repr(exc),
                )


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
        time.sleep(0.8)
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
    load_media_modules()
    output_dir.mkdir(parents=True, exist_ok=True)
    random_script = bundled_random_s00()
    if not random_script.is_file():
        raise FileNotFoundError("工具内缺少随机流程辅助文件")
    script_targets = (
        game_executable.parent / "RS" / "S_00.eex",
    )
    manage_script = os.environ.get("CCZ_SKIP_S00") != "1"
    backups = (
        {
            target: target.read_bytes() if target.is_file() else None
            for target in script_targets
        }
        if manage_script
        else {}
    )
    try:
        if manage_script:
            for target in script_targets:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(random_script, target)

        install(bundle_root())
        import task.CczReRandTask as task_module
        rules = load_rule_config(app_dir()).config

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

        with HiddenGameSession(game_executable) as game:
            panels, click_info_button = patch_inspection_runtime(
                task_module, game.pid, output_dir
            )
            time.sleep(1.2)
            if not title_load_verified(game.pid, slot - 1, save_path):
                raise RuntimeError("候选存档未能完成后台读取")
            time.sleep(0.8)
            before_jump_memory = read_memory(game.pid, 0, R0_MEMORY_SIZE)

            runner = task_module.CczReRandTask(0)
            runner.savePos = slot
            runner.initWind()
            post_key_to_game(game.pid, "z")
            native_wake_game(game.pid, game.main_window, 500)
            time.sleep(0.3)
            if not runner.jumpR0():
                raise RuntimeError("候选存档未能进入完整武将检查阶段")
            time.sleep(0.5)
            native_silent_click_burst(
                game.main_window, 360, 400, 80
            )
            native_wake_game(game.pid, game.main_window, 500)
            time.sleep(0.5)
            write_cv_image(
                output_dir / "after-jump.png",
                print_window_mat(game.main_window),
            )
            runner.openPeople()
            write_cv_image(
                output_dir / "people-window.png",
                print_window_mat(runner.peopleWind.hwnd),
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
            for member, job_id in zip(
                task_module.TEAM_MEMBER_LIST, job_ids
            ):
                job_name, score, job_type = JOB_MAP[job_id]
                member.job = SimpleNamespace(
                    name=job_name,
                    score=score,
                    type=job_type,
                )
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
            captured_names: set[str] = set()
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
                        time.sleep(0.05)
                if not info_hwnd:
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
                for skill_mat in runner.peopleInfoWind.getSkillMatList():
                    skill = task_module.CczUtils.getCczSkillWithMat(skill_mat)
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
                if member_index is not None:
                    carry_count = 0
                    imba_count = 0
                    special_count = 0
                    for skill in member.skillList:
                        if task_module.CczUtils.isSkillSpecial(skill):
                            special_count += 1
                        if not (
                            task_module.CczUtils.isSkillCarry(skill)
                            or task_module.CczUtils.isSkillImba(skill)
                        ):
                            continue
                        if (
                            member.cczType
                            == task_module.CczType.WARRIOR
                            and skill.type == task_module.CczType.MASTER
                        ) or (
                            member.cczType
                            == task_module.CczType.MASTER
                            and skill.type == task_module.CczType.WARRIOR
                        ):
                            continue
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
                        "panel": str(
                            output_dir / f"member-{panel_index + 1}.png"
                        ),
                        "carry_count": carry_count,
                        "imba_count": imba_count,
                        "special_count": special_count,
                        "effective_skills": [
                            skill.name
                            for skill in member.skillList
                            if not (
                                (
                                    member.cczType
                                    == task_module.CczType.WARRIOR
                                    and skill.type
                                    == task_module.CczType.MASTER
                                )
                                or (
                                    member.cczType
                                    == task_module.CczType.MASTER
                                    and skill.type
                                    == task_module.CczType.WARRIOR
                                )
                            )
                        ],
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
        return 0
    finally:
        for target, content in backups.items():
            if content is None:
                if target.exists():
                    target.unlink()
            else:
                target.write_bytes(content)


def patch_runtime(
    task_module,
    pid: int,
    three_person_mode: bool = False,
    rules: dict | None = None,
) -> None:
    from window.BaseWindow import BaseWindow
    from window.CczWindow import CczPeopleWindow

    if not hasattr(task_module.CczReRandTask, "_ccz_original_check_r0"):
        task_module.CczReRandTask._ccz_original_check_r0 = (
            task_module.CczReRandTask.checkPeopleAtR0
        )
        task_module.CczReRandTask._ccz_original_version_check = (
            task_module.CczReRandTask.checkCczVersion
        )
    if not hasattr(BaseWindow, "_ccz_original_get_mat"):
        BaseWindow._ccz_original_get_mat = BaseWindow.getMat
    original_check = task_module.CczReRandTask._ccz_original_check_r0
    original_version_check = (
        task_module.CczReRandTask._ccz_original_version_check
    )
    original_get_mat = BaseWindow._ccz_original_get_mat
    rules = rules or default_rule_config()
    game_path = process_executable(pid)
    if game_path is None:
        raise RuntimeError("无法定位游戏目录")
    source_save = game_path.parent / "SV" / "SV020.E5S"
    source_memory = source_save.read_bytes()[:R0_MEMORY_SIZE]

    def get_hwnd_by_name(self, window_name: str) -> None:
        self._BaseWindow__hwnd = find_process_window(pid, window_name)

    def set_foreground(self) -> None:
        return None

    def silent_click_rect(
        self, x: int, y: int, w: int, h: int, rightClick: bool = False
    ) -> None:
        if not self.hwnd or not user32.IsWindow(self.hwnd):
            return
        point = Point(x + w // 2, y + h // 2)
        user32.ClientToScreen(self.hwnd, ctypes.byref(point))
        post_click(
            self.hwnd,
            point.x,
            point.y,
            right=rightClick,
        )

    def silent_move_mouse_to_end(self) -> None:
        return None

    def robust_get_mat(
        self,
        x: int = 0,
        y: int = 0,
        w: int = 0,
        h: int = 0,
        toGray: bool = False,
    ):
        try:
            mat = original_get_mat(self, x, y, w, h, toGray)
            if mat.size and np.std(mat) > 1:
                return mat
        except Exception:
            pass
        mat = print_window_mat(self.hwnd, x, y, w, h)
        if toGray:
            task_module.CvUtils.transNotBlackToWhite(mat, 100)
        return mat

    def click_relative_hwnd(
        hwnd: int, x: int, y: int, w: int, h: int, count: int = 1
    ) -> None:
        rect = wintypes.RECT()
        if not hwnd or not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return
        post_click(
            hwnd,
            rect.left + x + w // 2,
            rect.top + y + h // 2,
            count=count,
        )

    def robust_load_and_confirm(self, index: int) -> None:
        game = self.wind.hwnd if getattr(self, "wind", None) else 0
        if not game:
            raise RuntimeError("读档前未找到游戏主窗口")
        activate_hidden_window(game)
        user32.PostMessageW(game, 0x0111, 102, 0)
        load_window = wait_list_dialog(pid, 3)
        if not load_window:
            raise RuntimeError("读取进度窗口未出现")
        activate_hidden_window(load_window)
        native_load_dialog_item(pid, index)

        deadline = time.perf_counter() + 10
        while time.perf_counter() < deadline:
            alerts = [
                row
                for row in visible_owned_windows(game)
                if row[0] not in (game, load_window)
                and window_class(row[0]) == "#32770"
                and row[2][2] - row[2][0] < 400
                and row[2][3] - row[2][1] < 220
            ]
            if (
                not user32.IsWindow(load_window)
                and user32.IsWindowEnabled(game)
            ):
                native_wake_game(pid, game, 1800)
                time.sleep(0.3)
                return
            for alert, _title, _rect in alerts:
                activate_hidden_window(alert)
                click_leftmost_dialog_button(alert)
            time.sleep(0.2)
        remaining = [
            (window_class(hwnd), window_text(hwnd))
            for hwnd in process_windows(pid)
        ]
        raise RuntimeError(
            f"第 {index} 号存档未能完成后台读取；"
            f"残留窗口={remaining}"
        )

    def robust_save_and_confirm(self, index: int) -> None:
        output = app_dir() / "SV" / f"SV{index:03}.E5S"
        before_mtime = output.stat().st_mtime_ns if output.is_file() else None
        native_direct_save(pid, index - 1)
        deadline = time.perf_counter() + 5
        while time.perf_counter() < deadline:
            if output.is_file() and output.stat().st_mtime_ns != before_mtime:
                time.sleep(0.3)
                return
            time.sleep(0.1)
        raise RuntimeError(f"第 {index} 号存档未能完成游戏原生保存")

    def fast_check_people_at_r0(self) -> bool:
        positions = (
            JOB_POSITIONS_R0 if three_person_mode else JOB_POSITIONS_R1
        )
        members = (
            INITIAL_TEAM_MEMBERS if three_person_mode else TEAM_MEMBERS
        )
        ids = read_job_ids(pid, positions)
        if any(job_id not in JOB_MAP for job_id in ids):
            print(f"内存快筛遇到未收录兵种编号 {ids}，本轮放弃")
            return False

        summaries = []
        jobs = []
        member_rules = []
        for job_id, member in zip(ids, members):
            name, score, job_type = JOB_MAP[job_id]
            member_name, primary_type, secondary_type = member
            jobs.append({"name": name, "score": score, "type": job_type})
            member_rules.append(
                {
                    "name": member_name,
                    "primaryType": primary_type,
                    "secondaryType": secondary_type,
                }
            )
            summaries.append(f"{member_name}:{name}")

        evaluation = evaluate_job_rules(
            rules,
            "three" if three_person_mode else "seven",
            jobs,
            member_rules,
        )
        average = evaluation.metrics["average"]
        success = (
            os.environ.get("CCZ_TEST_ACCEPT_FIRST") == "1"
            or evaluation.qualified
        )
        self._r0_job_ids = ids
        self._r0_average = average
        self._r0_summaries = summaries
        self._r0_rule_reasons = evaluation.reasons
        print(
            f"R0 {'三人' if three_person_mode else '七人'}兵种筛选: "
            + "; ".join(summaries)
            + "; 结果="
            + ("通过" if success else "未通过")
        )
        diagnostic_log(
            "job_rule_evaluation",
            mode="three" if three_person_mode else "seven",
            qualified=success,
            reasons=evaluation.reasons,
            metrics=evaluation.metrics,
        )
        if not success and evaluation.reasons:
            print("规则原因: " + "；".join(evaluation.reasons))
        return success

    def load_team_skills_from_memory(self):
        from models.CczModels import CCZ_MODELS

        skill_ids = read_skill_ids(pid, len(CCZ_MODELS.skills))
        for member, member_skill_ids in zip(
            task_module.TEAM_MEMBER_LIST, skill_ids
        ):
            member.skillList = [
                CCZ_MODELS.skills[skill_id]
                for skill_id in member_skill_ids
            ]
        self._r1_skill_ids = skill_ids
        self._team_members = task_module.TEAM_MEMBER_LIST
        print(
            "R1 七人特技内存读取: "
            + "; ".join(
                f"{member.name}="
                + ",".join(skill.name for skill in member.skillList)
                for member in task_module.TEAM_MEMBER_LIST
            )
        )
        return skill_ids

    def fast_check_people_at_r1(self) -> bool:
        load_team_skills_from_memory(self)
        evaluation = evaluate_task_skill_rules(
            rules,
            task_module,
            task_module.TEAM_MEMBER_LIST,
            self._r0_average,
        )
        success = evaluation.qualified
        self._r1_rule_reasons = evaluation.reasons
        print(
            "R1 特技内存快筛: "
            + ("通过" if success else "未通过")
        )
        diagnostic_log(
            "skill_rule_evaluation",
            qualified=success,
            reasons=evaluation.reasons,
            metrics=evaluation.metrics,
        )
        if not success and evaluation.reasons:
            print("规则原因: " + "；".join(evaluation.reasons))
        return success

    def collect_equipment(self):
        records = read_equipment_records(pid)
        equip_info, effects = decode_equipment_records(records)
        self._equip_info = equip_info
        self._equip_effects = effects
        self._equip_specials = build_equipment_specials(effects)
        equip_count = sum(len(items) for items, _type_name in equip_info)
        print(
            f"宝物内存读取完成：{len(equip_info)} 类，共 {equip_count} 件，"
            "未打开宝物图鉴"
        )
        return equip_info

    def verified_start_rand(self) -> bool:
        self.initWind()
        if not self.wind.isInitSuccess():
            print("随机前游戏窗口初始化失败")
            return False
        before = read_job_ids(pid, JOB_POSITIONS_R1)
        left, top, _right, _bottom = self.wind.getRect()
        npc_x = left + 356 + 16
        npc_y = top + 251 + 29
        choice_x = left + 240 + 130
        choice_y = top + 255 + 9

        for attempt in range(3):
            print(f"后台随机尝试 {attempt + 1}/3")
            native_wake_game(pid, self.wind.hwnd, 800)
            post_click(
                self.wind.hwnd,
                npc_x,
                npc_y,
                count=1 if attempt == 0 else 2,
            )
            native_wake_game(pid, self.wind.hwnd, 900)
            post_click(
                self.wind.hwnd,
                choice_x,
                choice_y,
                count=1 if attempt < 2 else 2,
            )
            native_wake_game(pid, self.wind.hwnd, 1200)

            deadline = time.perf_counter() + 2
            while time.perf_counter() < deadline:
                current = read_job_ids(pid, JOB_POSITIONS_R1)
                if current != before and any(current):
                    print(f"随机兵种已更新: {before}->{current}")
                    return True
                time.sleep(0.1)
        print(f"随机操作未改变兵种内存: {before}")
        return False

    def cached_version_check(self) -> bool:
        if getattr(self, "is2_08", None) is not None:
            return True
        return original_version_check(self)

    def direct_open_people(self) -> None:
        self.initWind()
        point = Point(138, 18)
        user32.ClientToScreen(self.wind.hwnd, ctypes.byref(point))
        post_click(self.wind.hwnd, point.x, point.y)
        time.sleep(0.4)
        self.initPeopleWind()

    def direct_click_people(self, index: int) -> None:
        # The personnel window is a game-rendered list, not a SysListView32.
        # The original tool clicks row rectangles at x=47, y=99+60*index.
        client_x = 54
        client_y = 129 + 60 * index
        native_background_click(self.hwnd, client_x, client_y, 1, False)
        game = find_process_window_by_class(pid, "SOUSOU")
        if game:
            native_wake_game(pid, game, 1600)
        time.sleep(0.6)

    def r0_only_run(self) -> bool:
        print(f"{self.name} 原生随机内存快筛流程 start")
        self._three_person_mode = three_person_mode
        diagnostic_log(
            "random_run_start",
            pid=pid,
            target_slot=getattr(self, "_target_save_pos", None),
            source_loaded=bool(getattr(self, "_source_loaded", False)),
            random_mode="three" if three_person_mode else "seven",
        )
        self.savePos = getattr(
            self,
            "_target_save_pos",
            int(os.environ.get("CCZ_OUTPUT_SLOT", "1")),
        )
        self.is2_08 = None
        game = find_process_window_by_class(pid, "SOUSOU")
        if not game:
            raise RuntimeError("未找到游戏主窗口")

        load_started = time.perf_counter()
        reused_session = bool(getattr(self, "_source_loaded", False))
        if reused_session:
            load_mode = "direct"
            diagnostic_log("source_load_start", pid=pid, mode=load_mode)
            native_direct_load(pid, SOURCE_TITLE_LIST_INDEX)
            reload_deadline = time.perf_counter() + 8
            while time.perf_counter() < reload_deadline:
                if read_memory(pid, 0, R0_MEMORY_SIZE) == source_memory:
                    break
                time.sleep(0.05)
            else:
                print("第 20 号源存档内存直读未确认，回退标题界面原生读取")
                self._source_loaded = False
                if not title_load_verified(
                    pid, SOURCE_TITLE_LIST_INDEX, source_save
                ):
                    print("第 20 号源存档标题界面回读也失败")
                    diagnostic_log(
                        "source_load_failed",
                        pid=pid,
                        mode="direct_and_title",
                    )
                    raise RuntimeError(
                        "第 20 号源存档连续两种后台读取方式均失败"
                    )
            scene_ready_delay = 2.0
        else:
            load_mode = "title"
            diagnostic_log("source_load_start", pid=pid, mode=load_mode)
            if not title_load_verified(
                pid, SOURCE_TITLE_LIST_INDEX, source_save
            ):
                diagnostic_log(
                    "source_load_failed",
                    pid=pid,
                    mode="title",
                )
                raise RuntimeError(
                    "第 20 号源存档读取失败，已停止本次随机；"
                    "请将普通日志和诊断日志一起发回"
                )
            self._source_loaded = True
            scene_ready_delay = 1.5

        active_positions = (
            JOB_POSITIONS_R0 if three_person_mode else JOB_POSITIONS_R1
        )
        load_deadline = time.perf_counter() + 8
        before = ()
        while time.perf_counter() < load_deadline:
            before = read_job_ids(pid, active_positions)
            if before == (0,) * len(active_positions):
                break
            time.sleep(0.1)
        else:
            diagnostic_log(
                "source_jobs_invalid",
                pid=pid,
                jobs=before,
            )
            raise RuntimeError(
                f"第 {SOURCE_SAVE_NUMBER} 号存档已经包含随机结果，"
                "不能作为源存档。\n"
                "请重新准备存档：完成许子将配置后，"
                "在与许子将对话并选择第一个选项之前，"
                f"将存档保存到第 {SOURCE_SAVE_NUMBER} 栏，然后重新运行工具。"
            )
        diagnostic_log(
            "source_ready",
            pid=pid,
            hwnd=game,
            jobs=before,
            elapsed_ms=round(
                (time.perf_counter() - load_started) * 1000
            ),
            scene_ready_delay_ms=round(scene_ready_delay * 1000),
            window_valid=bool(user32.IsWindow(game)),
            load_mode=load_mode,
            reused_session=reused_session,
            state=game_state_diagnostic(
                pid,
                game,
                jobs=before,
                source_memory=source_memory,
            ),
        )
        time.sleep(scene_ready_delay)

        current = before
        interaction_limit = 1 if reused_session else 3
        for interaction_attempt in range(1, interaction_limit + 1):
            interaction_started = time.perf_counter()
            diagnostic_log(
                "interaction_start",
                pid=pid,
                hwnd=game,
                attempt=interaction_attempt,
                before_jobs=before,
                window_valid=bool(user32.IsWindow(game)),
                load_mode=load_mode,
                reused_session=reused_session,
                geometry=click_geometry_diagnostic(game),
                state=game_state_diagnostic(
                    pid,
                    game,
                    jobs=before,
                    source_memory=source_memory,
                ),
            )
            npc_click_started = time.perf_counter()
            run_native_control(
                pid,
                [
                    "silent-click",
                    str(game),
                    str(XU_CLIENT_POSITION[0]),
                    str(XU_CLIENT_POSITION[1]),
                ],
            )
            time.sleep(0.5)
            after_npc = read_job_ids(pid, active_positions)
            diagnostic_log(
                "interaction_npc_clicked",
                pid=pid,
                attempt=interaction_attempt,
                jobs=after_npc,
                elapsed_ms=round(
                    (time.perf_counter() - npc_click_started) * 1000
                ),
                window_valid=bool(user32.IsWindow(game)),
                load_mode=load_mode,
                reused_session=reused_session,
                geometry=click_geometry_diagnostic(game),
                state=game_state_diagnostic(
                    pid,
                    game,
                    jobs=after_npc,
                    source_memory=source_memory,
                ),
            )
            choice_click_started = time.perf_counter()
            current = trigger_random_choice_click(
                pid,
                game,
                active_positions,
                before,
                interaction_attempt,
            )
            diagnostic_log(
                "interaction_choice_clicked",
                pid=pid,
                attempt=interaction_attempt,
                jobs=current,
                elapsed_ms=round(
                    (time.perf_counter() - choice_click_started) * 1000
                ),
                load_mode=load_mode,
                reused_session=reused_session,
                geometry=click_geometry_diagnostic(game),
            )
            random_deadline = time.perf_counter() + 3
            while time.perf_counter() < random_deadline:
                current = read_job_ids(pid, active_positions)
                if current != before and any(current):
                    break
                time.sleep(0.05)
            if current != before and any(current):
                diagnostic_log(
                    "interaction_succeeded",
                    pid=pid,
                    attempt=interaction_attempt,
                    jobs=current,
                    elapsed_ms=round(
                        (time.perf_counter() - interaction_started) * 1000
                    ),
                )
                break
            diagnostic_log(
                "interaction_no_change",
                pid=pid,
                attempt=interaction_attempt,
                jobs=current,
                elapsed_ms=round(
                    (time.perf_counter() - interaction_started) * 1000
                ),
                process_alive=find_process_id(GAME_EXE_NAME) == pid,
                window_valid=bool(user32.IsWindow(game)),
                load_mode=load_mode,
                reused_session=reused_session,
                state=game_state_diagnostic(
                    pid,
                    game,
                    jobs=current,
                    source_memory=source_memory,
                ),
            )
            if interaction_attempt < interaction_limit:
                print(
                    "许子将后台交互未触发随机，"
                    f"重试 {interaction_attempt}/{interaction_limit}"
                )
                native_wake_game(pid, game, 900)
            else:
                print("许子将后台交互未触发随机，正在记录现场")
        else:
            failure_state = game_state_diagnostic(
                pid,
                game,
                jobs=current,
                source_memory=source_memory,
            )
            failure_capture = capture_interaction_failure(pid, game)
            diagnostic_log(
                "interaction_failed",
                pid=pid,
                before_jobs=before,
                final_jobs=current,
                load_mode=load_mode,
                reused_session=reused_session,
                geometry=click_geometry_diagnostic(game),
                state=failure_state,
                screenshot=failure_capture,
            )
            raise InteractionNotTriggered(
                f"连续 {interaction_limit} 次点击许子将并选择第一项后，"
                f"{'初始三人' if three_person_mode else '七人'}"
                "兵种内存仍未发生变化"
            )
        print(f"游戏原生随机已触发: {before}->{current}")
        self._r0_initial_three = read_job_ids(pid, JOB_POSITIONS_R0)

        if not self.checkPeopleAtR0():
            diagnostic_log(
                "job_filter_rejected",
                pid=pid,
                jobs=current,
            )
            print("用户进度: 本轮最终结果=兵种不合格")
            return False
        diagnostic_log("job_filter_accepted", pid=pid, jobs=current)

        if three_person_mode:
            scratch_slot = 16
            scratch_path = (
                game_path.parent / "SV" / f"SV{scratch_slot:03}.E5S"
            )
            scratch_backup = (
                scratch_path.read_bytes() if scratch_path.is_file() else None
            )
            inspection_dir = None
            try:
                native_direct_save(pid, scratch_slot - 1)
                memory_after_save = read_memory(pid, 0, R0_MEMORY_SIZE)
                if not scratch_path.is_file():
                    raise RuntimeError("游戏报告保存成功，但未找到候选存档")
                saved = scratch_path.read_bytes()
                if saved[:R0_MEMORY_SIZE] != memory_after_save:
                    raise RuntimeError("初始三人候选存档与游戏内存不一致")
                self._candidate_save = saved
                print("初始三人兵种合格，正在检查特技条件")
                inspection_dir = Path(
                    tempfile.mkdtemp(
                        prefix="ccz-initial-inspect-",
                        dir=app_dir(),
                    )
                )
                inspection = run_initial_inspection_process(
                    game_path,
                    scratch_slot,
                    inspection_dir,
                    self._r0_average,
                )
                self._job_names = tuple(
                    JOB_MAP[job_id][0] for job_id in self._r0_job_ids
                )
                self._member_panels = tuple(
                    Image.open(panel_path).convert("RGB").copy()
                    for panel_path in inspection["panels"]
                )
                self._team_members = initial_team_members(
                    task_module.TEAM_MEMBER_LIST
                )
                diagnostic_log(
                    "initial_skill_rule_evaluation",
                    qualified=inspection["qualified"],
                    reasons=inspection.get("reasons", []),
                    skills=inspection.get("skills", []),
                    metrics=inspection.get("metrics", {}),
                )
                if not inspection["qualified"]:
                    reasons = inspection.get("reasons", [])
                    if reasons:
                        print("规则原因: " + "；".join(reasons))
                    print("用户进度: 本轮最终结果=特技不合格")
                    return False
                print("R1 特技界面筛选: 通过")
            finally:
                if inspection_dir is not None:
                    shutil.rmtree(inspection_dir, ignore_errors=True)
                if scratch_backup is None:
                    scratch_path.unlink(missing_ok=True)
                else:
                    scratch_path.write_bytes(scratch_backup)
        else:
            scratch_slot = 16
            scratch_path = (
                game_path.parent / "SV" / f"SV{scratch_slot:03}.E5S"
            )
            scratch_backup = (
                scratch_path.read_bytes() if scratch_path.is_file() else None
            )
            inspection_dir = None
            try:
                native_direct_save(pid, scratch_slot - 1)
                memory_after_save = read_memory(pid, 0, R0_MEMORY_SIZE)
                if not scratch_path.is_file():
                    raise RuntimeError("游戏报告保存成功，但未找到候选存档")
                saved = scratch_path.read_bytes()
                if saved[:R0_MEMORY_SIZE] != memory_after_save:
                    differences = [
                        index
                        for index, (left, right) in enumerate(
                            zip(saved[:R0_MEMORY_SIZE], memory_after_save)
                        )
                        if left != right
                    ]
                    preview = ", ".join(f"0x{x:X}" for x in differences[:12])
                    raise RuntimeError(
                        "R0 原生保存与内存不一致，"
                        f"共 {len(differences)} 字节：{preview}"
                    )
                print(
                    "R0 完整状态原生保存校验通过："
                    f"0x{R0_MEMORY_SIZE:X} 字节逐字节一致，"
                    f"SHA256={hashlib.sha256(memory_after_save).hexdigest()}"
                )
                self._candidate_save = saved
                print("候选存档已由游戏原生保存")

                inspection_dir = Path(
                    tempfile.mkdtemp(prefix="ccz-inspect-", dir=app_dir())
                )
                inspection = run_inspection_process(
                    game_path,
                    scratch_slot,
                    inspection_dir,
                    self._r0_average,
                )
                evidence_source = Path(
                    inspection.get("skill_evidence", "")
                )
                if evidence_source.is_file():
                    evidence_root = (
                        DIAGNOSTIC_LOG_PATH.parent
                        if DIAGNOSTIC_LOG_PATH is not None
                        else app_dir() / "ccz_fast_logs"
                    ) / "skill_evidence"
                    evidence_root.mkdir(parents=True, exist_ok=True)
                    evidence_name = (
                        dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                        + f"_slot{self.savePos}.zip"
                    )
                    archived_evidence = evidence_root / evidence_name
                    shutil.copyfile(evidence_source, archived_evidence)
                    diagnostic_log(
                        "skill_evidence_archived",
                        path=archived_evidence,
                        target_slot=self.savePos,
                        qualified=inspection["qualified"],
                    )
                self._job_names = tuple(inspection["job_names"])
                self._member_panels = tuple(
                    Image.open(panel_path).convert("RGB").copy()
                    for panel_path in inspection["panels"]
                )
                self._team_members = task_module.TEAM_MEMBER_LIST
                if not inspection["qualified"]:
                    reasons = inspection.get("reasons", [])
                    if reasons:
                        print("规则原因: " + "；".join(reasons))
                    print("用户进度: 本轮最终结果=特技不合格")
                    return False
            finally:
                if inspection_dir is not None:
                    shutil.rmtree(inspection_dir, ignore_errors=True)
                if scratch_backup is None:
                    scratch_path.unlink(missing_ok=True)
                else:
                    scratch_path.write_bytes(scratch_backup)

        print("用户进度: 本轮最终结果=合格，开始保存")
        target_path = (
            game_path.parent / "SV" / f"SV{self.savePos:03}.E5S"
        )
        target_mtime = (
            target_path.stat().st_mtime_ns
            if target_path.is_file()
            else None
        )
        native_direct_save(pid, self.savePos - 1)
        save_deadline = time.perf_counter() + 5
        while time.perf_counter() < save_deadline:
            if (
                target_path.is_file()
                and target_path.stat().st_mtime_ns != target_mtime
            ):
                break
            time.sleep(0.1)
        if (
            not target_path.is_file()
            or target_path.stat().st_mtime_ns == target_mtime
        ):
            raise RuntimeError(
                f"第 {self.savePos} 号结果存档未能完成游戏原生保存"
            )
        target_saved = target_path.read_bytes()
        memory_after_target_save = read_memory(pid, 0, R0_MEMORY_SIZE)
        if target_saved[:R0_MEMORY_SIZE] != memory_after_target_save:
            raise RuntimeError(
                f"第 {self.savePos} 号结果存档与保存时游戏内存不一致"
            )
        print(
            f"第 {self.savePos} 号结果存档已由游戏原生保存，"
            "并通过保存时内存逐字节校验"
        )
        return True

    BaseWindow.setForeground = set_foreground
    BaseWindow._BaseWindow__getHwndbyName = get_hwnd_by_name
    BaseWindow.clickRect = silent_click_rect
    BaseWindow.moveMouseToEnd = silent_move_mouse_to_end
    BaseWindow.getMat = robust_get_mat
    CczPeopleWindow.clickPeople = direct_click_people
    task_module.KeyboardUtils.tapKey = lambda key: post_key_to_game(pid, key)
    task_module.CczReRandTask.checkPeopleAtR0 = fast_check_people_at_r0
    # The legacy 0x6800 hypothesis has not matched UI-recognized skills.
    # Keep the proven UI inspection path until evidence establishes a mapping.
    task_module.CczReRandTask.collect_equipment = collect_equipment
    task_module.CczReRandTask.startRand = verified_start_rand
    task_module.CczReRandTask.checkCczVersion = cached_version_check
    task_module.CczReRandTask.openPeople = direct_open_people
    task_module.CczReRandTask.loadAndConfirm = robust_load_and_confirm
    task_module.CczReRandTask.saveAndConfirm = robust_save_and_confirm
    task_module.CczReRandTask.run = r0_only_run


def format_user_log(line: str) -> str:
    """Reduce the worker trace to user-facing progress information."""
    text = line.strip()
    if not text:
        return ""
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
        progress = text.replace("用户进度: ", "")
        progress = progress.replace("本轮最终结果=", "本轮结果：")
        progress = progress.replace("，开始保存", "")
        return progress
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
    if text.startswith("初始三人兵种合格，正在检查特技条件"):
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
    if text.startswith("R0 完整状态原生保存校验通过"):
        return ""
    if text.startswith("第 ") and "已由游戏原生保存" in text:
        prefix = text.split("号", 1)[0] if "号" in text else text
        return f"{prefix}号存档已保存"
    if text.startswith("第 ") and "回读校验通过" in text:
        prefix = text.split("号", 1)[0] if "号" in text else text
        return f"{prefix}号存档回读：合格"
    if text.startswith("宝物内存读取完成"):
        return ""
    if text.startswith("随机兵种已更新:"):
        return "随机结果已更新"
    if text.startswith("后台随机尝试"):
        return "正在触发随机……"
    if text.startswith("候选存档已由游戏原生保存"):
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
    if "个结果存档全部生成并通过回读校验" in text:
        return text.replace("结果存档全部生成并通过回读校验", "存档结果已完成")
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
    if isinstance(exc, NativeControlError):
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


def gui_main() -> int:
    import tkinter as tk
    from tkinter import messagebox, scrolledtext, ttk

    root = tk.Tk()
    root.title("2.10 随机工具")
    root.geometry("980x680")
    root.minsize(760, 520)

    worker: subprocess.Popen[str] | None = None
    output_queue: queue.Queue[str] = queue.Queue()
    log_path: Path | None = None
    result_image_path: Path | None = None
    stop_file: Path | None = None
    stop_requested_by_user = False
    last_formatted_line = ""
    mode_var = tk.StringVar(value="seven")
    loop_var = tk.BooleanVar(value=False)
    rule_load = load_rule_config(app_dir())
    current_rules = rule_load.config
    rule_profile_var = tk.StringVar(
        value=current_rules["activeProfile"]
    )

    outer = tk.Frame(root, padx=14, pady=12)
    outer.pack(fill="both", expand=True)

    header = tk.Frame(outer)
    header.pack(fill="x")
    tk.Label(
        header,
        text="2.10 随机工具",
        font=("Microsoft YaHei UI", 16, "bold"),
        anchor="w",
    ).pack(side="left")
    version = str(application_build_info().get("version", "")).strip()
    tk.Label(
        header,
        text=f"V{version}" if version else "",
        font=("Microsoft YaHei UI", 10),
        anchor="e",
        fg="#666666",
    ).pack(side="right", padx=(12, 2), pady=(6, 0))
    help_popup: tk.Toplevel | None = None
    help_image: tk.PhotoImage | None = None

    info = tk.Frame(outer)
    info.pack(fill="x", pady=(8, 10))
    tk.Label(
        info,
        text="请将本工具放置到游戏目录下，双击运行。",
        justify="left",
        anchor="w",
        fg="#444444",
    ).pack(fill="x")
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
    tk.Label(
        info,
        text=(
            "本版本不需要替换 S_00.eex。"
            "结果保存在工具目录的 randResult 文件夹。"
        ),
        justify="left",
        anchor="w",
        fg="#444444",
    ).pack(fill="x")

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

    settings_bar = tk.Frame(outer)
    settings_bar.pack(fill="x", pady=(0, 6))
    tk.Label(settings_bar, text="运行模式").pack(side="left", padx=(0, 6))
    mode_frame = tk.Frame(settings_bar)
    mode_frame.pack(side="left", padx=(0, 18))
    seven_mode_button = tk.Radiobutton(
        mode_frame,
        text="完整7人",
        variable=mode_var,
        value="seven",
    )
    three_mode_button = tk.Radiobutton(
        mode_frame,
        text="只随机初始3人",
        variable=mode_var,
        value="three",
    )
    seven_mode_button.pack(side="left")
    three_mode_button.pack(side="left", padx=(8, 0))
    loop_check = tk.Checkbutton(
        settings_bar,
        text="循环随机（每轮15个）",
        variable=loop_var,
    )
    loop_check.pack(side="left", padx=(0, 18))
    tk.Label(settings_bar, text="规则").pack(side="left", padx=(0, 6))
    rule_profile_combo = ttk.Combobox(
        settings_bar,
        textvariable=rule_profile_var,
        values=tuple(current_rules["profiles"]),
        state="readonly",
        width=18,
    )
    rule_profile_combo.pack(side="left", padx=(0, 8))
    rule_button = tk.Button(settings_bar, text="规则设置", width=10)
    rule_button.pack(side="left")

    action_bar = tk.Frame(outer)
    action_bar.pack(fill="x", pady=(0, 8))
    status = tk.StringVar(value="等待开始")
    tk.Label(action_bar, textvariable=status, anchor="w").pack(
        side="left", fill="x", expand=True
    )
    action_button = tk.Button(action_bar, text="开始随机", width=14)
    action_button.pack(side="right")

    output = scrolledtext.ScrolledText(
        outer,
        wrap="none",
        font=("Consolas", 10),
        state="disabled",
        bg="#fafafa",
        relief="solid",
        borderwidth=1,
    )
    output.pack(fill="both", expand=True)

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

    def legacy_rule_editor() -> None:
        nonlocal current_rules
        editor = tk.Toplevel(root)
        editor.title("规则设置")
        editor.geometry("900x700")
        editor.minsize(760, 600)
        editor.transient(root)
        editor.grab_set()

        working = json.loads(json.dumps(current_rules, ensure_ascii=False))
        profile_name = working["activeProfile"]
        profile = active_profile(working)
        values: dict[str, tk.Variable] = {}
        entries: dict[str, tk.Entry] = {}

        header = tk.Frame(editor, padx=14, pady=12)
        header.pack(fill="x")
        tk.Label(header, text="规则名称").pack(side="left")
        profile_var = tk.StringVar(value=profile_name)
        tk.Entry(header, textvariable=profile_var, width=24).pack(
            side="left", padx=(8, 0)
        )
        tk.Label(
            header,
            text="保存后，下一次随机会使用这套规则。",
            fg="#555555",
        ).pack(side="left", padx=(14, 0))

        notebook = ttk.Notebook(editor)
        notebook.pack(fill="both", expand=True, padx=14)
        job_tab = tk.Frame(notebook, padx=14, pady=14)
        skill_tab = tk.Frame(notebook, padx=14, pady=14)
        advanced_tab = tk.Frame(notebook, padx=14, pady=14)
        notebook.add(job_tab, text="兵种规则")
        notebook.add(skill_tab, text="特技规则")
        notebook.add(advanced_tab, text="高级设置")

        def add_entry(
            parent,
            row: int,
            key: str,
            label: str,
            value,
            width: int = 18,
            hint: str = "",
        ) -> tk.Entry:
            tk.Label(parent, text=label, anchor="w").grid(
                row=row, column=0, sticky="w", pady=4
            )
            variable = tk.StringVar(value="" if value is None else str(value))
            values[key] = variable
            entry = tk.Entry(parent, textvariable=variable, width=width)
            entry.grid(row=row, column=1, sticky="w", padx=(12, 8), pady=4)
            entries[key] = entry
            if hint:
                tk.Label(parent, text=hint, fg="#666666", anchor="w").grid(
                    row=row, column=2, sticky="w", pady=4
                )
            return entry

        three = profile["threePerson"]
        seven = profile["sevenPerson"]
        conditions = profile["jobConditions"]
        add_entry(
            job_tab, 0, "three_min", "初始3人兵种门槛",
            three["minJobAverage"], hint="只随机初始3人时使用",
        )
        add_entry(
            job_tab, 1, "seven_min", "完整7人兵种门槛",
            seven["minJobAverage"], hint="低于此条件直接重新随机",
        )
        max_master = add_entry(
            job_tab, 2, "max_master", "文官兵种人数上限",
            conditions["maxMasterCount"], hint="留空表示不限制",
        )
        max_master.configure(width=18)

        tk.Label(job_tab, text="指定兵种组合", anchor="nw").grid(
            row=3, column=0, sticky="nw", pady=(10, 4)
        )
        groups_text = scrolledtext.ScrolledText(
            job_tab, width=56, height=5, wrap="word"
        )
        groups_text.grid(
            row=3, column=1, columnspan=2, sticky="nsew",
            padx=(12, 0), pady=(10, 4),
        )
        groups_text.insert(
            "1.0",
            "\n".join(
                f"{join_names(group['jobs'])} | {group['minCount']}"
                for group in conditions["requiredJobGroups"]
            ),
        )
        tk.Label(
            job_tab,
            text="每行格式：虎豹骑，宿卫骑 | 1，表示这些兵种至少出现1人。",
            fg="#666666",
            anchor="w",
        ).grid(row=4, column=1, columnspan=2, sticky="w", padx=(12, 0))

        allowed_entries = {}
        blocked_entries = {}
        tk.Label(job_tab, text="武将").grid(row=5, column=0, pady=(14, 4))
        tk.Label(job_tab, text="只允许这些兵种").grid(
            row=5, column=1, pady=(14, 4)
        )
        tk.Label(job_tab, text="排除这些兵种").grid(
            row=5, column=2, pady=(14, 4)
        )
        for offset, member in enumerate(
            [item[0] for item in TEAM_MEMBERS], start=6
        ):
            tk.Label(job_tab, text=member).grid(
                row=offset, column=0, sticky="w", pady=2
            )
            allowed = tk.Entry(job_tab, width=34)
            allowed.insert(
                0, join_names(conditions["memberAllowedJobs"].get(member, []))
            )
            allowed.grid(row=offset, column=1, padx=(12, 8), pady=2)
            allowed_entries[member] = allowed
            blocked = tk.Entry(job_tab, width=34)
            blocked.insert(
                0, join_names(conditions["memberBlockedJobs"].get(member, []))
            )
            blocked.grid(row=offset, column=2, pady=2)
            blocked_entries[member] = blocked
        job_tab.columnconfigure(1, weight=1)
        job_tab.columnconfigure(2, weight=1)

        skills = profile["skillConditions"]
        add_entry(
            skill_tab, 0, "required_any", "至少出现其中一个特技",
            join_names(skills["requiredAny"]), width=58,
            hint="留空表示不限制",
        )
        add_entry(
            skill_tab, 1, "required_all", "必须全部出现的特技",
            join_names(skills["requiredAll"]), width=58,
            hint="留空表示不限制",
        )
        add_entry(
            skill_tab, 2, "blocked_skills", "排除特技",
            join_names(skills["blocked"]), width=58,
            hint="出现任意一个即不合格",
        )
        add_entry(
            skill_tab, 3, "min_quality_members", "至少几名武将有好特技",
            skills["minMembersWithQualitySkill"], hint="0 表示不限制",
        )
        member_required_entries = {}
        member_blocked_entries = {}
        tk.Label(skill_tab, text="武将").grid(
            row=4, column=0, pady=(14, 4)
        )
        tk.Label(skill_tab, text="至少出现其中一个特技").grid(
            row=4, column=1, pady=(14, 4)
        )
        tk.Label(skill_tab, text="排除特技").grid(
            row=4, column=2, pady=(14, 4)
        )
        for offset, member in enumerate(
            [item[0] for item in TEAM_MEMBERS], start=5
        ):
            tk.Label(skill_tab, text=member).grid(
                row=offset, column=0, sticky="w", pady=2
            )
            required = tk.Entry(skill_tab, width=34)
            required.insert(
                0, join_names(skills["memberRequired"].get(member, []))
            )
            required.grid(row=offset, column=1, padx=(12, 8), pady=2)
            member_required_entries[member] = required
            blocked = tk.Entry(skill_tab, width=34)
            blocked.insert(
                0, join_names(skills["memberBlocked"].get(member, []))
            )
            blocked.grid(row=offset, column=2, pady=2)
            member_blocked_entries[member] = blocked
        skill_tab.columnconfigure(1, weight=1)
        skill_tab.columnconfigure(2, weight=1)

        scoring = profile["jobScoring"]
        add_entry(
            advanced_tab, 0, "normal_average", "普通兵种分界",
            seven["normalJobAverage"],
        )
        add_entry(
            advanced_tab, 1, "high_average", "高兵种分界",
            seven["highJobAverage"],
        )
        add_entry(
            advanced_tab, 2, "medium_skills", "普通兵种所需有效特技",
            seven["mediumMinEffectiveSkills"],
        )
        add_entry(
            advanced_tab, 3, "low_skills", "较低兵种所需有效特技",
            seven["lowMinEffectiveSkills"],
        )
        add_entry(
            advanced_tab, 4, "strong_weight", "强力特技计数权重",
            seven["strongSkillWeight"],
        )
        boolean_specs = (
            ("special_auto", "特殊特技直接合格", seven["specialSkillAutoPass"]),
            ("high_auto", "高兵种直接合格", seven["highJobAutoPass"]),
            ("affinity", "启用武将兵种适配加成", scoring["affinityEnabled"]),
            (
                "master_penalty",
                "启用文官兵种过多扣分",
                scoring["extraMasterPenaltyEnabled"],
            ),
        )
        for row, (key, label, value) in enumerate(boolean_specs, start=5):
            variable = tk.BooleanVar(value=value)
            values[key] = variable
            tk.Checkbutton(
                advanced_tab, text=label, variable=variable, anchor="w"
            ).grid(row=row, column=0, columnspan=2, sticky="w", pady=3)
        add_entry(
            advanced_tab, 9, "affinity_min", "适配加成最低基础分",
            scoring["affinityMinBaseScore"],
        )
        add_entry(
            advanced_tab, 10, "primary_bonus", "主要类型加成比例",
            scoring["primaryBonusRate"], hint="例如 0.06 表示 6%",
        )
        add_entry(
            advanced_tab, 11, "secondary_bonus", "次要类型加成比例",
            scoring["secondaryBonusRate"], hint="例如 0.03 表示 3%",
        )
        add_entry(
            advanced_tab, 12, "xiahou_penalty", "夏侯惇为文官时扣分",
            scoring["xiahouDunMasterPenalty"],
        )

        def parse_groups() -> list[dict]:
            result = []
            for line_number, line in enumerate(
                groups_text.get("1.0", "end").splitlines(), start=1
            ):
                if not line.strip():
                    continue
                parts = line.replace("｜", "|").split("|")
                if len(parts) != 2:
                    raise ValueError(
                        f"指定兵种组合第 {line_number} 行格式不正确"
                    )
                result.append(
                    {
                        "jobs": split_names(parts[0]),
                        "minCount": int(parts[1].strip()),
                    }
                )
            return result

        def build_config() -> dict:
            name = profile_var.get().strip()
            if not name:
                raise ValueError("规则名称不能为空")
            result = default_rule_config()
            result["activeProfile"] = name
            result["profiles"] = {name: json.loads(json.dumps(profile))}
            target = result["profiles"][name]
            target["threePerson"]["minJobAverage"] = float(
                values["three_min"].get()
            )
            target["sevenPerson"].update(
                {
                    "minJobAverage": float(values["seven_min"].get()),
                    "normalJobAverage": float(values["normal_average"].get()),
                    "highJobAverage": float(values["high_average"].get()),
                    "mediumMinEffectiveSkills": int(
                        values["medium_skills"].get()
                    ),
                    "lowMinEffectiveSkills": int(values["low_skills"].get()),
                    "strongSkillWeight": int(values["strong_weight"].get()),
                    "specialSkillAutoPass": bool(
                        values["special_auto"].get()
                    ),
                    "highJobAutoPass": bool(values["high_auto"].get()),
                }
            )
            target["jobScoring"].update(
                {
                    "affinityEnabled": bool(values["affinity"].get()),
                    "affinityMinBaseScore": float(
                        values["affinity_min"].get()
                    ),
                    "primaryBonusRate": float(
                        values["primary_bonus"].get()
                    ),
                    "secondaryBonusRate": float(
                        values["secondary_bonus"].get()
                    ),
                    "xiahouDunMasterPenalty": float(
                        values["xiahou_penalty"].get()
                    ),
                    "extraMasterPenaltyEnabled": bool(
                        values["master_penalty"].get()
                    ),
                }
            )
            max_master_value = values["max_master"].get().strip()
            target["jobConditions"].update(
                {
                    "maxMasterCount": (
                        None
                        if not max_master_value
                        else int(max_master_value)
                    ),
                    "requiredJobGroups": parse_groups(),
                    "memberAllowedJobs": {
                        member: split_names(entry.get())
                        for member, entry in allowed_entries.items()
                        if split_names(entry.get())
                    },
                    "memberBlockedJobs": {
                        member: split_names(entry.get())
                        for member, entry in blocked_entries.items()
                        if split_names(entry.get())
                    },
                }
            )
            target["skillConditions"].update(
                {
                    "requiredAny": split_names(values["required_any"].get()),
                    "requiredAll": split_names(values["required_all"].get()),
                    "blocked": split_names(values["blocked_skills"].get()),
                    "minMembersWithQualitySkill": int(
                        values["min_quality_members"].get()
                    ),
                    "memberRequired": {
                        member: split_names(entry.get())
                        for member, entry in member_required_entries.items()
                        if split_names(entry.get())
                    },
                    "memberBlocked": {
                        member: split_names(entry.get())
                        for member, entry in member_blocked_entries.items()
                        if split_names(entry.get())
                    },
                }
            )
            return validate_rule_config(result)

        footer = tk.Frame(editor, padx=14, pady=12)
        footer.pack(fill="x")

        def save_rules() -> None:
            nonlocal current_rules
            try:
                config = build_config()
                path = save_rule_config(app_dir(), config)
            except Exception as exc:
                messagebox.showerror(
                    "规则无法保存",
                    f"请检查填写内容。\n\n{exc}",
                    parent=editor,
                )
                return
            current_rules = config
            rule_name_var.set(f"当前规则：{config['activeProfile']}")
            messagebox.showinfo(
                "规则已保存",
                f"规则已保存到工具目录：\n{path.name}",
                parent=editor,
            )
            editor.destroy()

        def restore_defaults() -> None:
            if not messagebox.askyesno(
                "恢复内置默认",
                "将关闭当前窗口并恢复内置默认规则，确定继续吗？",
                parent=editor,
            ):
                return
            nonlocal current_rules
            current_rules = default_rule_config()
            save_rule_config(app_dir(), current_rules)
            rule_name_var.set("当前规则：默认规则")
            editor.destroy()

        tk.Button(
            footer, text="恢复内置默认", command=restore_defaults, width=14
        ).pack(side="left")
        tk.Button(
            footer, text="取消", command=editor.destroy, width=10
        ).pack(side="right", padx=(8, 0))
        tk.Button(
            footer, text="保存规则", command=save_rules, width=12
        ).pack(side="right")

    def open_rule_editor() -> None:
        def rules_saved(config: dict) -> None:
            nonlocal current_rules
            current_rules = config
            rule_profile_combo.configure(
                values=tuple(config["profiles"])
            )
            rule_profile_var.set(config["activeProfile"])

        show_rule_editor(
            root,
            app_dir(),
            current_rules,
            JOB_MAP,
            TEAM_MEMBERS,
            skill_score_catalog(),
            rules_saved,
        )

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

    def append(text: str) -> None:
        if not text:
            return
        output.configure(state="normal")
        output.insert("end", text + "\n")
        output.see("end")
        output.configure(state="disabled")

    def append_result_link() -> None:
        if result_image_path is None or not result_image_path.is_file():
            return
        output.configure(state="normal")
        output.insert("end", "结果图（")
        tag = f"result-link-{output.index('end')}"
        output.insert("end", "点击打开结果图", tag)
        output.insert("end", "）\n")
        output.tag_configure(tag, foreground="#0563c1", underline=True)
        output.tag_bind(
            tag,
            "<Button-1>",
            lambda _event, path=result_image_path: os.startfile(path),
        )
        output.tag_bind(
            tag,
            "<Enter>",
            lambda _event: output.configure(cursor="hand2"),
        )
        output.tag_bind(
            tag,
            "<Leave>",
            lambda _event: output.configure(cursor=""),
        )
        output.see("end")
        output.configure(state="disabled")

    def append_stopped_summary() -> None:
        output.configure(state="normal")
        output.insert("end", "\n本次流程已停止")
        if result_image_path is not None and result_image_path.is_file():
            output.insert("end", "，结果图（")
            tag = f"result-link-{output.index('end')}"
            output.insert("end", "点击打开结果图", tag)
            output.insert("end", "）。\n")
            output.tag_configure(
                tag, foreground="#0563c1", underline=True
            )
            output.tag_bind(
                tag,
                "<Button-1>",
                lambda _event, path=result_image_path: os.startfile(path),
            )
            output.tag_bind(
                tag,
                "<Enter>",
                lambda _event: output.configure(cursor="hand2"),
            )
            output.tag_bind(
                tag,
                "<Leave>",
                lambda _event: output.configure(cursor=""),
            )
        else:
            output.insert("end", "。\n")
        output.see("end")
        output.configure(state="disabled")

    def read_worker(pipe) -> None:
        for line in iter(pipe.readline, ""):
            output_queue.put(line.rstrip("\r\n"))
        pipe.close()

    def poll_worker() -> None:
        nonlocal worker, result_image_path, stop_file
        nonlocal stop_requested_by_user, last_formatted_line
        while True:
            try:
                line = output_queue.get_nowait()
            except queue.Empty:
                break
            if line.startswith("本轮总图路径："):
                candidate = Path(line.split("：", 1)[1].strip())
                if candidate.is_file() or not loop_var.get():
                    result_image_path = candidate
            elif "总图已更新：" in line:
                candidate = Path(line.split("总图已更新：", 1)[1].strip())
                if candidate.is_file():
                    result_image_path = candidate
            formatted = format_user_log(line)
            if formatted:
                if (
                    formatted == "后台游戏已启动"
                    and last_formatted_line.endswith("号存档已保存")
                ):
                    formatted = "\n" + formatted
                append(formatted)
                last_formatted_line = formatted.strip()
        if worker is not None and worker.poll() is not None:
            code = worker.returncode
            worker = None
            action_button.configure(
                text="开始随机",
                command=start,
                state="normal",
            )
            seven_mode_button.configure(state="normal")
            three_mode_button.configure(state="normal")
            loop_check.configure(state="normal")
            rule_profile_combo.configure(state="readonly")
            rule_button.configure(state="normal")
            stopped = stop_requested_by_user or code == 130
            status.set("已停止" if stopped else ("已完成" if code == 0 else "执行失败"))
            if stopped:
                append_stopped_summary()
            elif code == 0:
                append("本次流程已结束。")
                append_result_link()
            else:
                append("本次流程执行失败，详细信息已写入日志文件。")
            if stop_file is not None:
                stop_file.unlink(missing_ok=True)
                stop_file = None
            stop_requested_by_user = False
        root.after(100, poll_worker)

    def start() -> None:
        nonlocal current_rules
        nonlocal worker, log_path, result_image_path, stop_file
        nonlocal stop_requested_by_user, last_formatted_line
        if worker is not None:
            return
        try:
            game_executable = locate_game_executable()
            validate_start_environment(game_executable)
        except Exception as exc:
            status.set("环境检查未通过")
            messagebox.showerror(
                "无法开始随机",
                str(exc),
                parent=root,
            )
            return
        latest_rules = load_rule_config(app_dir())
        current_rules = latest_rules.config
        rule_profile_combo.configure(
            values=tuple(current_rules["profiles"])
        )
        rule_profile_var.set(current_rules["activeProfile"])
        if latest_rules.warning:
            messagebox.showwarning(
                "规则文件无法使用",
                latest_rules.warning,
                parent=root,
            )
        result_image_path = None
        stop_requested_by_user = False
        last_formatted_line = ""
        stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        append(f"\n========== 开始随机：{stamp} ==========")
        append(
            "运行模式："
            + (
                "只随机初始3人"
                if mode_var.get() == "three"
                else "完整7人"
            )
        )
        append("循环随机：" + ("开启" if loop_var.get() else "关闭"))
        append("环境检查：通过")
        env = os.environ.copy()
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
        env["CCZ_RANDOM_MODE"] = mode_var.get()
        env["CCZ_LOOP_RANDOM"] = "1" if loop_var.get() else "0"
        env["CCZ_RUN_STAMP"] = dt.datetime.now().strftime(
            "%Y-%m-%d %H.%M.%S"
        )
        env["PYTHONIOENCODING"] = "utf-8"
        if getattr(sys, "frozen", False):
            command = [sys.executable, "--worker"]
        else:
            command = [sys.executable, str(source_entry_path()), "--worker"]
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
        threading.Thread(
            target=read_worker,
            args=(worker.stdout,),
            daemon=True,
        ).start()
        action_button.configure(
            text="停止随机",
            command=stop,
            state="normal",
        )
        seven_mode_button.configure(state="disabled")
        three_mode_button.configure(state="disabled")
        loop_check.configure(state="disabled")
        rule_profile_combo.configure(state="disabled")
        rule_button.configure(state="disabled")
        status.set("循环运行中" if loop_var.get() else "运行中")

    def stop() -> None:
        nonlocal stop_requested_by_user
        if worker is not None and worker.poll() is None:
            status.set("正在停止……")
            stop_requested_by_user = True
            action_button.configure(state="disabled")
            if stop_file is not None:
                stop_file.write_text("stop", encoding="ascii")

    def close() -> None:
        if worker is not None and worker.poll() is None:
            if not messagebox.askyesno("确认退出", "随机仍在运行，确定停止并退出吗？"):
                return
            worker.terminate()
        root.destroy()

    action_button.configure(command=start)
    rule_button.configure(command=open_rule_editor)
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
    root.after(
        250,
        lambda: threading.Thread(
            target=skill_score_catalog,
            name="rule-catalog-preload",
            daemon=True,
        ).start(),
    )
    root.after(100, poll_worker)
    root.mainloop()
    return 0


def main() -> int:
    global RESULT_BASE_DIR, DIAGNOSTIC_LOG_PATH
    load_media_modules()
    RESULT_BASE_DIR = app_dir()
    stop_file_value = os.environ.get("CCZ_STOP_FILE", "")
    stop_file = Path(stop_file_value) if stop_file_value else None

    def check_stop_requested() -> None:
        if stop_file is not None and stop_file.exists():
            raise KeyboardInterrupt

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    app = app_dir()
    log_dir = app / "ccz_fast_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"fast_{dt.datetime.now():%Y%m%d_%H%M%S}.log"
    DIAGNOSTIC_LOG_PATH = log_path.with_name(
        f"{log_path.stem}_diagnostic.jsonl"
    )
    log_file = log_path.open("w", encoding="utf-8")
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
    requested_run_stamp = os.environ.get(
        "CCZ_RUN_STAMP",
        dt.datetime.now().strftime("%Y-%m-%d %H.%M.%S"),
    )
    loop_run_stamp = (
        resolve_loop_run_stamp(app, requested_run_stamp)
        if loop_random
        else requested_run_stamp
    )
    print(
        "运行模式："
        + ("只随机初始3人" if three_person_mode else "完整7人")
    )
    print("循环随机：" + ("开启" if loop_random else "关闭"))
    print(f"日志: {log_path}")
    print(f"诊断日志: {DIAGNOSTIC_LOG_PATH}")
    rule_load = load_rule_config(app)
    rules = rule_load.config
    print(f"当前规则：{rules['activeProfile']}")
    if rule_load.warning:
        print(f"规则提示：{rule_load.warning}")
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
        rule_source=rule_load.source,
        rule_warning=rule_load.warning,
    )

    try:
        game_executable = locate_game_executable()
        if os.environ.get("CCZ_AUTOSTART") != "1":
            input("按回车启动静默测试...")
        running_pid = find_process_id(GAME_EXE_NAME)
        if running_pid is not None:
            raise RuntimeError("检测到游戏正在运行，请先关闭游戏后再执行随机。")
        source_save = game_executable.parent / "SV" / "SV020.E5S"
        if not source_save.is_file():
            raise FileNotFoundError(
                "未找到第 20 号源存档 SV020.E5S"
            )
        source_hash = hashlib.sha256(source_save.read_bytes()).hexdigest()
        diagnostic_log(
            "source_save_ready",
            path=source_save,
            size=source_save.stat().st_size,
            sha256=source_hash,
        )
        install(bundle_root())
        import task.CczReRandTask as task_module

        task_module.SAVE_NUM = 1
        result_count = (
            15
            if loop_random
            else int(os.environ.get("CCZ_RESULT_COUNT", "15"))
        )
        game: HiddenGameSession | None = None

        def start_game_session(
            restarted: bool = False,
            announce: bool = True,
        ) -> HiddenGameSession:
            session = HiddenGameSession(
                game_executable,
                restarted=restarted,
                announce=announce,
            )
            session.__enter__()
            try:
                diagnostic_log(
                    "game_session_restarted"
                    if restarted
                    else "game_session_started",
                    pid=session.pid,
                    hwnd=session.main_window,
                )
                patch_runtime(
                    task_module,
                    session.pid,
                    three_person_mode=three_person_mode,
                    rules=rules,
                )
            except Exception:
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
            round_number = 1
            while True:
                workspace = None
                expected_results = {}
                panel_paths: dict[int, Path] = {}
                round_started_at = dt.datetime.now()
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
                    }

                def archive_incomplete_round() -> Path | None:
                    if workspace is None:
                        return None
                    target = finalize_round(
                        workspace,
                        save_dir=game_executable.parent / "SV",
                        completed_slots=expected_results,
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
                        runner = task_module.CczReRandTask(0)
                        runner._target_save_pos = result_slot
                        runner._source_loaded = loaded
                        accepted = runner.run()
                        return AttemptResult(
                            accepted=accepted,
                            source_loaded=bool(
                                getattr(runner, "_source_loaded", False)
                            ),
                            payload=runner,
                        )

                    def recover_session(
                        exc: BaseException,
                        result_slot: int,
                        round_index: int,
                    ) -> None:
                        nonlocal game
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
                        print(
                            "后台游戏运行异常，正在自动重新启动……"
                        )
                        close_game_session(game)
                        game = start_game_session(
                            restarted=True,
                            announce=True,
                        )

                    def attempt_started(
                        result_slot: int,
                        round_index: int,
                    ) -> None:
                        print(
                            f"========== 结果 {result_slot}/"
                            f"{result_count}，原生随机第 "
                            f"{round_index} 轮 =========="
                        )

                    def accepted_result(
                        result: AcceptedResult,
                    ) -> None:
                        runner = result.payload
                        result_slot = result.result_slot
                        equip_info = runner.collect_equipment()
                        panel_paths[result_slot] = save_result_image(
                            runner, equip_info, result_slot
                        )
                        current_grid = compose_result_grid(panel_paths)
                        print(
                            f"第 {result_slot} 号结果图已生成，"
                            f"总图已更新：{current_grid}"
                        )
                        expected_results[result_slot] = (
                            tuple(runner._r0_job_ids),
                            tuple(runner._r0_initial_three),
                        )

                    run_random_workflow(
                        result_count=result_count,
                        max_attempts=10000,
                        run_attempt=run_attempt,
                        recover_session=recover_session,
                        should_recover=(
                            lambda exc: session_failure_requires_restart(
                                game, exc
                            )
                        ),
                        on_attempt_started=attempt_started,
                        on_accepted=accepted_result,
                        check_stop=check_stop_requested,
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

                    verify_on_title = False
                    for output_slot, (
                        expected_jobs,
                        expected_initial_three,
                    ) in expected_results.items():
                        check_stop_requested()
                        saved_path = (
                            game_executable.parent
                            / "SV"
                            / f"SV{output_slot:03}.E5S"
                        )
                        for recovery_attempt in range(2):
                            try:
                                if verify_on_title:
                                    loaded = title_load_verified(
                                        game.pid,
                                        output_slot - 1,
                                        saved_path,
                                    )
                                    verify_on_title = False
                                else:
                                    loaded = direct_load_verified(
                                        game.pid,
                                        output_slot - 1,
                                        saved_path,
                                    )
                                if not loaded:
                                    raise RuntimeError(
                                        f"第 {output_slot} 号存档"
                                        "回读时未能完成后台读取"
                                    )

                                initial_three = read_job_ids(
                                    game.pid, JOB_POSITIONS_R0
                                )
                                if not three_person_mode:
                                    reloaded_jobs = read_job_ids(
                                        game.pid, JOB_POSITIONS_R1
                                    )
                                else:
                                    reloaded_jobs = initial_three
                                validate_reloaded_jobs(
                                    output_slot=output_slot,
                                    expected_jobs=expected_jobs,
                                    expected_initial_three=(
                                        expected_initial_three
                                    ),
                                    reloaded_jobs=reloaded_jobs,
                                    initial_three=initial_three,
                                    three_person_mode=(
                                        three_person_mode
                                    ),
                                )
                                break
                            except Exception as exc:
                                if (
                                    recovery_attempt == 0
                                    and session_failure_requires_restart(
                                        game, exc
                                    )
                                ):
                                    diagnostic_log(
                                        "verify_session_recovery",
                                        pid=game.pid,
                                        output_slot=output_slot,
                                        loop_round=(
                                            round_number
                                            if loop_random
                                            else None
                                        ),
                                        error=repr(exc),
                                    )
                                    print(
                                        "后台游戏校验异常，"
                                        "正在自动重新启动……"
                                    )
                                    close_game_session(game)
                                    game = start_game_session(
                                        restarted=True
                                    )
                                    verify_on_title = True
                                    continue
                                raise
                        else:
                            raise RuntimeError(
                                "后台游戏恢复后仍无法完成回读校验"
                            )

                        print(
                            f"第 {output_slot} 号存档回读校验通过："
                            f"{reloaded_jobs}"
                        )
                except KeyboardInterrupt:
                    archive_incomplete_round()
                    raise

                if not loop_random:
                    break

                assert workspace is not None
                completed_dir = finalize_round(
                    workspace,
                    save_dir=game_executable.parent / "SV",
                    completed_slots=expected_results,
                    metadata=round_metadata(dt.datetime.now()),
                    complete=True,
                )
                assert completed_dir is not None
                final_grid = relocate_result_output(completed_dir)
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
            print(
                f"{result_count} 个结果存档全部生成并通过回读校验。"
            )
        return 0
    except KeyboardInterrupt:
        diagnostic_log("worker_stopped", reason="keyboard_interrupt")
        print("测试已中断。")
        return 130
    except Exception as exc:
        diagnostic_log(
            "worker_failed",
            error=repr(exc),
            traceback=traceback.format_exc(),
        )
        if isinstance(exc, NativeControlError):
            for message_line in str(exc).splitlines():
                if message_line.strip():
                    print(f"环境处理提示：{message_line}")
        traceback.print_exc()
        return 1
    finally:
        diagnostic_log("worker_exit")
        if stop_file is not None:
            stop_file.unlink(missing_ok=True)
        if os.environ.get("CCZ_NO_PAUSE") != "1":
            try:
                input("按回车退出...")
            except EOFError:
                pass
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        log_file.close()


def run_cli() -> int:
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
    if "--inspect-initial-slot" in sys.argv:
        slot_index = sys.argv.index("--inspect-initial-slot")
        output_index = sys.argv.index("--inspect-output")
        game_index = sys.argv.index("--game-executable")
        score_index = (
            sys.argv.index("--job-score")
            if "--job-score" in sys.argv
            else -1
        )
        try:
            inspect_code = inspect_initial_saved_slot(
                Path(sys.argv[game_index + 1]),
                int(sys.argv[slot_index + 1]),
                Path(sys.argv[output_index + 1]),
                float(sys.argv[score_index + 1])
                if score_index >= 0
                else 0.0,
            )
        except Exception:
            traceback.print_exc()
            inspect_code = 1
        return inspect_code
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
        try:
            inspect_code = inspect_saved_slot(
                Path(sys.argv[game_index + 1]),
                int(sys.argv[slot_index + 1]),
                Path(sys.argv[output_index + 1]),
                float(sys.argv[score_index + 1]) if score_index >= 0 else 0.0,
                (
                    int(sys.argv[member_index + 1])
                    if member_index >= 0
                    else None
                ),
            )
        except Exception:
            traceback.print_exc()
            inspect_code = 1
        return inspect_code
    if "--worker" in sys.argv:
        return main()
    return gui_main()


if __name__ == "__main__":
    raise SystemExit(run_cli())
