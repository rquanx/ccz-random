from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path

import fast_randomizer as fast


GAME = Path(
    r"E:\game\ccz\曹操传加强版V2.10.4c"
    r"\曹操传加强版V2.10.4c\Ekd5.exe"
)
TEST_SAVE = Path(
    os.environ.get(
        "CCZ_TEST_SAVE",
        r"C:\Users\91658\Downloads\SV020.E5S",
    )
)


def trigger_random(pid: int, hwnd: int) -> tuple[int, ...]:
    before = fast.read_job_ids(pid, fast.JOB_POSITIONS_R1)
    fast.run_native_control(
        pid,
        [
            "silent-click",
            str(hwnd),
            str(fast.XU_CLIENT_POSITION[0]),
            str(fast.XU_CLIENT_POSITION[1]),
        ],
    )
    time.sleep(0.5)
    fast.run_native_control(
        pid,
        [
            "silent-click",
            str(hwnd),
            str(fast.CONFIRM_FIRST_CLIENT_POSITION[0]),
            str(fast.CONFIRM_FIRST_CLIENT_POSITION[1]),
        ],
    )
    deadline = time.perf_counter() + 4
    while time.perf_counter() < deadline:
        current = fast.read_job_ids(pid, fast.JOB_POSITIONS_R1)
        if current != before and any(current):
            return current
        time.sleep(0.05)
    raise RuntimeError(f"许子将随机未触发，兵种仍为 {before}")


def main() -> int:
    game_save = GAME.parent / "SV" / "SV020.E5S"
    backup_dir = Path(tempfile.mkdtemp(prefix="ccz-sv020-backup-"))
    backup_save = backup_dir / "SV020.E5S"
    original_exists = game_save.is_file()
    if original_exists:
        shutil.copy2(game_save, backup_save)

    try:
        shutil.copy2(TEST_SAVE, game_save)
        for attempt in range(1, 6):
            with fast.HiddenGameSession(GAME) as game:
                time.sleep(1.5)
                if not fast.title_load_verified(
                    game.pid,
                    fast.SOURCE_TITLE_LIST_INDEX,
                    game_save,
                ):
                    raise RuntimeError(
                        f"第 {attempt} 次标题界面读取第 20 号存档失败"
                    )
                time.sleep(1.5)
                before = fast.read_job_ids(
                    game.pid, fast.JOB_POSITIONS_R1
                )
                if before != (0, 0, 0, 0, 0, 0, 0):
                    raise RuntimeError(
                        f"第 {attempt} 轮随机前兵种异常：{before}"
                    )
                after = trigger_random(game.pid, game.main_window)
                print(f"第 {attempt} 轮触发成功：{before}->{after}")
        return 0
    finally:
        if original_exists:
            shutil.copy2(backup_save, game_save)
        else:
            game_save.unlink(missing_ok=True)
        shutil.rmtree(backup_dir, ignore_errors=True)
        print("原第 20 号存档已恢复")


if __name__ == "__main__":
    raise SystemExit(main())
