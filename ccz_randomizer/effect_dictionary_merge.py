"""Reviewed equivalences only; similar names are not proof of equal mechanics."""
from dataclasses import replace
import re


# Equipment code -> independent skill IDs with the same documented mechanism.
# Composite equipment such as MP defence, active double attack and guide attack
# intentionally stay separate because they add recovery, level or trigger rules.
EQUIVALENT_EFFECTS = {
    43: (15,), 57: (46,), 59: (45,), 61: (32,), 62: (29,), 63: (33,),
    64: (47,), 67: (41,), 72: (111,), 76: (116,), 79: (99,),
    90: (56,), 91: (178,), 92: (61,), 97: (57,), 99: (59,),
    100: (60,), 101: (20,), 105: (71,), 106: (186,),
    112: (84,), 115: (87,), 117: (89,),
}


def merge_equivalent_effects(entries):
    by_key = {entry.key: entry for entry in entries}
    replacements, removed = {}, set()
    for code, skill_ids in EQUIVALENT_EFFECTS.items():
        key = f"equipment:{code}"
        if key not in by_key:
            continue
        original = by_key[key]
        members = [original, *(by_key[f"skill:{sid}"] for sid in skill_ids if f"skill:{sid}" in by_key)]
        name = "削铁如泥" if code == 72 else original.name
        aliases = tuple(dict.fromkeys(alias for member in members for alias in (member.name, *member.aliases)))
        patterns = [member.pattern for member in members if member.pattern]
        for member in members[1:]:
            # Match pasted skill labels with a different random numeric parameter.
            patterns.append(re.sub(r"\d+(?:\.\d+)?", r"\\d+(?:\\.\\d+)?", re.escape(member.name)))
        replacements[key] = replace(original, name=name, aliases=aliases,
            pattern="|".join(f"(?:{pattern})" for pattern in patterns),
            source_keys=tuple(member.key for member in members),
            categories=tuple(dict.fromkeys(member.category for member in members)))
        removed.update(member.key for member in members[1:])
    merged = [replacements.get(entry.key, entry) for entry in entries if entry.key not in removed]
    # Remaining shared base names represent different effects: label the domain.
    bases = {entry.key: re.sub(r"\s*[+\-]?\d+(?:\.\d+)?%?$", "", entry.name) for entry in merged}
    domains = {}
    for entry in merged:
        domains.setdefault(bases[entry.key], set()).add(entry.category)
    return tuple(replace(entry, name=f"{entry.name}（{'宝物' if entry.category == '宝物特效' else '特技'}）",
                         aliases=tuple(dict.fromkeys((entry.name, *entry.aliases))))
                 if len(domains[bases[entry.key]]) > 1 else entry for entry in merged)
