"""HTTPS profile release feed with a bundled default and local opt-out."""
from __future__ import annotations

import hashlib
import json
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlparse
import re

from ccz_randomizer.profiles import load_profile, install_profile_package
from ccz_randomizer.profile_compatibility import PROFILE_COMPATIBILITY_ID

OSS_BASE_URL = "https://ccz-fast-profile.oss-cn-guangzhou.aliyuncs.com"
LEGACY_FEED_URL = OSS_BASE_URL + "/profile.feed.json"
CHANNEL_URL = OSS_BASE_URL + "/channels/" + PROFILE_COMPATIBILITY_ID
DEFAULT_FEED_URL = CHANNEL_URL + "/profile.feed.json"
DEFAULT_PACKAGE_URL = CHANNEL_URL + "/latest.zip"


def feed_settings_path(directory: Path) -> Path:
    return directory / "ccz_fast_data" / ("profile_update." + PROFILE_COMPATIBILITY_ID + ".json")


def load_feed_url(directory: Path) -> str:
    path = feed_settings_path(directory)
    if not path.exists():
        legacy = directory / "ccz_fast_data" / "profile_update.json"
        if legacy.exists():
            try:
                if json.loads(legacy.read_text(encoding="utf-8")).get("feedUrl") == "":
                    return ""
            except (OSError, ValueError, TypeError, AttributeError):
                pass
        return DEFAULT_FEED_URL
    url = json.loads(path.read_text(encoding="utf-8")).get("feedUrl", "")
    return DEFAULT_FEED_URL if url in (LEGACY_FEED_URL, OSS_BASE_URL + "/channels/ccz-fast-v1/profile.feed.json") else url


def save_feed_url(directory: Path, url: str) -> None:
    if url and (urlparse(url).scheme != "https" or not urlparse(url).netloc):
        raise ValueError("更新源必须是 HTTPS 地址")
    path = feed_settings_path(directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"feedUrl": url}), encoding="utf-8")
    temporary.replace(path)


def read_https(url: str, *, limit: int, timeout: int = 10) -> bytes:
    if urlparse(url).scheme != "https" or not urlparse(url).netloc:
        raise ValueError("更新地址必须是 HTTPS")
    request = urllib.request.Request(url, headers={"User-Agent": "CCZRandomizer/4"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if urlparse(response.geturl()).scheme != "https":
            raise ValueError("不允许非 HTTPS 跳转")
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("更新内容超过大小限制")
    return data


def validate_feed(feed: dict) -> None:
    if not isinstance(feed, dict) or feed.get("schemaVersion") != 1:
        raise ValueError("更新源格式无效")
    if feed.get("compatibilityId") != PROFILE_COMPATIBILITY_ID:
        raise ValueError("更新源与当前工具不兼容，请使用匹配的工具更新源")
    if not isinstance(feed.get("profileId"), str) or type(feed.get("catalogVersion")) is not int or feed["catalogVersion"] < 1:
        raise ValueError("更新源缺少版本信息")
    if (not isinstance(feed.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", feed["sha256"])
            or not isinstance(feed.get("url"), str) or urlparse(feed["url"]).scheme != "https" or not urlparse(feed["url"]).netloc):
        raise ValueError("更新源缺少下载地址或校验值")


def check_profile_update(directory: Path) -> dict | None:
    url = load_feed_url(directory)
    if not url:
        return None
    feed = json.loads(read_https(url, limit=65536).decode("utf-8"))
    validate_feed(feed)
    profile = load_profile(app_directory=directory)
    if feed["profileId"] == profile.profile_id and feed["catalogVersion"] <= profile.manifest["catalogVersion"]:
        return None
    return feed


def install_feed_update(feed: dict, directory: Path):
    validate_feed(feed)
    data = read_https(feed["url"], limit=8 * 1024 * 1024, timeout=20)
    if hashlib.sha256(data).hexdigest() != feed["sha256"]:
        raise ValueError("下载包与更新源校验值不一致")
    with tempfile.TemporaryDirectory(prefix="ccz-update-") as temp:
        archive = Path(temp) / "profile.zip"
        archive.write_bytes(data)
        # Check feed/package identity before installation changes the active marker.
        import zipfile
        from ccz_randomizer.profiles import _safe_extract, validate_profile
        extracted = Path(temp) / "profile"
        extracted.mkdir()
        with zipfile.ZipFile(archive) as z:
            _safe_extract(z, extracted)
        manifests = list(extracted.rglob("manifest.json"))
        if len(manifests) != 1:
            raise ValueError("数据包清单无效")
        profile = validate_profile(manifests[0].parent)
        if profile.profile_id != feed["profileId"] or profile.manifest["catalogVersion"] != feed["catalogVersion"]:
            raise ValueError("数据包与更新源版本不一致")
        return install_profile_package(archive, directory)
