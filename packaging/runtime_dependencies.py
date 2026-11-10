"""Locate and fingerprint the proprietary runtime without machine-specific paths."""
import hashlib
import os
from pathlib import Path

RUNTIME_PACKAGES = frozenset({"cfg", "encrypt", "keyboard", "models", "pydirectinput",
                              "task", "utils", "win32con", "window"})


def runtime_root(project_root):
    configured = os.environ.get("CCZ_RUNTIME_ROOT")
    root = Path(configured) if configured else project_root.parent / "exe-analysis/tool.exe_extracted"
    if not root.is_absolute():
        root = project_root / root
    missing = [name for name in sorted(RUNTIME_PACKAGES)
               if not (root / "PYZ.pyz_extracted" / (name + ".pyc")).is_file()
               and not (root / "PYZ.pyz_extracted" / name).is_dir()]
    if missing:
        raise ValueError("Set CCZ_RUNTIME_ROOT to the extracted runtime. Missing: " + ", ".join(missing))
    return root.resolve()


def dependency_manifest(files, root):
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(files)}
