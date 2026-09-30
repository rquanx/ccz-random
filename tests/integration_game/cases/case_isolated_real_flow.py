from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import fast_randomizer as fast
from tools.diagnostics.trace_original_flow import read_absolute
from runtime_loader import install
from full_randomizer_normal_load import trigger_random


GAME = Path(
    os.environ.get(
        "CCZ_GAME_EXE",
        r"E:\game\ccz\曹操传加强版V2.10.4c"
        r"\曹操传加强版V2.10.4c\Ekd5.exe",
    )
)


def main() -> None:
    run_test()


def run_test() -> None:
    source_save = GAME.parent / "SV" / "SV020.E5S"
    with fast.HiddenGameSession(GAME) as game:
        if not fast.title_load_verified(
            game.pid,
            fast.SOURCE_TITLE_LIST_INDEX,
            source_save,
        ):
            raise RuntimeError("独立桌面读取第20号源存档失败")
        before = fast.read_job_ids(game.pid, fast.JOB_POSITIONS_R0)
        print(f"loaded jobs={before}")
        after = trigger_random(
            game.pid,
            game.main_window,
            fast.JOB_POSITIONS_R0,
        )
        print(f"random jobs={after}")
        if after == before or not any(after):
            raise RuntimeError("独立桌面点击未触发真实随机")


if __name__ == "__main__":
    main()
