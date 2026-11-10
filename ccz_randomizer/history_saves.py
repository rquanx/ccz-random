"""Read verified save copies and publish exports without partial files."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile


def verified_save(path: Path, expected_hash: str) -> tuple[bytes, str]:
    data = path.read_bytes()
    if not data:
        raise ValueError("存档文件为空，无法备份")
    digest = hashlib.sha256(data).hexdigest()
    if not expected_hash or digest != expected_hash:
        raise ValueError("原存档已变化或缺少校验信息，无法确认属于这条历史记录")
    return data, digest


def export_save(destination: Path, data: bytes, expected_hash: str) -> None:
    if not data or hashlib.sha256(data).hexdigest() != expected_hash:
        raise ValueError("历史存档副本校验失败，未导出文件")
    if destination.suffix.lower() != ".e5s":
        raise ValueError("请选择 .E5S 存档文件")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".ccz-export-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
