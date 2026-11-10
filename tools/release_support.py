"""Read-only release target validation, also usable by the Windows builder."""
import argparse
import hashlib
import json
from pathlib import Path


def validate_game_directory(directory: Path, profiles_root: Path):
    manifest = json.loads((profiles_root / "manifest.json").read_text(encoding="utf-8"))
    fingerprints = json.loads((profiles_root / manifest["files"]["fingerprints"]).read_text(encoding="utf-8"))
    expected = fingerprints[manifest.get("fingerprintVersion", manifest["gameVersion"])]
    for name, digest in expected.items():
        if digest is None:
            continue  # Scripts modified by normal gameplay are not stable fingerprints.
        path = directory / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"游戏目录与发布数据包不匹配：{name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("game_directory", type=Path)
    args = parser.parse_args()
    validate_game_directory(args.game_directory, Path(__file__).resolve().parents[1] /
                            "resources/data/profiles/ccz-v2.20-1104-night")
