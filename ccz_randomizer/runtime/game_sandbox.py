from __future__ import annotations

import os
import shutil
import tempfile
import ctypes
import logging
import re
import time
from collections.abc import Collection
from pathlib import Path


MUTABLE_DIRECTORIES = frozenset({"SV", "RS"})
CONCURRENT_SAVE_NAMES = frozenset({"SV020.E5S"})
UNKNOWN_SANDBOX_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
_SESSION_DIRECTORY_PATTERN = re.compile(r"^(?P<pid>\d+)-\d+$")
_LOGGER = logging.getLogger(__name__)
MUTABLE_ROOT_FILES = frozenset(
    {
        "CczCustom.ini",
        "randomizer_settings.json",
    }
)
EXCLUDED_NAMES = frozenset(
    {
        "artifacts",
        "ccz_diagnostics",
        "ccz_fast_backup",
        "ccz_fast_data",
        "ccz_fast_logs",
        "ccz_r1_test",
        "randResult",
        "兵种映射验证",
        "中文路径检查-20260925",
        "随即工具",
    }
)


def _root_file_can_be_linked(path: Path) -> bool:
    return (
        path.name.casefold() != "ekd5.exe"
        and path.name not in MUTABLE_ROOT_FILES
        and path.suffix.casefold() not in {".ini", ".log", ".txt"}
    )


def _should_skip(item: Path) -> bool:
    name = item.name
    return (
        name in EXCLUDED_NAMES
        or name.startswith("ccz-inspect-")
        or name.endswith("随机工具.exe")
        or name.casefold() == "ekd5.ccz-fast-random.exe"
    )


def ensure_hidden_runtime_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        return
    attributes = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    if attributes == 0xFFFFFFFF or attributes & 0x2:
        return
    if not ctypes.windll.kernel32.SetFileAttributesW(
        str(path),
        attributes | 0x2,
    ):
        raise ctypes.WinError(ctypes.get_last_error())


def _copy_or_link_file(source: Path, target: Path, *, hardlink: bool) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if hardlink:
        try:
            os.link(source, target)
            return
        except OSError:
            pass
    shutil.copy2(source, target)


def _copy_tree(source: Path, target: Path, *, mutable: bool) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        destination = target / item.name
        if item.is_dir():
            _copy_tree(item, destination, mutable=mutable)
        elif item.is_file():
            _copy_or_link_file(item, destination, hardlink=not mutable)


def _copy_selected_saves(
    source: Path,
    target: Path,
    save_names: Collection[str],
) -> None:
    target.mkdir(parents=True, exist_ok=True)
    selected = {name.casefold() for name in save_names}
    found: set[str] = set()
    for item in source.iterdir():
        if not item.is_file() or item.name.casefold() not in selected:
            continue
        _copy_or_link_file(item, target / item.name, hardlink=False)
        found.add(item.name.casefold())
    missing = selected - found
    if missing:
        names = "、".join(sorted(missing))
        raise FileNotFoundError(f"沙箱缺少必要存档：{names}")


def _process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        process = ctypes.windll.kernel32.OpenProcess(
            0x1000,
            False,
            pid,
        )
        if not process:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(
                process,
                ctypes.byref(exit_code),
            ):
                return False
            return exit_code.value == 259
        finally:
            ctypes.windll.kernel32.CloseHandle(process)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def cleanup_stale_sandboxes(
    root: Path,
    *,
    now: float | None = None,
    unknown_max_age_seconds: float = UNKNOWN_SANDBOX_MAX_AGE_SECONDS,
) -> list[Path]:
    """Remove abandoned sessions without touching active worker directories."""
    if not root.is_dir():
        return []
    current_time = time.time() if now is None else now
    removed: list[Path] = []
    for candidate in root.iterdir():
        if not candidate.is_dir():
            continue
        match = _SESSION_DIRECTORY_PATTERN.fullmatch(candidate.name)
        if match is not None:
            if _process_is_running(int(match.group("pid"))):
                continue
        else:
            try:
                age = current_time - candidate.stat().st_mtime
            except OSError:
                continue
            if age < unknown_max_age_seconds:
                continue
        try:
            shutil.rmtree(candidate)
        except OSError:
            _LOGGER.warning(
                "无法清理残留沙箱：%s",
                candidate,
                exc_info=True,
            )
            continue
        removed.append(candidate)
    return removed


def remove_sandbox_tree(path: Path) -> bool:
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        return True
    except OSError:
        _LOGGER.warning(
            "无法删除沙箱目录，将在下次启动时重试：%s",
            path,
            exc_info=True,
        )
        return False
    return True


def create_game_sandbox(
    game_dir: Path,
    *,
    root: Path | None = None,
    worker_name: str = "worker-1",
    include_executable: bool = True,
    save_names: Collection[str] | None = None,
) -> Path:
    """Create an isolated working copy of the game directory."""
    game_dir = game_dir.resolve()
    if not (game_dir / "Ekd5.exe").is_file():
        raise FileNotFoundError(f"未找到游戏程序：{game_dir / 'Ekd5.exe'}")
    base = root or (game_dir / "ccz_fast_data" / "sandboxes")
    ensure_hidden_runtime_directory(base)
    sandbox = Path(
        tempfile.mkdtemp(prefix=f"{worker_name}-", dir=str(base))
    )

    try:
        for item in game_dir.iterdir():
            if _should_skip(item):
                continue
            if (
                not include_executable
                and item.name.casefold() == "ekd5.exe"
            ):
                continue
            destination = sandbox / item.name
            if item.is_dir():
                if item.name.casefold() == "sv" and save_names is not None:
                    _copy_selected_saves(item, destination, save_names)
                else:
                    _copy_tree(
                        item,
                        destination,
                        mutable=item.name in MUTABLE_DIRECTORIES,
                    )
            elif item.is_file():
                _copy_or_link_file(
                    item,
                    destination,
                    hardlink=_root_file_can_be_linked(item),
                )
        return sandbox
    except BaseException:
        shutil.rmtree(sandbox, ignore_errors=True)
        raise


def remove_game_sandbox(path: Path) -> None:
    path = path.resolve()
    if "sandboxes" not in path.parent.parts:
        raise ValueError(f"拒绝删除非沙箱目录：{path}")
    if not remove_sandbox_tree(path):
        raise OSError(f"无法删除沙箱目录：{path}")
