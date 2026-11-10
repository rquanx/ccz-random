import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from ccz_randomizer.profile_updates import (
    UPDATE_FAILED_MESSAGE,
    show_profile_update_dialog, startup_profile_check,
)
from ccz_randomizer.profile_feed import DEFAULT_PACKAGE_URL
from ccz_randomizer.profiles import load_profile, profile_storage_root
from tools.build_profile_package import build_package


def immediate_background(parent, action, done, failed):
    try:
        result = action()
    except Exception as error:
        failed(error)
    else:
        done(result)


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class ProfileUpdateTests(unittest.TestCase):
    def test_unpublished_feed_is_green_but_other_failures_remain_distinct(self):
        from ccz_randomizer.ui.profile_status import STATES, STATUS_TOOLTIPS
        from ccz_randomizer.profile_feed import DEFAULT_FEED_URL
        feed = {"profileId": load_profile().profile_id, "catalogVersion": 999}
        missing = HTTPError(DEFAULT_FEED_URL, 404, "Not Found", {}, None)
        for check, install, expected in (
            (None, None, "latest"),
            (missing, None, "local"),
            (OSError("offline"), None, "unknown"),
            (HTTPError(DEFAULT_FEED_URL, 403, "Forbidden", {}, None), None, "unknown"),
            (HTTPError(DEFAULT_FEED_URL, 500, "Server Error", {}, None), None, "unknown"),
            (ValueError("incompatible feed"), None, "unknown"),
            (feed, missing, "old"),
        ):
            with self.subTest(expected=expected, error=str(check)):
                states, notices = [], []
                outcome = {"side_effect": check} if isinstance(check, Exception) else {"return_value": check}
                with patch("ccz_randomizer.profile_updates.background_call", side_effect=immediate_background), \
                     patch("ccz_randomizer.profile_updates.check_profile_update", **outcome), \
                     patch("ccz_randomizer.profile_updates.install_feed_update", side_effect=install):
                    startup_profile_check(Mock(), Path("unused"), notices.append, on_state=states.append)
                self.assertEqual(expected, states[-1])
                self.assertEqual("checking", states[0])
                self.assertEqual([UPDATE_FAILED_MESSAGE] if expected == "old" else [], notices)
        self.assertEqual(STATES["latest"][1], STATES["local"][1])
        self.assertEqual("暂无可用更新，正在使用本地数据包。", STATUS_TOOLTIPS["local"])

    def test_startup_only_notifies_install_failure_after_update_was_found(self):
        feed = {"profileId": load_profile().profile_id, "catalogVersion": 3}
        for check, install, messages in (
            (None, None, []),
            (OSError("feed unavailable"), None, []),
            (ValueError("incompatible feed"), None, []),
            (feed, load_profile(), []),
            (feed, OSError("download failed"), [UPDATE_FAILED_MESSAGE]),
            (feed, ValueError("checksum mismatch"), [UPDATE_FAILED_MESSAGE]),
        ):
            with self.subTest(check=str(check), install=str(install)):
                notices = []
                errors = []
                def outcome(value):
                    return {"side_effect": value} if isinstance(value, Exception) else {"return_value": value}
                with patch("ccz_randomizer.profile_updates.background_call", side_effect=immediate_background), \
                     patch("ccz_randomizer.profile_updates.check_profile_update", **outcome(check)), \
                     patch("ccz_randomizer.profile_updates.install_feed_update", **outcome(install)) as installer:
                    startup_profile_check(None, Path("unused"), notices.append, errors.append)
                self.assertEqual(1 if isinstance(check, dict) else 0, installer.call_count)
                self.assertEqual(messages, notices)
                expected_error = check if isinstance(check, Exception) else install
                self.assertEqual([expected_error] if isinstance(expected_error, Exception) else [], errors)

    def test_manual_dialog_download_and_rejected_import(self):
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        with tempfile.TemporaryDirectory() as temp:
            appdir = Path(temp)
            invalid = appdir / "invalid.zip"
            invalid.write_bytes(b"not a ZIP")
            show_profile_update_dialog(root, appdir)
            dialog = next(child for child in root.winfo_children() if isinstance(child, tk.Toplevel))
            buttons = {widget.cget("text"): widget for widget in descendants(dialog) if isinstance(widget, tk.Button)}
            self.assertEqual({"下载文件", "上传数据包"}, set(buttons))
            labels = "\n".join(widget.cget("text") for widget in descendants(dialog) if isinstance(widget, tk.Label))
            self.assertIn("自动更新失败", labels)
            with patch("ccz_randomizer.profile_updates.webbrowser.open", return_value=True) as browser:
                buttons["下载文件"].invoke()
                self.assertEqual(DEFAULT_PACKAGE_URL, browser.call_args.args[0])
            with patch("ccz_randomizer.profile_updates.filedialog.askopenfilename", return_value=str(invalid)), \
                 patch("ccz_randomizer.profile_updates.background_call", side_effect=immediate_background):
                buttons["上传数据包"].invoke()
            statuses = [widget.cget("textvariable") for widget in descendants(dialog) if isinstance(widget, tk.Label)]
            self.assertTrue(any("更新失败" in str(root.getvar(variable)) for variable in statuses if variable))
            self.assertFalse((profile_storage_root(appdir) / "active.json").exists())
            self.assertEqual("normal", str(buttons["上传数据包"].cget("state")))

    def test_manual_upload_installs_valid_package(self):
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            archive = build_package(load_profile().root, folder / "profile.zip")
            appdir = folder / "app"
            show_profile_update_dialog(root, appdir)
            upload = next(widget for widget in descendants(root)
                          if isinstance(widget, tk.Button) and widget.cget("text") == "上传数据包")
            with patch("ccz_randomizer.profile_updates.filedialog.askopenfilename", return_value=str(archive)), \
                 patch("ccz_randomizer.profile_updates.background_call", side_effect=immediate_background):
                upload.invoke()
            active = load_profile(app_directory=appdir)
            self.assertTrue(active.root.is_relative_to(profile_storage_root(appdir)))
            self.assertEqual(load_profile().manifest, active.manifest)
