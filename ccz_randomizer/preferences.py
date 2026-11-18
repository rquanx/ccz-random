from __future__ import annotations

import json
import hashlib
import os
import platform
from pathlib import Path


PREFERENCES_FILE_NAME = "randomizer_settings.json"
DEFAULT_RANDOM_MODE = "three"
VALID_RANDOM_MODES = frozenset({"three"})
DEFAULT_LOOP_RANDOM = False
DEFAULT_CONCURRENCY = 1
DEFAULT_COMPATIBILITY_MODE = False
MIN_CONCURRENCY = 1
LEGACY_AUDIO_MUTE_RECOVERY_KEY = "legacyAudioMuteRecovered"
AUDIO_MUTE_RECOVERY_VERSION_KEY = "audioMuteRecoveryVersion"
AUDIO_MUTE_RECOVERY_VERSION = 2
FIRST_USE_NOTICE_VERSION_KEY = "firstUseNoticeVersion"
# Increment this value only when the first-use notice itself needs to be
# shown again. Ordinary application releases keep the acknowledgement.
FIRST_USE_NOTICE_VERSION = 1


def first_use_notice_directory() -> Path:
    """Keep acknowledgements local, outside portable game/config directories."""
    local_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_data) if local_data else Path.home() / "AppData" / "Local"
    return base / "CCZRandomizer" / "notices"


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


def load_turbo_mode(app_directory: Path) -> bool:
    value = _load_preferences(app_directory).get("turboMode")
    return value if isinstance(value, bool) else False


def load_prevent_sleep(app_directory: Path) -> bool:
    value = _load_preferences(app_directory).get("preventSleep")
    return value if isinstance(value, bool) else False


def load_first_use_notice_seen(app_directory: Path) -> bool:
    """Return whether the current first-use notice version was acknowledged."""
    loaded = _load_preferences(app_directory)
    value = loaded.get(FIRST_USE_NOTICE_VERSION_KEY)
    if isinstance(value, int) and not isinstance(value, bool):
        return value >= FIRST_USE_NOTICE_VERSION
    # Migrate the original boolean marker without making existing users see
    # the same notice again. A future version bump will intentionally require
    # acknowledgement again.
    return (
        FIRST_USE_NOTICE_VERSION == 1
        and loaded.get("firstUseNoticeSeen") is True
    )


def mark_first_use_notice_seen(app_directory: Path) -> None:
    payload = _load_preferences(app_directory)
    previous = payload.get(FIRST_USE_NOTICE_VERSION_KEY)
    version = FIRST_USE_NOTICE_VERSION
    if isinstance(previous, int) and not isinstance(previous, bool):
        version = max(version, previous)
    payload.update(
        {"version": 1, FIRST_USE_NOTICE_VERSION_KEY: version}
    )
    _save_preferences(app_directory, payload)


def _notice_device_key() -> str:
    # Bind portable fallback records to the device, without storing its raw ID.
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
            0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            identity = str(winreg.QueryValueEx(key, "MachineGuid")[0])
    except (ImportError, OSError):
        identity = platform.node()
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def first_use_notice_acknowledged(game_directory: Path) -> bool:
    if load_first_use_notice_seen(first_use_notice_directory()):
        return True
    records = _load_preferences(game_directory).get("noticeVersionsByDevice", {})
    if not isinstance(records, dict):
        return False
    version = records.get(_notice_device_key())
    return isinstance(version, int) and not isinstance(version, bool) and version >= FIRST_USE_NOTICE_VERSION


def acknowledge_first_use_notice(game_directory: Path) -> bool:
    """Persist locally, then in the game directory; False allows session-only use."""
    try:
        mark_first_use_notice_seen(first_use_notice_directory())
        return True
    except OSError:
        pass
    try:
        payload = _load_preferences(game_directory)
        records = payload.get("noticeVersionsByDevice")
        if not isinstance(records, dict):
            records = {}
        device = _notice_device_key()
        previous = records.get(device)
        records[device] = max(
            previous if isinstance(previous, int) and not isinstance(previous, bool) else 0,
            FIRST_USE_NOTICE_VERSION,
        )
        payload["noticeVersionsByDevice"] = records
        _save_preferences(game_directory, payload)
        return True
    except OSError:
        return False


def save_random_runtime_settings(
    app_directory: Path,
    *,
    loop_random: bool,
    concurrency: int,
    compatibility_mode: bool = False,
    turbo_mode: bool = False,
    prevent_sleep: bool = False,
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
    if not isinstance(turbo_mode, bool):
        raise ValueError("极速模式设置必须是布尔值")
    if not isinstance(prevent_sleep, bool):
        raise ValueError("阻止系统睡眠设置必须是布尔值")
    payload = _load_preferences(app_directory)
    payload.update(
        {
            "version": 1,
            "loopRandom": loop_random,
            "concurrency": concurrency,
            "compatibilityMode": compatibility_mode,
            "turboMode": turbo_mode,
            "preventSleep": prevent_sleep,
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
