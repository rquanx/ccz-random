"""Install the self-contained audio launcher beside the game executable."""
import hashlib
import os
from pathlib import Path
import tempfile

LAUNCHER_NAME = 'Ekd5-audio-fix.exe'
LAUNCHER_SHA256 = '5bb66f71f7641da63473f9cd730dfbc37886ac448657ae61e87fbc86da734b32'


def install_launcher(executable: Path, resource: Path) -> Path:
    executable = Path(executable)
    if not executable.is_file():
        raise ValueError('没有找到游戏 EXE，请将工具放到游戏目录后重试。')
    content = Path(resource).read_bytes()
    if hashlib.sha256(content).hexdigest() != LAUNCHER_SHA256:
        raise ValueError('音效卡顿补丁校验失败，请重新获取工具。')
    target = executable.parent / LAUNCHER_NAME
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() == LAUNCHER_SHA256:
            return target
        raise ValueError(f'目录中已有其他 {LAUNCHER_NAME}，请先保留并移走该文件后重试。')
    staged = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.audio-', suffix='.tmp', delete=False) as file:
            staged = Path(file.name)
            file.write(content)
        # Refuse a file created concurrently rather than replacing it.
        staged.rename(target)
        return target
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
