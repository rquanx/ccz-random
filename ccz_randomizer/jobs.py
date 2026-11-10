"""Job metadata loaded from the active game profile."""
from __future__ import annotations

from ccz_randomizer.profiles import load_profile

JOB_MAP = {
    item["id"]: (item["name"], item["score"], item["type"])
    for item in load_profile().jobs["jobs"]
}
