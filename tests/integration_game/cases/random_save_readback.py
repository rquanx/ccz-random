"""Exercise the actual adapter, then restart and compare all saved personnel."""
import os
from pathlib import Path
from types import SimpleNamespace

from tools.diagnostics.benchmark_random_22 import run_benchmark


def run(*, turbo, skip_first_npc=False):
    result = run_benchmark(SimpleNamespace(
        game_dir=Path(os.environ["CCZ_GAME_DIR"]),
        output=Path(os.environ["CCZ_GAME_TEST_ARTIFACT_DIR"]) / "random-readback.json",
        attempts=3, turbo=turbo, save_results=True, skip_first_npc=skip_first_npc,
    ))
    if not result["saved_results_verified"] or len(result["rolls"]) != 3:
        raise RuntimeError("必须完成三轮实际筛选、保存及重启读回")
    expected_fast_loads = 2 if turbo and not skip_first_npc else 0
    if result['fast_menu_loads'] != expected_fast_loads:
        raise RuntimeError('实际极速读档次数与当前策略及回退状态不一致')
