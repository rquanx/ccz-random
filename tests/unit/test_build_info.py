from __future__ import annotations

import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch

from ccz_randomizer.app import (
    application_changelog,
    application_build_info,
    bind_version_changelog,
    build_version_text,
    format_user_log,
    show_changelog_window,
)


class BuildInfoTests(unittest.TestCase):
    def tearDown(self) -> None:
        application_build_info.cache_clear()
        application_changelog.cache_clear()

    def test_frozen_build_info_is_loaded_from_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "build_info.json").write_text(
                json.dumps(
                    {
                        "version": "2.0.0",
                        "buildId": "20260926.120000-abc123",
                        "gitCommit": "123456789abc",
                        "gitDirty": False,
                    }
                ),
                encoding="utf-8",
            )
            application_build_info.cache_clear()
            with (
                patch("ccz_randomizer.app.sys.frozen", True, create=True),
                patch("ccz_randomizer.app.sys._MEIPASS", str(root), create=True),
            ):
                info = application_build_info()

        self.assertEqual("2.0.0", info["version"])
        self.assertEqual("20260926.120000-abc123", info["buildId"])
        self.assertEqual(
            "2.0.0 | 构建 20260926.120000-abc123 | 源码 123456789abc",
            build_version_text(info),
        )

    def test_dirty_build_is_identified(self) -> None:
        text = build_version_text(
            {
                "version": "2.0.0",
                "buildId": "build",
                "gitCommit": "abcdef",
                "gitDirty": True,
            }
        )

        self.assertIn("abcdef+dirty", text)
        self.assertEqual(
            "",
            format_user_log("工具版本：" + text),
        )

    def test_release_version_is_3_1_1(self) -> None:
        version = (
            Path(__file__).resolve().parents[2] / "VERSION"
        ).read_text(encoding="utf-8").strip()

        self.assertEqual("3.1.1", version)

    def test_changelog_contains_only_verified_release_notes(self) -> None:
        entries = application_changelog()

        self.assertEqual(4, len(entries))
        self.assertEqual("3.1.1", entries[0]["version"])
        self.assertTrue(entries[0]["changes"])

    def test_frozen_changelog_is_loaded_from_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "CHANGELOG.json").write_text(
                json.dumps(
                    [
                        {
                            "version": "9.9.9",
                            "date": "2026-09-29",
                            "changes": ["测试更新"],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            application_changelog.cache_clear()
            with (
                patch("ccz_randomizer.app.sys.frozen", True, create=True),
                patch("ccz_randomizer.app.sys._MEIPASS", str(root), create=True),
            ):
                entries = application_changelog()

        self.assertEqual("9.9.9", entries[0]["version"])
        self.assertEqual(("测试更新",), entries[0]["changes"])

    def test_changelog_window_and_version_double_click_binding(self) -> None:
        root = tk.Tk()
        root.withdraw()
        try:
            label = tk.Label(root, text="V2.2.0")
            bind_version_changelog(label, root)
            self.assertEqual("hand2", label.cget("cursor"))
            self.assertTrue(label.bind("<Double-Button-1>"))

            show_changelog_window(
                root,
                (
                    {
                        "version": "2.2.0",
                        "date": "2026-09-29",
                        "changes": ("新增功能", "修复问题"),
                    },
                ),
            )
            root.update()
            dialog = next(
                child
                for child in root.winfo_children()
                if isinstance(child, tk.Toplevel)
            )
            self.assertEqual("版本更新记录", dialog.title())
            text = next(
                widget
                for widget in dialog.winfo_children()[1].winfo_children()
                if isinstance(widget, tk.Text)
            )
            content = text.get("1.0", "end")
            self.assertIn("V2.2.0", content)
            self.assertIn("新增功能", content)
            dialog.destroy()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
