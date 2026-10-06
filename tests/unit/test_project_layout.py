from __future__ import annotations

import unittest
from pathlib import Path

from ccz_randomizer.app import (
    bundled_original_s00,
    bundled_random_s00,
    ui_asset_path,
)


class ProjectLayoutTests(unittest.TestCase):
    def test_development_app_resources_exist(self) -> None:
        self.assertTrue(bundled_random_s00().is_file())
        self.assertTrue(bundled_original_s00().is_file())
        self.assertTrue(ui_asset_path("source_slot_20_help.png").is_file())

    def test_release_script_uses_an_explicit_spec_file(self) -> None:
        script = (
            Path(__file__).resolve().parents[2]
            / "tools"
            / "windows"
            / "build_release.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn(
            '[string]$SpecPath = "packaging\\CCZ_真实随机内存快筛版.spec"',
            script,
        )
        self.assertNotIn("Sort-Object Length", script)


if __name__ == "__main__":
    unittest.main()
