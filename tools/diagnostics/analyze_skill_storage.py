from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ccz_randomizer.app import TEAM_MEMBER_NUM, bundle_root
from ccz_randomizer.diagnostics.skill_storage import (
    SkillObservation,
    load_numbered_saves,
    read_legacy_records,
    stable_direct_offsets,
)
from ccz_randomizer.runtime.loader import install
from tools.project_paths import SKILL_DATA_DIR


DETAIL_TOP = 98
MEMBER_PANEL_SIZE = 130
SKILL_ROW_HEIGHT = 14
SKILL_ROW_STEP = 16
SKILL_ROW_TOP = 17
SKILL_PANEL_X = 2
SKILL_TEXT_X = 1
MATCH_THRESHOLD = 0.07


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="离线对比结果图中的特技与存档原始数据",
    )
    parser.add_argument("--save-dir", required=True, type=Path)
    parser.add_argument("--panel-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def read_skill_names() -> dict[int, str]:
    path = SKILL_DATA_DIR / "skill_dump_ascii.json"
    if not path.is_file():
        return {}
    return {
        int(item["id"]): item["name"]
        for item in json.loads(path.read_text(encoding="utf-8"))
    }


def recognize_panels(panel_dir: Path):
    import cv2
    import numpy as np
    from models.CczModels import CCZ_MODELS

    observations = []
    details = {}
    for panel_path in sorted(panel_dir.glob("save*.png")):
        try:
            save_number = int(panel_path.stem.removeprefix("save"))
        except ValueError:
            continue
        image = cv2.imdecode(
            np.fromfile(str(panel_path), dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )
        if image is None:
            continue
        members = []
        for member_index in range(TEAM_MEMBER_NUM):
            top = DETAIL_TOP + member_index * MEMBER_PANEL_SIZE
            panel = image[
                top : top + MEMBER_PANEL_SIZE,
                SKILL_PANEL_X : SKILL_PANEL_X + MEMBER_PANEL_SIZE,
            ]
            slots = []
            for slot_index in range(6):
                row_top = SKILL_ROW_TOP + slot_index * SKILL_ROW_STEP
                # getAllSkillMat starts one pixel before getSkillMatList.
                # The composed report therefore contains 129/130 columns.
                row = panel[
                    row_top : row_top + SKILL_ROW_HEIGHT,
                    SKILL_TEXT_X:MEMBER_PANEL_SIZE,
                ]
                candidates = []
                for model_id, skill in enumerate(CCZ_MODELS.skills):
                    template = skill.mat[:, : row.shape[1]]
                    score = float(
                        cv2.matchTemplate(
                            template,
                            row,
                            cv2.TM_SQDIFF_NORMED,
                        )[0, 0]
                    )
                    candidates.append((score, model_id))
                score, model_id = min(candidates)
                confidence = max(0.0, 1.0 - score)
                accepted = score < MATCH_THRESHOLD
                slots.append(
                    {
                        "model_id": model_id if accepted else None,
                        "distance": round(score, 6),
                        "confidence": round(confidence, 6),
                    }
                )
                if accepted:
                    observations.append(
                        SkillObservation(
                            save_number=save_number,
                            member_index=member_index,
                            slot_index=slot_index,
                            model_id=model_id,
                            confidence=confidence,
                        )
                    )
            members.append(slots)
        details[save_number] = members
    return observations, details


def main() -> int:
    args = parse_args()
    save_dir = args.save_dir.resolve()
    panel_dir = args.panel_dir.resolve()
    output = args.output.resolve()
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    install(bundle_root())

    observations, panel_details = recognize_panels(panel_dir)
    save_numbers = sorted(panel_details)
    saves = load_numbered_saves(save_dir, save_numbers)
    names = read_skill_names()

    direct_offsets = {}
    for value_size in (1, 2, 4):
        candidates = stable_direct_offsets(
            saves,
            observations,
            value_size=value_size,
        )
        direct_offsets[str(value_size)] = {
            f"member_{member + 1}_slot_{slot + 1}": [
                f"0x{offset:X}" for offset in offsets
            ]
            for (member, slot), offsets in candidates.items()
        }

    recognized = []
    for observation in observations:
        recognized.append(
            {
                "save": observation.save_number,
                "member": observation.member_index + 1,
                "slot": observation.slot_index + 1,
                "model_id": observation.model_id,
                "name": names.get(observation.model_id, ""),
                "confidence": round(observation.confidence, 6),
            }
        )

    legacy_samples = {
        str(number): read_legacy_records(data)[:6]
        for number, data in saves.items()
    }
    has_direct_offset = any(
        offsets
        for by_slot in direct_offsets.values()
        for offsets in by_slot.values()
    )
    report = {
        "save_count": len(saves),
        "panel_count": len(panel_details),
        "recognized_skill_count": len(observations),
        "recognition_threshold": MATCH_THRESHOLD,
        "recognized": recognized,
        "panel_details": panel_details,
        "stable_direct_offsets": direct_offsets,
        "legacy_0x6800_first_six_records": legacy_samples,
        "conclusion": (
            "发现稳定的直接编号偏移，需要逐项复核。"
            if has_direct_offset
            else "未发现把界面特技编号以 uint8/uint16/uint32 原值稳定保存的偏移；"
            "0x6800 不能按七人六特技直接解析。下一步需要配对采集剧情推进前后内存，"
            "定位游戏渲染阶段生成或解码后的结构。"
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"报告已生成：{output}")
    print(report["conclusion"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
