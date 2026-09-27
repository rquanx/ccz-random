from __future__ import annotations

import json
import os
from pathlib import Path


PREFERENCES_FILE_NAME = "randomizer_settings.json"
DEFAULT_RANDOM_MODE = "seven"
VALID_RANDOM_MODES = frozenset({"three", "seven"})


def preferences_path(app_directory: Path) -> Path:
    return app_directory / PREFERENCES_FILE_NAME


def load_random_mode(app_directory: Path) -> str:
    path = preferences_path(app_directory)
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return DEFAULT_RANDOM_MODE
    if not isinstance(loaded, dict):
        return DEFAULT_RANDOM_MODE
    mode = loaded.get("randomMode")
    return mode if mode in VALID_RANDOM_MODES else DEFAULT_RANDOM_MODE


def save_random_mode(app_directory: Path, mode: str) -> None:
    if mode not in VALID_RANDOM_MODES:
        raise ValueError(f"未知运行模式：{mode}")
    path = preferences_path(app_directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "randomMode": mode,
    }
    temporary_path = path.with_name(
        f".{path.name}.{os.getpid()}.tmp"
    )
    try:
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)
