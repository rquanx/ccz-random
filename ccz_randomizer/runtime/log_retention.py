from __future__ import annotations

import datetime as dt
import re
import threading
from dataclasses import dataclass
from pathlib import Path


DEFAULT_LOG_PART_BYTES = 20 * 1024 * 1024
DEFAULT_LOG_PARTS = 5
DEFAULT_RETENTION_DAYS = 30
DEFAULT_DIRECTORY_LIMIT_BYTES = 1024 * 1024 * 1024
DEFAULT_DIRECTORY_TARGET_BYTES = 750 * 1024 * 1024
CONSOLE_MAX_LINES = 12_000
CONSOLE_TARGET_LINES = 10_000
CONSOLE_TRIM_NOTICE = "较早信息已从界面隐藏，完整记录请查看日志文件。"

_MANAGED_LOG_PATTERN = re.compile(
    r"^fast_\d{8}_\d{6}"
    r"(?:_diagnostic(?:_summary)?)?"
    r"(?:\.part\d+)?"
    r"\.(?:log|jsonl|json)$",
    re.IGNORECASE,
)
_MANAGED_SCREENSHOT_PATTERN = re.compile(
    r"^fast_\d{8}_\d{6}_diagnostic_interaction_failure_.*\.png$",
    re.IGNORECASE,
)


def rotated_log_path(base_path: Path, part: int) -> Path:
    if part <= 1:
        return base_path
    return base_path.with_name(
        f"{base_path.stem}.part{part}{base_path.suffix}"
    )


class RotatingTextWriter:
    def __init__(
        self,
        path: Path,
        *,
        max_bytes: int = DEFAULT_LOG_PART_BYTES,
        max_parts: int = DEFAULT_LOG_PARTS,
    ):
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if max_parts <= 0:
            raise ValueError("max_parts must be positive")
        self.path = Path(path)
        self.max_bytes = max_bytes
        self.max_parts = max_parts
        self._lock = threading.RLock()
        self._part = self._find_current_part()
        self._stream = None
        self._size = 0
        self._open_current()

    def _find_current_part(self) -> int:
        existing = [
            part
            for part in range(1, self.max_parts + 1)
            if rotated_log_path(self.path, part).is_file()
        ]
        return max(existing, default=1)

    def _open_current(self) -> None:
        current = rotated_log_path(self.path, self._part)
        current.parent.mkdir(parents=True, exist_ok=True)
        self._stream = current.open(
            "a",
            encoding="utf-8",
            newline="\n",
        )
        self._size = current.stat().st_size

    def _shift_parts_left(self) -> None:
        self.path.unlink(missing_ok=True)
        for part in range(2, self.max_parts + 1):
            source = rotated_log_path(self.path, part)
            if not source.exists():
                continue
            destination = rotated_log_path(self.path, part - 1)
            destination.unlink(missing_ok=True)
            source.replace(destination)

    def _rotate(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        if self._part < self.max_parts:
            self._part += 1
        else:
            self._shift_parts_left()
        self._open_current()

    def write(self, text: str) -> int:
        if not text:
            return 0
        encoded_size = len(text.encode("utf-8"))
        with self._lock:
            if self._stream is None:
                raise ValueError("I/O operation on closed log")
            if self._size > 0 and self._size + encoded_size > self.max_bytes:
                self._rotate()
            self._stream.write(text)
            self._size += encoded_size
        return len(text)

    def flush(self) -> None:
        with self._lock:
            if self._stream is not None:
                self._stream.flush()

    def close(self) -> None:
        with self._lock:
            if self._stream is None:
                return
            self._stream.flush()
            self._stream.close()
            self._stream = None


@dataclass(frozen=True)
class CleanupResult:
    removed_files: int
    removed_bytes: int
    remaining_bytes: int


def is_managed_log_file(path: Path) -> bool:
    return bool(
        _MANAGED_LOG_PATTERN.fullmatch(path.name)
        or _MANAGED_SCREENSHOT_PATTERN.fullmatch(path.name)
    )


def cleanup_log_directory(
    log_dir: Path,
    *,
    now: dt.datetime | None = None,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    limit_bytes: int = DEFAULT_DIRECTORY_LIMIT_BYTES,
    target_bytes: int = DEFAULT_DIRECTORY_TARGET_BYTES,
) -> CleanupResult:
    if limit_bytes <= 0 or target_bytes < 0 or target_bytes > limit_bytes:
        raise ValueError("invalid directory size limits")
    now = now or dt.datetime.now()
    cutoff = now.timestamp() - retention_days * 24 * 60 * 60
    candidates = [
        path
        for path in log_dir.iterdir()
        if path.is_file() and is_managed_log_file(path)
    ]
    removed_files = 0
    removed_bytes = 0

    for path in candidates:
        try:
            stat = path.stat()
            if stat.st_mtime >= cutoff:
                continue
            path.unlink()
            removed_files += 1
            removed_bytes += stat.st_size
        except OSError:
            continue

    remaining = []
    total_size = 0
    for path in candidates:
        try:
            stat = path.stat()
        except OSError:
            continue
        remaining.append((stat.st_mtime, path, stat.st_size))
        total_size += stat.st_size

    if total_size > limit_bytes:
        for _mtime, path, size in sorted(remaining):
            if total_size <= target_bytes:
                break
            try:
                path.unlink()
            except OSError:
                continue
            removed_files += 1
            removed_bytes += size
            total_size -= size

    return CleanupResult(
        removed_files=removed_files,
        removed_bytes=removed_bytes,
        remaining_bytes=total_size,
    )


def trim_text_widget(
    widget,
    *,
    max_lines: int = CONSOLE_MAX_LINES,
    target_lines: int = CONSOLE_TARGET_LINES,
    notice: str = CONSOLE_TRIM_NOTICE,
) -> bool:
    if target_lines <= 0 or max_lines <= target_lines:
        raise ValueError("max_lines must be greater than target_lines")
    end_line = int(widget.index("end-1c").split(".", 1)[0])
    current_lines = max(0, end_line - 1)
    if current_lines <= max_lines:
        return False
    first_kept_line = current_lines - target_lines + 1
    widget.delete("1.0", f"{first_kept_line}.0")
    widget.insert("1.0", notice + "\n")
    return True
