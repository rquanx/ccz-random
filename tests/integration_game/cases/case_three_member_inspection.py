from __future__ import annotations

import os
from pathlib import Path

import fast_randomizer as fast
from rule_config import active_profile, default_rule_config
from runtime_loader import install


def main() -> None:
    game_executable = Path(os.environ["CCZ_GAME_EXE"])
    install(fast.bundle_root())
    import task.CczReRandTask as task_module

    rules = default_rule_config()
    profile = active_profile(rules)
    profile["sevenPerson"]["lowMinSkillScore"] = 0.0
    profile["sevenPerson"]["mediumMinSkillScore"] = 0.0

    previous_accept_first = os.environ.get("CCZ_TEST_ACCEPT_FIRST")
    os.environ["CCZ_TEST_ACCEPT_FIRST"] = "1"
    try:
        with fast.HiddenGameSession(game_executable) as game:
            fast.patch_runtime(
                task_module,
                game.pid,
                three_person_mode=True,
                rules=rules,
            )
            runner = task_module.CczReRandTask(0)
            runner._target_save_pos = 1
            runner._source_loaded = False
            if not runner.run():
                raise RuntimeError(
                    f"初始三人流程未合格：{runner._result_outcome}"
                )
    finally:
        if previous_accept_first is None:
            os.environ.pop("CCZ_TEST_ACCEPT_FIRST", None)
        else:
            os.environ["CCZ_TEST_ACCEPT_FIRST"] = previous_accept_first

    if len(getattr(runner, "_member_panels", ())) != 3:
        raise RuntimeError("同一实例没有读取到完整初始三人能力面板")
    if tuple(member.name for member in runner._team_members) != (
        "曹操",
        "夏侯惇",
        "夏侯渊",
    ):
        raise RuntimeError("初始三人成员顺序不正确")
    if runner._result_outcome != "accepted":
        raise RuntimeError("初始三人合格结果状态不正确")
    print("初始三人同实例检查通过：" + "、".join(runner._job_names))


if __name__ == "__main__":
    raise SystemExit(main())
