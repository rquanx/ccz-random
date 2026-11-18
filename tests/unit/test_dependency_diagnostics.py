"""Regression coverage for the user's 2026-11-15 win32ui failure log."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from ccz_randomizer.diagnostics import dependencies as health


SYSTEM = dict(major=10, version="10.0.19045", os_arch="x64", tool_arch="x64")
FAILURE = (Path(__file__).parents[1] / "fixtures/win32ui_dll_failure.log").read_text(encoding="utf-8")


class DependencyDiagnosticsTests(unittest.TestCase):
    def test_real_failure_provides_official_installer_matching_tool_architecture(self):
        for os_arch, tool_arch in (("x64", "x64"), ("x64", "x86"), ("arm64", "x64"), ("arm64", "arm64")):
            with self.subTest(os_arch=os_arch, tool_arch=tool_arch):
                guidance = health.dependency_guidance(FAILURE, dict(SYSTEM, os_arch=os_arch, tool_arch=tool_arch))
                self.assertIn("可能", guidance["message"])
                self.assertIn("MFC", guidance["message"])
                self.assertEqual(f"https://aka.ms/vc14/vc_redist.{tool_arch}.exe", guidance["downloads"][0]["url"])

    def test_old_windows_does_not_recommend_unsupported_latest_installer(self):
        guidance = health.dependency_guidance(FAILURE, dict(SYSTEM, major=6, version="6.1.7601"))
        self.assertIn("不支持", guidance["message"])
        self.assertEqual([health.VC_DOCUMENTATION], [row["url"] for row in guidance["downloads"]])

    def test_missing_component_and_wrong_architecture_do_not_blame_runtime(self):
        for error in ("win32ui 组件文件不存在", "ModuleNotFoundError: No module named 'cv2'", "[WinError 193] %1 不是有效的 Win32 应用程序"):
            with self.subTest(error=error):
                guidance = health.dependency_guidance(error, SYSTEM)
                self.assertEqual([], guidance["downloads"])
                self.assertIn("工具", guidance["message"])

    def test_probe_detects_missing_mfc_even_when_gui_crt_is_already_available(self):
        def load(library):
            if library == "mfc140u.dll":
                raise OSError("[WinError 126] 找不到指定的模块。")
        def component(name, _bundle):
            if name == "win32ui":
                raise ImportError(FAILURE.splitlines()[-1])
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(health, "system_information", return_value=SYSTEM), \
             patch.object(health.ctypes, "WinDLL", side_effect=load), \
             patch.object(health.os, "add_dll_directory"), \
             patch.object(health, "_load_component", side_effect=component):
            checks = health.probe_runtime(Path(folder))
        failed = {row["label"] for row in checks if not row["ok"]}
        self.assertEqual({"mfc140u.dll", "win32ui"}, failed)
        self.assertEqual([dict(label="微软 VC++ x64 运行库", url=health.VC_DOWNLOADS["x64"])], health.official_downloads(checks))
        self.assertIn("DLL load failed", "\n".join(health.format_checks(checks)))

    def test_current_success_does_not_recommend_installing_dependencies(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(health, "system_information", return_value=SYSTEM), \
             patch.object(health.ctypes, "WinDLL"), \
             patch.object(health.os, "add_dll_directory"), \
             patch.object(health, "_load_component"):
            checks = health.probe_runtime(Path(folder))
        self.assertTrue(all(row["ok"] for row in checks))
        self.assertEqual([], health.official_downloads(checks))

    def test_missing_bundled_win32ui_is_not_hidden_by_an_installed_pywin32(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ModuleNotFoundError, "组件文件不存在"):
                health._load_component("win32ui", Path(folder))

    def test_child_result_file_works_without_stdout_and_uses_safe_command(self):
        expected = [dict(label="win32ui", ok=False, message="组件加载失败。")]
        def run(command, **kwargs):
            self.assertEqual(["tool.exe", "--diagnose-runtime"], command[:2])
            self.assertEqual(30, kwargs["timeout"])
            self.assertNotIn("--worker", command)
            Path(command[2]).write_text(json.dumps(expected), encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout=None, stderr=None)
        with patch.object(health.subprocess, "run", side_effect=run):
            self.assertEqual(expected, health.inspect_runtime_dependencies(["tool.exe"], Path(".")))

    def test_child_failure_timeout_and_invalid_results_cannot_report_success(self):
        for result in (None, [], {}, [dict(label="x", ok="false", message="x")]):
            def run(command, **kwargs):
                if result is None:
                    raise TimeoutError("timeout")
                Path(command[-1]).write_text(json.dumps(result), encoding="utf-8")
                return SimpleNamespace(returncode=0)
            with self.subTest(result=result), patch.object(health.subprocess, "run", side_effect=run):
                checks = health.inspect_runtime_dependencies(["tool.exe"], Path("."))
                self.assertFalse(checks[0]["ok"])

    def test_only_verified_official_links_are_exposed(self):
        self.assertEqual([], health.official_downloads([dict(downloads=[dict(label="bad", url="https://example.com/redist.exe")])]))

    def test_diagnostic_cli_never_enters_gui_or_random_worker(self):
        from ccz_randomizer import app
        expected = [dict(label="win32ui", ok=False, message="加载失败")]
        with tempfile.TemporaryDirectory() as folder:
            result = Path(folder) / "report.json"
            with patch.object(app.sys, "argv", ["tool.exe", "--diagnose-runtime", str(result), "--worker"]), \
                 patch.object(health, "probe_runtime", return_value=expected), \
                 patch.object(app, "main") as worker, patch.object(app, "gui_main") as gui:
                self.assertEqual(0, app.run_cli())
            self.assertEqual(expected, json.loads(result.read_text(encoding="utf-8")))
            worker.assert_not_called()
            gui.assert_not_called()
