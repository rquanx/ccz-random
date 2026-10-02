from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any


def _data_path(*parts: str) -> Path:
    root = (
        Path(sys._MEIPASS)
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parents[1]
    )
    return root.joinpath("resources", "data", *parts)


def _load_json(*parts: str) -> Any:
    return json.loads(_data_path(*parts).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def job_catalog_rows() -> tuple[dict[str, Any], ...]:
    catalog = _load_json("jobs", "job_id_map.json")
    return tuple(
        {
            "value": str(job_id),
            "label": str(value["name"]),
        }
        for job_id, value in sorted(
            catalog.items(),
            key=lambda item: int(item[0]),
        )
    )


@lru_cache(maxsize=1)
def skill_catalog_rows() -> tuple[dict[str, Any], ...]:
    catalog = _load_json("skills", "runtime_skill_catalog.json")
    return tuple(
        {
            "value": str(value["id"]),
            "label": str(value["name"]),
        }
        for value in sorted(catalog, key=lambda item: int(item["id"]))
    )


@lru_cache(maxsize=1)
def treasure_property_catalog_rows() -> tuple[dict[str, Any], ...]:
    catalog = _load_json("equipment", "equip_effect_map.json")
    names = sorted({str(name) for name in catalog.values() if str(name)})
    return tuple({"value": name, "label": name} for name in names)
