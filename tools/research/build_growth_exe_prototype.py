"""Create a full, independent game copy with the experimental EXE import patch."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

ORIGINAL_SHA256 = "aece85339ff48c24e8d783d2d65766e8c9f7be00bd7389d38a8cad8f7cbd95a5"
PATCHED_SHA256 = "80e03aa0e57c870b94d51b361e588831190972efd00b533625a3969c66579990"
IMPORT_NAME_OFFSET = 0x6B58


def build(source: Path, destination: Path, patch_dll: Path) -> dict:
    source, destination, patch_dll = source.resolve(), destination.resolve(), patch_dll.resolve()
    if destination.exists():
        raise FileExistsError(f"目标目录已存在，拒绝覆盖：{destination}")
    if destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError("源目录和目标目录不能相互包含")
    original = (source / "Ekd5.exe").read_bytes()
    if hashlib.sha256(original).hexdigest() != ORIGINAL_SHA256:
        raise ValueError("仅支持已验证的 2.20-1104 夜版原 EXE")
    if not patch_dll.is_file():
        raise FileNotFoundError("请先执行 native/build_growth_prototype.bat")
    modified = bytearray(original)
    if modified[IMPORT_NAME_OFFSET:IMPORT_NAME_OFFSET + 10] != b"PSAPI.DLL\0":
        raise ValueError("导入项与预期不一致")
    modified[IMPORT_NAME_OFFSET:IMPORT_NAME_OFFSET + 10] = b"CCZFX.DLL\0"
    if hashlib.sha256(modified).hexdigest() != PATCHED_SHA256:
        raise ValueError("修改后的 EXE 指纹与补丁 DLL 不匹配")
    # Deliberately copy everything, never use links into a player's game.
    shutil.copytree(source, destination)
    (destination / "Ekd5.original.exe").write_bytes(original)
    (destination / "Ekd5.exe").write_bytes(modified)
    shutil.copy2(patch_dll, destination / "CCZFX.DLL")
    manifest = {
        "source": str(source), "destination": str(destination),
        "originalExeSha256": ORIGINAL_SHA256, "patchedExeSha256": PATCHED_SHA256,
        "patchDllSha256": hashlib.sha256(patch_dll.read_bytes()).hexdigest(),
        "modifiedExeBytes": sum(a != b for a, b in zip(original, modified)),
        "experimental": True,
    }
    (destination / "growth-prototype-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--patch-dll", type=Path, default=Path(__file__).resolve().parents[2] / "native/CCZFX.DLL")
    args = parser.parse_args()
    result = build(args.source, args.destination, args.patch_dll)
    print(f"实验副本已生成：{result['destination']}。运行其中的 Ekd5.exe 进行测试。")


if __name__ == "__main__":
    main()
