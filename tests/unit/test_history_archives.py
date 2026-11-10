from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ccz_randomizer.history import HistoryRepository, SCHEMA_VERSION


class HistoryArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        project = Path(__file__).resolve().parents[2]
        # The repository transports opaque game bytes, without parsing their format.
        self.data = (project / "resources/legacy/random_save_templates.bin").read_bytes()
        self.snapshot = json.loads((project / "tests/fixtures/personnel_220_1104/randomized-result.json").read_text(encoding="utf-8"))
        self.source = self.base / "SV001.E5S"
        self.source.write_bytes(self.data)
        self.snapshot.update(slot=1, acceptedAttempt=1)
        self.snapshot["save"] = dict(path=str(self.source), sha256=hashlib.sha256(self.data).hexdigest())
        self.repo = HistoryRepository(self.base)
        self.repo.start_run("run", mode="three", loop_random=True, rule_name="默认规则", rule={}, build={})
        self.rid = self.repo.start_round("run", 1)

    def save(self, backup=True, rid=None):
        return self.repo.save_result(rid or self.rid, self.snapshot, save_path=self.source if backup else None)

    def test_copy_survives_source_overwrite_deletion_and_repository_reopen(self):
        self.save()
        self.source.write_bytes(self.data[::-1])
        self.source.unlink()
        repo = HistoryRepository(self.base)
        output = self.base / "recovered.E5S"
        repo.export_result_save(self.rid, 1, output)
        self.assertEqual(self.data, output.read_bytes())
        self.assertTrue(repo.get_round_summaries(self.rid)[0]["history"]["backed_up"])

    def test_worker_source_is_used_instead_of_remapped_public_path(self):
        self.snapshot["save"]["path"] = str(self.base / "public" / "SV001.E5S")
        self.save()
        output = self.base / "restored.E5S"
        self.repo.export_result_save(self.rid, 1, output)
        self.assertEqual(self.data, output.read_bytes())

    def test_mismatch_never_archives_wrong_file_or_replaces_existing_copy(self):
        self.save()
        self.source.write_bytes(self.data[::-1])
        with self.assertRaisesRegex(ValueError, "已变化"):
            self.save()
        output = self.base / "restored.E5S"
        self.repo.export_result_save(self.rid, 1, output)
        self.assertEqual(self.data, output.read_bytes())

    def test_backfill_only_copies_matching_files_and_never_guesses(self):
        self.save(backup=False)
        second = self.repo.start_round("run", 2)
        other = copy.deepcopy(self.snapshot)
        other["save"]["sha256"] = hashlib.sha256(self.data[::-1]).hexdigest()
        self.repo.save_result(second, other)
        missing = copy.deepcopy(self.snapshot)
        missing["slot"] = 2
        missing["save"]["path"] = str(self.base / "missing.E5S")
        self.repo.save_result(second, missing)
        self.assertEqual(dict(saved=1, unavailable=2), self.repo.backfill_saves())
        self.assertEqual(dict(saved=0, unavailable=2), self.repo.backfill_saves())
        self.assertFalse(self.repo.get_round_summaries(second)[0]["history"]["backed_up"])

    def test_corrupt_copy_leaves_export_destination_unchanged(self):
        self.save()
        with closing(self.repo._connect()) as db, db:
            db.execute("UPDATE result_saves SET data=?", (self.data[::-1],))
        output = self.base / "SV002.E5S"
        output.write_bytes(self.data)
        with self.assertRaisesRegex(ValueError, "校验失败"):
            self.repo.export_result_save(self.rid, 1, output)
        self.assertEqual(self.data, output.read_bytes())

    def test_failed_export_is_atomic_and_temporary_file_is_removed(self):
        self.save()
        output = self.base / "SV002.E5S"
        output.write_bytes(self.data[::-1])
        with patch("ccz_randomizer.history_saves.os.replace", side_effect=OSError("设备暂不可写")):
            with self.assertRaises(OSError):
                self.repo.export_result_save(self.rid, 1, output)
        self.assertEqual(self.data[::-1], output.read_bytes())
        self.assertEqual([], list(self.base.glob(".ccz-export-*")))

    def test_annotation_search_mark_filters_and_pagination_persist(self):
        self.save()
        self.repo.annotate_round(self.rid, title="优选队伍", note="准备开局", marked=True)
        second = self.repo.start_round("run", 2)
        self.save(rid=second)
        self.repo.annotate_round(second, title="曹操%_", note="喜欢这个兵种")
        repo = HistoryRepository(self.base)
        self.assertEqual(2, repo.count_rounds())
        self.assertEqual([second], [r["id"] for r in repo.list_rounds(query="%_")])
        self.assertEqual([self.rid], [r["id"] for r in repo.list_rounds(query="准备开局")])
        self.assertEqual(1, repo.count_rounds(query="喜欢这个"))
        self.assertEqual(1, len(repo.list_rounds(page=2, page_size=1)))
        repo.annotate_round(self.rid, title="", note="")
        annotation = repo.get_round_summaries(second)[0]["history"]
        self.assertEqual("曹操%_", annotation["title"])
        self.assertEqual("喜欢这个兵种", annotation["note"])

    def test_repeat_save_preserves_annotations_and_deletion_cleans_archives(self):
        self.save()
        self.repo.annotate_round(self.rid, title="保留", note="备注")
        self.save()
        self.assertEqual("保留", self.repo.get_round_summaries(self.rid)[0]["history"]["title"])
        second = self.repo.start_round("run", 2)
        self.save(rid=second)
        self.repo.delete_round(self.rid)
        with closing(self.repo._connect()) as db:
            self.assertEqual(1, db.execute("SELECT COUNT(*) FROM result_saves").fetchone()[0])
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM result_annotations").fetchone()[0])
        self.repo.clear()
        with closing(self.repo._connect()) as db:
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM result_saves").fetchone()[0])

    def test_v2_upgrade_is_lazy_and_preserves_snapshots(self):
        self.save(backup=False)
        with closing(self.repo._connect()) as db, db:
            before = db.execute("SELECT snapshot_json FROM results").fetchone()[0]
            db.execute("DROP TABLE result_saves")
            db.execute("DROP TABLE result_annotations")
            for column in ("title", "note", "marked"):
                db.execute(f"ALTER TABLE rounds DROP COLUMN {column}")
            db.execute("PRAGMA user_version=2")
        with patch("ccz_randomizer.history.json.loads", side_effect=AssertionError("不应扫描旧快照")):
            repo = HistoryRepository(self.base)
        with closing(repo._connect()) as db:
            self.assertEqual(SCHEMA_VERSION, db.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual(before, db.execute("SELECT snapshot_json FROM results").fetchone()[0])
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM result_saves").fetchone()[0])
        self.assertEqual(dict(saved=1, unavailable=0), repo.backfill_saves())

    def test_parallel_writers_keep_both_backups(self):
        other = copy.deepcopy(self.snapshot)
        other["slot"] = 2
        def write(snapshot):
            repo = HistoryRepository(self.base)
            repo.save_result(self.rid, snapshot, save_path=self.source)
        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(write, [self.snapshot, other]))
        for slot in (1, 2):
            output = self.base / f"export{slot}.E5S"
            self.repo.export_result_save(self.rid, slot, output)
            self.assertEqual(self.data, output.read_bytes())
