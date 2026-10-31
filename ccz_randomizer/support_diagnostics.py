"""User initiated diagnostics and bounded log packaging."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import urllib.request
import uuid
import http.client
from urllib.parse import urlparse
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any


MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_FILE_BYTES = 1 * 1024 * 1024
UPLOAD_URL = "https://0x0.st"


class UploadCancelled(RuntimeError):
    pass


def _file_check(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        return {"label": label, "ok": False, "message": f"缺少 {path.name}。"}
    try:
        size = path.stat().st_size
    except OSError as exc:
        return {"label": label, "ok": False, "message": f"无法读取 {path.name}：{exc}"}
    return {"label": label, "ok": True, "message": f"{path.name} 可用（{size:,} 字节）。"}


def inspect_environment(
    game_executable: Path,
    *,
    app_root: Path,
    native_root: Path,
    bundle_root: Path,
    log_root: Path,
) -> list[dict[str, Any]]:
    """Run checks that do not start the game or modify game data."""
    checks = [_file_check(game_executable, "游戏程序")]
    checks.extend(
        _file_check(native_root / name, "运行组件")
        for name in ("ccz_injector.exe", "ccz_control.dll")
    )
    checks.append({
        "label": "工具组件",
        "ok": bundle_root.is_dir(),
        "message": "工具运行组件目录可用。" if bundle_root.is_dir() else "缺少工具运行组件目录。",
    })
    for directory, label in ((app_root, "工具目录"), (game_executable.parent, "游戏目录"), (log_root, "日志目录")):
        try:
            directory.mkdir(parents=True, exist_ok=True)
            descriptor, probe_name = tempfile.mkstemp(prefix=".ccz-support-", dir=directory)
            os.close(descriptor)
            probe = Path(probe_name)
            probe.unlink(missing_ok=True)
            checks.append({"label": label, "ok": True, "message": f"{label}可写。"})
        except OSError as exc:
            checks.append({"label": label, "ok": False, "message": f"{label}不可写：{exc}"})
    try:
        free = shutil.disk_usage(game_executable.parent).free
        checks.append({"label": "磁盘空间", "ok": free >= 100 * 1024 * 1024,
                       "message": f"游戏磁盘剩余约 {free // (1024 * 1024)} MB。"})
    except OSError as exc:
        checks.append({"label": "磁盘空间", "ok": False, "message": f"无法读取磁盘空间：{exc}"})
    return checks


def _bounded_copy(source: Path, target: Path) -> int:
    size = source.stat().st_size
    with source.open("rb") as handle:
        if size > MAX_FILE_BYTES:
            handle.seek(-MAX_FILE_BYTES, os.SEEK_END)
            data = "[文件过大，仅保留末尾内容]\n".encode("utf-8") + handle.read(MAX_FILE_BYTES)
        else:
            data = handle.read(MAX_FILE_BYTES)
    target.write_bytes(data)
    return len(data)


def create_log_archive(log_root: Path, *, extra: dict[str, Any] | None = None) -> Path:
    """Create a bounded archive containing recent logs and a diagnostic manifest."""
    candidates = sorted(
        (
            path for path in log_root.glob("*")
            if path.is_file() and not path.name.startswith("support_")
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = log_root / f"support_{stamp}.zip"
    total = 0
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        manifest = {"createdAt": datetime.now().isoformat(timespec="seconds"), "files": [], "extra": extra or {}}
        for source in candidates:
            if source == archive or total >= MAX_ARCHIVE_BYTES:
                continue
            with tempfile.NamedTemporaryFile(prefix="ccz-support-", delete=False) as handle:
                temp = Path(handle.name)
            try:
                size = _bounded_copy(source, temp)
                if total + size > MAX_ARCHIVE_BYTES:
                    continue
                bundle.write(temp, arcname=source.name)
                total += size
                manifest["files"].append({"name": source.name, "bytes": size})
            finally:
                temp.unlink(missing_ok=True)
        bundle.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return archive


def upload_log_archive(archive: Path, *, timeout: float = 30.0, cancel_event=None, progress_callback=None) -> str:
    """Upload only after an explicit user action; returns the provider URL."""
    boundary = f"----ccz-support-{uuid.uuid4().hex}".encode()
    payload = archive.read_bytes()
    body = b"--" + boundary + b"\r\n"
    body += b'Content-Disposition: form-data; name="file"; filename="support.zip"\r\n'
    body += b"Content-Type: application/zip\r\n\r\n" + payload
    body += b"\r\n--" + boundary + b"--\r\n"
    parsed = urlparse(UPLOAD_URL)
    connection = http.client.HTTPSConnection(parsed.netloc, timeout=timeout)
    try:
        connection.putrequest("POST", parsed.path or "/")
        connection.putheader("Content-Type", f"multipart/form-data; boundary={boundary.decode()}")
        connection.putheader("Content-Length", str(len(body)))
        connection.putheader("User-Agent", "CCZRandomizer-Support")
        connection.endheaders()
        sent = 0
        for offset in range(0, len(body), 64 * 1024):
            if cancel_event is not None and cancel_event.is_set():
                connection.close()
                raise UploadCancelled("用户取消了日志上传")
            chunk = body[offset:offset + 64 * 1024]
            connection.send(chunk)
            sent += len(chunk)
            if progress_callback is not None:
                progress_callback(sent, len(body))
        response = connection.getresponse()
        result = response.read().decode("utf-8", errors="replace").strip()
        if response.status >= 400:
            raise RuntimeError(f"日志服务返回 HTTP {response.status}：{result[:160]}")
    finally:
        connection.close()
    if not result.startswith(("http://", "https://")):
        raise RuntimeError(f"日志服务返回了无效地址：{result[:160]}")
    return result
