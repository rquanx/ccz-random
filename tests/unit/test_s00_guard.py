from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ccz_randomizer.runtime.s00_guard import (
    S00ScriptGuard,
    repair_game_s00,
    restore_bundled_original_s00,
)


class S00GuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.game_dir = self.root / "game"
        self.game_dir.mkdir()
        self.original = self.root / "original_s00.eex"
        self.helper = self.root / "random_s00.eex"
        self.original.write_bytes(b"correct-original")
        self.helper.write_bytes(b"battle-skip")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_startup_preserves_root_backup_and_replaces_stale_helper(self) -> None:
        root_target = self.game_dir / "S_00.eex"
        override = self.game_dir / "RS" / "S_00.eex"
        root_target.write_bytes(b"user-backup")
        override.parent.mkdir()
        override.write_bytes(b"battle-skip")

        result = repair_game_s00(
            self.game_dir,
            self.original,
            self.helper,
        )

        self.assertTrue(result.active_script_repaired)
        self.assertTrue(result.stale_helper_replaced)
        self.assertEqual(b"user-backup", root_target.read_bytes())
        self.assertEqual(b"correct-original", override.read_bytes())

    def test_missing_active_script_is_restored_without_touching_root(self) -> None:
        root_target = self.game_dir / "S_00.eex"
        root_target.write_bytes(b"user-backup")

        result = repair_game_s00(
            self.game_dir,
            self.original,
            self.helper,
        )

        self.assertTrue(result.active_script_repaired)
        self.assertFalse(result.stale_helper_replaced)
        self.assertEqual(b"user-backup", root_target.read_bytes())
        self.assertEqual(
            b"correct-original",
            (self.game_dir / "RS" / "S_00.eex").read_bytes(),
        )

    def test_root_backup_and_custom_active_script_are_preserved(self) -> None:
        root_target = self.game_dir / "S_00.eex"
        override = self.game_dir / "RS" / "S_00.eex"
        root_target.write_bytes(b"user-backup")
        override.parent.mkdir()
        override.write_bytes(b"custom-script")

        result = repair_game_s00(
            self.game_dir,
            self.original,
            self.helper,
        )

        self.assertFalse(result.active_script_repaired)
        self.assertFalse(result.stale_helper_replaced)
        self.assertEqual(b"user-backup", root_target.read_bytes())
        self.assertEqual(b"custom-script", override.read_bytes())

    def test_guard_restores_bundled_script_after_install(self) -> None:
        (self.game_dir / "S_00.eex").write_bytes(b"user-backup")
        guard = S00ScriptGuard(
            self.game_dir,
            self.original,
            self.helper,
        )

        guard.prepare()
        guard.install()
        self.assertEqual(
            b"battle-skip",
            guard.override_target.read_bytes(),
        )
        guard.restore()

        self.assertEqual(
            b"correct-original",
            guard.override_target.read_bytes(),
        )
        self.assertEqual(
            b"user-backup",
            (self.game_dir / "S_00.eex").read_bytes(),
        )

    def test_guard_restores_existing_override_after_error(self) -> None:
        root_target = self.game_dir / "S_00.eex"
        override = self.game_dir / "RS" / "S_00.eex"
        root_target.write_bytes(b"user-backup")
        override.parent.mkdir()
        override.write_bytes(b"custom-script")
        guard = S00ScriptGuard(
            self.game_dir,
            self.original,
            self.helper,
        )

        guard.prepare()
        try:
            guard.install()
            raise RuntimeError("test failure")
        except RuntimeError:
            pass
        finally:
            guard.restore()

        self.assertEqual(b"custom-script", override.read_bytes())
        self.assertEqual(b"user-backup", root_target.read_bytes())

    def test_restore_is_idempotent(self) -> None:
        (self.game_dir / "S_00.eex").write_bytes(b"user-backup")
        guard = S00ScriptGuard(
            self.game_dir,
            self.original,
            self.helper,
        )

        guard.prepare()
        guard.install()
        guard.restore()
        guard.restore()

        self.assertEqual(
            b"correct-original",
            guard.override_target.read_bytes(),
        )

    def test_startup_recovers_override_after_forced_worker_exit(self) -> None:
        root_target = self.game_dir / "S_00.eex"
        override = self.game_dir / "RS" / "S_00.eex"
        root_target.write_bytes(b"user-backup")
        override.parent.mkdir()
        override.write_bytes(b"custom-script")
        guard = S00ScriptGuard(
            self.game_dir,
            self.original,
            self.helper,
        )

        guard.prepare()
        guard.install()
        result = repair_game_s00(
            self.game_dir,
            self.original,
            self.helper,
        )

        self.assertTrue(result.transaction_recovered)
        self.assertEqual(b"custom-script", override.read_bytes())
        self.assertEqual(b"user-backup", root_target.read_bytes())
        self.assertFalse(guard.override_backup_path.exists())
        self.assertFalse(guard.override_state_path.exists())

    def test_startup_repairs_legacy_missing_transaction(self) -> None:
        root_target = self.game_dir / "S_00.eex"
        override = self.game_dir / "RS" / "S_00.eex"
        root_target.write_bytes(b"user-backup")
        override.parent.mkdir()
        override.write_bytes(b"battle-skip")
        state_path = override.parent / ".S_00.eex.ccz-fast.state"
        state_path.write_text("missing", encoding="ascii")

        result = repair_game_s00(
            self.game_dir,
            self.original,
            self.helper,
        )

        self.assertTrue(result.transaction_recovered)
        self.assertEqual(b"correct-original", override.read_bytes())
        self.assertEqual(b"user-backup", root_target.read_bytes())
        self.assertFalse(state_path.exists())

    def test_startup_accepts_already_restored_transaction(self) -> None:
        override = self.game_dir / "RS" / "S_00.eex"
        override.parent.mkdir()
        override.write_bytes(b"custom-script")
        state_path = override.parent / ".S_00.eex.ccz-fast.state"
        state_path.write_text("present", encoding="ascii")

        result = repair_game_s00(
            self.game_dir,
            self.original,
            self.helper,
        )

        self.assertTrue(result.transaction_recovered)
        self.assertEqual(b"custom-script", override.read_bytes())
        self.assertFalse(state_path.exists())

    def test_manual_restore_replaces_helper_with_bundled_original(self) -> None:
        override = self.game_dir / "RS" / "S_00.eex"
        override.parent.mkdir()
        override.write_bytes(b"battle-skip")

        result = restore_bundled_original_s00(
            self.game_dir,
            self.original,
            self.helper,
        )

        self.assertTrue(result.restored)
        self.assertIsNone(result.backup_path)
        self.assertEqual(b"correct-original", override.read_bytes())

    def test_manual_restore_preserves_unknown_script_as_backup(self) -> None:
        override = self.game_dir / "RS" / "S_00.eex"
        override.parent.mkdir()
        override.write_bytes(b"custom-script")

        result = restore_bundled_original_s00(
            self.game_dir,
            self.original,
            self.helper,
        )

        self.assertTrue(result.restored)
        self.assertIsNotNone(result.backup_path)
        self.assertEqual(b"custom-script", result.backup_path.read_bytes())
        self.assertEqual(b"correct-original", override.read_bytes())

    def test_manual_restore_reports_already_normal_script(self) -> None:
        override = self.game_dir / "RS" / "S_00.eex"
        override.parent.mkdir()
        override.write_bytes(b"correct-original")

        result = restore_bundled_original_s00(
            self.game_dir,
            self.original,
            self.helper,
        )

        self.assertFalse(result.restored)
        self.assertIsNone(result.backup_path)

    def test_manual_restore_reports_recovered_stale_transaction(self) -> None:
        override = self.game_dir / "RS" / "S_00.eex"
        override.parent.mkdir()
        override.write_bytes(b"battle-skip")
        state_path = override.parent / ".S_00.eex.ccz-fast.state"
        state_path.write_text("missing", encoding="ascii")

        result = restore_bundled_original_s00(
            self.game_dir,
            self.original,
            self.helper,
        )

        self.assertTrue(result.restored)
        self.assertEqual(b"correct-original", override.read_bytes())
