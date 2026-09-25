from __future__ import annotations

import json
import os
import re
from difflib import SequenceMatcher
from pathlib import Path


EQUIP_NAMES = (
    "倚天剑", "雌雄双剑", "青釭剑", "古锭刀", "青龙偃月刀",
    "丈八蛇矛", "方天画戟", "龙胆枪", "李广之弓", "吕布之弓",
    "龙渊剑", "流星锤", "双鞭", "霸王枪", "青冥剑",
    "开山斧", "双戟", "龙骑枪", "金火罐车", "白羽扇",
    "五火神焰扇", "芭蕉扇", "圣者宝剑", "七星剑", "镜铠",
    "黄金铠", "白银铠", "龙鳞铠", "连环铠", "霸王乌金甲",
    "蚩尤战甲", "兽面吞云铠", "亮银甲", "青云羽衣", "短打劲装",
    "凤凰羽衣", "飞龙斗袍", "青龙战袍", "天仙洞衣", "鹤氅",
    "国士无双袍", "漆黑道袍", "名士华服", "虎豹嘶风铠", "上将铠",
    "贯日袍", "白银盾", "风神盾", "淮南子", "风车轮",
    "诸葛巾", "精铁盔", "的卢", "绝影", "赤兔",
    "爪黄飞电", "照夜玉狮子", "飞刀", "孟德新书", "六韬",
    "三略", "太平清领书", "遁甲天书", "孙子兵法", "青囊书",
    "玉玺", "青龙宝玉", "朱雀宝玉", "玄武宝玉", "白虎宝玉",
)


def records(save: bytes) -> list[bytes]:
    result = [
        save[0x54D8 + index * 4 : 0x54DC + index * 4]
        for index in range(46)
    ]
    result.extend(
        save[0x5590 + index * 8 : 0x5598 + index * 8]
        for index in range(24)
    )
    return result


def clean(text: str) -> str:
    return re.sub(r"\s+", "", text).replace("→", "-")


def split_pair(text: str) -> tuple[str, str] | None:
    for separator in ("：", ":"):
        if separator in text:
            left, right = text.split(separator, 1)
            return clean(left), clean(right)
    return None


def closest_name(source: str) -> tuple[str, float]:
    candidates = EQUIP_NAMES
    return max(
        (
            (name, SequenceMatcher(None, source, name).ratio())
            for name in candidates
        ),
        key=lambda pair: pair[1],
    )


def slot_one_effects(root: Path) -> dict[str, str]:
    data = json.loads((root / "equip_slot001_ocr.json").read_text("utf-8"))
    return {
        EQUIP_NAMES[int(index) - 1]: clean(entry["effect"])
        for index, entry in data.items()
    }


def reference_effects(root: Path, slot: int) -> dict[str, str]:
    path = root / f"ref_{slot:02}_equip_ocr.json"
    lines = json.loads(path.read_text("utf-8"))
    result: dict[str, tuple[str, float]] = {}
    for line in lines:
        pair = split_pair(line["text"])
        if pair is None:
            continue
        source_name, effect = pair
        if not effect or source_name in {
            "剑", "佩剑", "刀", "枪", "弓", "炮车", "扇", "法剑",
            "铠甲", "衣服", "辅助",
        }:
            continue
        name, similarity = closest_name(source_name)
        if similarity < 0.5:
            continue
        previous = result.get(name)
        confidence = similarity * float(line["score"])
        if previous is None or confidence > previous[1]:
            result[name] = (clean(effect), confidence)
    return {name: pair[0] for name, pair in result.items()}


def main() -> int:
    root = Path(__file__).resolve().parent
    game_root = Path(os.environ["CCZ_GAME_ROOT"])
    save_root = game_root / "SV"
    observations = []
    for slot in range(1, 16):
        save = (save_root / f"SV{slot:03}.E5S").read_bytes()
        effects = (
            slot_one_effects(root)
            if slot == 1
            else reference_effects(root, slot)
        )
        raw_records = records(save)
        missing = [name for name in EQUIP_NAMES if name not in effects]
        print(
            f"slot={slot:02} effects={len(effects)} "
            f"missing={','.join(missing)}"
        )
        for index, (name, raw) in enumerate(
            zip(EQUIP_NAMES, raw_records, strict=True), 1
        ):
            effect = effects.get(name)
            if effect:
                observations.append(
                    {
                        "slot": slot,
                        "index": index,
                        "name": name,
                        "record": raw.hex(),
                        "bytes": list(raw),
                        "effect": effect,
                    }
                )
    (root / "equip_ground_truth.json").write_text(
        json.dumps(observations, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"observations={len(observations)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
