from __future__ import annotations

import json
import os
import shutil
import statistics
import time
from pathlib import Path

import fast_randomizer as fast


GAME = Path(os.environ["CCZ_GAME_EXE"])
ARTIFACT_DIR = Path(os.environ["CCZ_GAME_TEST_ARTIFACT_DIR"])
TOTAL_DELAYS_MS = tuple(
    int(value)
    for value in os.environ.get(
        "CCZ_STORY_BURST_DELAYS", "150,120,100,80"
    ).split(",")
    if value.strip()
)
ROUNDS_PER_DELAY = int(os.environ.get("CCZ_STORY_BURST_ROUNDS", "4"))
DOWN_DELAY_MS = int(os.environ.get("CCZ_STORY_BURST_DOWN_MS", "55"))
MAX_CLICKS = int(os.environ.get("CCZ_STORY_BURST_MAX_CLICKS", "80"))
USE_NATIVE_ACCELERATION = os.environ.get(
    "CCZ_STORY_NATIVE_ACCELERATION", "0"
) == "1"


def trigger_random(game: fast.HiddenGameSession) -> tuple[int, ...]:
    source_save = GAME.parent / "SV" / "SV020.E5S"
    if not fast.title_load_verified(
        game.pid,
        fast.SOURCE_TITLE_LIST_INDEX,
        source_save,
    ):
        raise RuntimeError("第20号源存档读取失败")
    fast.post_key_to_game(game.pid, "z")
    time.sleep(1.5)
    before = fast.read_job_ids(game.pid, fast.JOB_POSITIONS_R1)
    fast.native_silent_click(
        game.pid,
        game.main_window,
        fast.XU_CLIENT_POSITION[0],
        fast.XU_CLIENT_POSITION[1],
    )
    time.sleep(0.5)
    fast.native_silent_click(
        game.pid,
        game.main_window,
        fast.CONFIRM_FIRST_CLIENT_POSITION[0],
        fast.CONFIRM_FIRST_CLIENT_POSITION[1],
        tail_delay_ms=0,
    )
    deadline = time.perf_counter() + 3
    while time.perf_counter() < deadline:
        jobs = fast.read_job_ids(game.pid, fast.JOB_POSITIONS_R1)
        if jobs != before and any(jobs):
            return jobs
        time.sleep(0.025)
    raise RuntimeError("剧情连点测试未能触发随机")


def run_round(total_delay_ms: int) -> float:
    up_delay_ms = total_delay_ms - DOWN_DELAY_MS
    if up_delay_ms < 0:
        raise ValueError("总点击间隔不能小于按下时间")
    with fast.HiddenGameSession(GAME) as game:
        trigger_random(game)
        if USE_NATIVE_ACCELERATION:
            fast.enable_game_acceleration(game.pid)
        fast.trigger_seven_member_story(
            None,
            game.pid,
            game.main_window,
            click_strategy="story-burst-benchmark",
        )
        started = time.perf_counter()
        if USE_NATIVE_ACCELERATION:
            fast.wait_for_seven_member_scene(game.pid)
        else:
            fast.native_silent_click_burst(
                game.main_window,
                360,
                400,
                MAX_CLICKS,
                down_delay_ms=DOWN_DELAY_MS,
                up_delay_ms=up_delay_ms,
            )
        elapsed = time.perf_counter() - started
        fast.native_wake_game(game.pid, game.main_window, 500)
        time.sleep(0.5)
        if not fast.seven_member_scene_ready(game.pid):
            raise RuntimeError(
                f"剧情连点结束后七人场景未就绪：{total_delay_ms}ms"
            )
        return elapsed


def main() -> int:
    helper_target = GAME.parent / "RS" / "S_00.eex"
    shutil.copyfile(fast.bundled_random_s00(), helper_target)
    results: dict[str, object] = {
        "roundsPerDelay": ROUNDS_PER_DELAY,
        "downDelayMs": DOWN_DELAY_MS,
        "maxClicks": MAX_CLICKS,
        "nativeAcceleration": USE_NATIVE_ACCELERATION,
        "delays": {},
    }
    for total_delay_ms in TOTAL_DELAYS_MS:
        elapsed_values: list[float] = []
        failures: list[str] = []
        for round_index in range(1, ROUNDS_PER_DELAY + 1):
            try:
                elapsed = run_round(total_delay_ms)
            except Exception as exc:
                failures.append(repr(exc))
                print(
                    f"delay={total_delay_ms}ms "
                    f"round={round_index}/{ROUNDS_PER_DELAY} "
                    f"failed={exc!r}"
                )
                continue
            elapsed_values.append(elapsed)
            print(
                f"delay={total_delay_ms}ms "
                f"round={round_index}/{ROUNDS_PER_DELAY} "
                f"burst={elapsed:.3f}s"
            )
        results["delays"][str(total_delay_ms)] = {
            "successCount": len(elapsed_values),
            "failureCount": len(failures),
            "burstP50Seconds": (
                round(statistics.median(elapsed_values), 3)
                if elapsed_values
                else None
            ),
            "burstMinSeconds": (
                round(min(elapsed_values), 3) if elapsed_values else None
            ),
            "burstMaxSeconds": (
                round(max(elapsed_values), 3) if elapsed_values else None
            ),
            "failures": failures,
        }

    output = ARTIFACT_DIR / "benchmark.json"
    output.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))
    baseline = results["delays"].get("150")
    if baseline is not None and baseline["successCount"] != ROUNDS_PER_DELAY:
        raise RuntimeError("原始150ms对照组未全部成功")
    if not any(
        result["successCount"] == ROUNDS_PER_DELAY
        for result in results["delays"].values()
    ):
        raise RuntimeError("所有剧情连点参数均未达到连续成功门槛")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
