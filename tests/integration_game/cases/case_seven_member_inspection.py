from __future__ import annotations

import json
import os
from pathlib import Path

import fast_randomizer as fast


def main() -> None:
    game_executable = Path(os.environ["CCZ_GAME_EXE"])
    artifact_dir = Path(os.environ["CCZ_GAME_TEST_ARTIFACT_DIR"])
    output_dir = artifact_dir / "inspection"
    save_path = game_executable.parent / "SV" / "SV001.E5S"
    if not save_path.is_file():
        raise FileNotFoundError("七人检查测试需要第 1 号结果存档")

    fast.inspect_saved_slot(
        game_executable,
        1,
        output_dir,
        7.5,
    )
    result = json.loads(
        (output_dir / "inspection.json").read_text(encoding="utf-8")
    )
    expected_count = fast.TEAM_MEMBER_NUM
    for field in ("job_names", "skills", "panels"):
        values = result.get(field)
        if not isinstance(values, list) or len(values) != expected_count:
            raise RuntimeError(
                f"七人检查结果字段不完整：{field}={values!r}"
            )
    missing_panels = [
        panel
        for panel in result["panels"]
        if not Path(panel).is_file()
    ]
    if missing_panels:
        raise RuntimeError(f"七人能力面板缺失：{missing_panels}")
    print(
        "七人候选检查通过："
        + "、".join(result["job_names"])
    )


if __name__ == "__main__":
    main()
