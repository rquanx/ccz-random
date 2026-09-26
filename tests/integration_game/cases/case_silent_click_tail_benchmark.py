from __future__ import annotations

import json
import os
import statistics
import time
from pathlib import Path

import fast_randomizer as fast


GAME = Path(os.environ["CCZ_GAME_EXE"])
ARTIFACT_DIR = Path(os.environ["CCZ_GAME_TEST_ARTIFACT_DIR"])
TAIL_DELAYS_MS = tuple(
    int(value)
    for value in os.environ.get(
        "CCZ_TAIL_BENCHMARK_DELAYS", "0,300,600,900,1200"
    ).split(",")
    if value.strip()
)
ROUNDS_PER_DELAY = int(
    os.environ.get("CCZ_TAIL_BENCHMARK_ROUNDS", "4")
)


def reload_source(game: fast.HiddenGameSession) -> float:
    time.sleep(1.5)
    started = time.perf_counter()
    loaded = fast.direct_load_verified(
        game.pid,
        fast.SOURCE_TITLE_LIST_INDEX,
        GAME.parent / "SV" / "SV020.E5S",
    )
    if not loaded:
        raise RuntimeError("第20号源存档后台读取失败")
    jobs = fast.read_job_ids(game.pid, fast.JOB_POSITIONS_R1)
    if jobs != (0, 0, 0, 0, 0, 0, 0):
        raise RuntimeError(f"源存档兵种状态异常：{jobs}")
    time.sleep(1.2)
    return time.perf_counter() - started


def trigger_with_timed_choice(
    game: fast.HiddenGameSession,
    tail_delay_ms: int,
) -> tuple[tuple[int, ...], float]:
    before = fast.read_job_ids(game.pid, fast.JOB_POSITIONS_R1)
    started = time.perf_counter()
    fast.run_native_control(
        game.pid,
        [
            "silent-click",
            str(game.main_window),
            str(fast.XU_CLIENT_POSITION[0]),
            str(fast.XU_CLIENT_POSITION[1]),
        ],
    )
    time.sleep(0.5)
    fast.run_native_control(
        game.pid,
        [
            "silent-click-timed",
            str(game.main_window),
            str(fast.CONFIRM_FIRST_CLIENT_POSITION[0]),
            str(fast.CONFIRM_FIRST_CLIENT_POSITION[1]),
            str(tail_delay_ms),
        ],
    )
    deadline = time.perf_counter() + 3
    while time.perf_counter() < deadline:
        jobs = fast.read_job_ids(game.pid, fast.JOB_POSITIONS_R1)
        if jobs != before and any(jobs):
            return jobs, time.perf_counter() - started
        time.sleep(0.025)
    raise RuntimeError(
        f"缩短第二次点击尾部等待后未触发随机："
        f"tail={tail_delay_ms}ms"
    )


def percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    return ordered[int((len(ordered) - 1) * ratio)]


def main() -> int:
    results: dict[str, object] = {
        "roundsPerDelay": ROUNDS_PER_DELAY,
        "baselineInteractionP50Seconds": 3.705,
        "baselineInteractionP95Seconds": 4.075,
        "tailDelays": {},
    }
    with fast.HiddenGameSession(GAME) as game:
        time.sleep(2)
        if not fast.title_load_verified(
            game.pid,
            fast.SOURCE_TITLE_LIST_INDEX,
            GAME.parent / "SV" / "SV020.E5S",
        ):
            raise RuntimeError("首次读取第20号源存档失败")

        for tail_delay_ms in TAIL_DELAYS_MS:
            load_times: list[float] = []
            interaction_times: list[float] = []
            failures: list[str] = []
            for round_index in range(1, ROUNDS_PER_DELAY + 1):
                load_times.append(reload_source(game))
                try:
                    jobs, elapsed = trigger_with_timed_choice(
                        game, tail_delay_ms
                    )
                except Exception as exc:
                    failures.append(repr(exc))
                    print(
                        f"tail={tail_delay_ms}ms round={round_index}/"
                        f"{ROUNDS_PER_DELAY} failed={exc!r}"
                    )
                    continue
                interaction_times.append(elapsed)
                print(
                    f"tail={tail_delay_ms}ms round={round_index}/"
                    f"{ROUNDS_PER_DELAY} interaction={elapsed:.3f}s "
                    f"jobs={jobs}"
                )
            results["tailDelays"][str(tail_delay_ms)] = {
                "successCount": len(interaction_times),
                "failureCount": len(failures),
                "loadP50Seconds": round(
                    statistics.median(load_times), 3
                ),
                "interactionP50Seconds": (
                    round(statistics.median(interaction_times), 3)
                    if interaction_times
                    else None
                ),
                "interactionP95Seconds": (
                    round(percentile(interaction_times, 0.95), 3)
                    if interaction_times
                    else None
                ),
                "failures": failures,
            }

    output = ARTIFACT_DIR / "benchmark.json"
    output.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if not any(
        result["successCount"] == ROUNDS_PER_DELAY
        for result in results["tailDelays"].values()
    ):
        raise RuntimeError("所有第二次点击尾部等待参数均未达到连续成功门槛")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
