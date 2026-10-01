from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ccz_randomizer.runtime.game_sandbox import (
    cleanup_stale_sandboxes,
    create_game_sandbox,
)


class GameSandboxTests(unittest.TestCase):
    def test_mutable_game_data_is_copied_and_static_assets_are_linked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "game"
            (root / "SV").mkdir(parents=True)
            (root / "RS").mkdir()
            (root / "Map").mkdir()
            (root / "Ekd5.exe").write_bytes(b"game")
            (root / "SV" / "SV016.E5S").write_bytes(b"user-save")
            (root / "RS" / "S_00.eex").write_bytes(b"normal-script")
            (root / "Map" / "asset.bin").write_bytes(b"static")

            sandbox = create_game_sandbox(
                root,
                root=Path(temporary) / "sandboxes",
            )
            (sandbox / "SV" / "SV016.E5S").write_bytes(b"candidate")
            (sandbox / "RS" / "S_00.eex").write_bytes(b"helper")

            self.assertEqual(
                b"user-save",
                (root / "SV" / "SV016.E5S").read_bytes(),
            )
            self.assertEqual(
                b"normal-script",
                (root / "RS" / "S_00.eex").read_bytes(),
            )
            self.assertTrue(
                os.path.samefile(
                    root / "Map" / "asset.bin",
                    sandbox / "Map" / "asset.bin",
                )
            )
            self.assertFalse(
                os.path.samefile(
                    root / "Ekd5.exe",
                    sandbox / "Ekd5.exe",
                )
            )
            self.assertEqual("Ekd5.exe", (sandbox / "Ekd5.exe").name)

    def test_tool_output_directories_are_not_copied(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "game"
            root.mkdir()
            (root / "Ekd5.exe").write_bytes(b"game")
            (root / "ccz_fast_logs").mkdir()
            (root / "ccz_fast_logs" / "old.log").write_text("old")
            (root / "randResult").mkdir()

            sandbox = create_game_sandbox(
                root,
                root=Path(temporary) / "sandboxes",
            )

            self.assertFalse((sandbox / "ccz_fast_logs").exists())
            self.assertFalse((sandbox / "randResult").exists())

    def test_sandbox_omits_audio_directories_for_silent_game_instances(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "game"
            root.mkdir()
            (root / "Ekd5.exe").write_bytes(b"game")
            (root / "SoundTrk").mkdir()
            (root / "SoundTrk" / "track.dat").write_bytes(b"music")
            (root / "WAV").mkdir()
            (root / "WAV" / "effect.wav").write_bytes(b"effect")
            (root / "Map").mkdir()
            (root / "Map" / "asset.bin").write_bytes(b"asset")

            sandbox = create_game_sandbox(
                root,
                root=Path(temporary) / "sandboxes",
            )

            self.assertFalse((sandbox / "SoundTrk").exists())
            self.assertFalse((sandbox / "WAV").exists())
            self.assertTrue((sandbox / "Map" / "asset.bin").is_file())

    def test_compatibility_sandbox_does_not_create_game_executable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "game"
            root.mkdir()
            (root / "Ekd5.exe").write_bytes(b"game")
            (root / "asset.bin").write_bytes(b"asset")

            sandbox = create_game_sandbox(
                root,
                root=Path(temporary) / "sandboxes",
                include_executable=False,
            )

            self.assertFalse((sandbox / "Ekd5.exe").exists())
            self.assertTrue((sandbox / "asset.bin").is_file())

    def test_concurrent_sandbox_only_copies_requested_source_save(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "game"
            (root / "SV").mkdir(parents=True)
            (root / "Ekd5.exe").write_bytes(b"game")
            (root / "SV" / "SV001.E5S").write_bytes(b"user-save")
            (root / "SV" / "SV020.E5S").write_bytes(b"source")

            sandbox = create_game_sandbox(
                root,
                root=Path(temporary) / "sandboxes",
                save_names={"SV020.E5S"},
            )

            self.assertEqual(
                ["SV020.E5S"],
                [path.name for path in (sandbox / "SV").iterdir()],
            )
            self.assertFalse(
                os.path.samefile(
                    root / "SV" / "SV020.E5S",
                    sandbox / "SV" / "SV020.E5S",
                )
            )

    def test_requested_source_save_must_exist(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "game"
            (root / "SV").mkdir(parents=True)
            (root / "Ekd5.exe").write_bytes(b"game")

            with self.assertRaises(FileNotFoundError):
                create_game_sandbox(
                    root,
                    root=Path(temporary) / "sandboxes",
                    save_names={"SV020.E5S"},
                )

    def test_stale_cleanup_keeps_live_session_and_removes_dead_session(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "sandboxes"
            live = root / "100-1"
            dead = root / "200-2"
            live.mkdir(parents=True)
            dead.mkdir()
            (live / "in-use").write_bytes(b"live")
            (dead / "leftover").write_bytes(b"dead")

            with patch(
                "ccz_randomizer.runtime.game_sandbox._process_is_running",
                side_effect=lambda pid: pid == 100,
            ):
                removed = cleanup_stale_sandboxes(root)

            self.assertEqual([dead], removed)
            self.assertTrue(live.is_dir())
            self.assertFalse(dead.exists())

    def test_recent_unknown_sandbox_is_not_removed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "sandboxes"
            unknown = root / "legacy-worker"
            unknown.mkdir(parents=True)

            removed = cleanup_stale_sandboxes(
                root,
                now=unknown.stat().st_mtime + 60,
            )

            self.assertEqual([], removed)
            self.assertTrue(unknown.is_dir())


if __name__ == "__main__":
    unittest.main()
