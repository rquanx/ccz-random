from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from ccz_randomizer.history import HistoryRepository
from ccz_randomizer.runtime.concurrent import run_concurrent_workers
from ccz_randomizer.statistics import StatisticsFilters, StatisticsRepository


def configure_environment(state_base: Path, run_id: str) -> None:
    os.environ.update(
        {
            "CCZ_HISTORY_SHARED": "1",
            "CCZ_HISTORY_RUN_ID": run_id,
            "CCZ_HISTORY_RULE_NAME": "统计并发真实测试",
            "CCZ_HISTORY_RULE_JSON": (
                '{"id":"statistics-concurrent-real-test",'
                '"schemaVersion":"test-v1"}'
            ),
            "CCZ_HISTORY_BUILD_JSON": '{"version":"test"}',
            "CCZ_TEST_ACCEPT_FIRST": "1",
            "CCZ_STATE_BASE_DIR": str(state_base),
        }
    )


def main() -> None:
    game_executable = Path(os.environ["CCZ_GAME_EXE"])
    state_base = Path(os.environ["CCZ_STATE_BASE_DIR"])
    run_id = "statistics-concurrent-real"
    configure_environment(state_base, run_id)

    result = run_concurrent_workers(
        game_executable=game_executable,
        result_count=2,
        mode="three",
        stop_file=None,
        base_dir=state_base,
        worker_count=2,
        loop_random=False,
    )
    if result != 0:
        raise RuntimeError(f"并发真实测试失败，退出码：{result}")

    repository = StatisticsRepository(state_base)
    final = repository.get_summary(StatisticsFilters())
    validation = repository.validate_statistics(StatisticsFilters())
    if final["save_count"] != 2 or final["accepted"] != 2:
        raise RuntimeError(f"并发最终统计数量不正确：{final}")
    if not validation.valid:
        raise RuntimeError(
            "并发统计校验失败：" + "；".join(validation.issues)
        )

    loop_run_id = "statistics-loop-real"
    configure_environment(state_base, loop_run_id)
    stop_file = state_base / "stop-loop-test"
    loop_result: list[int] = []

    def run_loop() -> None:
        loop_result.append(
            run_concurrent_workers(
                game_executable=game_executable,
                result_count=1,
                mode="three",
                stop_file=stop_file,
                base_dir=state_base,
                worker_count=2,
                loop_random=True,
            )
        )

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        if thread.is_alive():
            rounds = HistoryRepository(state_base).list_rounds(
                page=1,
                page_size=20,
            )
            completed = [
                row
                for row in rounds
                if str(row.get("run_id")) == loop_run_id
                and row.get("status") == "completed"
            ]
            if len(completed) >= 2:
                stop_file.touch()
                break
            time.sleep(0.5)
        else:
            break
    thread.join(timeout=60)
    stop_file.unlink(missing_ok=True)
    if thread.is_alive():
        raise RuntimeError("循环并发真实测试未能停止")
    if loop_result != [0]:
        raise RuntimeError(f"循环并发真实测试退出码不正确：{loop_result}")

    loop_rounds = [
        row
        for row in HistoryRepository(state_base).list_rounds(
            page=1,
            page_size=50,
        )
        if str(row.get("run_id")) == loop_run_id
    ]
    if len(
        [row for row in loop_rounds if row.get("status") == "completed"]
    ) < 2:
        raise RuntimeError(f"循环并发轮次不足：{loop_rounds}")
    loop_validation = StatisticsRepository(state_base).validate_statistics(
        StatisticsFilters()
    )
    if not loop_validation.valid:
        raise RuntimeError(
            "循环并发统计校验失败："
            + "；".join(loop_validation.issues)
        )
    print("统计模块真实并发和循环流程验证通过")


if __name__ == "__main__":
    main()
