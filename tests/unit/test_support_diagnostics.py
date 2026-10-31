import tempfile
import unittest
from pathlib import Path

from ccz_randomizer.support_diagnostics import create_log_archive, inspect_environment


class SupportDiagnosticsTests(unittest.TestCase):
    def test_environment_checks_report_missing_components_and_writable_dirs(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            game = base / "Ekd5.exe"
            game.write_bytes(b"game")
            native = base / "native"
            native.mkdir()
            (native / "ccz_injector.exe").write_bytes(b"injector")
            (native / "ccz_control.dll").write_bytes(b"control")
            checks = inspect_environment(
                game,
                app_root=base,
                native_root=native,
                bundle_root=base / "bundle",
                log_root=base / "logs",
            )
            self.assertTrue(any(item["label"] == "游戏目录" and item["ok"] for item in checks))
            self.assertTrue(any(item["label"] == "日志目录" and item["ok"] for item in checks))
            self.assertTrue(any(item["label"] == "工具组件" and not item["ok"] for item in checks))

    def test_archive_is_bounded_and_contains_recent_logs(self):
        with tempfile.TemporaryDirectory() as root:
            log_root = Path(root)
            (log_root / "old.log").write_text("old", encoding="utf-8")
            (log_root / "latest.log").write_text("latest", encoding="utf-8")
            archive = create_log_archive(log_root, extra={"case": "test"})
            self.assertTrue(archive.is_file())
            self.assertLessEqual(archive.stat().st_size, 8 * 1024 * 1024 + 4096)
            import zipfile
            with zipfile.ZipFile(archive) as bundle:
                self.assertIn("manifest.json", bundle.namelist())
                self.assertIn("latest.log", bundle.namelist())


if __name__ == "__main__":
    unittest.main()
