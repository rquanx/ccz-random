from __future__ import annotations

import importlib.abc
import importlib.util
import marshal
import os
import sys
from pathlib import Path


APP_PACKAGES = {
    "PIL",
    "cfg",
    "encrypt",
    "keyboard",
    "models",
    "pydirectinput",
    "task",
    "utils",
    "win32con",
    "window",
}


class ExtractedPycLoader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self, pyz_root: Path, binary_root: Path):
        self.pyz_root = pyz_root
        self.binary_root = binary_root

    def find_spec(self, fullname: str, path=None, target=None):
        if fullname.split(".", 1)[0] not in APP_PACKAGES:
            return None

        pyc_path = self.pyz_root.joinpath(*fullname.split(".")).with_suffix(".pyc")
        package_path = self.pyz_root.joinpath(*fullname.split("."))
        package_init = package_path / "__init__.pyc"
        if package_init.exists():
            return importlib.util.spec_from_loader(fullname, self, is_package=True)
        if pyc_path.exists():
            is_package = package_path.is_dir() or pyc_path.stat().st_size == 16
            return importlib.util.spec_from_loader(fullname, self, is_package=is_package)
        if package_path.is_dir():
            return importlib.util.spec_from_loader(fullname, self, is_package=True)
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module) -> None:
        parts = module.__name__.split(".")
        pyc_path = self.pyz_root.joinpath(*parts).with_suffix(".pyc")
        package_path = self.pyz_root.joinpath(*parts)
        if package_path.is_dir():
            paths = [str(package_path)]
            binary_package = self.binary_root.joinpath(*parts)
            if binary_package.is_dir():
                paths.append(str(binary_package))
            module.__path__ = paths
        code_path = package_path / "__init__.pyc"
        if not code_path.exists():
            code_path = pyc_path
        if code_path.exists() and code_path.stat().st_size > 16:
            code = marshal.loads(code_path.read_bytes()[16:])
            exec(code, module.__dict__)


def install(extracted_root: Path) -> None:
    extracted_root = extracted_root.resolve()
    pyz_root = extracted_root / "PYZ.pyz_extracted"

    # Import the local wheels before exposing the extracted application tree.
    import cv2  # noqa: F401
    import numpy  # noqa: F401

    for folder in (
        extracted_root / "win32",
        extracted_root / "pythonwin",
        extracted_root,
    ):
        sys.path.append(str(folder))
    os.add_dll_directory(str(extracted_root / "pywin32_system32"))
    sys.meta_path.insert(0, ExtractedPycLoader(pyz_root, extracted_root))
    os.chdir(extracted_root)
