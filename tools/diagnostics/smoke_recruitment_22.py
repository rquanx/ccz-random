"""Exercise supported game randomization in a disposable game copy only."""
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
from ccz_randomizer.fixed_members import fixed_member_indices
from ccz_randomizer.game_versions import activate_game_version
from ccz_randomizer.entry_catalog import attach_fixed_entries



def diagnostic_rules(version, *, all_members=False, members=None, image_members=None):
    from ccz_randomizer.rule_members import rule_member_indices
    rules = default_rule_config()
    profile = rules["profiles"][rules["activeProfile"]]
    # Explicitly exercise collection and an active skill gate, regardless of
    # product defaults. A custom image tests its automatic collection dependency.
    profile["dataCollection"].update(recruitment=not bool(image_members), jobTalents=True, allRandomPersonnel=True)
    profile["skillQualification"].update(mode="count", threshold=0, requiredCount=1)
    profile["threePerson"].update(minJobAverage=0, minQualifiedCount=1)
    if all_members:
        profile["threePerson"]["qualifiedMembers"] = list(rule_member_indices(version))
    if members:
        profile["threePerson"]["qualifiedMembers"] = list(members)
    if image_members:
        profile["resultImage"] = {"mode": "custom", "members": list(image_members)}
    profile["sevenPerson"].update(lowMinSkillScore=0, mediumMinSkillScore=0)
    return rules


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--all-rule-members", action="store_true")
    parser.add_argument("--rule-member", action="append")
    parser.add_argument("--image-member", action="append")
    args = parser.parse_args()
    source = args.game_dir.resolve()
    version = activate_game_version(source / "Ekd5.exe")
    fixed_indices = fixed_member_indices(version)
    expected_count = len(load_catalog(version=version))
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    protected = [source / "SV/SV020.E5S", source / "RS/S_00.EEX"]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    with tempfile.TemporaryDirectory(prefix="ccz-recruit-smoke-") as temp:
        sandbox = create_game_sandbox(source, root=Path(temp))
        os.environ.update(CCZ_GAME_EXE=str(sandbox / "Ekd5.exe"), CCZ_GAME_VERSION=version, CCZ_RANDOM_MODE="three")
        app.install(app.bundle_root())
        import task.CczReRandTask as task_module
        rules = diagnostic_rules(version, all_members=args.all_rule_members,
                                 members=args.rule_member, image_members=args.image_member)
        from ccz_randomizer.rule_members import rule_member_indices
        RULE_MEMBER_NAMES = tuple(rule_member_indices(version))
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
            (output / "result.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
            (output / "result.E5S").write_bytes(save.read_bytes())
            assert snapshot["equipment"]["categories"], "宝物信息未采集"
            assert app.result_detail_for_runner(runner, 1, 1)["equipment"] == snapshot["equipment"]
            if args.image_member:
                from ccz_randomizer.ui.result_image import report_members
                assert [row["name"] for row in report_members(runner)] == args.image_member
            rows = parse_recruits(snapshot)
            assert len(rows) == expected_count and all(row.availability_verified for row in rows)
            assert len(snapshot["fixedPersonnel"]) == len(fixed_indices)
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
            app.native_direct_load(game.pid, 1)
            runner.collect_equipment()
            assert app.result_detail_for_runner(runner, 1, 1)["equipment"] == snapshot["equipment"], "重读存档后宝物信息不一致"
            from ccz_randomizer.runtime.job_talents import read_job_talents
            assert read_job_talents(game.pid) == snapshot["jobTalents"], "重读存档后兵种天赋目录不一致"
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
                game.pid, fixed_indices.values(), planned=True,
                reader_factory=RecordingReader,
            ))
            assert [{k: row[k] for k in keys} for row in fixed_restored] == [{k: row[k] for k in keys} for row in snapshot["fixedPersonnel"]], "重读存档后固定入队人物数据不一致"
            (output / "memory-reads.json").write_text(json.dumps(reads), encoding="utf-8")
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in before.items())
    print(f"PASS: {version} 的 {expected_count} 名招募候选与 {len(fixed_indices)} 名固定入队人物、保存及回读一致；源存档和脚本未改变")


if __name__ == "__main__":
    main()
