import os
"""Exercise real Tk upload buttons without sending logs to a server."""
from ccz_randomizer.ui.inputs import TextEntry
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from ccz_randomizer import app


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class SupportUiTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)

    def test_grouped_menu_routes_each_action_to_the_same_dialog(self):
        from ccz_randomizer.ui.support_menu import show_support_menu
        root = tk.Tk()
        self.addCleanup(root.destroy)
        root.withdraw()
        calls = []
        keys = ("guide", "effects", "diagnostics", "sound", "logs", "update", "cleanup")
        actions = {key: lambda parent, key=key: calls.append((key, parent)) for key in keys}
        dialog = show_support_menu(root, actions, "3")
        root.update()
        buttons = [widget for widget in descendants(dialog) if isinstance(widget, tk.Button)]
        self.assertEqual(["不会用？", "特效字典", "随机用不了？", "游戏没声音", "上传最新日志", "手动更新数据（3）", "空间清理", "关闭"],
            [button.cget("text") for button in buttons])
        headings = [widget.cget("text") for widget in descendants(dialog) if isinstance(widget, tk.Label)]
        self.assertEqual(["使用帮助", "故障排查", "数据与维护"], headings)
        for button in buttons[:-1]:
            button.invoke()
        self.assertEqual([(key, dialog) for key in keys], calls)
        buttons[-1].invoke()
        self.assertFalse(dialog.winfo_exists())

    def test_upload_failure_can_retry_and_success_url_can_be_copied(self):
        targets = []
        errors = []
        url = "https://tmpfiles.org/123/support.zip"

        def capture_thread_start(thread):
            targets.append(thread._target)

        def exercise(root):
            state = sys._getframe(1).f_locals
            def wait_until(predicate):
                import time
                deadline = time.monotonic() + 3
                while not predicate() and time.monotonic() < deadline:
                    root.update()
                    time.sleep(.002)
                self.assertTrue(predicate())
            try:
                state["open_log_upload_progress"]()
                targets.pop()()
                wait_until(lambda: any(isinstance(w, tk.Button) and w.cget("text") == "再次上传"
                                       for w in descendants(root)))
                retry = next(w for w in descendants(root)
                             if isinstance(w, tk.Button) and w.cget("text") == "再次上传")
                retry.invoke()
                targets.pop()()
                wait_until(lambda: any(isinstance(w, TextEntry) and w.get() == url
                                       for w in descendants(root)))
                entry = next(w for w in descendants(root)
                             if isinstance(w, TextEntry) and w.get() == url)
                self.assertEqual(url, entry.get())
                copy = next(w for w in descendants(root)
                            if isinstance(w, tk.Button) and w.cget("text") == "复制地址")
                copy.invoke()
                root.update()
                self.assertEqual(url, root.clipboard_get())
                self.assertFalse(any(isinstance(w, tk.Button) and w.cget("text") == "再次上传"
                                     for w in descendants(root)))
            finally:
                # Let each toplevel cancel timers it owns before cancelling
                # root callbacks; Tk keeps command ownership per widget.
                for child in list(root.winfo_children()):
                    if isinstance(child, tk.Toplevel):
                        child.destroy()
                for child in list(root.winfo_children()):
                    child.destroy()
                for callback in root.tk.call("after", "info"):
                    root.after_cancel(callback)
                root.destroy()

        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "support.zip"
            archive.write_bytes(b"local test logs")
            with patch.object(tk.Tk, "mainloop", exercise), \
                 patch.object(tk.Tk, "report_callback_exception", lambda _self, *exc: errors.append(exc)), \
                 patch.object(app, "app_dir", return_value=Path(folder)), \
                 patch.object(app, "create_log_archive", return_value=archive), \
                 patch.object(app, "upload_log_archive", side_effect=[RuntimeError("TLS reset"), url]) as upload, \
                 patch("ccz_randomizer.profile_session.startup_profile_check"), \
                 patch("tkinter.messagebox.askyesno", return_value=True), \
                 patch.object(app.threading.Thread, "start", capture_thread_start):
                app.gui_main()
            self.assertEqual(2, upload.call_count)
            self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
