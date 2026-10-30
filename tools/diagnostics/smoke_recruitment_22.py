"""Exercise real 2.2 randomization in a disposable game copy only."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from ccz_randomizer import app
from ccz_randomizer.rules.config import default_rule_config
from ccz_randomizer.runtime.game_sandbox import create_game_sandbox
from ccz_randomizer.recruitment import parse_recruits
from ccz_randomizer.recruitment_catalog import load_catalog, attach_recruitment
from ccz_randomizer.runtime.personnel_memory import read_personnel
from ccz_randomizer.runtime.skill_memory import ProcessMemoryReader
from ccz_randomizer.fixed_members import FIXED_MEMBER_INDICES
from ccz_randomizer.entry_catalog import attach_fixed_entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--all-rule-members", action="store_true")
    parser.add_argument("--rule-member", action="append")
    args = parser.parse_args()
    source = args.game_dir.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    protected = [source / "SV/SV020.E5S", source / "RS/S_00.EEX"]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    with tempfile.TemporaryDirectory(prefix="ccz-recruit-smoke-") as temp:
        sandbox = create_game_sandbox(source, root=Path(temp))
        os.environ.update(CCZ_GAME_EXE=str(sandbox / "Ekd5.exe"), CCZ_GAME_VERSION="2.2", CCZ_RANDOM_MODE="three")
        app.install(app.bundle_root())
        import task.CczReRandTask as task_module
        rules = default_rule_config()
        if args.all_rule_members:
            from ccz_randomizer.rule_members import RULE_MEMBER_NAMES
            rules["profiles"][rules["activeProfile"]]["threePerson"]["qualifiedMembers"] = list(RULE_MEMBER_NAMES)
        if args.rule_member:
            rules["profiles"][rules["activeProfile"]]["threePerson"].update(
                qualifiedMembers=args.rule_member, minQualifiedCount=1)
        rules["profiles"][rules["activeProfile"]]["skillQualification"]["threshold"] = 0
        rules["profiles"][rules["activeProfile"]]["threePerson"]["minJobAverage"] = 0
        rules["profiles"][rules["activeProfile"]]["sevenPerson"]["lowMinSkillScore"] = 0
        rules["profiles"][rules["activeProfile"]]["sevenPerson"]["mediumMinSkillScore"] = 0
        with app.HiddenGameSession(sandbox / "Ekd5.exe", announce=False) as game:
            app.patch_runtime(task_module, game.pid, three_person_mode=True, rules=rules)
            runner = task_module.CczReRandTask(0)
            runner._target_save_pos = 1
            runner._source_loaded = False
            assert runner.run(), "随机未通过诊断阈值"
            runner.collect_equipment()
            save = sandbox / "SV/SV001.E5S"
            assert save.is_file() and save.stat().st_size > 0, "随机结果未保存"
            snapshot = app.build_history_result_snapshot(runner, result_slot=1,
                accepted_attempt=1, round_number=1, equip_info=None, save_path=save)
            assert snapshot["equipment"]["categories"], "宝物信息未采集"
            assert app.result_detail_for_runner(runner, 1, 1)["equipment"] == snapshot["equipment"]
            rows = parse_recruits(snapshot)
            assert len(rows) == 116 and all(row.availability_verified for row in rows)
            assert len(snapshot["fixedPersonnel"]) == len(FIXED_MEMBER_INDICES)
            talent_previews = {row["name"]: row["personalTalents"] + row["jobTalents"]
                               for row in snapshot["personnel"] + snapshot["fixedPersonnel"]}
            for scored_member in snapshot["detail"]["skill"]["members"]:
                assert scored_member["skills"] == talent_previews[scored_member["name"]], f"{scored_member['name']} 特技筛选与保存后预览不一致"
            if args.all_rule_members:
                previews = {row["name"]: row["jobId"] for row in snapshot["personnel"] + snapshot["fixedPersonnel"]}
                scored = snapshot["detail"]["job"]["members"]
                assert {row["name"] for row in scored} == set(RULE_MEMBER_NAMES)
                assert all(row["job"] == app.JOB_MAP[previews[row["name"]]][0] for row in scored), "筛选兵种与保存后预览不一致"
            if args.rule_member:
                assert [row["name"] for row in snapshot["detail"]["job"]["members"]] == args.rule_member
                assert [row.split(":", 1)[0] for row in runner._r0_summaries] == args.rule_member
                assert [row["name"] for row in snapshot["detail"]["skill"]["members"]] == args.rule_member
                assert [row["name"] for row in snapshot["members"]] == args.rule_member
            (output / "result.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
            (output / "result.E5S").write_bytes(save.read_bytes())
            app.native_direct_load(game.pid, 1)
            runner.collect_equipment()
            assert app.result_detail_for_runner(runner, 1, 1)["equipment"] == snapshot["equipment"], "重读存档后宝物信息不一致"
            catalog = load_catalog()
            reads = {}
            class RecordingReader(ProcessMemoryReader):
                def read(self, address, size):
                    data = super().read(address, size)
                    reads[f"{address}:{size}"] = data.hex()
                    return data
            restored = attach_recruitment(read_personnel(game.pid,
                [person["recordIndex"] for person in catalog], planned=True,
                fixed_indices=[person["recordIndex"] for person in catalog if person["fixedConfiguration"]],
                reader_factory=RecordingReader), catalog)
            (output / "restored.json").write_text(json.dumps(restored, ensure_ascii=False, indent=2), encoding="utf-8")
            (output / "memory-reads.json").write_text(json.dumps(reads), encoding="utf-8")
            keys = ("recordIndex", "jobId", "jobTalents", "personalTalents")
            assert [{k: row[k] for k in keys} for row in restored] == [{k: row[k] for k in keys} for row in snapshot["personnel"]], "重读存档后候选数据不一致"
            fixed_restored = attach_fixed_entries(read_personnel(
                game.pid, FIXED_MEMBER_INDICES.values(), planned=True,
                reader_factory=RecordingReader,
            ))
            assert [{k: row[k] for k in keys} for row in fixed_restored] == [{k: row[k] for k in keys} for row in snapshot["fixedPersonnel"]], "重读存档后固定入队人物数据不一致"
            (output / "memory-reads.json").write_text(json.dumps(reads), encoding="utf-8")
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in before.items())
    print("PASS: 116 招募候选与 14 名固定入队人物、保存及回读一致；源存档和脚本未改变")


if __name__ == "__main__":
    main()
