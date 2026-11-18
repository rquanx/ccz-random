"""Equipment display names and optional grouping without changing observations."""
import re
from collections import Counter

from ccz_randomizer.profile_context import current_context

_LEGACY_STRATEGY = re.compile(r'(攻击追加|策略先手|策略反击)-策略编号(\d+)')
_LEGACY_PENETRATION = re.compile(r'穿透攻击-(\d+)')
_LEGACY_REMOTE = re.compile(r'远[距程]攻击\s*-?\s*(\d+)(?:\s*[(（][^()（）]*[)）])?')
_PERCENT_VALUE = re.compile(r'\s*[+\-]?\d+(?:\.\d+)?\s*[%％]$')
_MP_DEFENSE_VALUE = re.compile(r'^MP防御\s*\+\s*\d+(?:\.\d+)?$', re.IGNORECASE)


def merge_equipment_frequencies(rows):
    """Combine percentage and MP defense magnitudes; preserve distinct ranges."""
    counts = Counter()
    for label, count in rows:
        name = 'MP防御' if _MP_DEFENSE_VALUE.fullmatch(label) else _PERCENT_VALUE.sub('', label).rstrip()
        counts[name or label] += count
    return sorted(counts.items(), key=lambda row: (-row[1], row[0]))


def equipment_label_resolver():
    equipment = current_context().skills['displayRules']['equipment']
    names = equipment['STRATEGY_NAMES']
    ranges = equipment['effects']['51']['values']
    remote_ranges = equipment['effects']['50'].get('values', {})
    remote_aliases = {}
    for code, label in remote_ranges.items():
        match = _LEGACY_REMOTE.fullmatch(label)
        if match:
            name = label[label.find('(') + 1:-1] if '(' in label else ''
            if name:
                remote_aliases[f'远距攻击-{name}'] = label
                remote_aliases[f'远程攻击-{name}'] = label

    def resolve(label):
        match = _LEGACY_REMOTE.fullmatch(label)
        if match:
            return remote_ranges.get(str(int(match[1])), label)
        if label in remote_aliases:
            return remote_aliases[label]
        match = _LEGACY_PENETRATION.fullmatch(label)
        if match:
            return ranges.get(str(int(match[1])), label)
        match = _LEGACY_STRATEGY.fullmatch(label)
        if match:
            name = names.get(str(int(match[2])))
            if name:
                return f'{match[1]}-{name}'
        return label

    return resolve


def equipment_display(equipment):
    """Resolve old snapshot labels for viewing without rewriting stored data."""
    resolve = equipment_label_resolver()
    def display(effect):
        return resolve(effect) if isinstance(effect, str) and effect.startswith(('远距攻击', '远程攻击')) else effect
    return {**equipment, 'categories': [
        {**category, 'items': [
            {**item, 'effect': display(item.get('effect', ''))}
            for item in category.get('items') or []]}
        for category in equipment.get('categories') or []]}
