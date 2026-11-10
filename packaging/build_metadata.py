from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import struct
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
    for folder in ("resources", "packaging", "native", "tools/windows"):
        candidates.extend(sorted(path for path in (project_root / folder).rglob("*")
                                 if path.is_file() and "__pycache__" not in path.parts
                                 and path.suffix not in {".pyc", ".obj", ".res", ".lib", ".exp"}))
    candidates = sorted(set(candidates))
    digest = hashlib.sha256()
    for path in candidates:
        if not path.is_file():
            continue
        digest.update(path.relative_to(project_root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def write_build_info(project_root: Path, *, runtime_files=None) -> Path:
    version_path = project_root / "VERSION"
    version = os.environ.get("CCZ_APP_VERSION", "").strip()
    if not version:
        version = version_path.read_text(encoding="utf-8").strip()

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
    output = project_root / "build" / "generated" / "build_info.json"
    stable_fields = {
        "version": version,
        "sourceHash": source_hash,
        "gitCommit": commit or "unknown",
        "gitDirty": dirty,
        "python": sys.version.split()[0],
        "architectureBits": struct.calcsize("P") * 8,
        "runtimeFiles": runtime_files or {},
        "dependencies": {name: _dependency_version(name) for name in
                         ("pyinstaller", "pyinstaller-hooks-contrib", "pillow", "psutil", "pycaw",
                          "numpy", "opencv-python-headless", "comtypes", "packaging",
                          "pywin32-ctypes", "setuptools")},
        "profiles": _profile_metadata(project_root),
    }
    if output.is_file():
        try:
            existing = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            existing = {}
        if all(
            existing.get(key) == value
            for key, value in stable_fields.items()
        ):
            return output

    provenance_hash = hashlib.sha256(json.dumps(stable_fields, sort_keys=True,
                                                ensure_ascii=False).encode("utf-8")).hexdigest()
    built_at = dt.datetime.now().astimezone()
    build_id = (
        built_at.strftime("%Y%m%d.%H%M%S")
        + "-"
        + provenance_hash[:12]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                **stable_fields,
                "buildId": build_id,
                "builtAt": built_at.isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return output


def _dependency_version(name):
    from importlib.metadata import version, PackageNotFoundError
    try:
        return version(name)
    except PackageNotFoundError:
        return "not-installed"


def _profile_metadata(project_root):
    result = []
    for manifest in sorted((project_root / "resources/data/profiles").glob("*/manifest.json")):
        data = json.loads(manifest.read_text(encoding="utf-8"))
        result.append({"profileId": data["profileId"], "catalogVersion": data["catalogVersion"],
                       "files": data.get("sha256", {})})
    return result
