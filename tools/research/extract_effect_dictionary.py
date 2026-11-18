"""Freeze version-specific independent skill help, never randomized item help.

Usage: python tools/research/extract_effect_dictionary.py <game-directory>
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROFILE_ID = "ccz-v2.20-1104-night"
EXPECTED_HELP_SHA256 = "a29c01b83cbc5b1bc9a1f0f071b9f9480a91f7673ce50b618d91de5a932941f9"
EXPECTED_EXECUTABLE_SHA256 = "aece85339ff48c24e8d783d2d65766e8c9f7be00bd7389d38a8cad8f7cbd95a5"
# Empty, placeholder, or non-mechanical help in this version.
UNVERIFIED = {3, 4, 5, 36, *range(73, 81), 103, 211}


def catalog_hash(skills):
    data = [skills["runtimeCatalog"], skills["displayRules"]["equipment"]["effects"]]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def extract(game_directory: Path):
    profile = ROOT / "resources/data/profiles" / PROFILE_ID
    skills = json.loads((profile / "skills.json").read_text("utf-8"))
    raw = (game_directory / "Imsg.e5").read_bytes()
    if len(raw) != 450000 or hashlib.sha256(raw).hexdigest() != EXPECTED_HELP_SHA256:
        raise ValueError("不是已核对的 2.20-1104 夜版说明表")
    entries = []
    for skill in skills["runtimeCatalog"]:
        skill_id = skill["id"]
        record = 430 + skill_id
        description = raw[record * 200:(record + 1) * 200].split(b"\0", 1)[0].decode("gbk").strip()
        # The table uses CRCRLF in several records; retain paragraphs without blank-line inflation.
        description = "\n\n".join(line.strip() for line in description.splitlines() if line.strip())
        entries.append({"id": skill_id, "name": skill["name"], "baseName": skill["baseName"],
                        "record": record, "description": description if skill_id not in UNVERIFIED else ""})
    # Independent anchors verified against the game help and current runtime catalogue.
    anchors = {24: "连续攻击范围内的另一个敌人", 57: "取最高的一项能力值", 178: "110%"}
    for skill_id, expected in anchors.items():
        if expected not in entries[skill_id]["description"]:
            raise ValueError("说明表与已核对版本不匹配")
    updates = (game_directory / "更新说明.txt").read_bytes()
    statement = "1.穿越移动→穿越偷袭=穿越移动+偷袭攻击。"
    if statement not in updates.decode("utf-8-sig"):
        raise ValueError("更新说明缺少已核对的特效定义")
    if hashlib.sha256((game_directory / "Ekd5.exe").read_bytes()).hexdigest() != EXPECTED_EXECUTABLE_SHA256:
        raise ValueError("游戏程序与已核对的原始宝物配置不匹配")
    equipment = json.loads((Path(__file__).parent / "data/equipment_effects_1104.json").read_text("utf-8"))
    if equipment.keys() != skills["displayRules"]["equipment"]["effects"].keys():
        raise ValueError("宝物特效说明未完整覆盖当前特效编号")
    evidence = []
    for code, entry in equipment.items():
        if not entry["description"].strip():
            raise ValueError("宝物特效说明为空")
        for observation in entry.get("originalItems", []):
            record = bytes.fromhex(observation["bytes"])
            observed_code = record[17] if record[20] == 2 else record[20]
            if len(record) != 25 or observed_code != int(code):
                raise ValueError("原始宝物特效编号不一致")
            index = observation["record"]
            help_text = raw[index * 200:(index + 1) * 200].split(b"\0", 1)[0].decode("gbk")
            if "效果" not in help_text:
                raise ValueError("原始宝物说明记录不匹配")
            evidence.append(observation)
    data = {"profileId": PROFILE_ID, "gameVersion": "2.20-1104-night",
            "catalogHash": catalog_hash(skills),
            "source": {"file": "Imsg.e5", "sha256": hashlib.sha256(raw).hexdigest(),
                       "recordSize": 200, "firstSkillRecord": 430},
            "updatesSource": {"file": "更新说明.txt", "sha256": hashlib.sha256(updates).hexdigest(),
                              "statement": statement},
            "equipment": equipment,
            "equipmentSource": {"executableSha256": EXPECTED_EXECUTABLE_SHA256,
                "itemTableAddress": "0x4A1140", "recordSize": 25, "descriptionIndexBase": 1946,
                "itemEvidenceSha256": hashlib.sha256(json.dumps(evidence, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()},
            "skills": entries}
    target = profile / "effect_dictionary.json"
    previous = json.loads(target.read_text("utf-8"))
    data['schemaVersion'] = 1
    data['mergeRules'] = previous['mergeRules']
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path = profile / 'manifest.json'
    manifest = json.loads(manifest_path.read_text('utf-8'))
    manifest['files']['effectDictionary'] = target.name
    manifest['sha256'][target.name] = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game_directory", type=Path)
    extract(parser.parse_args().game_directory)
