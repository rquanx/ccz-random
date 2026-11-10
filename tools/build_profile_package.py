"""Seal, validate and package a profile plus an optional HTTPS update feed."""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import shutil
import zipfile
from pathlib import Path

from ccz_randomizer.profiles import validate_profile
from ccz_randomizer.profile_compatibility import PROFILE_COMPATIBILITY_ID


def build_package(source: Path, output: Path, *, download_url: str = "") -> Path:
    with tempfile.TemporaryDirectory(prefix="ccz-profile-build-") as temp:
        root = Path(temp) / "profile"
        shutil.copytree(source, root)
        manifest_path = root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["sha256"] = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in manifest["files"].values()}
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        profile = validate_profile(root)
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in ("manifest.json", *profile.manifest["files"].values()):
                archive.write(root / name, name)
        if download_url:
            from urllib.parse import urlparse
            if urlparse(download_url).scheme != "https":
                raise ValueError("发布地址必须为 HTTPS")
            feed = dict(schemaVersion=1, compatibilityId=PROFILE_COMPATIBILITY_ID, profileId=profile.profile_id,
                        catalogVersion=manifest["catalogVersion"], url=download_url,
                        sha256=hashlib.sha256(output.read_bytes()).hexdigest())
            output.with_suffix(".feed.json").write_text(json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def main():
    parser = argparse.ArgumentParser(description="构建游戏 profile 更新包")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--download-url", default="")
    args = parser.parse_args()
    build_package(args.source, args.output, download_url=args.download_url)


if __name__ == "__main__":
    main()
