"""Serialize equipment once for live detail and persisted history."""
from __future__ import annotations


def serialize_equipment(equip_info, equip_specials=()) -> dict:
    categories = [
        {"name": type_name, "items": [{"name": name, "effect": effect} for name, effect in items]}
        for items, type_name in (equip_info or ())
    ]
    specials = []
    for title, items in equip_specials:
        serialized = []
        for item in items:
            if (isinstance(item, (list, tuple)) and len(item) == 2
                    and all(isinstance(value, str) for value in item)):
                serialized.append(f"{item[0]}：{item[1]}")
            else:
                serialized.append(str(item))
        specials.append({"title": title, "items": serialized})
    return {"categories": categories, "specials": specials}
