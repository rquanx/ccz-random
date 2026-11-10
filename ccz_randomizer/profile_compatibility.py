"""Tool/data compatibility contract, independent of the app release number."""
from __future__ import annotations

import re

# Keep this ID across compatible tool releases. Change it when data alone
# cannot bridge an engine change; publish that group's feed independently.
PROFILE_COMPATIBILITY_ID = "ccz-fast-v2"


def require_profile_compatibility(manifest: dict) -> None:
    groups = manifest.get("toolCompatibility")
    if (not isinstance(groups, list) or not groups
            or any(not isinstance(group, str) or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,63}", group) for group in groups)):
        raise ValueError("数据包缺少工具兼容信息，请下载适用于当前工具的数据包")
    if PROFILE_COMPATIBILITY_ID not in groups:
        raise ValueError("数据包与当前工具不兼容，请更新工具或下载匹配的数据包")
