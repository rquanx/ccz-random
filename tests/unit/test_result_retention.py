import tempfile
import unittest
from pathlib import Path

from ccz_randomizer.runtime.result_retention import cleanup_result_directory


class ResultRetentionTests(unittest.TestCase):
    def test_oldest_run_directories_are_removed_to_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old = root / "panels" / "old-run"
            new = root / "panels" / "new-run"
            old.mkdir(parents=True)
            new.mkdir(parents=True)
            (old / "save1.png").write_bytes(b"a" * 100)
            (new / "save1.png").write_bytes(b"b" * 100)
            result = cleanup_result_directory(root, limit_bytes=50, target_bytes=0, protected=(new,))
            self.assertFalse(old.exists())
            self.assertTrue(new.exists())
            self.assertEqual(0, result.remaining_bytes)

    def test_loop_runs_are_grouped_and_active_run_is_protected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old = root / "loop" / "old-run" / "round-000001"
            active = root / "loop" / "active-run" / "round-000001"
            old.mkdir(parents=True)
            active.mkdir(parents=True)
            (old / "random.png").write_bytes(b"a" * 100)
            (active / "random.png").write_bytes(b"b" * 100)
            cleanup_result_directory(root, limit_bytes=50, target_bytes=0, protected=(active.parent,))
            self.assertFalse(old.parent.exists())
            self.assertTrue(active.exists())
