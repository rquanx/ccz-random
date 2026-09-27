from __future__ import annotations

import json
import os
import time
from pathlib import Path

import fast_randomizer as fast
from runtime_loader import install
from tests.integration_game.cases.full_randomizer_normal_load import (
    trigger_random,
)


def main() -> None:
    game_executable = Path(os.environ["CCZ_GAME_EXE"])
    artifact_dir = Path(os.environ["CCZ_GAME_TEST_ARTIFACT_DIR"])
    output_dir = artifact_dir / "inspection"
    source_save = game_executable.parent / "SV" / "SV020.E5S"
    if not source_save.is_file():
        raise FileNotFoundError("七人检查测试需要第 20 号源存档")

    install(fast.bundle_root())
    import task.CczReRandTask as task_module

    candidate_slot = 16
    with fast.HiddenGameSession(game_executable) as game:
        fast.patch_runtime(task_module, game.pid)
        if not fast.title_load_verified(
            game.pid,
            fast.SOURCE_TITLE_LIST_INDEX,
            source_save,
        ):
            raise RuntimeError("标题界面读取第20号存档失败")
        time.sleep(1.5)
        trigger_random(game.pid, game.main_window, fast.JOB_POSITIONS_R1)
        time.sleep(2.0)
        fast.native_direct_save(game.pid, candidate_slot - 1)

    fast.inspect_saved_slot(
        game_executable,
        candidate_slot,
        output_dir,
        7.5,
    )
    result = json.loads(
        (output_dir / "inspection.json").read_text(encoding="utf-8")
    )
    expected_count = fast.TEAM_MEMBER_NUM
    for field in ("job_names", "skills", "panels"):
        values = result.get(field)
        if not isinstance(values, list) or len(values) != expected_count:
            raise RuntimeError(
                f"七人检查结果字段不完整：{field}={values!r}"
            )
    missing_panels = [
        panel
        for panel in result["panels"]
        if not Path(panel).is_file()
    ]
    if missing_panels:
        raise RuntimeError(f"七人能力面板缺失：{missing_panels}")
    print(
        "七人候选检查通过："
        + "、".join(result["job_names"])
    )


if __name__ == "__main__":
    main()
