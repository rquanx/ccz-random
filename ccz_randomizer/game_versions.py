"""The supported game rules for this release."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from ccz_randomizer.profiles import load_profile

DEFAULT_GAME_VERSION = "2.2"
APP_DEFAULT_GAME_VERSION = load_profile().game_version
LATEST_GAME_VERSION = "2.20-1104"
NIGHT_GAME_VERSION = "2.20-1104-night"
VALID_GAME_VERSIONS = frozenset({"2.2", DEFAULT_GAME_VERSION, LATEST_GAME_VERSION, NIGHT_GAME_VERSION, APP_DEFAULT_GAME_VERSION})


def catalog_game_version(version: str) -> str:
    """Return the shared data catalog used by a compatible game build."""
    version = normalize_game_version(version)
    return "2.2" if version == "2.2" else load_profile().game_version


def is_enhanced_game_version(version: str) -> bool:
    normalize_game_version(version)
    return version != "2.2" and load_profile().manifest.get("capabilities", {}).get("validateRoster", True)


def normalize_game_version(value: str = DEFAULT_GAME_VERSION) -> str:
    if value not in VALID_GAME_VERSIONS:
        raise ValueError("本版本支持游戏版本：2.2、2.20-1104、2.20-1104夜")
    return value


def current_game_version() -> str:
    return normalize_game_version(os.environ.get("CCZ_GAME_VERSION", DEFAULT_GAME_VERSION))


def data_directory() -> Path:
    return load_profile().root


def detect_game_version(executable: Path, *, manifest: dict | None = None) -> str:
    """Use known fingerprints as hints, never as a compatibility gate.

    Unknown distributions use the active profile. Real I/O errors propagate;
    process, script and memory operations retain their own integrity checks.
    """
    if manifest is None:
        manifest = load_profile().fingerprints
    exe_hash = hashlib.sha256(executable.read_bytes()).hexdigest()
    for version, files in manifest.items():
        if files["Ekd5.exe"] != exe_hash:
            continue
        return normalize_game_version(version)
    return load_profile().game_version


def activate_game_version(executable: Path) -> str:
    version = detect_game_version(executable)
    os.environ["CCZ_GAME_VERSION"] = version
    return version


def effective_random_mode(version: str = DEFAULT_GAME_VERSION, requested_mode: str = "three") -> str:
    normalize_game_version(version)
    if requested_mode not in {"three", "seven"}:
        raise ValueError(f"未知运行模式：{requested_mode}")
    return "three"
