from __future__ import annotations

import datetime as dt
import os
import tempfile
import unittest
from pathlib import Path

from ccz_randomizer.runtime.log_retention import (
    RotatingTextWriter,
    cleanup_log_directory,
    rotated_log_path,
    trim_text_widget,
)


class FakeTextWidget:
    def __init__(self, lines: list[str]):
        self.lines = list(lines)

    def index(self, _index: str) -> str:
        return f"{len(self.lines) + 1}.0"

    def delete(self, _start: str, end: str) -> None:
        first_kept = int(end.split(".", 1)[0])
        del self.lines[: first_kept - 1]

    def insert(self, index: str, text: str) -> None:
        new_lines = text.rstrip("\n").splitlines()
        if index == "1.0":
            self.lines[:0] = new_lines
        else:
            self.lines.extend(new_lines)


class RotatingTextWriterTests(unittest.TestCase):
    def test_rotates_and_keeps_only_configured_parts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fast_20260926_120000.log"
            writer = RotatingTextWriter(path, max_bytes=10, max_parts=3)
            for value in ("111111\n", "222222\n", "333333\n", "444444\n"):
                writer.write(value)
                writer.flush()
            writer.close()

            self.assertEqual(path.read_text(encoding="utf-8"), "222222\n")
            self.assertEqual(
                rotated_log_path(path, 2).read_text(encoding="utf-8"),
                "333333\n",
            )
            self.assertEqual(
                rotated_log_path(path, 3).read_text(encoding="utf-8"),
                "444444\n",
            )
            self.assertFalse(rotated_log_path(path, 4).exists())


class CleanupLogDirectoryTests(unittest.TestCase):
    def test_keeps_only_newest_diagnostic_screenshots_per_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            screenshots = []
            for index in range(14):
                path = root / (
                    "fast_20260926_145744_"
                    f"diagnostic_interaction_failure_{index}.png"
                )
                path.write_bytes(bytes([index]) * 5)
                timestamp = dt.datetime(2026, 9, 26, 12, 0, index).timestamp()
                os.utime(path, (timestamp, timestamp))
                screenshots.append(path)
            other_run = root / (
                "fast_20260926_161050_"
                "inspection_failure_roster_slot1.png"
            )
            other_run.write_bytes(b"other")

            result = cleanup_log_directory(
                root,
                now=dt.datetime(2026, 9, 27),
                retention_days=30,
                screenshots_per_run=10,
            )

            self.assertEqual(result.removed_files, 4)
            self.assertTrue(all(not path.exists() for path in screenshots[:4]))
            self.assertTrue(all(path.exists() for path in screenshots[4:]))
            self.assertTrue(other_run.exists())

    def test_removes_expired_managed_files_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old_log = root / "fast_20260801_120000.log"
            old_image = (
                root
                / "fast_20260801_120000_diagnostic_interaction_failure_1.png"
            )
            old_summary = (
                root
                / "fast_20260801_120000_diagnostic_summary.json"
            )
            old_inspection = (
                root
                / "fast_20260801_120000_inspection_slot1_"
                "attempt-1_abc_diagnostic.jsonl"
            )
            unrelated = root / "notes.log"
            for path in (
                old_log,
                old_image,
                old_summary,
                old_inspection,
                unrelated,
            ):
                path.write_bytes(b"x" * 5)
            old_timestamp = dt.datetime(2026, 8, 1).timestamp()
            os.utime(old_log, (old_timestamp, old_timestamp))
            os.utime(old_image, (old_timestamp, old_timestamp))
            os.utime(old_summary, (old_timestamp, old_timestamp))
            os.utime(old_inspection, (old_timestamp, old_timestamp))
            os.utime(unrelated, (old_timestamp, old_timestamp))

            result = cleanup_log_directory(
                root,
                now=dt.datetime(2026, 9, 26),
            )

            self.assertEqual(result.removed_files, 4)
            self.assertFalse(old_log.exists())
            self.assertFalse(old_image.exists())
            self.assertFalse(old_summary.exists())
            self.assertFalse(old_inspection.exists())
            self.assertTrue(unrelated.exists())

    def test_reduces_managed_directory_size_to_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = []
            for index in range(4):
                path = root / f"fast_2026092{index}_120000.log"
                path.write_bytes(bytes([index]) * 10)
                timestamp = dt.datetime(2026, 9, 20 + index).timestamp()
                os.utime(path, (timestamp, timestamp))
                paths.append(path)

            result = cleanup_log_directory(
                root,
                now=dt.datetime(2026, 9, 26),
                retention_days=30,
                limit_bytes=30,
                target_bytes=20,
            )

            self.assertEqual(result.removed_files, 2)
            self.assertEqual(result.remaining_bytes, 20)
            self.assertFalse(paths[0].exists())
            self.assertFalse(paths[1].exists())
            self.assertTrue(paths[2].exists())
            self.assertTrue(paths[3].exists())


class TrimTextWidgetTests(unittest.TestCase):
    def test_trims_old_lines_in_one_batch(self) -> None:
        widget = FakeTextWidget([f"line-{index}" for index in range(13)])

        trimmed = trim_text_widget(
            widget,
            max_lines=12,
            target_lines=10,
            notice="trimmed",
        )

        self.assertTrue(trimmed)
        self.assertEqual(widget.lines[0], "trimmed")
        self.assertEqual(widget.lines[1:], [f"line-{index}" for index in range(3, 13)])

    def test_does_nothing_below_limit(self) -> None:
        widget = FakeTextWidget(["one", "two"])

        self.assertFalse(
            trim_text_widget(widget, max_lines=12, target_lines=10)
        )
        self.assertEqual(widget.lines, ["one", "two"])


if __name__ == "__main__":
    unittest.main()
