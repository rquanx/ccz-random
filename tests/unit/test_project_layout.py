from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
