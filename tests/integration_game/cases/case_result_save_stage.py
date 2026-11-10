from __future__ import annotations

import hashlib
import os
from pathlib import Path

import fast_randomizer as fast


def run() -> None:
    target = Path(os.environ["CCZ_GAME_EXE"]).parent / "SV/SV015.E5S"
    captured: dict[str, object] = {}
    original_commit = fast.commit_qualified_result_save

    def capture_commit(runner, slot, path, *, candidate_save=None):
        result = original_commit(runner, slot, path, candidate_save=candidate_save)
        captured.update(slot=slot, path=path, content=path.read_bytes(), method=result[2])
        return result

    fast.commit_qualified_result_save = capture_commit
    os.environ.update(
        CCZ_AUTOSTART="1", CCZ_NO_PAUSE="1", CCZ_RANDOM_MODE="three",
        CCZ_LOOP_RANDOM="0", CCZ_RESULT_COUNT="1", CCZ_RESULT_SLOT_START="15",
        CCZ_TEST_ACCEPT_FIRST="1",
    )
    if fast.main() != 0:
        raise RuntimeError("当前随机流程失败")
    if captured.get("slot") != 15 or captured.get("path") != target:
        raise RuntimeError("结果未保存到指定的第15号槽位")
    if captured.get("method") != "game_menu":
        raise RuntimeError("当前随机结果未通过游戏菜单保存")
    content = captured.get("content")
    if not content or target.read_bytes() != content:
        raise RuntimeError("最终结果存档与游戏实际保存内容不一致")
    if content == (target.parent / "SV020.E5S").read_bytes():
        raise RuntimeError("结果存档仍为未随机的源存档")
    print(f"结果保存验证通过：size={len(content)}, sha256={hashlib.sha256(content).hexdigest()}")


if __name__ == "__main__":
    run()
