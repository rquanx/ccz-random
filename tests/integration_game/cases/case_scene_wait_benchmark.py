from __future__ import annotations

import json
import os
import statistics
import time
from pathlib import Path

import fast_randomizer as fast


GAME = Path(os.environ["CCZ_GAME_EXE"])
ARTIFACT_DIR = Path(os.environ["CCZ_GAME_TEST_ARTIFACT_DIR"])
DELAYS_MS = (0, 300, 600, 900, 1200, 1500)
ROUNDS_PER_DELAY = int(os.environ.get("CCZ_SCENE_WAIT_ROUNDS", "3"))
BENCHMARK_AXIS = os.environ.get("CCZ_SCENE_WAIT_AXIS", "both")
BENCHMARK_DELAYS = tuple(
    int(value)
    for value in os.environ.get(
        "CCZ_SCENE_WAIT_DELAYS", ",".join(map(str, DELAYS_MS))
    ).split(",")
    if value.strip()
)


def trigger_random(game: fast.HiddenGameSession) -> float:
    before = fast.read_job_ids(game.pid, fast.JOB_POSITIONS_R1)
    started = time.perf_counter()
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
            return time.perf_counter() - started
        time.sleep(0.025)
    raise RuntimeError("场景等待测试未触发随机")


def run_candidate(
    game: fast.HiddenGameSession,
    *,
    pre_delay_ms: int,
    post_delay_ms: int,
) -> tuple[float, float]:
    time.sleep(pre_delay_ms / 1000)
    load_started = time.perf_counter()
    if not fast.direct_load_verified(
        game.pid,
        fast.SOURCE_TITLE_LIST_INDEX,
        GAME.parent / "SV" / "SV020.E5S",
    ):
        raise RuntimeError("第20号源存档后台读取失败")
    load_elapsed = time.perf_counter() - load_started
    jobs = fast.read_job_ids(game.pid, fast.JOB_POSITIONS_R1)
    if jobs != (0, 0, 0, 0, 0, 0, 0):
        raise RuntimeError(f"源存档兵种状态异常：{jobs}")
    time.sleep(post_delay_ms / 1000)
    return load_elapsed, trigger_random(game)


def run_axis(
    game: fast.HiddenGameSession,
    *,
    axis: str,
    candidates: tuple[int, ...],
    fixed_delay_ms: int,
) -> dict[str, object]:
    output: dict[str, object] = {}
    for delay_ms in candidates:
        loads: list[float] = []
        interactions: list[float] = []
        failures: list[str] = []
        for round_index in range(1, ROUNDS_PER_DELAY + 1):
            pre_delay_ms = delay_ms if axis == "pre" else fixed_delay_ms
            post_delay_ms = delay_ms if axis == "post" else fixed_delay_ms
            try:
                load_elapsed, interaction_elapsed = run_candidate(
                    game,
                    pre_delay_ms=pre_delay_ms,
                    post_delay_ms=post_delay_ms,
                )
            except Exception as exc:
                failures.append(repr(exc))
                print(
                    f"{axis}={delay_ms}ms round={round_index}/"
                    f"{ROUNDS_PER_DELAY} failed={exc!r}"
                )
                continue
            loads.append(load_elapsed)
            interactions.append(interaction_elapsed)
            print(
                f"{axis}={delay_ms}ms round={round_index}/"
                f"{ROUNDS_PER_DELAY} load={load_elapsed:.3f}s "
                f"interaction={interaction_elapsed:.3f}s"
            )
        output[str(delay_ms)] = {
            "successCount": len(interactions),
            "failureCount": len(failures),
            "loadP50Seconds": (
                round(statistics.median(loads), 3) if loads else None
            ),
            "interactionP50Seconds": (
                round(statistics.median(interactions), 3)
                if interactions
                else None
            ),
            "failures": failures,
        }
    return output


def main() -> int:
    with fast.HiddenGameSession(GAME) as game:
        time.sleep(2)
        if not fast.title_load_verified(
            game.pid,
            fast.SOURCE_TITLE_LIST_INDEX,
            GAME.parent / "SV" / "SV020.E5S",
        ):
            raise RuntimeError("首次读取第20号源存档失败")
        results: dict[str, object] = {
            "roundsPerDelay": ROUNDS_PER_DELAY,
        }
        if BENCHMARK_AXIS in {"both", "post"}:
            results["postLoadDelay"] = run_axis(
                game,
                axis="post",
                candidates=tuple(
                    value for value in BENCHMARK_DELAYS if value <= 1200
                ),
                fixed_delay_ms=1500,
            )
        if BENCHMARK_AXIS in {"both", "pre"}:
            results["preLoadDelay"] = run_axis(
                game,
                axis="pre",
                candidates=BENCHMARK_DELAYS,
                fixed_delay_ms=1200,
            )

    output = ARTIFACT_DIR / "benchmark.json"
    output.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if BENCHMARK_AXIS == "both":
        controls = (
            results["postLoadDelay"]["1200"],
            results["preLoadDelay"]["1500"],
        )
        if any(
            item["successCount"] != ROUNDS_PER_DELAY
            for item in controls
        ):
            raise RuntimeError("场景等待基准的原值对照组未全部成功")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
