from __future__ import annotations

import os
import shutil
from pathlib import Path

import fast_randomizer as fast
from runtime_loader import install


def main() -> None:
    game_executable = Path(os.environ["CCZ_GAME_EXE"])
    source_save = game_executable.parent / "SV" / "SV020.E5S"
    if not source_save.is_file():
        raise FileNotFoundError("七人检查测试需要第 20 号源存档")
    helper_target = game_executable.parent / "RS" / "S_00.eex"
    shutil.copyfile(fast.bundled_random_s00(), helper_target)

    install(fast.bundle_root())
    import task.CczReRandTask as task_module

    previous_accept_first = os.environ.get("CCZ_TEST_ACCEPT_FIRST")
    os.environ["CCZ_TEST_ACCEPT_FIRST"] = "1"
    try:
        with fast.HiddenGameSession(game_executable) as game:
            fast.patch_runtime(task_module, game.pid)
            runner = task_module.CczReRandTask(0)
            runner._target_save_pos = 16
            runner._source_loaded = False
            runner.run()
    finally:
        if previous_accept_first is None:
            os.environ.pop("CCZ_TEST_ACCEPT_FIRST", None)
        else:
            os.environ["CCZ_TEST_ACCEPT_FIRST"] = previous_accept_first

    expected_count = fast.TEAM_MEMBER_NUM
    if len(getattr(runner, "_member_panels", ())) != expected_count:
        raise RuntimeError("同一实例没有读取到完整七人能力面板")
    if len(getattr(runner, "_team_members", ())) != expected_count:
        raise RuntimeError("同一实例没有读取到完整七人特技")
    print(
        "七人候选检查通过："
        + "、".join(runner._job_names)
    )


if __name__ == "__main__":
    artifact_dir = Path(os.environ["CCZ_GAME_TEST_ARTIFACT_DIR"])
    os.environ["CCZ_INSPECTION_LOG_PATH"] = str(
        artifact_dir / "inspection.log"
    )
    os.environ["CCZ_INSPECTION_DIAGNOSTIC_PATH"] = str(
        artifact_dir / "inspection_diagnostic.jsonl"
    )
    raise SystemExit(
        fast.run_inspection_cli_with_diagnostics(
            "seven-member-integration",
            lambda: (main(), 0)[1],
        )
    )
