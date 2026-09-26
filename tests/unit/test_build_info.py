from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ccz_randomizer.app import (
    application_build_info,
    build_version_text,
    format_user_log,
)


class BuildInfoTests(unittest.TestCase):
    def tearDown(self) -> None:
        application_build_info.cache_clear()

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


if __name__ == "__main__":
    unittest.main()
