from __future__ import annotations

import json
import os
from pathlib import Path


PREFERENCES_FILE_NAME = "randomizer_settings.json"
DEFAULT_RANDOM_MODE = "seven"
VALID_RANDOM_MODES = frozenset({"three", "seven"})
DEFAULT_LOOP_RANDOM = False
DEFAULT_CONCURRENCY = 1
DEFAULT_COMPATIBILITY_MODE = False
MIN_CONCURRENCY = 1
LEGACY_AUDIO_MUTE_RECOVERY_KEY = "legacyAudioMuteRecovered"
AUDIO_MUTE_RECOVERY_VERSION_KEY = "audioMuteRecoveryVersion"
AUDIO_MUTE_RECOVERY_VERSION = 2


def preferences_path(app_directory: Path) -> Path:
    return app_directory / PREFERENCES_FILE_NAME


def _load_preferences(app_directory: Path) -> dict:
    path = preferences_path(app_directory)
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _save_preferences(app_directory: Path, payload: dict) -> None:
    path = preferences_path(app_directory)
    path.parent.mkdir(parents=True, exist_ok=True)
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


def load_random_mode(app_directory: Path) -> str:
    loaded = _load_preferences(app_directory)
    mode = loaded.get("randomMode")
    return mode if mode in VALID_RANDOM_MODES else DEFAULT_RANDOM_MODE


def save_random_mode(app_directory: Path, mode: str) -> None:
    if mode not in VALID_RANDOM_MODES:
        raise ValueError(f"未知运行模式：{mode}")
    payload = _load_preferences(app_directory)
    payload.update({"version": 1, "randomMode": mode})
    _save_preferences(app_directory, payload)


def load_loop_random(app_directory: Path) -> bool:
    value = _load_preferences(app_directory).get("loopRandom")
    return value if isinstance(value, bool) else DEFAULT_LOOP_RANDOM


def load_concurrency(app_directory: Path) -> int:
    value = _load_preferences(app_directory).get("concurrency")
    if (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= MIN_CONCURRENCY
    ):
        return value
    return DEFAULT_CONCURRENCY


def load_compatibility_mode(app_directory: Path) -> bool:
    value = _load_preferences(app_directory).get("compatibilityMode")
    return (
        value
        if isinstance(value, bool)
        else DEFAULT_COMPATIBILITY_MODE
    )


def save_random_runtime_settings(
    app_directory: Path,
    *,
    loop_random: bool,
    concurrency: int,
    compatibility_mode: bool = False,
) -> None:
    if not isinstance(loop_random, bool):
        raise ValueError("循环随机设置必须是布尔值")
    if (
        not isinstance(concurrency, int)
        or isinstance(concurrency, bool)
        or concurrency < MIN_CONCURRENCY
    ):
        raise ValueError("同时运行数量必须大于 0")
    if not isinstance(compatibility_mode, bool):
        raise ValueError("兼容模式设置必须是布尔值")
    payload = _load_preferences(app_directory)
    payload.update(
        {
            "version": 1,
            "loopRandom": loop_random,
            "concurrency": concurrency,
            "compatibilityMode": compatibility_mode,
        }
    )
    _save_preferences(app_directory, payload)


def legacy_audio_mute_recovery_pending(app_directory: Path) -> bool:
    return int(
        _load_preferences(app_directory).get(
            AUDIO_MUTE_RECOVERY_VERSION_KEY,
            0,
        )
        or 0
    ) < AUDIO_MUTE_RECOVERY_VERSION


def mark_legacy_audio_mute_recovered(app_directory: Path) -> None:
    payload = _load_preferences(app_directory)
    payload.update(
        {
            "version": 1,
            LEGACY_AUDIO_MUTE_RECOVERY_KEY: True,
            AUDIO_MUTE_RECOVERY_VERSION_KEY: (
                AUDIO_MUTE_RECOVERY_VERSION
            ),
        }
    )
    _save_preferences(app_directory, payload)
