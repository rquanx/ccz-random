from __future__ import annotations

import os
import platform
import hashlib
import sys
import threading
import time
import traceback
import uuid
from collections import deque
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 2
_LOCK = threading.RLock()
_RUN_ID = ""
_STARTED_AT = time.perf_counter()
_SEQUENCE = 0
_CONTEXT: dict[str, Any] = {}
_BREADCRUMBS: deque[dict[str, Any]] = deque(maxlen=40)


def start_diagnostic_run(**context: Any) -> str:
    global _RUN_ID, _STARTED_AT, _SEQUENCE
    with _LOCK:
        _RUN_ID = uuid.uuid4().hex[:12]
        _STARTED_AT = time.perf_counter()
        _SEQUENCE = 0
        _CONTEXT.clear()
        _CONTEXT.update(_clean_fields(context))
        _BREADCRUMBS.clear()
        return _RUN_ID


def update_diagnostic_context(**fields: Any) -> None:
    with _LOCK:
        for key, value in fields.items():
            if value is None:
                _CONTEXT.pop(key, None)
            else:
                _CONTEXT[key] = value


def clear_diagnostic_context(*names: str) -> None:
    with _LOCK:
        for name in names:
            _CONTEXT.pop(name, None)


def build_diagnostic_record(event: str, **fields: Any) -> dict[str, Any]:
    global _SEQUENCE
    with _LOCK:
        _SEQUENCE += 1
        record = {
            "schema": SCHEMA_VERSION,
            "run_id": _RUN_ID or "uninitialized",
            "sequence": _SEQUENCE,
            "elapsed_ms": round((time.perf_counter() - _STARTED_AT) * 1000),
            "thread": {
                "id": threading.get_ident(),
                "name": threading.current_thread().name,
            },
            "event": event,
            "context": dict(_CONTEXT),
            **_clean_fields(fields),
        }
        _BREADCRUMBS.append(
            {
                "sequence": _SEQUENCE,
                "elapsed_ms": record["elapsed_ms"],
                "event": event,
                "phase": _CONTEXT.get("phase"),
                "result_slot": _CONTEXT.get("result_slot"),
                "attempt": _CONTEXT.get("attempt"),
            }
        )
        return record


def recent_diagnostic_events() -> list[dict[str, Any]]:
    with _LOCK:
        return list(_BREADCRUMBS)


def exception_diagnostic(exc: BaseException) -> dict[str, Any]:
    chain = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        item = {
            "type": type(current).__name__,
            "module": type(current).__module__,
            "message": str(current),
            "repr": repr(current),
        }
        for name in (
            "errno",
            "winerror",
            "return_code",
            "details",
            "stage",
            "subprocess_returncode",
            "inner_error_type",
            "native_timeout",
            "child_log_path",
            "child_diagnostic_path",
            "child_stdout_path",
            "click_strategy",
            "elapsed_seconds",
        ):
            value = getattr(current, name, None)
            if value is not None:
                item[name] = value
        chain.append(item)
        current = current.__cause__ or current.__context__

    classification = classify_exception(exc)
    last_frame = None
    extracted = traceback.extract_tb(exc.__traceback__)
    if extracted:
        frame = extracted[-1]
        last_frame = {
            "file": Path(frame.filename).name,
            "line": frame.lineno,
            "function": frame.name,
        }
    fingerprint_source = "|".join(
        (
            str(classification["layer"]),
            str(classification["category"]),
            str(classification["code"]),
            type(exc).__name__,
            last_frame["file"] if last_frame else "",
            last_frame["function"] if last_frame else "",
        )
    )
    return {
        "error_id": uuid.uuid4().hex[:12],
        "fingerprint": hashlib.sha256(
            fingerprint_source.encode("utf-8")
        ).hexdigest()[:16],
        **classification,
        "exception": chain[0],
        "chain": chain,
        "last_frame": last_frame,
        "traceback": "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        ),
        "recent_events": recent_diagnostic_events(),
    }


def classify_exception(exc: BaseException) -> dict[str, Any]:
    name = type(exc).__name__
    message = str(exc).casefold()
    return_code = getattr(exc, "return_code", None)
    winerror = getattr(exc, "winerror", None)

    if name == "InspectionProcessError":
        native_timeout = bool(getattr(exc, "native_timeout", False))
        inner_type = getattr(exc, "inner_error_type", None)
        if inner_type == "NativeControlError" or return_code is not None:
            return {
                "layer": "native_control",
                "category": (
                    "native_timeout" if native_timeout else "native_failure"
                ),
                "code": return_code,
                "likely_cause": _native_likely_cause(return_code, message),
            }
        return {
            "layer": "result_inspection",
            "category": (
                "inspection_timeout"
                if native_timeout
                else "inspection_process_failure"
            ),
            "code": getattr(exc, "subprocess_returncode", None),
            "likely_cause": "独立能力检查实例未能完成界面读取",
        }
    if name in {"NativeControlError", "NativeControlTimeout"}:
        return {
            "layer": "native_control",
            "category": (
                "native_timeout"
                if name == "NativeControlTimeout"
                else "native_failure"
            ),
            "code": return_code,
            "likely_cause": _native_likely_cause(return_code, message),
        }
    if name in {
        "InteractionNotTriggered",
        "DirectReloadUnsupported",
        "NormalReloadUnsupported",
    }:
        return {
            "layer": "game_interaction",
            "category": "interaction_not_triggered",
            "code": name,
            "likely_cause": "游戏场景未进入可交互状态或后台输入未被处理",
        }
    if isinstance(exc, FileNotFoundError):
        return {
            "layer": "environment",
            "category": "required_file_missing",
            "code": winerror if winerror is not None else exc.errno,
            "likely_cause": "工具位置不正确、文件未完整解压或必要文件缺失",
        }
    if isinstance(exc, OSError):
        return {
            "layer": "operating_system",
            "category": "windows_error",
            "code": winerror if winerror is not None else exc.errno,
            "likely_cause": _os_likely_cause(winerror, message),
        }
    if "存档" in message and ("回读" in message or "保存" in message):
        return {
            "layer": "save_verification",
            "category": "save_mismatch",
            "code": name,
            "likely_cause": "存档写入、回读或保存前后数据校验不一致",
        }
    if "结果图" in message or "图片" in message or "panel" in message:
        return {
            "layer": "result_rendering",
            "category": "render_failure",
            "code": name,
            "likely_cause": "结果数据整理或图片生成失败",
        }
    if "兵种" in message or "特技" in message or "规则" in message:
        return {
            "layer": "rule_evaluation",
            "category": "rule_or_data_failure",
            "code": name,
            "likely_cause": "随机数据读取、映射或规则计算异常",
        }
    return {
        "layer": "workflow",
        "category": "unclassified_failure",
        "code": name,
        "likely_cause": "当前信息不足，需结合阶段、现场状态和最近事件定位",
    }


def environment_diagnostic(*paths: Path) -> dict[str, Any]:
    path_details = []
    for raw_path in paths:
        path = Path(raw_path)
        try:
            resolved = path.resolve()
            usage = None
            anchor = Path(resolved.anchor) if resolved.anchor else resolved
            if anchor.exists():
                stat = os.statvfs(anchor) if os.name != "nt" else None
                if stat is not None:
                    usage = {
                        "free": stat.f_bavail * stat.f_frsize,
                        "total": stat.f_blocks * stat.f_frsize,
                    }
                else:
                    import shutil

                    disk = shutil.disk_usage(anchor)
                    usage = {"free": disk.free, "total": disk.total}
            path_details.append(
                {
                    "path": str(resolved),
                    "exists": resolved.exists(),
                    "drive": resolved.drive,
                    "disk": usage,
                }
            )
        except Exception as exc:
            path_details.append({"path": str(path), "error": repr(exc)})

    return {
        "os": {
            "platform": platform.platform(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "windows": tuple(sys.getwindowsversion())
            if hasattr(sys, "getwindowsversion")
            else None,
        },
        "process": {
            "pid": os.getpid(),
            "python": sys.version,
            "architecture": platform.architecture()[0],
            "frozen": bool(getattr(sys, "frozen", False)),
            "executable": sys.executable,
            "cwd": os.getcwd(),
            "admin": _is_admin(),
        },
        "paths": path_details,
    }


def _native_likely_cause(return_code: Any, message: str) -> str:
    if return_code in {200, 201, 202, 203, 206, 207, 208, 209}:
        return "后台控制线程等待、超时或退出状态异常"
    if return_code in {3, 4, 5, 6, 7, 8, 9, 10, 204, 205}:
        return "后台控制组件加载、内存写入或安全策略拦截异常"
    if "c000010a" in message:
        return "目标游戏进程正在退出"
    return "后台控制组件返回了未归类结果"


def _os_likely_cause(winerror: Any, message: str) -> str:
    if winerror == 5 or "拒绝访问" in message:
        return "权限不足或安全软件阻止访问"
    if winerror == 32:
        return "文件正被其他程序占用"
    if winerror == 299:
        return "目标进程在读取期间退出或内存区域发生变化"
    return "Windows 文件、进程、内存或窗口接口调用失败"


def _is_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _clean_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value is not None}
