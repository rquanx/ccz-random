import tempfile
import unittest
from pathlib import Path
import io
import json
import threading
import zipfile
from unittest.mock import Mock, patch

from ccz_randomizer.support_diagnostics import create_log_archive, inspect_environment
from ccz_randomizer import support_diagnostics as support


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

    def test_archive_excludes_previous_support_archives(self):
        with tempfile.TemporaryDirectory() as root:
            log_root = Path(root)
            (log_root / "support_previous.zip").write_bytes(b"old report")
            (log_root / "latest.log").write_bytes(b"new log")
            with zipfile.ZipFile(create_log_archive(log_root)) as bundle:
                self.assertEqual({"manifest.json", "latest.log"}, set(bundle.namelist()))

    def test_large_log_preserves_only_tail_without_unbounded_reads(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            source, target = base / "large.log", base / "tail.log"
            source.write_bytes(b"discarded" + b"x" * support.MAX_FILE_BYTES)
            real_open = Path.open
            reads = []

            class BoundedReader:
                def __enter__(self):
                    self.handle = real_open(source, "rb")
                    return self
                def __exit__(self, *args):
                    self.handle.close()
                def seek(self, *args):
                    return self.handle.seek(*args)
                def read(self, size=-1):
                    reads.append(size)
                    if size < 0 or size > support.MAX_FILE_BYTES:
                        raise AssertionError("unbounded log read")
                    return self.handle.read(size)

            def open_file(path, *args, **kwargs):
                return BoundedReader() if path == source else real_open(path, *args, **kwargs)

            with patch.object(Path, "open", open_file):
                support._bounded_copy(source, target)
            self.assertEqual([support.MAX_FILE_BYTES], reads)
            self.assertEqual("[文件过大，仅保留末尾内容]\n".encode() + b"x" * support.MAX_FILE_BYTES,
                             target.read_bytes())


class UploadCompatibilityTests(unittest.TestCase):
    # The JSON envelope and TLS reset fallback are the provider contract and
    # failure handled by f21b782 / 784da56; no real user logs leave the machine.
    response = json.dumps({"data": {"url": "https://tmpfiles.org/123/support.zip"}}).encode()

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.archive = Path(self.folder.name) / "日志.zip"
        self.archive.write_bytes(b"zip fixture")

    def test_https_upload_returns_copyable_provider_url_and_finishes_progress(self):
        progress = Mock()
        with patch.object(support.urllib.request, "urlopen", return_value=io.BytesIO(self.response)), \
             patch.object(support.subprocess, "Popen") as fallback:
            url = support.upload_log_archive(self.archive, progress_callback=progress)
        self.assertEqual("https://tmpfiles.org/123/support.zip", url)
        self.assertEqual(0, progress.call_args_list[0].args[0])
        sent, total = progress.call_args_list[-1].args
        self.assertEqual(sent, total)
        self.assertGreater(total, self.archive.stat().st_size)
        fallback.assert_not_called()

    def test_tls_reset_falls_back_to_curl_and_returns_same_url(self):
        child = Mock(returncode=0)
        child.poll.return_value = 0
        child.communicate.return_value = (self.response, b"")
        with patch.object(support.urllib.request, "urlopen", side_effect=ConnectionResetError("TLS reset")), \
             patch.object(support.subprocess, "Popen", return_value=child):
            self.assertEqual("https://tmpfiles.org/123/support.zip", support.upload_log_archive(self.archive))

    def test_cancel_before_upload_never_sends_data(self):
        cancel = threading.Event()
        cancel.set()
        with patch.object(support.urllib.request, "urlopen") as network, \
             patch.object(support.subprocess, "Popen") as fallback:
            with self.assertRaises(support.UploadCancelled):
                support.upload_log_archive(self.archive, cancel_event=cancel)
        network.assert_not_called()
        fallback.assert_not_called()

    def test_cancel_during_curl_kills_and_reaps_child(self):
        cancel = threading.Event()
        child = Mock(returncode=None)
        def running():
            cancel.set()
            return None
        child.poll.side_effect = running
        with patch.object(support.urllib.request, "urlopen", side_effect=ConnectionResetError("TLS reset")), \
             patch.object(support.subprocess, "Popen", return_value=child):
            with self.assertRaises(support.UploadCancelled):
                support.upload_log_archive(self.archive, cancel_event=cancel)
        child.kill.assert_called_once()
        child.wait.assert_called_once()

    def test_curl_timeout_kills_and_reaps_child(self):
        child = Mock(returncode=None)
        child.poll.return_value = None
        with patch.object(support.urllib.request, "urlopen", side_effect=ConnectionResetError("TLS reset")), \
             patch.object(support.subprocess, "Popen", return_value=child), \
             patch.object(support.time, "monotonic", side_effect=[0, 40]):
            with self.assertRaisesRegex(RuntimeError, "超时"):
                support.upload_log_archive(self.archive, timeout=1)
        child.kill.assert_called_once()
        child.wait.assert_called_once()

    def test_curl_error_keeps_diagnostic_message(self):
        child = Mock(returncode=35)
        child.poll.return_value = 35
        child.communicate.return_value = (b"", b"SSL connect error")
        with patch.object(support.urllib.request, "urlopen", side_effect=ConnectionResetError("TLS reset")), \
             patch.object(support.subprocess, "Popen", return_value=child):
            with self.assertRaisesRegex(RuntimeError, "SSL connect error"):
                support.upload_log_archive(self.archive)

    def test_invalid_provider_response_is_rejected(self):
        for response in (b"not json", b"{}", b'{"data":{"url":"file:///private"}}'):
            with self.subTest(response=response), \
                 patch.object(support.urllib.request, "urlopen", return_value=io.BytesIO(response)):
                with self.assertRaisesRegex(RuntimeError, "无效"):
                    support.upload_log_archive(self.archive)


if __name__ == "__main__":
    unittest.main()
