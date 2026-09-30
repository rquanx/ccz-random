from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def _git_output(project_root: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _source_hash(project_root: Path) -> str:
    candidates = [
        project_root / "VERSION",
        project_root / "CHANGELOG.json",
        project_root / "fast_randomizer.py",
    ]
    candidates.extend(
        sorted((project_root / "ccz_randomizer").rglob("*.py"))
    )
    candidates.extend(
        path
        for path in (
            project_root / "native" / "ccz_control.dll",
            project_root / "native" / "ccz_injector.exe",
            project_root / "resources" / "app" / "random_s00.eex",
        )
        if path.is_file()
    )
    digest = hashlib.sha256()
    for path in candidates:
        if not path.is_file():
            continue
        digest.update(path.relative_to(project_root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def write_build_info(project_root: Path) -> Path:
    version_path = project_root / "VERSION"
    version = os.environ.get("CCZ_APP_VERSION", "").strip()
    if not version:
        version = version_path.read_text(encoding="utf-8").strip()

    built_at = dt.datetime.now().astimezone()
    source_hash = _source_hash(project_root)
    commit = _git_output(project_root, "rev-parse", "--short=12", "HEAD")
    dirty = bool(
        _git_output(
            project_root,
            "status",
            "--porcelain",
            "--untracked-files=no",
        )
    )
    build_id = (
        built_at.strftime("%Y%m%d.%H%M%S")
        + "-"
        + source_hash[:12]
    )
    output = project_root / "build" / "generated" / "build_info.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "version": version,
                "buildId": build_id,
                "builtAt": built_at.isoformat(timespec="seconds"),
                "sourceHash": source_hash,
                "gitCommit": commit or "unknown",
                "gitDirty": dirty,
                "python": sys.version.split()[0],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return output
