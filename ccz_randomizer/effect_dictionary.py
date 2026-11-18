"""Version-bound searchable help, independent of randomized item descriptions."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import re

from ccz_randomizer.profile_context import current_context

@dataclass(frozen=True)
class EffectEntry:
    key: str
    name: str
    category: str
    description: str
    aliases: tuple[str, ...] = ()
    pattern: str = ""
    source_keys: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()


class EffectDictionary:
    def __init__(self, entries=(), *, version="", notice=""):
        self.entries = tuple(entries)
        self.version = version
        self.notice = notice
        self._index = tuple((entry, " ".join((entry.name, *entry.aliases, entry.description)).casefold(),
                             re.compile(entry.pattern, re.IGNORECASE) if entry.pattern else None)
                            for entry in self.entries)

    def search(self, query="", category="全部"):
        query = query.strip().casefold()
        terms = query.split()
        return tuple(entry for entry, text, pattern in self._index
                     if (category == "全部" or category == entry.category or category in entry.categories)
                     and (all(term in text for term in terms)
                          or bool(query and pattern and pattern.fullmatch(query))))


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def load_effect_dictionary(context=None):
    context = context or current_context()
    data = context.effect_dictionary
    if data is None:
        # Older packages have no handbook. Reuse bundled data only if its exact
        # profile, game version and effect catalogue match (checked below).
        from ccz_randomizer.profiles import DEFAULT_PROFILE_ID, load_profile
        if context.profile_id == DEFAULT_PROFILE_ID:
            data = load_profile(DEFAULT_PROFILE_ID).effect_dictionary
    unavailable = "当前数据包暂无配套特效说明，暂不显示其他版本的字典。"
    if not data or data["gameVersion"] != context.game_version or data["profileId"] != context.profile_id:
        return EffectDictionary(version=context.game_version, notice=unavailable)
    skills = context.skills
    effects = skills["displayRules"]["equipment"]["effects"]
    catalog = [skills["runtimeCatalog"], effects]
    digest = hashlib.sha256(json.dumps(_plain(catalog), ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    if digest != data["catalogHash"]:
        return EffectDictionary(version=context.game_version, notice=unavailable)
    entries = []
    for skill in data["skills"]:
        description = skill["description"]
        if not description:
            continue
        entries.append(EffectEntry(f'skill:{skill["id"]}', skill["name"], "特技说明",
            description, (skill["baseName"],)))
    for code, rule in sorted(effects.items(), key=lambda item: int(item[0])):
        template = rule.get("template", rule.get("base", ""))
        name = re.sub(r"[+\-]?\{value\}%?|[\-]?\{strategy\}", "", template).strip()
        aliases = ()
        pattern = re.escape(template)
        pattern = pattern.replace(re.escape("{value}"), r"\d+(?:\.\d+)?").replace(re.escape("{strategy}"), r".+")
        if rule["op"] == "skill":
            pattern = re.escape(name) + r"(?:[\s-].+)?"
        if rule["op"] == "lookup":
            aliases = tuple(dict.fromkeys(rule["values"].values()))
        explanation = data.get("equipment", {}).get(code)
        if not explanation or explanation["name"] != name or not explanation["description"].strip():
            return EffectDictionary(version=context.game_version, notice=unavailable)
        entries.append(EffectEntry(f"equipment:{code}", name, "宝物特效", explanation["description"],
                                   aliases, pattern))
    entries.sort(key=lambda item: item.category != "宝物特效")
    from ccz_randomizer.effect_dictionary_merge import merge_equivalent_effects
    return EffectDictionary(merge_equivalent_effects(entries, data["mergeRules"]), version=context.game_version)
