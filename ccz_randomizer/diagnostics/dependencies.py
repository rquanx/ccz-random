"""Read-only native dependency checks, isolated from the GUI and game runtime."""
from __future__ import annotations

import ctypes
import importlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import sysconfig
import tempfile


VC_DOCUMENTATION = "https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist"
VC_DOWNLOADS = {arch: f"https://aka.ms/vc14/vc_redist.{arch}.exe"
                for arch in ("x86", "x64", "arm64")}
# win32ui.pyd in the supplied runtime imports MFC and the v14 CRT.
VC_LIBRARIES = ("mfc140u.dll", "VCRUNTIME140.dll", "VCRUNTIME140_1.dll", "MSVCP140.dll")


def system_information() -> dict:
    version = sys.getwindowsversion() if sys.platform == "win32" else None
    native_arch = os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROCESSOR_ARCHITECTURE") or platform.machine()
    names = {"amd64": "x64", "x86_64": "x64", "x86": "x86", "arm64": "arm64", "aarch64": "arm64"}
    process_arch = {"win-amd64": "x64", "win32": "x86", "win-arm64": "arm64"}.get(sysconfig.get_platform(), "unknown")
    name = "Windows"
    if version is not None:
        if version.product_type != 1:
            name = "Windows Server"
        elif version.major >= 10:
            name = "Windows 11" if version.build >= 22000 else "Windows 10"
        else:
            name = {(6, 1): "Windows 7", (6, 2): "Windows 8", (6, 3): "Windows 8.1"}.get((version.major, version.minor), "Windows")
    return dict(name=name, major=version.major if version else 0,
                version=".".join(map(str, (version.major, version.minor, version.build))) if version else platform.platform(),
                os_arch=names.get(native_arch.lower(), native_arch), tool_arch=process_arch)


def dependency_guidance(error: str, system: dict) -> dict:
    """Do not turn an ambiguous DLL error into a definite missing-CRT diagnosis."""
    lower = error.casefold()
    if system["major"] < 10:
        return dict(message="当前工具及最新版 VC++ 运行库不支持此系统，请使用 Windows 10/11 或 Windows Server 2016 及以上系统。安装运行库不能解决系统版本不兼容。",
                    downloads=[dict(label="微软运行库系统要求", url=VC_DOCUMENTATION)])
    if "193" in lower or "not a valid win32" in lower or "不是有效的 win32" in lower:
        return dict(message="组件架构与工具不匹配，请重新下载完整的对应架构工具；安装运行库无法修复架构错误。", downloads=[])
    if "no module named" in lower or "组件文件不存在" in lower:
        return dict(message="工具组件缺失，请重新下载并完整解压工具，检查安全软件是否隔离了组件；无需另行安装 Python 或 pywin32。", downloads=[])
    if any(name in lower for name in ("dll load failed", "mfc140", "vcruntime140", "msvcp140", "api-ms-win-crt")):
        arch = system["tool_arch"]
        downloads = ([dict(label=f"微软 VC++ {arch} 运行库", url=VC_DOWNLOADS[arch])]
                     if arch in VC_DOWNLOADS else [dict(label="微软运行库下载说明", url=VC_DOCUMENTATION)])
        return dict(message="可能缺少或损坏 Microsoft Visual C++ v14（含 MFC）运行库。请下载下方微软官方安装包，手动安装或选择“修复”，按安装提示重启后重新检测。若仍失败，请检查工具组件是否完整并上报日志。",
                    downloads=downloads)
    return dict(message="组件无法正常加载，请重新下载完整工具；若仍失败，请上报日志。", downloads=[])


def _load_component(name: str, bundle: Path) -> None:
    if name == "win32ui":
        path = bundle / "pythonwin" / "win32ui.pyd"
        if not path.is_file():
            raise ModuleNotFoundError("win32ui 组件文件不存在")
        # Check the actual bundled extension, not an unrelated installed pywin32.
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    else:
        importlib.import_module(name)


def probe_runtime(bundle: Path) -> list[dict]:
    """Called only in the dedicated child process; never starts the game."""
    system = system_information()
    supported = system["major"] >= 10 and system["tool_arch"] in VC_DOWNLOADS
    checks = [dict(label="系统环境", ok=supported,
                   message=f"{system.get('name', 'Windows')} {system['version']}（系统 {system['os_arch']}，工具 {system['tool_arch']}）。")]
    if not supported:
        if system["major"] < 10:
            checks[0].update(dependency_guidance("", system))
        else:
            checks[0].update(message="无法确认当前工具架构，请上报日志；请勿随意安装不匹配的运行库。",
                             downloads=[dict(label="微软运行库下载说明", url=VC_DOCUMENTATION)])
        return checks
    handles = []
    try:
        for directory in (bundle, bundle / "pywin32_system32", bundle / "pythonwin", bundle / "win32"):
            if directory.is_dir():
                handles.append(os.add_dll_directory(str(directory.resolve())))
        for library in VC_LIBRARIES:
            try:
                ctypes.WinDLL(library)
                checks.append(dict(label=library, ok=True, message="运行库可以正常加载。"))
            except OSError as error:
                checks.append(dict(label=library, ok=False, detail=str(error),
                                   **dependency_guidance(f"{library}: {error}", system)))
        for name in ("win32ui", "numpy", "cv2"):
            try:
                _load_component(name, bundle)
                checks.append(dict(label=name, ok=True, message="组件可以正常加载。"))
            except Exception as error:
                text = f"{type(error).__name__}: {error}"
                checks.append(dict(label=name, ok=False, detail=text,
                                   **dependency_guidance(text, system)))
    finally:
        for handle in reversed(handles):
            handle.close()
    return checks


def inspect_runtime_dependencies(command: list[str], bundle: Path) -> list[dict]:
    """Use a result file so frozen windowed builds do not need stdout."""
    try:
        with tempfile.TemporaryDirectory(prefix="ccz-dependency-check-") as directory:
            result = Path(directory) / "result.json"
            completed = subprocess.run(
                [*command, "--diagnose-runtime", str(result)], capture_output=True,
                timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                env=dict(os.environ, CCZ_RUNTIME_ROOT=str(bundle.resolve())),
            )
            if completed.returncode != 0 or not result.is_file():
                raise RuntimeError("依赖检测子进程未能完成，请上报日志检查工具完整性。")
            if result.stat().st_size > 128 * 1024:
                raise ValueError("依赖检测结果过大")
            checks = json.loads(result.read_text(encoding="utf-8"))
            if not isinstance(checks, list) or not checks or any(
                not isinstance(row, dict) or not isinstance(row.get("ok"), bool)
                or not isinstance(row.get("label"), str) or not isinstance(row.get("message"), str)
                for row in checks
            ):
                raise ValueError("依赖检测结果无效")
            return checks
    except Exception as error:
        return [dict(label="依赖检测", ok=False, message=f"未能完成依赖检测：{error}。请重新检测或上报日志。")]


def format_checks(checks: list[dict]) -> list[str]:
    lines = []
    for check in checks:
        lines.append(("通过  " if check["ok"] else "异常  ") + check["label"] + "：" + check["message"])
        if check.get("detail"):
            lines.append("  加载错误：" + check["detail"])
    return lines


def official_downloads(checks: list[dict]) -> list[dict]:
    allowed = {VC_DOCUMENTATION, *VC_DOWNLOADS.values()}
    urls = {}
    for check in checks:
        for download in check.get("downloads", []):
            if isinstance(download, dict) and download.get("url") in allowed:
                urls[download["url"]] = download
    return list(urls.values())
