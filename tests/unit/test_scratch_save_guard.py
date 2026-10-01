from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ccz_randomizer.runtime.scratch_save_guard import (
    ScratchSaveGuard,
    publish_candidate_save,
)


class ScratchSaveGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.game_dir = Path(self.temporary.name) / "game"
        (self.game_dir / "SV").mkdir(parents=True)
        self.guard = ScratchSaveGuard(self.game_dir)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_existing_slot_is_restored_after_temporary_save(self) -> None:
        self.guard.target.write_bytes(b"user-save-16")

        self.assertFalse(self.guard.prepare())
        self.guard.begin()
        self.guard.target.write_bytes(b"random-candidate")
        self.assertTrue(self.guard.restore())

        self.assertEqual(b"user-save-16", self.guard.target.read_bytes())
        self.assertFalse(self.guard.backup_path.exists())
        self.assertFalse(self.guard.state_path.exists())

    def test_missing_slot_is_removed_after_temporary_save(self) -> None:
        self.guard.prepare()
        self.guard.begin()
        self.guard.target.write_bytes(b"random-candidate")

        self.assertTrue(self.guard.restore())

        self.assertFalse(self.guard.target.exists())
        self.assertFalse(self.guard.state_path.exists())

    def test_next_start_recovers_existing_slot_after_forced_exit(self) -> None:
        self.guard.target.write_bytes(b"user-save-16")
        self.guard.prepare()
        self.guard.begin()
        self.guard.target.write_bytes(b"random-candidate")

        restarted_guard = ScratchSaveGuard(self.game_dir)
        self.assertTrue(restarted_guard.prepare())

        self.assertEqual(
            b"user-save-16",
            restarted_guard.target.read_bytes(),
        )
        self.assertFalse(restarted_guard.backup_path.exists())
        self.assertFalse(restarted_guard.state_path.exists())

    def test_next_start_removes_created_slot_after_forced_exit(self) -> None:
        self.guard.prepare()
        self.guard.begin()
        self.guard.target.write_bytes(b"random-candidate")

        restarted_guard = ScratchSaveGuard(self.game_dir)
        self.assertTrue(restarted_guard.prepare())

        self.assertFalse(restarted_guard.target.exists())

    def test_restore_is_idempotent(self) -> None:
        self.guard.target.write_bytes(b"user-save-16")
        self.guard.prepare()
        self.guard.begin()
        self.guard.target.write_bytes(b"random-candidate")

        self.assertTrue(self.guard.restore())
        self.assertFalse(self.guard.restore())
        self.assertEqual(b"user-save-16", self.guard.target.read_bytes())

    def test_other_save_slots_are_never_changed(self) -> None:
        protected = {
            slot: self.game_dir / "SV" / f"SV{slot:03}.E5S"
            for slot in (1, 15, 20)
        }
        for slot, path in protected.items():
            path.write_bytes(f"save-{slot}".encode("ascii"))

        self.guard.prepare()
        self.guard.begin()
        self.guard.target.write_bytes(b"random-candidate")
        self.guard.restore()

        for slot, path in protected.items():
            self.assertEqual(
                f"save-{slot}".encode("ascii"),
                path.read_bytes(),
            )

    def test_candidate_save_is_published_without_modifying_content(self):
        target = self.game_dir / "SV" / "SV005.E5S"
        target.write_bytes(b"previous")
        candidate = b"game-created-save-at-initial-scene"

        publish_candidate_save(target, candidate)

        self.assertEqual(candidate, target.read_bytes())

    def test_empty_candidate_does_not_replace_existing_result(self):
        target = self.game_dir / "SV" / "SV005.E5S"
        target.write_bytes(b"previous")

        with self.assertRaisesRegex(ValueError, "候选存档内容为空"):
            publish_candidate_save(target, b"")

        self.assertEqual(b"previous", target.read_bytes())
