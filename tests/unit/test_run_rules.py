from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from ccz_randomizer.history import HistoryRepository
from ccz_randomizer.app import activate_rule_profile
from ccz_randomizer.rules.config import active_profile, default_rule_config, save_rule_config, validate_rule_config
from ccz_randomizer.workflow.history_lifecycle import HistoryLifecycle
from ccz_randomizer.workflow.run_rules import RUN_RULE_ENV, capture_run_rules, load_run_rules
from ccz_randomizer.runtime.concurrent import run_concurrent_workers


class RunRuleSnapshotTests(unittest.TestCase):
    def test_actual_parallel_scheduler_keeps_rules_and_all_53_archived_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "game"
            (game / "SV").mkdir(parents=True)
            executable = game / "Ekd5.exe"
            executable.write_bytes(b"game")
            (game / "SV/SV020.E5S").write_bytes(b"source")
            config = validate_rule_config(default_rule_config())
            expected = copy.deepcopy(active_profile(config))
            environment = {}
            capture_run_rules(config, environment)
            repository = HistoryRepository(root)
            owner = HistoryLifecycle(repository, "parallel")
            owner.start_run(mode="three", loop_random=True, rule_name=config["activeProfile"], rule=expected, build={})
            stop = root / "stop"
            fixture = json.loads((Path(__file__).parents[1] / "fixtures/personnel_220_1104/randomized-result.json").read_text(encoding="utf-8"))
            case = self

            class Process:
                def __init__(self, command, *, env, **kwargs):
                    self.returncode = 0
                    if stop.exists():
                        self.stdout = io.StringIO("")
                        self.returncode = 130
                        return
                    case.assertEqual(expected, active_profile(load_run_rules(root, env).config))
                    number, slot = int(env["CCZ_HISTORY_ROUND_NUMBER"]), int(env["CCZ_CONCURRENT_SLOT_LIST"])
                    source = Path(env["CCZ_GAME_EXE"]).parent / "SV" / f"SV{slot:03}.E5S"
                    source.write_bytes(f"transport-fixture-{number}-{slot}".encode())
                    snapshot = copy.deepcopy(fixture)
                    snapshot.update(slot=slot, acceptedAttempt=1, roundNumber=number)
                    snapshot["save"] = dict(path=str(source), sha256=hashlib.sha256(source.read_bytes()).hexdigest())
                    worker_repo = HistoryRepository(Path(env["CCZ_STATE_BASE_DIR"]))
                    worker = HistoryLifecycle(worker_repo, env["CCZ_HISTORY_RUN_ID"], owner=False)
                    worker_repo.save_result(worker.start_round(number), snapshot, save_path=source)
                    worker.finish_run("completed")
                    self.stdout = io.StringIO("游戏原生随机已触发: (0,)->(1,)\n"
                                             f"第 {slot} 号结果存档已通过游戏菜单保存\n")
                    # Simulate a settings edit while subsequent workers start.
                    changed = copy.deepcopy(config)
                    active_profile(changed)["threePerson"]["minJobAverage"] = 20
                    save_rule_config(root, changed)
                    if (number, slot) == (4, 8):
                        stop.touch()

                def poll(self):
                    return self.returncode

                def wait(self, timeout=None):
                    return self.returncode

                def terminate(self):
                    self.returncode = 130

                kill = terminate

            def sandbox(source, *, root, worker_name, save_names):
                target = root / worker_name
                (target / "SV").mkdir(parents=True)
                (target / "Ekd5.exe").write_bytes(b"game")
                (target / "SV/SV020.E5S").write_bytes(b"source")
                return target

            with patch.dict(os.environ, environment), \
                 patch("ccz_randomizer.runtime.concurrent.create_game_sandbox", side_effect=sandbox), \
                 patch("ccz_randomizer.runtime.concurrent.subprocess.Popen", side_effect=Process):
                self.assertEqual(0, run_concurrent_workers(history=owner, game_executable=executable,
                    result_count=15, mode="three", stop_file=stop, base_dir=root, worker_count=7, loop_random=True))
            rows = repository.list_rounds()
            self.assertEqual({1: 15, 2: 15, 3: 15, 4: 8}, {row["round_number"]: row["result_count"] for row in rows})
            archives = list((root / "randResult/loop").glob("*/round-*/SV/*.E5S"))
            self.assertEqual(53, len(archives))
            with closing(repository._connect()) as connection:
                backups = connection.execute("SELECT sha256,data FROM result_saves").fetchall()
                self.assertEqual(53, len(backups))
                self.assertEqual(sorted(hashlib.sha256(path.read_bytes()).hexdigest() for path in archives),
                                 sorted(row[0] for row in backups))
                self.assertTrue(all(hashlib.sha256(row[1]).hexdigest() == row[0] for row in backups))

    def test_switch_rules_between_normal_and_loop_runs_preserves_each_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = default_rule_config()
            original = config["activeProfile"]
            config["profiles"]["切换规则"] = copy.deepcopy(active_profile(config))
            config["profiles"]["切换规则"]["threePerson"]["qualifiedMembers"] = ["曹操"]
            config["profiles"]["切换规则"]["threePerson"]["minQualifiedCount"] = 1
            repository = HistoryRepository(root)
            fixture = json.loads((Path(__file__).parents[1] / "fixtures/personnel_220_1104/randomized-result.json").read_text(encoding="utf-8"))
            for index, (name, loop) in enumerate(((original, False), ("切换规则", False),
                                                  ("切换规则", True), (original, True))):
                config = activate_rule_profile(root, config, name)
                environment = {}
                selected = load_run_rules(root, environment).config
                expected = copy.deepcopy(active_profile(selected))
                capture_run_rules(selected, environment)
                owner = HistoryLifecycle(repository, f"run-{index}", expected_results=2)
                owner.start_run(mode="three", loop_random=loop, rule_name=name, rule=expected, build={})
                # Edit and switch the disk profile while slot workers are starting.
                changed = copy.deepcopy(config)
                changed["activeProfile"] = original if name != original else "切换规则"
                changed["profiles"][name]["threePerson"]["qualifiedMembers"] = ["夏侯惇", "曹操", "夏侯渊"]
                save_rule_config(root, changed)
                for number in range(1, 4 if loop else 2):
                    round_id = owner.start_round(number)
                    for slot in range(1, 3):
                        child_config = load_run_rules(root, dict(environment)).config
                        self.assertEqual(name, child_config["activeProfile"])
                        self.assertEqual(expected, active_profile(child_config))
                        child = HistoryLifecycle(HistoryRepository(root), owner.run_id, owner=False)
                        child.start_run(mode="three", loop_random=False, rule_name="不能覆盖", rule={}, build={})
                        snapshot = copy.deepcopy(fixture)
                        snapshot.update(slot=slot, acceptedAttempt=1, roundNumber=number)
                        child.repository.save_result(child.start_round(number), snapshot)
                        child.finish_run("completed")
                    owner.finish_round(round_id, "completed")
                owner.finish_run("completed")
                with closing(repository._connect()) as connection:
                    row = connection.execute("SELECT rule_name,rule_json,loop_random,status FROM runs WHERE id=?", (owner.run_id,)).fetchone()
                    self.assertEqual((name, expected, int(loop), "completed"),
                                     (row[0], json.loads(row[1]), row[2], row[3]))
                rows = [row for row in repository.list_rounds(rule_name=name) if row["run_id"] == owner.run_id]
                self.assertEqual(3 if loop else 1, len(rows))
                self.assertTrue(all(row["result_count"] == 2 for row in rows))

    def test_snapshot_is_independent_and_corruption_does_not_fall_back(self):
        with tempfile.TemporaryDirectory() as directory:
            config = validate_rule_config(default_rule_config())
            environment = {}
            capture_run_rules(config, environment)
            expected = copy.deepcopy(active_profile(config))
            config["profiles"][config["activeProfile"]]["threePerson"]["qualifiedMembers"] = ["曹操"]
            loaded = load_run_rules(Path(directory), environment)
            self.assertEqual(expected, active_profile(loaded.config))
            self.assertLess(len(environment[RUN_RULE_ENV]), 32000)
            environment[RUN_RULE_ENV] = "corrupt"
            with self.assertRaisesRegex(ValueError, "规则快照无效"):
                load_run_rules(Path(directory), environment)
