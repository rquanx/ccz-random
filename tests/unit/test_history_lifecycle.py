from __future__ import annotations

import sqlite3
import io
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from ccz_randomizer.history import HistoryRepository
from ccz_randomizer.workflow.history_lifecycle import HistoryLifecycle
from ccz_randomizer.runtime.concurrent import run_concurrent_workers


class HistoryLifecycleTests(unittest.TestCase):
    def test_stop_file_finalizes_partial_batch_as_stopped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = HistoryRepository(root)
            owner = HistoryLifecycle(repository, "run", expected_results=2)
            owner.start_run(mode="three", loop_random=False, rule_name="rule", rule={}, build={})
            stop = root / "stop"
            def scheduler(**options):
                round_id = options["history"].start_round(1)
                repository.save_result(round_id, dict(slot=1, acceptedAttempt=1))
                stop.touch()
                return 0
            with patch("ccz_randomizer.runtime.concurrent._run_concurrent_workers", side_effect=scheduler):
                self.assertEqual(0, run_concurrent_workers(history=owner, stop_file=stop))
            with closing(sqlite3.connect(repository.path)) as connection:
                self.assertEqual("stopped", connection.execute("SELECT status FROM runs").fetchone()[0])
                self.assertEqual("stopped", connection.execute("SELECT status FROM rounds").fetchone()[0])

    def test_scheduler_children_attach_to_parent_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "game"
            (game / "SV").mkdir(parents=True)
            executable = game / "Ekd5.exe"
            executable.write_bytes(b"game")
            (game / "SV" / "SV020.E5S").write_bytes(b"source")
            repository = HistoryRepository(root)
            owner = HistoryLifecycle(repository, "parent", expected_results=2)
            owner.start_run(mode="three", loop_random=False, rule_name="rule", rule={}, build={})
            case = self

            class Process:
                def __init__(self, command, *, env, **kwargs):
                    case.assertEqual("1", env["CCZ_HISTORY_MANAGED"])
                    child = HistoryRepository(Path(env["CCZ_STATE_BASE_DIR"]))
                    case.assertEqual(repository.path, child.path)
                    lifecycle = HistoryLifecycle(child, env["CCZ_HISTORY_RUN_ID"], owner=False)
                    round_id = lifecycle.start_round(int(env["CCZ_HISTORY_ROUND_NUMBER"]))
                    slot = int(env["CCZ_CONCURRENT_SLOT_LIST"])
                    child.save_result(round_id, dict(slot=slot, acceptedAttempt=1))
                    lifecycle.finish_run("completed")
                    (Path(env["CCZ_GAME_EXE"]).parent / "SV" / f"SV{slot:03}.E5S").write_bytes(b"saved")
                    self.stdout = io.StringIO(f"第 {slot} 号结果存档已通过游戏菜单保存\n")
                    self.returncode = 0

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
                (target / "SV" / "SV020.E5S").write_bytes(b"source")
                return target

            with patch("ccz_randomizer.runtime.concurrent.create_game_sandbox", side_effect=sandbox), \
                 patch("ccz_randomizer.runtime.concurrent.subprocess.Popen", side_effect=Process):
                self.assertEqual(0, run_concurrent_workers(history=owner, game_executable=executable,
                    result_count=2, mode="three", stop_file=None, base_dir=root, worker_count=2))
            self.assertEqual([1, 2], [row["slot"] for row in repository.get_round_results(owner.start_round(1))])
            with closing(sqlite3.connect(repository.path)) as connection:
                self.assertEqual("completed", connection.execute("SELECT status FROM runs").fetchone()[0])

    def test_interleaved_workers_preserve_four_rounds_and_partial_stop(self):
        # Actual incident: seven workers, three complete rounds and eight saves
        # in round four. Previous workers finished after the next round opened.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = HistoryRepository(root)
            owner = HistoryLifecycle(repository, "loop")
            metadata = dict(mode="three", loop_random=True, rule_name="rule", rule={}, build={})
            owner.start_run(**metadata)
            workers = [HistoryLifecycle(HistoryRepository(root), "loop", owner=False) for _ in range(7)]
            current = owner.start_round(1)
            for number, count in ((1, 15), (2, 15), (3, 15), (4, 8)):
                following = owner.start_round(number + 1)
                for slot in range(1, count + 1):
                    worker = workers[(slot - 1) % 7]
                    worker.start_run(**dict(metadata, loop_random=False))
                    self.assertEqual(current, worker.start_round(number))
                    worker.repository.save_result(current, dict(slot=slot, acceptedAttempt=1))
                    worker.finish_round(current, "completed")
                    worker.finish_run("completed")
                    # The following empty round must remain attachable.
                    self.assertEqual(following, worker.start_round(number + 1))
                if count == 15:
                    owner.finish_round(current, "completed")
                current = following
            owner.finish_run("stopped")
            with closing(sqlite3.connect(repository.path)) as connection:
                self.assertEqual((1, "stopped"), connection.execute(
                    "SELECT loop_random,status FROM runs WHERE id='loop'").fetchone())
                self.assertEqual([(1, "completed", 15), (2, "completed", 15),
                                  (3, "completed", 15), (4, "stopped", 8)],
                    connection.execute("SELECT round_number,status,count(results.id) FROM rounds "
                                       "JOIN results ON results.round_id=rounds.id "
                                       "GROUP BY rounds.id ORDER BY round_number").fetchall())
                self.assertEqual(4, connection.execute("SELECT count(*) FROM rounds").fetchone()[0])
                self.assertEqual([], connection.execute("PRAGMA foreign_key_check").fetchall())

    def test_worker_cannot_create_missing_round_or_reopen_finished_round(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = HistoryRepository(Path(directory))
            owner = HistoryLifecycle(repository, "run", expected_results=1)
            owner.start_run(mode="three", loop_random=False, rule_name="rule", rule={}, build={})
            worker = HistoryLifecycle(repository, "run", owner=False)
            with self.assertRaisesRegex(RuntimeError, "调度进程"):
                worker.start_round(1)
            round_id = owner.start_round(1)
            repository.save_result(round_id, dict(slot=1, acceptedAttempt=1))
            owner.finish_round(round_id, "completed")
            self.assertEqual(round_id, worker.start_round(1))
            worker.finish_round(round_id, "stopped")
            with closing(sqlite3.connect(repository.path)) as connection:
                self.assertEqual("completed", connection.execute("SELECT status FROM rounds").fetchone()[0])

    def test_scheduler_finalizes_after_worker_cleanup_on_all_exit_paths(self):
        for outcome in (0, 1, KeyboardInterrupt(), RuntimeError("worker failed")):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                repository = HistoryRepository(root)
                owner = HistoryLifecycle(repository, "run", expected_results=1)
                owner.start_run(mode="three", loop_random=False, rule_name="rule", rule={}, build={})
                def scheduler(**options):
                    round_id = options["history"].start_round(1)
                    repository.save_result(round_id, dict(slot=1, acceptedAttempt=1))
                    if isinstance(outcome, BaseException):
                        raise outcome
                    return outcome
                with patch("ccz_randomizer.runtime.concurrent._run_concurrent_workers", side_effect=scheduler):
                    options = dict(history=owner, stop_file=None)
                    if isinstance(outcome, BaseException):
                        with self.assertRaises(type(outcome)):
                            run_concurrent_workers(**options)
                    else:
                        self.assertEqual(outcome, run_concurrent_workers(**options))
                with closing(sqlite3.connect(repository.path)) as connection:
                    expected = "stopped" if isinstance(outcome, KeyboardInterrupt) else (
                        "completed" if outcome == 0 else "failed")
                    self.assertEqual(expected, connection.execute("SELECT status FROM runs").fetchone()[0])
                    self.assertEqual("completed", connection.execute("SELECT status FROM rounds").fetchone()[0])
