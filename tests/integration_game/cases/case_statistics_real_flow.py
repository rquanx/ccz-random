from __future__ import annotations

import json
import os
from pathlib import Path

import fast_randomizer as fast
from ccz_randomizer.statistics import StatisticsFilters, StatisticsRepository


def run_mode(mode: str, slot: int, state_base: Path) -> None:
    os.environ.update(
        {
            "CCZ_AUTOSTART": "1",
            "CCZ_NO_PAUSE": "1",
            "CCZ_RANDOM_MODE": mode,
            "CCZ_LOOP_RANDOM": "0",
            "CCZ_RESULT_COUNT": "1",
            "CCZ_RESULT_SLOT_START": str(slot),
            "CCZ_TEST_ACCEPT_FIRST": "1",
            "CCZ_STATE_BASE_DIR": str(state_base),
        }
    )
    return_code = fast.main()
    if return_code != 0:
        raise RuntimeError(f"{mode} 模式真实随机失败，退出码：{return_code}")


def main() -> None:
    state_base = Path(os.environ["CCZ_STATE_BASE_DIR"])
    run_mode("three", 14, state_base)
    run_mode("seven", 15, state_base)

    repository = StatisticsRepository(state_base)
    final = repository.get_summary(StatisticsFilters())
    completed = repository.get_summary(
        StatisticsFilters(metric="completed")
    )
    attempts = repository.get_summary(
        StatisticsFilters(metric="attempts")
    )
    validation = repository.validate_statistics(StatisticsFilters())
    details = repository.get_detail_rows(StatisticsFilters())
    if final["save_count"] != 2 or final["accepted"] != 2:
        raise RuntimeError(f"真实结果统计数量不正确：{final}")
    if completed["completed_count"] != 2 or attempts["attempt_count"] < 2:
        raise RuntimeError(
            f"真实完成/尝试统计数量不正确：{completed}/{attempts}"
        )
    if not validation.valid:
        raise RuntimeError(
            "真实结果统计校验失败：" + "；".join(validation.issues)
        )
    modes = {str(row.get("mode") or "") for row in details}
    if modes != {"three", "seven"}:
        raise RuntimeError(f"真实统计未同时记录 3 人和 7 人：{modes}")

    (state_base / "statistics-real-summary.json").write_text(
        json.dumps(
            {
                "final": final,
                "completed": completed,
                "attempts": attempts,
                "validation": validation.__dict__,
                "modes": sorted(modes),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("统计模块真实三人/七人流程验证通过")


if __name__ == "__main__":
    main()
