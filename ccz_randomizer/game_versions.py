"""The supported game rules for this release."""
from __future__ import annotations

DEFAULT_GAME_VERSION = "2.2"
VALID_GAME_VERSIONS = frozenset({DEFAULT_GAME_VERSION})


def normalize_game_version(value: str = DEFAULT_GAME_VERSION) -> str:
    if value != DEFAULT_GAME_VERSION:
        raise ValueError(f"本版本只支持游戏版本：{DEFAULT_GAME_VERSION}")
    return DEFAULT_GAME_VERSION


def effective_random_mode(version: str = DEFAULT_GAME_VERSION, requested_mode: str = "three") -> str:
    normalize_game_version(version)
    if requested_mode not in {"three", "seven"}:
        raise ValueError(f"未知运行模式：{requested_mode}")
    return "three"
