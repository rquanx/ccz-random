from __future__ import annotations

import hashlib
import os
from pathlib import Path

import fast_randomizer as fast


def run() -> None:
    game_executable = Path(os.environ["CCZ_GAME_EXE"])
    target = game_executable.parent / "SV" / "SV015.E5S"
    captured: dict[str, bytes] = {}
    original_publish = fast.publish_candidate_save

    def capture_publish(path: Path, content: bytes) -> None:
        captured["content"] = content
        captured["target"] = str(path).encode("utf-8")
        original_publish(path, content)

    fast.publish_candidate_save = capture_publish
    os.environ.update(
        {
            "CCZ_AUTOSTART": "1",
            "CCZ_NO_PAUSE": "1",
            "CCZ_RANDOM_MODE": "seven",
            "CCZ_LOOP_RANDOM": "0",
            "CCZ_RESULT_COUNT": "1",
            "CCZ_RESULT_SLOT_START": "15",
            "CCZ_TEST_ACCEPT_FIRST": "1",
        }
    )

    return_code = fast.main()
    if return_code != 0:
        raise RuntimeError(f"七人随机流程失败，退出码：{return_code}")
    candidate = captured.get("content")
    if candidate is None:
        raise RuntimeError("七人随机未发布初始场景候选存档")
    if captured.get("target", b"").decode("utf-8") != str(target):
        raise RuntimeError("七人随机发布到了错误的目标槽位")
    if not target.is_file():
        raise RuntimeError("七人随机完成后未生成第15号结果存档")
    if target.read_bytes() != candidate:
        raise RuntimeError("结果存档不是剧情推进前保存的候选存档")

    print(
        "七人结果存档阶段验证通过："
        f"size={len(candidate)}, "
        f"sha256={hashlib.sha256(candidate).hexdigest()}"
    )


if __name__ == "__main__":
    run()
