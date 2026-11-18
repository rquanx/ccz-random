"""Install the growth patch without overwriting the original backup."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
from zipfile import ZipFile

ORIGINAL_SHA256 = 'aece85339ff48c24e8d783d2d65766e8c9f7be00bd7389d38a8cad8f7cbd95a5'
PATCHED_SHA256 = '80e03aa0e57c870b94d51b361e588831190972efd00b533625a3969c66579990'
DLL_SHA256 = '9479df61fb18fcdec03c79ffe1a32fc4c661a7ab10e3954a586b5a01a870b21a'
PACKAGE_NAME = 'growth-fix.zip'


def backup_path(executable: Path) -> Path:
    return executable.with_name(executable.stem + '.peach-backup.exe')


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _stage(directory: Path, content: bytes) -> Path:
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix='.peach-', suffix='.tmp', delete=False) as file:
            name = Path(file.name)
            file.write(content)
        return name
    except BaseException:
        if name is not None:
            name.unlink(missing_ok=True)
        raise


def install_patch(executable: Path, package: Path) -> str:
    executable = Path(executable)
    backup = backup_path(executable)
    current = _digest(executable.read_bytes())
    if current == PATCHED_SHA256:
        raise ValueError('已经使用吃桃补丁，请勿重复安装。')
    if backup.exists():
        raise ValueError(f'已有备份 {backup.name}，请先还原，避免覆盖原 EXE。')
    with ZipFile(package) as archive:
        exe_data = archive.read('Ekd5.exe')
        dll_data = archive.read('CCZFX.DLL')
    if _digest(exe_data) != PATCHED_SHA256 or _digest(dll_data) != DLL_SHA256:
        raise ValueError('补丁文件校验失败，请重新获取工具。')
    dll = executable.parent / 'CCZFX.DLL'
    had_dll = dll.exists()
    if had_dll and _digest(dll.read_bytes()) != DLL_SHA256:
        raise ValueError('游戏目录已有其他 CCZFX.DLL，无法覆盖，请先确认已有补丁。')
    staged_exe = staged_dll = None
    renamed = installed_dll = False
    try:
        staged_exe = _stage(executable.parent, exe_data)
        staged_dll = _stage(executable.parent, dll_data)
        # rename (not replace) deliberately refuses an existing backup on Windows.
        executable.rename(backup)
        renamed = True
        os.replace(staged_dll, dll)
        installed_dll = True
        os.replace(staged_exe, executable)
    except BaseException:
        if renamed:
            os.replace(backup, executable)
        if installed_dll and not had_dll:
            dll.unlink(missing_ok=True)
        raise
    finally:
        for staged in (staged_exe, staged_dll):
            if staged is not None:
                staged.unlink(missing_ok=True)
    return f'吃桃补丁已启用，原 EXE 已备份为 {backup.name}。可点击“还原”回退。'


def restore_patch(executable: Path) -> str:
    executable = Path(executable)
    backup = backup_path(executable)
    if not backup.is_file():
        raise ValueError('没有可以还原的 EXE。')
    os.replace(backup, executable)
    # The original EXE does not import CCZFX.DLL. Keep the unused DLL so restoring
    # the EXE never risks deleting a component that another program may use.
    return '已还原原 EXE。'
