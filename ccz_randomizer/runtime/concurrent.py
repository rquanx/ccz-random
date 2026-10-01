from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import queue
import datetime as dt
import hashlib
import json
import re
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from ccz_randomizer.runtime.game_sandbox import (
    CONCURRENT_SAVE_NAMES,
    cleanup_stale_sandboxes,
    create_game_sandbox,
    ensure_hidden_runtime_directory,
    remove_sandbox_tree,
)
CONCURRENT_EVENT_PREFIX = "@@CCZ_CONCURRENT_EVENT@@"
CONCURRENT_HEARTBEAT_LINE = "@@CCZ_CONCURRENT_HEARTBEAT@@"
CONCURRENT_SLOT_ASSIGNED_PREFIX = "@@CCZ_SLOT_ASSIGNED@@"
CONCURRENT_SLOT_RETRY_PREFIX = "@@CCZ_SLOT_RETRY@@"
CONCURRENT_SLOT_FAILED_PREFIX = "@@CCZ_SLOT_FAILED@@"
CONCURRENT_RESULT_IMAGE_PREFIX = "@@CCZ_RESULT_IMAGE@@"
CONCURRENT_HEARTBEAT_INTERVAL_SECONDS = 2.0
CONCURRENT_WORKER_TIMEOUT_SECONDS = 60.0
CONCURRENT_SLOT_MAX_FAILURES = 3
CONCURRENT_STARTUP_FAILURE_LIMIT = 3
CONCURRENT_COMPATIBILITY_FALLBACK_CODE = 75
CONCURRENT_STOP_GRACE_SECONDS = 2.0
CONCURRENT_CRITICAL_STOP_GRACE_SECONDS = 15.0
CONCURRENT_STOP_HARD_TIMEOUT_SECONDS = 20.0
CONCURRENT_STARTUP_STAGGER_SECONDS = 0.2
_STARTUP_CONFIRMED_PREFIXES = (
    "游戏原生随机已触发",
    "R0 ",
    "R1 ",
    "第 ",
)
_STARTUP_FAILURE_MARKERS = (
    "随机游戏实例启动后退出",
    "静默游戏实例启动后立即退出",
    "静默游戏实例启动超时",
)
_RESULT_SAVE_CONFIRMATION = re.compile(
    r"^第\s*(\d+)\s*号结果存档已通过游戏菜单保存(?:$|[，。])"
)


class _TimingRecorder:
    """Write scheduler timings without adding user-facing console output."""

    def __init__(self, base_dir: Path, *, mode: str, worker_count: int) -> None:
        log_dir = base_dir / "ccz_fast_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = log_dir / (
            f"concurrent_{stamp}_{os.getpid()}_timing.jsonl"
        )
        self._file = self.path.open("a", encoding="utf-8")
        self._lock = threading.Lock()
        self._common = {
            "mode": mode,
            "worker_count": worker_count,
            "pid": os.getpid(),
        }

    def close(self) -> None:
        with self._lock:
            if not self._file.closed:
                self._file.close()

    def write(self, event: str, **fields) -> None:
        record = {
            "time": dt.datetime.now().isoformat(timespec="milliseconds"),
            "event": event,
            **self._common,
            **fields,
        }
        try:
            line = json.dumps(
                record,
                ensure_ascii=False,
                default=str,
                separators=(",", ":"),
            )
            with self._lock:
                if not self._file.closed:
                    self._file.write(line + "\n")
                    self._file.flush()
        except (OSError, ValueError):
            pass

    @contextmanager
    def phase(self, name: str, **fields):
        started = time.perf_counter()
        self.write("timing_started", phase=name, **fields)
        try:
            yield
        except BaseException as exc:
            self.write(
                "timing_finished",
                phase=name,
                elapsed_ms=round((time.perf_counter() - started) * 1000),
                outcome="error",
                error=repr(exc),
                **fields,
            )
            raise
        else:
            self.write(
                "timing_finished",
                phase=name,
                elapsed_ms=round((time.perf_counter() - started) * 1000),
                outcome="ok",
                **fields,
            )


def _is_worker_progress_line(line: str | None) -> bool:
    return line is not None and line != CONCURRENT_HEARTBEAT_LINE


class CompatibilitySandboxSetupError(RuntimeError):
    """Compatibility sandbox could not be prepared before a worker started."""


def start_concurrent_worker_heartbeat(
    stream,
    *,
    interval: float = CONCURRENT_HEARTBEAT_INTERVAL_SECONDS,
) -> threading.Event:
    """Keep the parent scheduler informed even while native work is blocked."""
    stop_event = threading.Event()

    def emit() -> None:
        while not stop_event.wait(interval):
            try:
                stream.write(CONCURRENT_HEARTBEAT_LINE + "\n")
                stream.flush()
            except (BrokenPipeError, OSError, ValueError):
                return

    threading.Thread(
        target=emit,
        name="ccz-concurrent-heartbeat",
        daemon=True,
    ).start()
    return stop_event


def encode_concurrent_event(
    worker_index: int,
    line: str,
    *,
    round_number: int | None = None,
) -> str:
    payload = {
        "worker": worker_index,
        "line": line,
    }
    if round_number is not None:
        payload["round"] = round_number
    return CONCURRENT_EVENT_PREFIX + json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
    )


def decode_concurrent_event(
    line: str,
) -> tuple[int, int | None, str] | None:
    if not line.startswith(CONCURRENT_EVENT_PREFIX):
        return None
    payload = json.loads(line[len(CONCURRENT_EVENT_PREFIX):])
    worker_index = int(payload["worker"])
    round_value = payload.get("round")
    round_number = int(round_value) if round_value is not None else None
    child_line = str(payload["line"])
    if worker_index < 1:
        raise ValueError("并发实例编号必须大于 0")
    if round_number is not None and round_number < 1:
        raise ValueError("并发轮次必须大于 0")
    return worker_index, round_number, child_line


def _publish_save(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _file_hash(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _worker_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--worker"]
    return [sys.executable, str(Path(__file__).resolve().parents[2] / "fast_randomizer.py"), "--worker"]


def _should_forward_line(line: str) -> bool:
    if line.startswith(
        (
            "@@CCZ_RESULT_DETAIL@@",
            "@@CCZ_SECURITY_SOFTWARE_BLOCKED@@",
        )
    ):
        return True
    return line.startswith(
        (
            "========== 结果 ",
            "R0 ",
            "R1 ",
            "初始三人兵种合格，正在检查特技条件",
            "用户进度:",
            "规则原因:",
            "第 ",
            "后台游戏",
            "隐藏游戏",
            "兼容模式:",
            "游戏原生随机已触发",
            "并发轮次开始：",
            "循环轮次",
            "本轮结果目录:",
            "本轮结果目录：",
            "结果图",
        )
    )


def _batch_stamp(round_number: int) -> str:
    return dt.datetime.now().strftime(
        f"%Y-%m-%d %H.%M.%S-r{round_number}"
    )


def partition_slots(result_count: int, worker_count: int) -> list[list[int]]:
    if not 1 <= result_count <= 15:
        raise ValueError("结果数量必须位于 1-15")
    if worker_count < 1:
        raise ValueError("同时运行数量必须大于 0")
    worker_count = min(worker_count, result_count)
    return [
        list(range(index + 1, result_count + 1, worker_count))
        for index in range(worker_count)
    ]


class DynamicSlotQueue:
    """Assign the next unfinished slot to whichever worker becomes free."""

    def __init__(self, result_count: int) -> None:
        if not 1 <= result_count <= 15:
            raise ValueError("结果数量必须位于 1-15")
        self._pending = deque(range(1, result_count + 1))
        self._active: dict[int, int] = {}

    def claim(self, worker_index: int) -> int | None:
        if worker_index in self._active:
            raise ValueError("实例仍有未完成的存档任务")
        if not self._pending:
            return None
        slot = self._pending.popleft()
        self._active[worker_index] = slot
        return slot

    def finish(self, worker_index: int, *, retry: bool = False) -> int:
        slot = self._active.pop(worker_index)
        if retry:
            self._pending.appendleft(slot)
        return slot

    def cancel_pending(self) -> None:
        """Discard tasks that have not been claimed after a stop request."""
        self._pending.clear()

    @property
    def has_pending(self) -> bool:
        return bool(self._pending)

    @property
    def has_active(self) -> bool:
        return bool(self._active)


@dataclass
class _WorkerLane:
    index: int
    sandbox: Path
    process: subprocess.Popen[str] | None = None
    output_thread: threading.Thread | None = None
    slot: int | None = None
    round_number: int | None = None
    baseline: str | None = None
    panel_baseline: dict[str, tuple[int, int]] | None = None
    disabled: bool = False
    last_activity_at: float = 0.0
    timed_out: bool = False
    startup_confirmed: bool = False
    startup_failed: bool = False
    attempt_completed: bool = False
    result_saved: bool = False
    generation: int = 0
    started_at: float = 0.0


def _record_worker_output(lane: _WorkerLane, line: str) -> bool:
    was_confirmed = lane.startup_confirmed
    if line.startswith(_STARTUP_CONFIRMED_PREFIXES):
        lane.startup_confirmed = True
    if line.startswith("@@CCZ_RESULT_DETAIL@@"):
        lane.attempt_completed = True
    save_confirmation = _RESULT_SAVE_CONFIRMATION.match(line)
    if (
        save_confirmation is not None
        and lane.slot == int(save_confirmation.group(1))
    ):
        lane.result_saved = True
    if any(marker in line for marker in _STARTUP_FAILURE_MARKERS):
        lane.startup_failed = True
    return lane.startup_confirmed and not was_confirmed


@dataclass(frozen=True)
class _LoopTask:
    round_number: int
    slot: int


@dataclass
class _LoopRound:
    number: int
    workspace: Path
    completed_slots: set[int]
    archived_path: Path | None = None
    grid_path: Path | None = None
    grid_announced: bool = False


def _stop_worker_process(
    process: subprocess.Popen[str],
    *,
    wait_seconds: float = 5.0,
) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=wait_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _stop_worker_processes(
    processes: list[subprocess.Popen[str]],
    *,
    wait_seconds: float = 2.0,
) -> None:
    running = [process for process in processes if process.poll() is None]
    for process in running:
        process.terminate()
    deadline = time.monotonic() + wait_seconds
    while running and time.monotonic() < deadline:
        running = [
            process for process in running
            if process.poll() is None
        ]
        if running:
            time.sleep(0.05)
    for process in running:
        process.kill()
    for process in running:
        process.wait()


def _collect_result_images(
    sandboxes: list[Path],
    slots: list[int],
    base_dir: Path,
) -> Path | None:
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H.%M.%S")
    result_root = base_dir / "randResult"
    panel_dir = result_root / "panels" / stamp
    grid_path = result_root / f"{stamp}-random.png"
    duplicate = 2
    while panel_dir.exists() or grid_path.exists():
        unique = f"{stamp} ({duplicate})"
        panel_dir = result_root / "panels" / unique
        grid_path = result_root / f"{unique}-random.png"
        duplicate += 1
    panel_dir.mkdir(parents=True, exist_ok=False)

    copied: dict[int, Path] = {}
    for slot in slots:
        pattern = f"randResult/panels/*/save{slot}.png"
        source = next(
            (
                candidate
                for sandbox in sandboxes
                for candidate in sandbox.glob(pattern)
            ),
            None,
        )
        if source is None:
            continue
        target = panel_dir / source.name
        shutil.copy2(source, target)
        copied[slot] = target
    if not copied:
        shutil.rmtree(panel_dir, ignore_errors=True)
        return None

    _compose_result_grid(copied, grid_path)
    return grid_path


def _unique_batch_result_paths(base_dir: Path) -> tuple[Path, Path]:
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H.%M.%S")
    result_root = base_dir / "randResult"
    panel_dir = result_root / "panels" / stamp
    grid_path = result_root / f"{stamp}-random.png"
    duplicate = 2
    while panel_dir.exists() or grid_path.exists():
        unique = f"{stamp} ({duplicate})"
        panel_dir = result_root / "panels" / unique
        grid_path = result_root / f"{unique}-random.png"
        duplicate += 1
    return panel_dir, grid_path


def _update_result_grid(
    panel_dir: Path,
    grid_path: Path,
    result_count: int,
) -> bool:
    panels = {
        slot: panel_dir / f"save{slot}.png"
        for slot in range(1, result_count + 1)
        if (panel_dir / f"save{slot}.png").is_file()
    }
    if not panels:
        return False
    _compose_result_grid(panels, grid_path)
    return True


def _compose_result_grid(
    panels: dict[int, Path],
    grid_path: Path,
) -> None:
    from PIL import Image

    panel_width, panel_height = 740, 1028
    grid = Image.new(
        "RGB",
        (panel_width * 5, panel_height * 3),
        (235, 233, 228),
    )
    for slot, panel_path in sorted(panels.items()):
        with Image.open(panel_path) as source:
            panel = source.convert("RGB")
        if panel.size != (panel_width, panel_height):
            panel = panel.resize(
                (panel_width, panel_height),
                Image.Resampling.LANCZOS,
            )
        position = slot - 1
        grid.paste(
            panel,
            (
                (position % 5) * panel_width,
                (position // 5) * panel_height,
            ),
        )
    temporary = grid_path.with_suffix(".tmp.png")
    grid_path.parent.mkdir(parents=True, exist_ok=True)
    grid.save(temporary, "PNG")
    os.replace(temporary, grid_path)


def run_concurrent_workers(
    *,
    game_executable: Path,
    result_count: int,
    mode: str,
    stop_file: Path | None,
    base_dir: Path,
    worker_count: int = 1,
    loop_random: bool = False,
    compatibility_mode: bool = False,
) -> int:
    """Run isolated workers and publish each completed result."""
    if worker_count < 1:
        raise ValueError("同时运行数量必须大于 0")
    if not loop_random and worker_count > 15:
        raise ValueError("非循环模式同时运行数量必须位于 1-15")
    if not 1 <= result_count <= 15:
        raise ValueError("结果数量必须位于 1-15")

    try:
        if loop_random:
            result = _run_continuous_loop(
                game_executable=game_executable,
                result_count=result_count,
                mode=mode,
                stop_file=stop_file,
                base_dir=base_dir,
                worker_count=worker_count,
                compatibility_mode=compatibility_mode,
            )
        else:
            result = _run_concurrent_batch(
                game_executable=game_executable,
                result_count=result_count,
                mode=mode,
                stop_file=stop_file,
                base_dir=base_dir,
                worker_count=worker_count,
                round_number=1,
                compatibility_mode=compatibility_mode,
            )
    except CompatibilitySandboxSetupError as exc:
        print(
            f"无法准备独立运行目录：{exc}",
            flush=True,
        )
        result = CONCURRENT_COMPATIBILITY_FALLBACK_CODE

    if (
        result == CONCURRENT_COMPATIBILITY_FALLBACK_CODE
        and not compatibility_mode
    ):
        print(
            "沙箱副本无法启动，正在尝试兼容模式多实例。",
            flush=True,
        )
        try:
            if loop_random:
                result = _run_continuous_loop(
                    game_executable=game_executable,
                    result_count=result_count,
                    mode=mode,
                    stop_file=stop_file,
                    base_dir=base_dir,
                    worker_count=worker_count,
                    compatibility_mode=True,
                )
            else:
                result = _run_concurrent_batch(
                    game_executable=game_executable,
                    result_count=result_count,
                    mode=mode,
                    stop_file=stop_file,
                    base_dir=base_dir,
                    worker_count=worker_count,
                    round_number=1,
                    compatibility_mode=True,
                )
        except CompatibilitySandboxSetupError:
            result = CONCURRENT_COMPATIBILITY_FALLBACK_CODE

    if result == CONCURRENT_COMPATIBILITY_FALLBACK_CODE:
        print(
            "兼容模式多实例无法启动，已回退为单实例并使用游戏原目录。",
            flush=True,
        )
        return _run_original_directory_worker(
            game_executable=game_executable,
            result_count=result_count,
            mode=mode,
            stop_file=stop_file,
            base_dir=base_dir,
            loop_random=loop_random,
        )
    return result


def _run_original_directory_worker(
    *,
    game_executable: Path,
    result_count: int,
    mode: str,
    stop_file: Path | None,
    base_dir: Path,
    loop_random: bool,
) -> int:
    child_env = os.environ.copy()
    child_env.pop("CCZ_GAME_RUNTIME_DIR", None)
    child_env.update(
        {
            "CCZ_AUTOSTART": "1",
            "CCZ_NO_PAUSE": "1",
            "CCZ_GAME_EXE": str(game_executable),
            "CCZ_RESULT_BASE_DIR": str(base_dir),
            "CCZ_LOG_BASE_DIR": str(base_dir),
            "CCZ_HISTORY_SAVE_ROOT": str(game_executable.parent),
            "CCZ_RESULT_COUNT": str(result_count),
            "CCZ_RESULT_SLOT_START": "1",
            "CCZ_TOTAL_RESULT_COUNT": str(result_count),
            "CCZ_RANDOM_MODE": mode,
            "CCZ_LOOP_RANDOM": "1" if loop_random else "0",
            "CCZ_CONCURRENT_MODE": "1",
            "CCZ_CONCURRENT_WORKER": "1",
            "CCZ_CONCURRENT_COUNT": "1",
            "CCZ_COMPATIBILITY_DIRECT": "1",
            "CCZ_RUN_STAMP": _batch_stamp(1),
            "CCZ_CRITICAL_OPERATION_FILE": str(
                base_dir / "ccz_fast_data" / ".ccz-critical-operation"
            ),
        }
    )
    if stop_file is not None:
        child_env["CCZ_STOP_FILE"] = str(stop_file)
    process = subprocess.Popen(
        _worker_command(),
        cwd=str(base_dir),
        env=child_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert process.stdout is not None
    try:
        for raw_line in iter(process.stdout.readline, ""):
            line = raw_line.rstrip("\r\n")
            if line == CONCURRENT_HEARTBEAT_LINE:
                continue
            round_match = re.match(
                r"^循环轮次开始：第\s*(\d+)\s*轮$",
                line,
            )
            if round_match:
                print(
                    f"并发轮次开始：第 {round_match.group(1)} 轮",
                    flush=True,
                )
                continue
            result_match = re.match(
                r"^========== 结果\s+(\d+)/",
                line,
            )
            if result_match:
                print(
                    encode_concurrent_event(
                        1,
                        CONCURRENT_SLOT_ASSIGNED_PREFIX
                        + result_match.group(1),
                    ),
                    flush=True,
                )
            if (
                _should_forward_line(line)
                or line.startswith("本轮总图路径：")
            ):
                print(encode_concurrent_event(1, line), flush=True)
        return process.wait()
    finally:
        process.stdout.close()
        _stop_worker_process(process)


def _panel_snapshot(sandbox: Path, slot: int) -> dict[str, tuple[int, int]]:
    snapshot: dict[str, tuple[int, int]] = {}
    for path in sandbox.glob(f"randResult/panels/*/save{slot}.png"):
        try:
            stat = path.stat()
        except OSError:
            continue
        snapshot[str(path)] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


def _copy_updated_panel(
    sandbox: Path,
    slot: int,
    baseline: dict[str, tuple[int, int]] | None,
    target: Path,
) -> bool:
    baseline = baseline or {}
    candidates: list[tuple[int, Path]] = []
    for path in sandbox.glob(f"randResult/panels/*/save{slot}.png"):
        try:
            stat = path.stat()
        except OSError:
            continue
        if baseline.get(str(path)) == (stat.st_size, stat.st_mtime_ns):
            continue
        candidates.append((stat.st_mtime_ns, path))
    if not candidates:
        return False
    _, source = max(candidates, key=lambda item: item[0])
    _publish_save(source, target)
    return True


def _unique_loop_result_root(base_dir: Path) -> Path:
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H.%M.%S")
    root = base_dir / "randResult" / "loop" / stamp
    duplicate = 2
    while root.exists():
        root = base_dir / "randResult" / "loop" / f"{stamp} ({duplicate})"
        duplicate += 1
    root.mkdir(parents=True, exist_ok=False)
    return root


def _run_continuous_loop(
    *,
    game_executable: Path,
    result_count: int,
    mode: str,
    stop_file: Path | None,
    base_dir: Path,
    worker_count: int,
    compatibility_mode: bool = False,
) -> int:
    stamp = f"{os.getpid()}-{time.time_ns()}"
    runtime_root = base_dir / "ccz_fast_data"
    try:
        ensure_hidden_runtime_directory(runtime_root)
        sandboxes_root = runtime_root / "sandboxes"
        sandboxes_root.mkdir(parents=True, exist_ok=True)
        cleanup_stale_sandboxes(sandboxes_root)
        session_root = sandboxes_root / stamp
        sandbox_root = session_root / "workers"
        sandbox_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        if compatibility_mode:
            raise CompatibilitySandboxSetupError(str(exc)) from exc
        raise
    result_root = _unique_loop_result_root(base_dir)
    timing = _TimingRecorder(
        base_dir,
        mode=mode,
        worker_count=worker_count,
    )
    lanes: list[_WorkerLane] = []
    pending: deque[_LoopTask] = deque()
    active: dict[int, _LoopTask] = {}
    rounds: dict[int, _LoopRound] = {}
    task_failures: dict[_LoopTask, int] = {}
    output_queue: queue.Queue[
        tuple[int, int, int, str | None, float]
    ] = queue.Queue()
    next_round_number = 1
    next_publish_round = 1
    stopped = False
    fatal_error = False
    stop_requested_at: float | None = None
    startup_gate_open = worker_count == 1
    consecutive_startup_failures = 0
    compatibility_probe_passed = not compatibility_mode
    compatibility_probe_failed = False
    startup_circuit_open = False

    def forward_output(
        worker_index: int,
        round_number: int,
        generation: int,
        stream,
    ) -> None:
        for line in iter(stream.readline, ""):
            output_queue.put(
                (
                    worker_index,
                    round_number,
                    generation,
                    line.rstrip("\r\n"),
                    time.monotonic(),
                )
            )
        stream.close()
        output_queue.put(
            (
                worker_index,
                round_number,
                generation,
                None,
                time.monotonic(),
            )
        )

    def drain_output() -> None:
        nonlocal consecutive_startup_failures
        nonlocal compatibility_probe_passed
        while True:
            try:
                index, round_number, generation, line, received_at = (
                    output_queue.get_nowait()
                )
            except queue.Empty:
                break
            lane = lanes[index - 1]
            if generation != lane.generation:
                continue
            if _is_worker_progress_line(line):
                lane.last_activity_at = received_at
                attempt_was_completed = lane.attempt_completed
                if _record_worker_output(lane, line):
                    consecutive_startup_failures = 0
                if (
                    not attempt_was_completed
                    and lane.attempt_completed
                ):
                    compatibility_probe_passed = True
            if line == CONCURRENT_HEARTBEAT_LINE:
                continue
            if line is not None and _should_forward_line(line):
                print(
                    encode_concurrent_event(
                        index,
                        line,
                        round_number=round_number,
                    ),
                    flush=True,
                )

    def create_round() -> None:
        nonlocal next_round_number
        round_number = next_round_number
        workspace = result_root / f"round-{round_number:06d}"
        (workspace / "SV").mkdir(parents=True, exist_ok=True)
        (workspace / "panels").mkdir(parents=True, exist_ok=True)
        rounds[round_number] = _LoopRound(
            number=round_number,
            workspace=workspace,
            completed_slots=set(),
        )
        pending.extend(
            _LoopTask(round_number, slot)
            for slot in range(1, result_count + 1)
        )
        next_round_number += 1
        print(f"并发轮次开始：第 {round_number} 轮", flush=True)

    def claim_task(worker_index: int) -> _LoopTask | None:
        if stopped or fatal_error:
            return None
        if not pending:
            create_round()
        task = pending.popleft()
        active[worker_index] = task
        return task

    def launch_next(lane: _WorkerLane) -> bool:
        if lane.disabled:
            return False
        if stop_file is not None and stop_file.exists():
            return False
        task = claim_task(lane.index)
        if task is None:
            return False
        lane.slot = task.slot
        lane.round_number = task.round_number
        target_save = lane.sandbox / "SV" / f"SV{task.slot:03}.E5S"
        source_save = lane.sandbox / "SV" / "SV020.E5S"
        with timing.phase(
            "prepare_task",
            worker=lane.index,
            round_number=task.round_number,
            result_slot=task.slot,
        ):
            if source_save.is_file():
                shutil.copy2(source_save, target_save)
            lane.baseline = _file_hash(target_save)
            lane.panel_baseline = _panel_snapshot(lane.sandbox, task.slot)
        child_env = os.environ.copy()
        child_env.update(
            {
                "CCZ_AUTOSTART": "1",
                "CCZ_NO_PAUSE": "1",
                "CCZ_GAME_EXE": str(
                    game_executable
                    if compatibility_mode
                    else lane.sandbox / "Ekd5.exe"
                ),
                "CCZ_RESULT_BASE_DIR": str(lane.sandbox),
                "CCZ_LOG_BASE_DIR": str(base_dir),
                "CCZ_HISTORY_SAVE_ROOT": str(game_executable.parent),
                "CCZ_RESULT_COUNT": "1",
                "CCZ_RESULT_SLOT_START": str(task.slot),
                "CCZ_TOTAL_RESULT_COUNT": str(result_count),
                "CCZ_RANDOM_MODE": mode,
                "CCZ_LOOP_RANDOM": "0",
                "CCZ_RUN_STAMP": _batch_stamp(task.round_number),
                "CCZ_CONCURRENT_WORKER": str(lane.index),
                "CCZ_CONCURRENT_SLOT_LIST": str(task.slot),
                "CCZ_CRITICAL_OPERATION_FILE": str(
                    lane.sandbox / ".ccz-critical-operation"
                ),
            }
        )
        if not compatibility_mode:
            child_env["CCZ_DISABLE_AUDIO_MUTE"] = "1"
        if compatibility_mode:
            child_env["CCZ_GAME_RUNTIME_DIR"] = str(lane.sandbox)
        if stop_file is not None:
            child_env["CCZ_STOP_FILE"] = str(stop_file)
        with timing.phase(
            "worker_launch",
            worker=lane.index,
            round_number=task.round_number,
            result_slot=task.slot,
        ):
            lane.process = subprocess.Popen(
                _worker_command(),
                cwd=str(base_dir),
                env=child_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        lane.last_activity_at = time.monotonic()
        lane.started_at = lane.last_activity_at
        lane.timed_out = False
        lane.startup_confirmed = False
        lane.startup_failed = False
        lane.attempt_completed = False
        lane.result_saved = False
        lane.generation += 1
        assert lane.process.stdout is not None
        lane.output_thread = threading.Thread(
            target=forward_output,
            args=(
                lane.index,
                task.round_number,
                lane.generation,
                lane.process.stdout,
            ),
            daemon=True,
        )
        lane.output_thread.start()
        print(
            encode_concurrent_event(
                lane.index,
                f"{CONCURRENT_SLOT_ASSIGNED_PREFIX}{task.slot}",
                round_number=task.round_number,
            ),
            flush=True,
        )
        return True

    def create_lane(index: int) -> _WorkerLane:
        sandbox_options = {
            "root": sandbox_root,
            "worker_name": f"worker-{index}",
            "save_names": CONCURRENT_SAVE_NAMES,
        }
        if compatibility_mode:
            sandbox_options["include_executable"] = False
        try:
            with timing.phase(
                "sandbox_create",
                worker=index,
                compatibility_mode=compatibility_mode,
            ):
                sandbox = create_game_sandbox(
                    game_executable.parent,
                    **sandbox_options,
                )
        except OSError as exc:
            if compatibility_mode:
                raise CompatibilitySandboxSetupError(str(exc)) from exc
            raise
        lane = _WorkerLane(index=index, sandbox=sandbox)
        lanes.append(lane)
        return lane

    def open_startup_gate() -> None:
        nonlocal startup_gate_open
        if startup_gate_open or stopped or fatal_error:
            return
        startup_gate_open = True
        print(
            "首个随机实例已进入随机流程，正在启动其余并发实例",
            flush=True,
        )
        for index in range(len(lanes) + 1, worker_count + 1):
            launch_next(create_lane(index))
            if index < worker_count:
                time.sleep(CONCURRENT_STARTUP_STAGGER_SECONDS)

    def trip_startup_circuit() -> None:
        nonlocal fatal_error, startup_circuit_open
        if fatal_error:
            return
        startup_circuit_open = True
        fatal_error = True
        pending.clear()
        print(
            f"连续 {CONCURRENT_STARTUP_FAILURE_LIMIT} 个随机实例"
            "在启动阶段退出，已停止循环随机，避免反复重启。"
            "请查看最新日志中的游戏退出码。",
            flush=True,
        )
        for candidate in lanes:
            process = candidate.process
            if process is not None and process.poll() is None:
                _stop_worker_process(process, wait_seconds=1.0)

    def finalize_round(round_state: _LoopRound) -> None:
        archive = round_state.workspace
        round_state.archived_path = archive
        grid_path = archive / "random.png"
        if _update_result_grid(
            archive / "panels",
            grid_path,
            result_count,
        ):
            round_state.grid_path = grid_path
            if round_state.grid_announced:
                return
            round_state.grid_announced = True
            print(
                encode_concurrent_event(
                    1,
                    f"本轮总图路径：{grid_path}",
                    round_number=round_state.number,
                ),
                flush=True,
            )

    def publish_completed_rounds() -> None:
        nonlocal next_publish_round
        while True:
            round_state = rounds.get(next_publish_round)
            if round_state is None or round_state.archived_path is None:
                return
            for slot in range(1, result_count + 1):
                source = (
                    round_state.archived_path
                    / "SV"
                    / f"SV{slot:03}.E5S"
                )
                _publish_save(
                    source,
                    game_executable.parent / "SV" / source.name,
                )
            print(
                encode_concurrent_event(
                    1,
                    f"循环轮次完成：第 {next_publish_round} 轮已完成，"
                    f"共保存{result_count}个存档",
                    round_number=next_publish_round,
                ),
                flush=True,
            )
            next_publish_round += 1

    try:
        launch_next(create_lane(1))

        while True:
            if stop_file is not None and stop_file.exists():
                if not stopped:
                    stopped = True
                    stop_requested_at = time.monotonic()
                    pending.clear()
                assert stop_requested_at is not None
                stop_elapsed = time.monotonic() - stop_requested_at
                if stop_elapsed > CONCURRENT_STOP_GRACE_SECONDS:
                    for lane in lanes:
                        process = lane.process
                        if process is None or process.poll() is not None:
                            continue
                        critical = (
                            lane.sandbox
                            / ".ccz-critical-operation"
                        ).is_file()
                        grace_seconds = (
                            CONCURRENT_CRITICAL_STOP_GRACE_SECONDS
                            if critical
                            else CONCURRENT_STOP_GRACE_SECONDS
                        )
                        if (
                            stop_elapsed > grace_seconds
                            or stop_elapsed
                            > CONCURRENT_STOP_HARD_TIMEOUT_SECONDS
                        ):
                            _stop_worker_process(
                                process,
                                wait_seconds=1.0,
                            )
            drain_output()
            if (
                compatibility_probe_passed
                if compatibility_mode
                else any(lane.startup_confirmed for lane in lanes)
            ):
                open_startup_gate()
            made_progress = False
            now = time.monotonic()
            for lane in lanes:
                process = lane.process
                if process is None:
                    continue
                if (
                    process.poll() is None
                    and now - lane.last_activity_at
                    > CONCURRENT_WORKER_TIMEOUT_SECONDS
                ):
                    lane.timed_out = True
                    print(
                        f"[实例 {lane.index}] 超过 "
                        f"{int(CONCURRENT_WORKER_TIMEOUT_SECONDS)} 秒"
                        "未响应，正在重启并重试当前存档",
                        flush=True,
                    )
                    _stop_worker_process(process)
                if process.poll() is None:
                    continue
                made_progress = True
                if lane.output_thread is not None:
                    lane.output_thread.join(timeout=1)
                drain_output()
                task = active.pop(lane.index)
                timing.write(
                    "timing_finished",
                    phase="worker_total_runtime",
                    worker=lane.index,
                    round_number=task.round_number,
                    result_slot=task.slot,
                    elapsed_ms=round(
                        (time.monotonic() - lane.started_at) * 1000
                    ),
                    outcome=(
                        "ok"
                        if lane.result_saved
                        else "error"
                    ),
                    returncode=process.returncode,
                )
                source = (
                    lane.sandbox
                    / "SV"
                    / f"SV{task.slot:03}.E5S"
                )
                current_hash = _file_hash(source)
                task_succeeded = (
                    lane.result_saved
                    and current_hash is not None
                    and (process.returncode == 0 or stopped)
                )
                probe_failed_now = (
                    compatibility_mode
                    and not compatibility_probe_passed
                    and not compatibility_probe_failed
                    and not stopped
                    and not task_succeeded
                    and not any(
                        round_state.completed_slots
                        for round_state in rounds.values()
                    )
                )
                if probe_failed_now:
                    compatibility_probe_failed = True
                    fatal_error = True
                    pending.clear()
                    for candidate in lanes:
                        candidate_process = candidate.process
                        if (
                            candidate_process is not None
                            and candidate_process.poll() is None
                        ):
                            _stop_worker_process(
                                candidate_process,
                                wait_seconds=1.0,
                            )

                if task_succeeded:
                    consecutive_startup_failures = 0
                    open_startup_gate()
                    task_failures.pop(task, None)
                    round_state = rounds[task.round_number]
                    target_save = (
                        round_state.workspace
                        / "SV"
                        / source.name
                    )
                    with timing.phase(
                        "result_save_publish",
                        worker=lane.index,
                        round_number=task.round_number,
                        result_slot=task.slot,
                    ):
                        _publish_save(source, target_save)
                    with timing.phase(
                        "panel_copy",
                        worker=lane.index,
                        round_number=task.round_number,
                        result_slot=task.slot,
                    ):
                        panel_published = _copy_updated_panel(
                            lane.sandbox,
                            task.slot,
                            lane.panel_baseline,
                            round_state.workspace
                            / "panels"
                            / f"save{task.slot}.png",
                        )
                    if panel_published:
                        grid_path = round_state.workspace / "random.png"
                        with timing.phase(
                            "grid_compose",
                            round_number=task.round_number,
                            result_slot=task.slot,
                            panel_count=len(round_state.completed_slots) + 1,
                        ):
                            _update_result_grid(
                                round_state.workspace / "panels",
                                grid_path,
                                result_count,
                            )
                        round_state.grid_path = grid_path
                        if not round_state.grid_announced:
                            round_state.grid_announced = True
                            print(
                                encode_concurrent_event(
                                    1,
                                    f"本轮总图路径：{grid_path}",
                                    round_number=round_state.number,
                                ),
                                flush=True,
                            )
                    round_state.completed_slots.add(task.slot)
                    if len(round_state.completed_slots) == result_count:
                        finalize_round(round_state)
                        publish_completed_rounds()
                elif not stopped and not compatibility_probe_failed:
                    if lane.startup_failed:
                        consecutive_startup_failures += 1
                        if (
                            consecutive_startup_failures
                            >= CONCURRENT_STARTUP_FAILURE_LIMIT
                        ):
                            trip_startup_circuit()
                    failure_count = task_failures.get(task, 0) + 1
                    task_failures[task] = failure_count
                    reason = (
                        "失去响应"
                        if lane.timed_out
                        else f"退出码 {process.returncode}"
                    )
                    print(
                        f"[实例 {lane.index}] 第 {task.round_number} 轮"
                        f"第 {task.slot} 号任务失败，{reason}，"
                        f"第 {failure_count}/"
                        f"{CONCURRENT_SLOT_MAX_FAILURES} 次",
                        flush=True,
                    )
                    if (
                        not fatal_error
                        and failure_count < CONCURRENT_SLOT_MAX_FAILURES
                    ):
                        pending.appendleft(task)
                    elif not fatal_error:
                        fatal_error = True
                        pending.clear()
                        print(
                            f"第 {task.round_number} 轮第 {task.slot} "
                            f"号存档连续失败 "
                            f"{CONCURRENT_SLOT_MAX_FAILURES} 次，"
                            "已停止循环随机",
                            flush=True,
                        )

                with timing.phase(
                    "worker_cleanup",
                    worker=lane.index,
                    round_number=task.round_number,
                    result_slot=task.slot,
                ):
                    shutil.rmtree(
                        lane.sandbox / "randResult",
                        ignore_errors=True,
                    )
                lane.process = None
                lane.output_thread = None
                lane.slot = None
                lane.round_number = None
                lane.baseline = None
                lane.panel_baseline = None
                lane.timed_out = False
                lane.startup_confirmed = False
                lane.startup_failed = False
                lane.attempt_completed = False
                lane.result_saved = False
                lane.started_at = 0.0
                if not stopped and not fatal_error:
                    launch_next(lane)

            active_lanes = [
                lane
                for lane in lanes
                if lane.process is not None
                and lane.process.poll() is None
            ]
            if (stopped or fatal_error) and not active_lanes:
                break
            if active_lanes and not made_progress:
                time.sleep(0.1)
        drain_output()
        if (
            (
                compatibility_probe_failed
                and compatibility_mode
            )
            or startup_circuit_open
        ) and not any(
            round_state.completed_slots
            for round_state in rounds.values()
        ):
            return CONCURRENT_COMPATIBILITY_FALLBACK_CODE
        return 0 if stopped or not fatal_error else 1
    finally:
        for lane in lanes:
            process = lane.process
            if process is None:
                continue
            _stop_worker_process(process)
        try:
            with timing.phase("sandbox_cleanup"):
                remove_sandbox_tree(session_root)
        finally:
            timing.close()


def _run_concurrent_batch(
    *,
    game_executable: Path,
    result_count: int,
    mode: str,
    stop_file: Path | None,
    base_dir: Path,
    worker_count: int,
    round_number: int,
    compatibility_mode: bool = False,
) -> int:
    stamp = f"{os.getpid()}-{time.time_ns()}"
    runtime_root = base_dir / "ccz_fast_data"
    try:
        ensure_hidden_runtime_directory(runtime_root)
        sandboxes_root = runtime_root / "sandboxes"
        sandboxes_root.mkdir(parents=True, exist_ok=True)
        cleanup_stale_sandboxes(sandboxes_root)
        sandbox_root = sandboxes_root / stamp
        sandbox_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        if compatibility_mode:
            raise CompatibilitySandboxSetupError(str(exc)) from exc
        raise
    slots = list(range(1, result_count + 1))
    worker_count = min(worker_count, len(slots))
    sandboxes: list[Path] = []
    lanes: list[_WorkerLane] = []
    slot_queue = DynamicSlotQueue(result_count)
    output_queue: queue.Queue[
        tuple[int, int, str | None, float]
    ] = queue.Queue()
    slot_failures: dict[int, int] = {}
    startup_gate_open = worker_count == 1
    startup_circuit_open = False
    consecutive_startup_failures = 0
    compatibility_probe_passed = not compatibility_mode
    compatibility_probe_failed = False
    published_slots: set[int] = set()
    result_panel_dir, result_grid_path = _unique_batch_result_paths(base_dir)
    result_path_announced = False
    timing = _TimingRecorder(
        base_dir,
        mode=mode,
        worker_count=worker_count,
    )

    def forward_output(
        worker_index: int,
        generation: int,
        stream,
    ) -> None:
        for line in iter(stream.readline, ""):
            output_queue.put(
                (
                    worker_index,
                    generation,
                    line.rstrip("\r\n"),
                    time.monotonic(),
                )
            )
        stream.close()
        output_queue.put(
            (worker_index, generation, None, time.monotonic())
        )

    def drain_output() -> None:
        nonlocal consecutive_startup_failures
        nonlocal compatibility_probe_passed
        while True:
            try:
                index, generation, line, received_at = (
                    output_queue.get_nowait()
                )
            except queue.Empty:
                break
            lane = lanes[index - 1]
            if generation != lane.generation:
                continue
            if _is_worker_progress_line(line):
                lane.last_activity_at = received_at
                attempt_was_completed = lane.attempt_completed
                if _record_worker_output(lane, line):
                    consecutive_startup_failures = 0
                if (
                    not attempt_was_completed
                    and lane.attempt_completed
                ):
                    compatibility_probe_passed = True
            if line == CONCURRENT_HEARTBEAT_LINE:
                continue
            if line is not None and _should_forward_line(line):
                print(
                    encode_concurrent_event(index, line),
                    flush=True,
                )

    def launch_next(lane: _WorkerLane) -> bool:
        if lane.disabled:
            return False
        if stop_file is not None and stop_file.exists():
            return False
        slot = slot_queue.claim(lane.index)
        if slot is None:
            return False
        lane.slot = slot
        lane.baseline = _file_hash(
            lane.sandbox / "SV" / f"SV{slot:03}.E5S"
        )
        lane.panel_baseline = _panel_snapshot(lane.sandbox, slot)
        child_env = os.environ.copy()
        child_env.update(
            {
                "CCZ_AUTOSTART": "1",
                "CCZ_NO_PAUSE": "1",
                "CCZ_GAME_EXE": str(
                    game_executable
                    if compatibility_mode
                    else lane.sandbox / "Ekd5.exe"
                ),
                "CCZ_RESULT_BASE_DIR": str(lane.sandbox),
                "CCZ_LOG_BASE_DIR": str(base_dir),
                "CCZ_HISTORY_SAVE_ROOT": str(game_executable.parent),
                "CCZ_RESULT_COUNT": "1",
                "CCZ_RESULT_SLOT_START": str(slot),
                "CCZ_TOTAL_RESULT_COUNT": str(result_count),
                "CCZ_RANDOM_MODE": mode,
                "CCZ_LOOP_RANDOM": "0",
                "CCZ_RUN_STAMP": _batch_stamp(round_number),
                "CCZ_CONCURRENT_WORKER": str(lane.index),
                "CCZ_CONCURRENT_SLOT_LIST": str(slot),
                "CCZ_CRITICAL_OPERATION_FILE": str(
                    lane.sandbox / ".ccz-critical-operation"
                ),
            }
        )
        if not compatibility_mode:
            child_env["CCZ_DISABLE_AUDIO_MUTE"] = "1"
        if compatibility_mode:
            child_env["CCZ_GAME_RUNTIME_DIR"] = str(lane.sandbox)
        if stop_file is not None:
            child_env["CCZ_STOP_FILE"] = str(stop_file)
        with timing.phase(
            "worker_launch",
            worker=lane.index,
            round_number=round_number,
            result_slot=slot,
        ):
            lane.process = subprocess.Popen(
                _worker_command(),
                cwd=str(base_dir),
                env=child_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        lane.last_activity_at = time.monotonic()
        lane.started_at = lane.last_activity_at
        lane.timed_out = False
        lane.startup_confirmed = False
        lane.startup_failed = False
        lane.attempt_completed = False
        lane.result_saved = False
        lane.generation += 1
        assert lane.process.stdout is not None
        lane.output_thread = threading.Thread(
            target=forward_output,
            args=(lane.index, lane.generation, lane.process.stdout),
            daemon=True,
        )
        lane.output_thread.start()
        print(
            encode_concurrent_event(
                lane.index,
                f"{CONCURRENT_SLOT_ASSIGNED_PREFIX}{slot}",
            ),
            flush=True,
        )
        return True

    def create_lane(index: int) -> _WorkerLane:
        sandbox_options = {
            "root": sandbox_root,
            "worker_name": f"worker-{index}",
            "save_names": CONCURRENT_SAVE_NAMES,
        }
        if compatibility_mode:
            sandbox_options["include_executable"] = False
        try:
            with timing.phase(
                "sandbox_create",
                worker=index,
                compatibility_mode=compatibility_mode,
            ):
                sandbox = create_game_sandbox(
                    game_executable.parent,
                    **sandbox_options,
                )
        except OSError as exc:
            if compatibility_mode:
                raise CompatibilitySandboxSetupError(str(exc)) from exc
            raise
        sandboxes.append(sandbox)
        lane = _WorkerLane(index=index, sandbox=sandbox)
        lanes.append(lane)
        return lane

    def open_startup_gate() -> None:
        nonlocal startup_gate_open
        if startup_gate_open or stopped or startup_circuit_open:
            return
        startup_gate_open = True
        print(
            "首个随机实例已进入随机流程，正在启动其余并发实例",
            flush=True,
        )
        for index in range(len(lanes) + 1, worker_count + 1):
            launch_next(create_lane(index))

    def trip_startup_circuit() -> None:
        nonlocal startup_circuit_open
        if startup_circuit_open:
            return
        startup_circuit_open = True
        print(
            f"连续 {CONCURRENT_STARTUP_FAILURE_LIMIT} 个随机实例"
            "在启动阶段退出，已停止本次随机，避免反复重启。"
            "请查看最新日志中的游戏退出码。",
            flush=True,
        )
        for candidate in lanes:
            process = candidate.process
            if process is not None and process.poll() is None:
                _stop_worker_process(process, wait_seconds=1.0)

    try:
        launch_next(create_lane(1))

        stopped = False
        stop_requested_at: float | None = None
        while slot_queue.has_active or slot_queue.has_pending:
            if stop_file is not None and stop_file.exists():
                if not stopped:
                    stopped = True
                    stop_requested_at = time.monotonic()
                    slot_queue.cancel_pending()
                assert stop_requested_at is not None
                if (
                    time.monotonic() - stop_requested_at
                    > CONCURRENT_STOP_GRACE_SECONDS
                ):
                    stop_elapsed = time.monotonic() - stop_requested_at
                    for lane in lanes:
                        process = lane.process
                        if process is None or process.poll() is not None:
                            continue
                        critical = (
                            lane.sandbox
                            / ".ccz-critical-operation"
                        ).is_file()
                        grace_seconds = (
                            CONCURRENT_CRITICAL_STOP_GRACE_SECONDS
                            if critical
                            else CONCURRENT_STOP_GRACE_SECONDS
                        )
                        if (
                            stop_elapsed > grace_seconds
                            or stop_elapsed
                            > CONCURRENT_STOP_HARD_TIMEOUT_SECONDS
                        ):
                            _stop_worker_process(
                                process,
                                wait_seconds=1.0,
                            )
            drain_output()
            if (
                compatibility_probe_passed
                if compatibility_mode
                else any(lane.startup_confirmed for lane in lanes)
            ):
                open_startup_gate()
            made_progress = False
            now = time.monotonic()
            for lane in lanes:
                process = lane.process
                if process is None:
                    continue
                if (
                    process.poll() is None
                    and now - lane.last_activity_at
                    > CONCURRENT_WORKER_TIMEOUT_SECONDS
                ):
                    lane.timed_out = True
                    print(
                        f"[实例 {lane.index}] 超过 "
                        f"{int(CONCURRENT_WORKER_TIMEOUT_SECONDS)} 秒"
                        "未响应，正在重启并重试当前存档",
                        flush=True,
                    )
                    _stop_worker_process(process)
                if process.poll() is None:
                    continue
                made_progress = True
                if lane.output_thread is not None:
                    lane.output_thread.join(timeout=1)
                drain_output()
                assert lane.slot is not None
                slot = lane.slot
                timing.write(
                    "timing_finished",
                    phase="worker_total_runtime",
                    worker=lane.index,
                    round_number=round_number,
                    result_slot=slot,
                    elapsed_ms=round(
                        (time.monotonic() - lane.started_at) * 1000
                    ),
                    outcome=(
                        "ok"
                        if lane.result_saved
                        else "error"
                    ),
                    returncode=process.returncode,
                )
                source = lane.sandbox / "SV" / f"SV{slot:03}.E5S"
                current_hash = _file_hash(source)
                task_succeeded = (
                    lane.result_saved
                    and current_hash is not None
                    and (process.returncode == 0 or stopped)
                )
                probe_failed_now = (
                    compatibility_mode
                    and not compatibility_probe_passed
                    and not compatibility_probe_failed
                    and not stopped
                    and not task_succeeded
                    and not published_slots
                )
                if probe_failed_now:
                    compatibility_probe_failed = True
                    startup_circuit_open = True
                    for candidate in lanes:
                        candidate_process = candidate.process
                        if (
                            candidate_process is not None
                            and candidate_process.poll() is None
                        ):
                            _stop_worker_process(
                                candidate_process,
                                wait_seconds=1.0,
                            )
                next_failure_count = (
                    0
                    if task_succeeded
                    else slot_failures.get(slot, 0) + 1
                )
                should_retry = (
                    not task_succeeded
                    and not stopped
                    and not startup_circuit_open
                    and next_failure_count
                    < CONCURRENT_SLOT_MAX_FAILURES
                )
                slot_queue.finish(
                    lane.index,
                    retry=should_retry,
                )
                if task_succeeded:
                    consecutive_startup_failures = 0
                    open_startup_gate()
                    slot_failures.pop(slot, None)
                    with timing.phase(
                        "result_save_publish",
                        worker=lane.index,
                        round_number=round_number,
                        result_slot=slot,
                    ):
                        _publish_save(
                            source,
                            game_executable.parent / "SV" / source.name,
                        )
                    with timing.phase(
                        "panel_copy",
                        worker=lane.index,
                        round_number=round_number,
                        result_slot=slot,
                    ):
                        panel_published = _copy_updated_panel(
                            lane.sandbox,
                            slot,
                            lane.panel_baseline,
                            result_panel_dir / f"save{slot}.png",
                        )
                    if panel_published:
                        with timing.phase(
                            "grid_compose",
                            round_number=round_number,
                            result_slot=slot,
                            panel_count=len(published_slots) + 1,
                        ):
                            _update_result_grid(
                                result_panel_dir,
                                result_grid_path,
                                result_count,
                            )
                        if not result_path_announced:
                            result_path_announced = True
                            print(
                                f"本轮总图路径：{result_grid_path}",
                                flush=True,
                            )
                    print(
                        f"并发结果已发布：第 {slot} 号存档",
                        flush=True,
                    )
                    published_slots.add(slot)
                else:
                    if stopped:
                        next_failure_count = 0
                        slot_failures.pop(slot, None)
                    elif startup_circuit_open:
                        slot_failures.pop(slot, None)
                    else:
                        if lane.startup_failed:
                            consecutive_startup_failures += 1
                            if (
                                consecutive_startup_failures
                                >= CONCURRENT_STARTUP_FAILURE_LIMIT
                            ):
                                trip_startup_circuit()
                        failure_count = next_failure_count
                        slot_failures[slot] = failure_count
                        reason = (
                            "失去响应"
                            if lane.timed_out
                            else f"退出码 {process.returncode}"
                        )
                        print(
                            f"[实例 {lane.index}] 第 {slot} 号任务失败，"
                            f"{reason}，第 {failure_count}/"
                            f"{CONCURRENT_SLOT_MAX_FAILURES} 次",
                            flush=True,
                        )
                        lifecycle_prefix = (
                            CONCURRENT_SLOT_RETRY_PREFIX
                            if should_retry
                            else CONCURRENT_SLOT_FAILED_PREFIX
                        )
                        print(
                            encode_concurrent_event(
                                lane.index,
                                f"{lifecycle_prefix}{slot}",
                            ),
                            flush=True,
                        )
                lane.process = None
                lane.output_thread = None
                lane.slot = None
                lane.baseline = None
                lane.panel_baseline = None
                lane.timed_out = False
                lane.startup_confirmed = False
                lane.startup_failed = False
                lane.attempt_completed = False
                lane.result_saved = False
                lane.started_at = 0.0
                if (
                    not stopped
                    and not startup_circuit_open
                    and (
                        task_succeeded
                        or next_failure_count < CONCURRENT_SLOT_MAX_FAILURES
                    )
                ):
                    launch_next(lane)
                elif not stopped and not startup_circuit_open:
                    print(
                        f"第 {slot} 号存档连续失败 "
                        f"{CONCURRENT_SLOT_MAX_FAILURES} 次，"
                        "已停止重试",
                        flush=True,
                    )
                    if slot_queue.has_pending:
                        launch_next(lane)

            active_lanes = [
                lane
                for lane in lanes
                if lane.process is not None
                and lane.process.poll() is None
            ]
            tracked_lanes = [
                lane for lane in lanes if lane.process is not None
            ]
            if stopped and not active_lanes:
                break
            if startup_circuit_open and not active_lanes:
                break
            if slot_queue.has_pending and not tracked_lanes:
                if stop_file is not None and stop_file.exists():
                    stopped = True
                    break
                print(
                    "没有可用并发实例继续处理剩余存档",
                    flush=True,
                )
                break
            if tracked_lanes and not made_progress:
                time.sleep(0.1)
        drain_output()
        if result_grid_path.is_file():
            print(
                f"{CONCURRENT_RESULT_IMAGE_PREFIX}{result_grid_path}",
                flush=True,
            )
        if stopped:
            return 0
        if (
            (
                compatibility_probe_failed
                and compatibility_mode
            )
            or startup_circuit_open
        ) and not published_slots:
            return CONCURRENT_COMPATIBILITY_FALLBACK_CODE
        return 0 if len(published_slots) == result_count else 1
    finally:
        for lane in lanes:
            process = lane.process
            if process is None:
                continue
            _stop_worker_process(process)
        try:
            with timing.phase("sandbox_cleanup"):
                remove_sandbox_tree(sandbox_root)
        finally:
            timing.close()
