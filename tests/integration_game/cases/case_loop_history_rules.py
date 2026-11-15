"""Run the production scheduler and workers in an isolated copy/private desktop."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import shutil
import subprocess
import sys
import time
from contextlib import closing

from ccz_randomizer import app
from ccz_randomizer.rules.config import active_profile, default_rule_config, save_rule_config
from ccz_randomizer.runtime import concurrent
from tests.helpers.desktop import background_desktop


def worker():
    # Redirect application state/output only. Actual randomization, menu saves,
    # result handling and history writes all use the production implementation.
    app.app_dir = lambda: Path(os.environ["CCZ_GAME_DIR"])
    concurrent._worker_command = lambda: [sys.executable, str(Path(__file__).resolve()), "--worker"]
    return app.main()


def run():
    game = Path(os.environ["CCZ_GAME_DIR"])
    output = Path(os.environ["CCZ_GAME_TEST_ARTIFACT_DIR"])
    database = Path(os.environ["CCZ_STATE_BASE_DIR"]) / "ccz_fast_data/history.sqlite3"
    executable = os.environ.get("CCZ_HISTORY_TEST_EXECUTABLE")
    command = [sys.executable, str(Path(__file__).resolve()), "--worker"]
    if executable:
        packaged = game / "history-test.exe"
        shutil.copy2(executable, packaged)
        command = [str(packaged), "--worker"]
    config = default_rule_config()
    template = copy.deepcopy(active_profile(config))
    template.update(builtin=False, editorMode="advanced")
    template["threePerson"].update(jobQualificationMode="none", minQualifiedCount=1)
    template["skillQualification"]["mode"] = "none"
    template["resultImage"]["mode"] = "selected"
    config["profiles"] = {"联动规则A": copy.deepcopy(template), "联动规则B": copy.deepcopy(template)}
    config["profiles"]["联动规则B"]["threePerson"]["qualifiedMembers"] = ["曹操"]
    reports = []
    for index, (name, loop) in enumerate((("联动规则A", False), ("联动规则B", False),
                                          ("联动规则B", True), ("联动规则A", True))):
        config = app.activate_rule_profile(game, config, name)
        run_id = f"history-rule-{index}"
        stop = output / f"stop-{index}"
        environment = dict(os.environ, CCZ_AUTOSTART="1", CCZ_NO_PAUSE="1", CCZ_CONCURRENT_MODE="1",
                           CCZ_CONCURRENT_COUNT="2", CCZ_RESULT_COUNT="3", CCZ_LOOP_RANDOM=str(int(loop)),
                           CCZ_TURBO_MODE="0", CCZ_HISTORY_RUN_ID=run_id, CCZ_STOP_FILE=str(stop),
                           CCZ_RUN_STAMP=f"history-rule-{index}", PYTHONIOENCODING="utf-8")
        for key in ("CCZ_RUN_RULE_CONFIG", "CCZ_CONCURRENT_WORKER", "CCZ_HISTORY_MANAGED"):
            environment.pop(key, None)
        started = time.monotonic()
        existing_archives = set((game / "randResult").rglob("*.E5S"))
        changed = False
        with background_desktop() as startup, (output / f"run-{index}.log").open("w", encoding="utf-8") as log:
            with subprocess.Popen(command,
                                  env=environment, stdout=log, stderr=subprocess.STDOUT,
                                  startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW) as process:
                while process.poll() is None:
                    if time.monotonic() - started > 150:
                        stop.touch()
                        process.wait(timeout=30)
                        raise TimeoutError(f"History rule test timed out: {run_id}")
                    if database.exists():
                        with closing(sqlite3.connect(database)) as connection:
                            run_row = connection.execute("SELECT rule_json FROM runs WHERE id=?", (run_id,)).fetchone()
                            count = connection.execute("SELECT count(*) FROM results JOIN rounds ON rounds.id=results.round_id WHERE run_id=?", (run_id,)).fetchone()[0]
                        if run_row and not changed:
                            expected_rule = json.loads(run_row[0])
                            other = copy.deepcopy(config)
                            other["activeProfile"] = "联动规则B" if name == "联动规则A" else "联动规则A"
                            save_rule_config(game, other)
                            changed = True
                        # Original-directory fallback uses full 15-slot rounds;
                        # continue far enough to exercise a real round boundary too.
                        if loop and count >= 17:
                            stop.touch()
                    time.sleep(.05)
                assert process.returncode in ((0, 130) if loop else (0,)), (run_id, process.returncode)
        assert changed
        with closing(sqlite3.connect(database)) as connection:
            connection.row_factory = sqlite3.Row
            run_row = connection.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            assert run_row["rule_name"] == name and json.loads(run_row["rule_json"]) == expected_rule
            assert run_row["loop_random"] == int(loop)
            assert run_row["status"] == ("stopped" if loop else "completed")
            rows = connection.execute("SELECT rounds.round_number,results.slot,results.snapshot_json,s.data,s.sha256 "
                                      "FROM results JOIN rounds ON rounds.id=results.round_id "
                                      "JOIN result_saves s ON s.result_id=results.id WHERE run_id=?", (run_id,)).fetchall()
            counts = {}
            archived = []
            if loop:
                archived = list(set((game / "randResult").rglob("*.E5S")) - existing_archives)
                archive_hashes = sorted(hashlib.sha256(path.read_bytes()).hexdigest() for path in archived)
            for row in rows:
                from ccz_randomizer.storage_codec import unpack
                snapshot = json.loads(unpack(row["snapshot_json"]))
                counts[row["round_number"]] = counts.get(row["round_number"], 0) + 1
                digest = hashlib.sha256(unpack(row["data"])).hexdigest()
                assert digest == row["sha256"] == snapshot["save"]["sha256"]
                assert snapshot["detail"]["job"]["metrics"]["eligibleMembers"] == expected_rule["threePerson"]["qualifiedMembers"]
            if loop:
                assert len(counts) >= 2 and len(archived) == len(rows)
                assert archive_hashes == sorted(row["sha256"] for row in rows)
            else:
                assert counts == {1: 3}
            fallback = "已回退为单实例" in (output / f"run-{index}.log").read_text(encoding="utf-8")
            for row in connection.execute("SELECT round_number,status FROM rounds WHERE run_id=?", (run_id,)):
                width = 15 if loop and fallback else 3
                assert row["status"] == ("completed" if counts[row["round_number"]] == width else "stopped")
            assert not connection.execute("PRAGMA foreign_key_check").fetchall()
            reports.append(dict(runId=run_id, rule=name, loop=loop, roundCounts=counts, saved=len(rows),
                                originalDirectoryFallback=fallback))
    (output / "history-rules.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    if "--worker" in sys.argv:
        raise SystemExit(worker())
    run()
