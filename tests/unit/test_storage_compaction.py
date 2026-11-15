"""Lossless upgrades of released statistical and history storage formats."""
from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ccz_randomizer.statistics import StatisticsRecorder
from ccz_randomizer.statistics_store import StatisticsRepository, SCHEMA
from ccz_randomizer.statistics_equipment_store import initialize
from ccz_randomizer.statistics_equipment import capture_equipment_statistics
from ccz_randomizer.storage_codec import pack, unpack, MAGIC
from ccz_randomizer.history import HistoryRepository
from tests.unit.test_statistics import runner_fixture
from tests.unit.test_statistics_equipment import equipment_fixture
from tests.unit import test_history_archives as history_archives


class StatisticsCompactionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.repo = StatisticsRepository(self.base)
        recorder = StatisticsRecorder(self.base, run_id="run", rule_name="规则", rule={}, mode="three")
        for index in range(4):
            runner = runner_fixture(reject=bool(index % 2))
            capture_equipment_statistics(runner, equipment_fixture, self.fail)
            with recorder.attempt(runner, round_number=1, slot=1, attempt=index + 1) as event:
                event["saved"] = not index % 2
        recorder.close()
        self.assertEqual(0, recorder.lost)

    def legacy(self):
        with self.repo.connect() as db:
            db.execute("CREATE TABLE old_equipment(attempt_id TEXT NOT NULL,name TEXT NOT NULL,effect TEXT NOT NULL,PRIMARY KEY(attempt_id,name))")
            db.execute("INSERT INTO old_equipment SELECT * FROM equipment")
            db.execute("DROP VIEW equipment")
            for table in ("equipment_samples", "equipment_attempts", "equipment_names", "equipment_effects"):
                db.execute("DROP TABLE " + table)
            db.execute("ALTER TABLE old_equipment RENAME TO equipment")
            db.execute("CREATE INDEX equipment_name ON equipment(name,attempt_id)")
            db.execute("PRAGMA user_version=2")

    def test_upgrade_preserves_all_filters_frequencies_and_stable_links_after_vacuum(self):
        filters = ({}, {"person": "曹操"}, {"result": "qualified"}, {"result": "rejected"},
                   {"equipment_name": equipment_fixture()[0][0][0][0]}, {"start": 0, "end": 1})
        expected = [self.repo.query(**f) for f in filters]
        rankings = self.repo.ranking("equipment", page_size=12, page=2)
        self.legacy()
        self.assertEqual(expected, [self.repo.query(**f) for f in filters])
        self.assertEqual(rankings, self.repo.ranking("equipment", page_size=12, page=2))
        with self.repo.connect() as db:
            self.assertEqual(280, db.execute("SELECT COUNT(*) FROM equipment_samples").fetchone()[0])
            self.assertEqual(70, db.execute("SELECT COUNT(*) FROM equipment_names").fetchone()[0])
            db.execute("VACUUM")
        self.assertEqual(expected[0], self.repo.query())
        with closing(sqlite3.connect(self.repo.path)) as db:
            self.assertEqual(3, db.execute("PRAGMA user_version").fetchone()[0])

    def test_failed_migration_rolls_back_schema_and_all_equipment_rows(self):
        self.legacy()
        with closing(sqlite3.connect(self.repo.path)) as db:
            before = db.execute("SELECT * FROM equipment ORDER BY attempt_id,name").fetchall()
            db.set_authorizer(lambda action, first, *_: sqlite3.SQLITE_DENY
                              if action == sqlite3.SQLITE_DROP_TABLE and first == "equipment_legacy"
                              else sqlite3.SQLITE_OK)
            with self.assertRaises(sqlite3.DatabaseError):
                initialize(db, SCHEMA)
            db.set_authorizer(None)
            self.assertEqual(before, db.execute("SELECT * FROM equipment ORDER BY attempt_id,name").fetchall())
            self.assertEqual(2, db.execute("PRAGMA user_version").fetchone()[0])
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='equipment_samples'").fetchone())
        self.assertEqual(4, self.repo.query()["totals"][0])


class HistoryCompactionTests(unittest.TestCase):
    setUp = history_archives.HistoryArchiveTests.setUp
    save = history_archives.HistoryArchiveTests.save

    def legacy(self):
        self.save()
        self.repo.annotate_round(self.rid, title="保留名称", note="保留备注", marked=True)
        with closing(self.repo._connect()) as db, db:
            for row in db.execute("SELECT id,snapshot_json FROM results").fetchall():
                db.execute("UPDATE results SET snapshot_json=? WHERE id=?", (unpack(row[1]).decode(), row[0]))
            for row in db.execute("SELECT result_id,data FROM result_saves").fetchall():
                db.execute("UPDATE result_saves SET data=? WHERE result_id=?", (unpack(row[1]), row[0]))
            db.execute("PRAGMA user_version=3")

    def test_upgrade_preserves_complete_snapshot_annotations_and_exact_export(self):
        self.legacy()
        repo = HistoryRepository(self.base)
        self.assertEqual(self.snapshot, repo.get_result(self.rid, 1))
        summary = repo.get_round_summaries(self.rid)[0]
        self.assertEqual("保留名称", summary["history"]["title"])
        self.assertTrue(summary["history"]["marked"])
        self.assertEqual(1, repo.count_rounds(query="保留备注", marked_only=True))
        output = self.base / "export.E5S"
        self.source.unlink()
        repo.export_result_save(self.rid, 1, output)
        self.assertEqual(self.data, output.read_bytes())
        with closing(repo._connect()) as db:
            snapshot = db.execute("SELECT snapshot_json FROM results").fetchone()[0]
            saved = db.execute("SELECT data FROM result_saves").fetchone()[0]
            self.assertLess(len(snapshot), len(json.dumps(self.snapshot, ensure_ascii=False).encode()) / 2)
            self.assertLess(len(saved), len(self.data))
        repo.update_verification(self.rid, 1, verified=True)
        self.assertTrue(repo.get_result(self.rid, 1)["save"]["verified"])

    def test_failed_compression_upgrade_restores_original_data_and_version(self):
        self.legacy()
        with closing(self.repo._connect()) as db:
            before = db.execute("SELECT snapshot_json FROM results").fetchone()[0]
        calls = []
        def fail_after_first(value):
            calls.append(value)
            if len(calls) == 2:
                raise OSError("模拟写入失败")
            return pack(value)
        with patch("ccz_randomizer.storage_codec.pack", side_effect=fail_after_first):
            with self.assertRaisesRegex(OSError, "模拟写入失败"):
                HistoryRepository(self.base)
        with closing(self.repo._connect()) as db:
            self.assertEqual(3, db.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual(before, db.execute("SELECT snapshot_json FROM results").fetchone()[0])
            self.assertEqual(self.data, db.execute("SELECT data FROM result_saves").fetchone()[0])
        self.assertEqual(self.snapshot, HistoryRepository(self.base).get_result(self.rid, 1))

    def test_codec_reads_legacy_and_rejects_truncated_compressed_payload(self):
        raw = json.dumps(self.snapshot, ensure_ascii=False).encode()
        encoded = pack(raw)
        self.assertTrue(encoded.startswith(MAGIC))
        self.assertEqual(raw, unpack(encoded))
        self.assertEqual(encoded, pack(encoded))
        self.assertEqual(raw, unpack(raw.decode()))
        with self.assertRaises(ValueError):
            unpack(encoded[:-3])
