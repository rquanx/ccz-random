"""Recover missing loop history only from matching archived saves and real logs.

Run with ``python -m tools.diagnostics.recover_loop_history --help``.
The default creates a backup and a verified preview; --apply inserts missing rows.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from ccz_randomizer.history import HistoryRepository
from ccz_randomizer.history_members import history_members


# R0 memory block recorded by the diagnostic logger and saved at E5S offset zero.
R0_SIZE = 0x30000


def records(path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)


def target_state(connection, run_id):
    """Detect changes to this run, including notes and save backups, before merge."""
    queries = {
        "runs": "SELECT * FROM runs WHERE id=? ORDER BY id",
        "rounds": "SELECT * FROM rounds WHERE run_id=? ORDER BY id",
        "results": "SELECT * FROM results WHERE round_id IN (SELECT id FROM rounds WHERE run_id=?) ORDER BY id",
    }
    for table in ("result_annotations", "result_summaries", "result_saves"):
        queries[table] = (f"SELECT * FROM {table} WHERE result_id IN (SELECT results.id FROM results "
                          "JOIN rounds ON rounds.id=results.round_id WHERE run_id=?) ORDER BY result_id")
    return {name: [[hashlib.sha256(value).hexdigest() if isinstance(value, bytes) else value
                   for value in row] for row in connection.execute(query, (run_id,))]
            for name, query in queries.items()}


def recovery_candidates(archive, log_paths):
    """Require a failed history write and an accepted detail for the exact R0."""
    evidence = {}
    for diagnostic in log_paths:
        events = list(records(diagnostic))
        failures = [event for event in events if event.get("event") == "history_result_write_failed"]
        if not failures:
            continue
        log = diagnostic.with_name(diagnostic.name.replace("_diagnostic.jsonl", ".log"))
        details = [json.loads(line.split("@@CCZ_RESULT_DETAIL@@", 1)[1])
                   for line in log.read_text(encoding="utf-8").splitlines()
                   if line.startswith("@@CCZ_RESULT_DETAIL@@")]
        for event in failures:
            context = event["context"]
            digest = (((event.get("failure") or {}).get("game_state") or {}).get("memory") or {}).get("sha256")
            if not digest or not context.get("loop_round") or not event.get("result_slot"):
                continue
            key = (int(context["loop_round"]), int(event["result_slot"]))
            matches = [detail for detail in details if detail.get("status") == "accepted"
                       and detail["resultSlot"] == key[1] and detail["attempt"] == context["attempt"]]
            if len(matches) == 1:
                evidence.setdefault(key, []).append((digest, matches[0], event["time"], diagnostic))
    candidates = {}
    for folder in sorted(archive.glob("round-*")):
        number = int(folder.name.split("-")[1])
        for save in sorted((folder / "SV").glob("SV*.E5S")):
            slot = int(save.stem[2:])
            data = save.read_bytes()
            digest = hashlib.sha256(data[:R0_SIZE]).hexdigest()
            matches = [item for item in evidence.get((number, slot), []) if item[0] == digest]
            if not matches:
                continue
            if any(item[1] != matches[0][1] for item in matches[1:]):
                raise ValueError(f"Ambiguous recovery evidence: round {number}, slot {slot}")
            _, detail, time, diagnostic = matches[0]
            snapshot = {key: detail.get(key) for key in (
                "schemaVersion", "gameVersion", "personnel", "fixedPersonnel", "jobTalents", "dataCollection", "equipment")}
            snapshot.update(
                phase="randomized" if detail.get("personnel") else "unknown",
                createdAt=dt.datetime.fromisoformat(time).astimezone().isoformat(timespec="seconds"),
                roundNumber=number, slot=slot, acceptedAttempt=detail["attempt"],
                mode=detail["mode"], detail=detail,
                save=dict(path=str(save), size=len(data), sha256=hashlib.sha256(data).hexdigest(),
                          verified=False, verificationError=""),
                recovery=dict(diagnostic=str(diagnostic), archive=str(save), r0Sha256=digest,
                              limitations="未采集的人员详情及个人/兵种特技分类无法从日志恢复；保留未保存标记。"))
            snapshot["members"] = history_members(snapshot)
            candidates[(number, slot)] = snapshot
    return candidates


def stage_recovery(base, run_id, archive, log_paths, output, timing_path):
    output.mkdir(parents=True, exist_ok=False)
    source = base / "ccz_fast_data" / "history.sqlite3"
    backup = output / "before.sqlite3"
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as connection:
        baseline = target_state(connection, run_id)
        with closing(sqlite3.connect(backup)) as destination:
            connection.backup(destination)
    if not baseline["runs"] or baseline["runs"][0][3] != "stopped":
        raise ValueError("Recovery requires the selected run to be stopped")
    preview_base = output / "preview"
    (preview_base / "ccz_fast_data").mkdir(parents=True)
    preview_path = preview_base / "ccz_fast_data" / "history.sqlite3"
    with closing(sqlite3.connect(backup)) as connection, closing(sqlite3.connect(preview_path)) as destination:
        connection.backup(destination)
    repository = HistoryRepository(preview_base)
    with closing(repository._connect()) as connection:
        existing = {(row[0], row[1]) for row in connection.execute(
            "SELECT round_number,slot FROM results JOIN rounds ON rounds.id=results.round_id WHERE run_id=?", (run_id,))}
    candidates = recovery_candidates(archive, log_paths)
    archived = {(int(folder.name.split("-")[1]), int(save.stem[2:]))
                for folder in archive.glob("round-*") for save in (folder / "SV").glob("SV*.E5S")}
    missing = archived - existing
    if missing - candidates.keys():
        raise ValueError(f"Missing hash-matched evidence for: {sorted(missing - candidates.keys())}")
    times = {}
    for event in records(timing_path):
        if event.get("phase") == "worker_launch" and event.get("event") == "timing_started":
            number = int(event["round_number"])
            time = dt.datetime.fromisoformat(event["time"]).astimezone().isoformat(timespec="seconds")
            times[number] = min(times.get(number, time), time)
    created_rounds = set()
    for number, slot in sorted(missing):
        try:
            round_id = repository.require_round(run_id, number)
        except RuntimeError:
            round_id = repository.start_round(run_id, number)
            created_rounds.add(number)
        snapshot = candidates[number, slot]
        repository.save_result(round_id, snapshot, save_path=Path(snapshot["save"]["path"]))
    with closing(repository._connect()) as connection, connection:
        for number in sorted(created_rounds):
            count = sum(n == number for n, _ in archived)
            # The run's stop timestamp is authoritative for the partial final round.
            end = max(candidates[n, s]["createdAt"] for n, s in missing if n == number)
            connection.execute("UPDATE rounds SET started_at=?,finished_at=?,status=? WHERE run_id=? AND round_number=?",
                               (times[number], end if count == 15 else baseline["runs"][0][2],
                                "completed" if count == 15 else "stopped", run_id, number))
        connection.execute("UPDATE runs SET loop_random=1 WHERE id=?", (run_id,))
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Invalid staged database foreign keys")
    return dict(runId=run_id, baseline=baseline, missing=sorted(missing),
                preview=str(preview_path), backup=str(backup))


def apply_recovery(base, plan):
    """Merge missing rows in one transaction; existing rows and other runs stay intact."""
    source = base / "ccz_fast_data" / "history.sqlite3"
    with closing(sqlite3.connect(source)) as connection, closing(sqlite3.connect(plan["preview"])) as staged:
        staged.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN IMMEDIATE")
        try:
            if target_state(connection, plan["runId"]) != plan["baseline"]:
                raise ValueError("Selected history changed after preview; generate a fresh plan")
            for number, slot in plan["missing"]:
                row = staged.execute("SELECT results.* FROM results JOIN rounds ON rounds.id=results.round_id "
                                     "WHERE run_id=? AND round_number=? AND slot=?", (plan["runId"], number, slot)).fetchone()
                from ccz_randomizer.storage_codec import unpack
                snapshot = json.loads(unpack(row["snapshot_json"]))
                if hashlib.sha256(Path(snapshot["save"]["path"]).read_bytes()).hexdigest() != row["save_sha256"]:
                    raise ValueError("Archive changed after preview")
                round_row = staged.execute("SELECT * FROM rounds WHERE id=?", (row["round_id"],)).fetchone()
                connection.execute("INSERT INTO rounds(run_id,round_number,started_at,finished_at,status) "
                                   "VALUES (?,?,?,?,?) ON CONFLICT(run_id,round_number) DO NOTHING",
                                   tuple(round_row[key] for key in ("run_id", "round_number", "started_at", "finished_at", "status")))
                round_id = connection.execute("SELECT id FROM rounds WHERE run_id=? AND round_number=?", (plan["runId"], number)).fetchone()[0]
                columns = [key for key in row.keys() if key != "id"]
                values = [round_id if key == "round_id" else row[key] for key in columns]
                result_id = connection.execute(f"INSERT INTO results({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", values).lastrowid
                for table in ("result_summaries", "result_saves"):
                    child = staged.execute(f"SELECT * FROM {table} WHERE result_id=?", (row["id"],)).fetchone()
                    columns = list(child.keys())
                    connection.execute(f"INSERT INTO {table}({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                                       [result_id if key == "result_id" else child[key] for key in columns])
            connection.execute("UPDATE runs SET loop_random=1 WHERE id=?", (plan["runId"],))
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("Invalid recovered database foreign keys")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "archive", "logs", "output", "timing"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    plan = stage_recovery(args.base, args.run_id, args.archive, sorted(args.logs.glob("*_diagnostic.jsonl")), args.output, args.timing)
    (args.output / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.apply:
        apply_recovery(args.base, plan)
    print(json.dumps(dict(recovered=len(plan["missing"]), applied=args.apply, backup=plan["backup"]), ensure_ascii=False))


if __name__ == "__main__":
    main()
