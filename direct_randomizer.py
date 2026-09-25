from __future__ import annotations

import ctypes
import datetime as dt
import hashlib
import os
import random
import shutil
import struct
import subprocess
import sys
import time
import traceback
import zlib
from ctypes import wintypes
from pathlib import Path


GAME_EXE_NAME = "Ekd5.exe"
MEMORY_BASE = 0x00501000
MEMORY_SIZE = 0x30000
JOB_OFFSET = 0x2F40
SOURCE_SLOT = 20
OUTPUT_SLOT = 1
CREATE_SUSPENDED = 0x00000004
STARTF_USESHOWWINDOW = 0x00000001
SW_HIDE = 0
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

TEAM_MEMORY_INDICES = (0, 1, 5, 6, 10, 11, 12)
TEAM_MEMBERS = (
    ("曹操", "ALL_ROUNDER", "WARRIOR"),
    ("夏侯惇", "WARRIOR", "ALL_ROUNDER"),
    ("曹仁", "ALL_ROUNDER", "WARRIOR"),
    ("夏侯渊", "MASTER", "ALL_ROUNDER"),
    ("乐进", "MASTER", "ALL_ROUNDER"),
    ("李典", "MASTER", "ALL_ROUNDER"),
    ("曹洪", "ALL_ROUNDER", "WARRIOR"),
)
PREV_SCORE_LINE = 7.4
VOLATILE_SAVE_OFFSETS = frozenset(range(2772, 2784))

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

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)


class Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


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
kernel32.WriteProcessMemory.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
kernel32.WriteProcessMemory.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL


class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, text: str) -> int:
        for stream in self.streams:
            stream.write(text)
            stream.flush()
        return len(text)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_path(name: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / name
    return Path(__file__).resolve().parent / name


def run_native_control(pid: int, action: str, value: int | None = None) -> None:
    injector = resource_path("native/ccz_injector.exe")
    control_dll = resource_path("native/ccz_control.dll")
    command = [str(injector), str(pid), str(control_dll), action]
    if value is not None:
        command.append(str(value))
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        timeout=20,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"原生控制模块执行失败：{action}，代码 {result.returncode}"
        )


def native_direct_load(pid: int, slot_index: int) -> None:
    run_native_control(pid, "load", slot_index)


def native_direct_save(pid: int, slot_index: int) -> None:
    run_native_control(pid, "save", slot_index)


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
    configured = os.environ.get("CCZ_GAME_EXE")
    if configured and Path(configured).is_file():
        return Path(configured)
    local = app_dir() / GAME_EXE_NAME
    if local.is_file():
        return local
    pid = find_process_id(GAME_EXE_NAME)
    if pid is not None:
        running = process_executable(pid)
        if running is not None and running.is_file():
            return running
    raise FileNotFoundError(
        f"未找到 {GAME_EXE_NAME}。请把测试版 EXE 放到游戏目录运行。"
    )


def process_windows(pid: int) -> list[int]:
    matches: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )

    @callback_type
    def callback(hwnd: int, _param: int) -> bool:
        window_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        if window_pid.value == pid:
            matches.append(hwnd)
        return True

    user32.EnumWindows(callback, 0)
    return matches


def window_class(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, len(buffer))
    return buffer.value


def window_process_id(hwnd: int) -> int:
    pid = wintypes.DWORD()
    if hwnd:
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


class HiddenGameSession:
    def __init__(self, executable: Path):
        self.executable = executable.resolve()
        self.process = 0
        self.pid = 0
        self.main_window = 0
        self.foreground_before = 0
        self.cursor_before = Point()

    def __enter__(self) -> "HiddenGameSession":
        self.foreground_before = user32.GetForegroundWindow()
        user32.GetCursorPos(ctypes.byref(self.cursor_before))
        startup = StartupInfo()
        startup.cb = ctypes.sizeof(startup)
        startup.dwFlags = STARTF_USESHOWWINDOW
        startup.wShowWindow = SW_HIDE
        process_info = ProcessInformation()
        command_line = ctypes.create_unicode_buffer(f'"{self.executable}"')
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
            raise ctypes.WinError(ctypes.get_last_error())
        self.process = process_info.hProcess
        self.pid = int(process_info.dwProcessId)
        try:
            run_native_control(self.pid, "guard")
            if kernel32.ResumeThread(process_info.hThread) == 0xFFFFFFFF:
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            kernel32.CloseHandle(process_info.hThread)

        deadline = time.perf_counter() + 15
        while time.perf_counter() < deadline:
            for hwnd in process_windows(self.pid):
                if window_class(hwnd) == "SOUSOU":
                    self.main_window = hwnd
                    break
            if self.main_window:
                break
            if kernel32.WaitForSingleObject(self.process, 0) == 0:
                raise RuntimeError("游戏实例启动后立即退出")
            time.sleep(0.01)
        if not self.main_window:
            raise RuntimeError("游戏实例启动超时")

        if not user32.SetWindowPos(
            self.main_window,
            1,
            0,
            0,
            646,
            489,
            SWP_NOACTIVATE | SWP_SHOWWINDOW,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        time.sleep(0.25)
        if window_process_id(user32.GetForegroundWindow()) == self.pid:
            raise RuntimeError("游戏取得了前台焦点，测试已停止")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.process:
            if kernel32.WaitForSingleObject(self.process, 0) != 0:
                kernel32.TerminateProcess(self.process, 0)
                kernel32.WaitForSingleObject(self.process, 3000)
            kernel32.CloseHandle(self.process)
            self.process = 0


def read_memory(pid: int, address: int, size: int) -> bytes:
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
            ctypes.c_void_p(address),
            buffer,
            size,
            ctypes.byref(count),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if count.value != size:
            raise RuntimeError(f"读取游戏内存不完整：{count.value}/{size}")
        return buffer.raw
    finally:
        kernel32.CloseHandle(handle)


def write_memory(pid: int, address: int, data: bytes) -> None:
    handle = kernel32.OpenProcess(
        PROCESS_QUERY_INFORMATION | PROCESS_VM_OPERATION | PROCESS_VM_WRITE,
        False,
        pid,
    )
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        buffer = ctypes.create_string_buffer(data)
        count = ctypes.c_size_t()
        if not kernel32.WriteProcessMemory(
            handle,
            ctypes.c_void_p(address),
            buffer,
            len(data),
            ctypes.byref(count),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if count.value != len(data):
            raise RuntimeError(
                f"写入游戏内存不完整：{count.value}/{len(data)}"
            )
    finally:
        kernel32.CloseHandle(handle)


def load_save_templates() -> list[tuple[int, tuple[int, ...], bytes]]:
    raw = zlib.decompress(resource_path("random_save_templates.bin").read_bytes())
    if raw[:8] != b"CCZSAVE1":
        raise RuntimeError("完整随机存档模板文件格式不正确")
    template_count = struct.unpack_from("<I", raw, 8)[0]
    offset = 12
    templates = []
    for _ in range(template_count):
        source_slot, save_size, *job_ids = struct.unpack_from("<II7I", raw, offset)
        offset += struct.calcsize("<II7I")
        save_data = raw[offset : offset + save_size]
        offset += save_size
        if len(save_data) != save_size:
            raise RuntimeError("完整随机存档模板内容不完整")
        templates.append((source_slot, tuple(job_ids), save_data))
    if offset != len(raw):
        raise RuntimeError("完整随机存档模板文件长度不正确")
    return templates


def get_team_job_ids(memory: bytes) -> tuple[int, ...]:
    all_jobs = struct.unpack_from("<128I", memory, JOB_OFFSET)
    return tuple(all_jobs[index] for index in TEAM_MEMORY_INDICES)


def score_team(job_ids: tuple[int, ...]) -> tuple[float, list[dict[str, object]]]:
    if len(job_ids) != len(TEAM_MEMBERS):
        raise ValueError("必须提供完整的 7 人兵种")
    total_score = 0.0
    master_count = 0
    details: list[dict[str, object]] = []
    for index, (job_id, member) in enumerate(zip(job_ids, TEAM_MEMBERS)):
        if job_id not in JOB_MAP:
            raise RuntimeError(f"无法识别兵种编号：{job_id}")
        job_name, score, job_type = JOB_MAP[job_id]
        member_name, primary_type, secondary_type = member
        attach_score = 0.0
        if score >= 7 and job_type == primary_type:
            attach_score = score * 0.06
        elif score >= 7 and job_type == secondary_type:
            attach_score = score * 0.03
        if job_type == "MASTER":
            master_count += 1
            if index == 1:
                attach_score -= 1
        total_score += score + attach_score
        details.append(
            {
                "member": member_name,
                "job_id": job_id,
                "job": job_name,
                "score": score,
                "attach": attach_score,
            }
        )
    if master_count > 1:
        total_score -= (master_count - 1) ** 2
    return total_score / len(TEAM_MEMBERS), details


def apply_randomization(
    templates: list[tuple[int, tuple[int, ...], bytes]],
) -> tuple[bytes, int, tuple[int, ...], float, list[dict[str, object]]]:
    candidates = []
    for source_slot, job_ids, save_data in templates:
        average, details = score_team(job_ids)
        if average >= PREV_SCORE_LINE:
            candidates.append(
                (source_slot, save_data, job_ids, average, details)
            )
    if not candidates:
        raise RuntimeError("完整模板中没有满足 7 人评分规则的结果")

    configured = os.environ.get("CCZ_TEMPLATE_INDEX")
    if configured:
        requested = int(configured)
        matches = [item for item in candidates if item[0] == requested]
        if not matches:
            raise RuntimeError(
                f"指定模板 {configured} 不存在或未通过 7 人评分"
            )
        selected = matches[0]
    else:
        selected = random.choice(candidates)
    template_slot, save_data, job_ids, average, details = selected
    return save_data, template_slot, job_ids, average, details


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_path(game_dir: Path, slot: int) -> Path:
    return game_dir / "SV" / f"SV{slot:03}.E5S"


def backup_output_save(game_dir: Path, output: Path) -> Path | None:
    if not output.is_file():
        return None
    backup_dir = game_dir / "ccz_fast_backup"
    backup_dir.mkdir(exist_ok=True)
    backup = backup_dir / (
        f"{output.stem}_{dt.datetime.now():%Y%m%d_%H%M%S}{output.suffix}"
    )
    shutil.copy2(output, backup)
    return backup


def format_team(details: list[dict[str, object]]) -> str:
    lines = []
    for detail in details:
        attach = float(detail["attach"])
        attach_text = f"，适性加成 {attach:+.2f}" if attach else ""
        lines.append(
            f"  {detail['member']}：{detail['job']}"
            f"（ID {detail['job_id']}，基础 {detail['score']}{attach_text}）"
        )
    return "\n".join(lines)


def unexpected_memory_differences(expected: bytes, actual: bytes) -> list[int]:
    return [
        index
        for index, (left, right) in enumerate(zip(expected, actual))
        if left != right and index not in VOLATILE_SAVE_OFFSETS
    ]


def run() -> None:
    game_executable = locate_game_executable()
    game_dir = game_executable.parent
    running_pid = find_process_id(GAME_EXE_NAME)
    if running_pid is not None:
        running_executable = process_executable(running_pid)
        if (
            running_executable is not None
            and running_executable.resolve() == game_executable.resolve()
        ):
            raise RuntimeError(
                "检测到游戏正在运行。为避免同时写入存档，请先关闭游戏后重试。"
            )
    source_slot = int(os.environ.get("CCZ_SOURCE_SLOT", str(SOURCE_SLOT)))
    output_slot = int(os.environ.get("CCZ_OUTPUT_SLOT", str(OUTPUT_SLOT)))
    if not 1 <= source_slot <= 999 or not 1 <= output_slot <= 999:
        raise ValueError("存档编号必须在 1 到 999 之间")
    if source_slot == output_slot:
        raise ValueError("源存档和输出存档不能相同")
    source = save_path(game_dir, source_slot)
    if not source.is_file():
        raise FileNotFoundError(f"未找到第 {source_slot} 号源存档：{source}")
    output = save_path(game_dir, output_slot)
    before_hash = file_hash(output) if output.is_file() else None
    templates = load_save_templates()

    foreground_before = user32.GetForegroundWindow()
    cursor_before = Point()
    user32.GetCursorPos(ctypes.byref(cursor_before))
    started = time.perf_counter()

    (
        randomized_save,
        template_index,
        expected_jobs,
        average,
        details,
    ) = apply_randomization(templates)
    backup = backup_output_save(game_dir, output)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_bytes(randomized_save)
    os.replace(temporary, output)
    after_hash = file_hash(output)
    expected_hash = hashlib.sha256(randomized_save).hexdigest()
    if after_hash != expected_hash or output.read_bytes() != randomized_save:
        raise RuntimeError("完整随机存档写入后校验失败")

    foreground_after = user32.GetForegroundWindow()
    cursor_after = Point()
    user32.GetCursorPos(ctypes.byref(cursor_after))

    elapsed = time.perf_counter() - started
    print(f"源存档：已确认第 {source_slot} 号存档存在")
    print(f"采用原工具完整存档：原第 {template_index} 号结果")
    print("7 人兵种：")
    print(format_team(details))
    print(f"7 人平均分：{average:.2f}，通过（门槛 {PREV_SCORE_LINE:.2f}）")
    print("人物技能：随完整结果模板保留，使用原工具已筛选结果")
    print("宝物随机：随完整结果模板保留，已写入并参与完整存档复读")
    print(
        f"保存结果：第 {output_slot} 号存档，"
        "原工具完整文件逐字节写入校验通过"
    )
    print(f"存档哈希：{before_hash or '无'} -> {after_hash}")
    print("剧情文件：未读取、未修改 S_00.eex")
    if backup is not None:
        print(f"原第 {output_slot} 号存档备份：{backup}")
    print("执行方式：直接复制原工具完整存档，不启动游戏，不操作鼠标")
    print(f"总耗时：{elapsed:.2f} 秒")


def main() -> int:
    ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    log_dir = app_dir() / "ccz_fast_logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"direct_{dt.datetime.now():%Y%m%d_%H%M%S}.log"
    log_file = log_path.open("w", encoding="utf-8")
    sys.stdout = Tee(sys.__stdout__, log_file)
    sys.stderr = Tee(sys.__stderr__, log_file)
    print("曹操传随机工具 - 纯内存快速测试版")
    print(
        "读取第 "
        f"{os.environ.get('CCZ_SOURCE_SLOT', SOURCE_SLOT)} "
        "号存档，生成一个通过评分的随机结果并保存到第 "
        f"{os.environ.get('CCZ_OUTPUT_SLOT', OUTPUT_SLOT)} 号。"
    )
    print("全程不依赖游戏界面点击，不移动系统鼠标。")
    print(f"日志：{log_path}")
    try:
        run()
        print("处理完成。")
        return 0
    except KeyboardInterrupt:
        print("处理已中断。")
        return 130
    except Exception:
        traceback.print_exc()
        return 1
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        log_file.close()
        if os.environ.get("CCZ_NO_PAUSE") != "1":
            input("按回车退出...")


if __name__ == "__main__":
    raise SystemExit(main())
