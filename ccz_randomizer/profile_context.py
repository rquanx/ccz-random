"""Immutable process snapshot, published once at an idle UI boundary.

Legacy module constants remain a compatibility bridge; new consumers retain
this value for a whole operation so later activation cannot change their data.
"""
from dataclasses import dataclass
from types import MappingProxyType
from collections.abc import Mapping
from ccz_randomizer.profiles import load_profile


def _freeze(value):
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class ProfileContext:
    profile_id: str
    game_version: str
    revision: int
    jobs: Mapping
    skills: Mapping
    memory_layout: Mapping
    fixed_entries: Mapping
    recruitment: Mapping
    script_rules: Mapping
    effect_dictionary: Mapping | None = None

    @classmethod
    def from_profile(cls, profile):
        return cls(profile.profile_id, profile.game_version, profile.manifest["catalogVersion"],
                   *(_freeze(getattr(profile, name)) for name in
                     ("jobs", "skills", "memory_layout", "fixed_entries", "recruitment", "script_rules", "effect_dictionary")))


_current = None


def current_context():
    global _current
    if _current is None:
        _current = ProfileContext.from_profile(load_profile())
    return _current


def publish_context(context):
    global _current
    _current = context
