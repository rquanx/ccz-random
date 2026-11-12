"""Version-bound searchable help, independent of randomized item descriptions."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import sys

from ccz_randomizer.profile_context import current_context

PENDING = "说明待核实"


@dataclass(frozen=True)
class EffectEntry:
    key: str
    name: str
    category: str
    description: str
    status: str
    aliases: tuple[str, ...] = ()
    pattern: str = ""


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
                     if (category == "全部" or category == entry.category)
                     and (all(term in text for term in terms)
                          or bool(query and pattern and pattern.fullmatch(query))))


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


@lru_cache(maxsize=4)
def _read_resource(profile_id):
    # IDs come from installed profiles, but must never become arbitrary filesystem paths.
    if not re.fullmatch(r"\w[\w.-]*", profile_id):
        return None
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    path = root / "resources/data/effects" / f"{profile_id}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text("utf-8"))


def load_effect_dictionary(context=None):
    context = context or current_context()
    data = _read_resource(context.profile_id)
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
    by_base = {}
    for skill in data["skills"]:
        by_base.setdefault(skill["baseName"], []).append(skill)
        description = skill["description"]
        entries.append(EffectEntry(f'skill:{skill["id"]}', skill["name"], "特技说明",
            description or "游戏独立说明表未提供已核实的机制说明。", "游戏说明" if description else PENDING,
            (skill["baseName"],)))
    for code, rule in sorted(effects.items(), key=lambda item: int(item[0])):
        template = rule.get("template", rule.get("base", ""))
        name = re.sub(r"[+\-]?\{value\}%?|[\-]?\{strategy\}", "", template).strip()
        description = "该宝物特效的机制尚未核实，请勿依据宝物自带的固定描述判断效果。"
        status = PENDING
        aliases = ()
        # Same-name skill help is a reference, never evidence that item parameters use
        # the same formula. Do not infer composite effects or map similar names.
        references = [item for item in by_base.get(name, ()) if item["description"]]
        if references:
            parts = []
            for item in references:
                text = f'{item["name"]}\n{item["description"]}'
                if text not in parts:
                    parts.append(text)
            description = "\n\n".join(parts)
            description += "\n\n以上为同名特技的原始说明，仅供理解机制。宝物的参数、倍率和触发规则仍需核实，不能直接套用说明中的固定数字。"
            status = "同名特技参考"
            aliases = tuple(item["name"] for item in references)
        confirmed = data.get("equipment", {}).get(code)
        if confirmed and confirmed["name"] == name:
            description = confirmed["description"]
            status = "游戏更新说明"
        pattern = re.escape(template)
        pattern = pattern.replace(re.escape("{value}"), r"\d+(?:\.\d+)?").replace(re.escape("{strategy}"), r".+")
        if rule["op"] == "skill":
            pattern = re.escape(name) + r"(?:[\s-].+)?"
        if rule["op"] == "lookup":
            name = "穿透攻击"
            aliases = tuple(rule["values"].values())
        entries.append(EffectEntry(f"equipment:{code}", name, "宝物特效", description, status, aliases, pattern))
    entries.sort(key=lambda item: (item.category != "宝物特效",
                                  {"游戏更新说明": 0, "同名特技参考": 1, "游戏说明": 1, PENDING: 2}[item.status]))
    return EffectDictionary(entries, version=context.game_version,
        notice="按实际特效名称查询，不按宝物名称判断。说明来自本版游戏独立特技说明；复合特效和参数差异仍需核实。")
