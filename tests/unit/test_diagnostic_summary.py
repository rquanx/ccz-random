import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ccz_randomizer import app as app_module
from ccz_randomizer.diagnostics.runtime import start_diagnostic_run


class DiagnosticSummaryTests(unittest.TestCase):
    def test_summary_preserves_run_metadata_and_groups_same_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "diagnostic_summary.json"
            start_diagnostic_run(phase="test")
            with (
                patch.object(
                    app_module, "DIAGNOSTIC_SUMMARY_PATH", path
                ),
                patch.object(
                    app_module, "DIAGNOSTIC_FAILURE_COUNTS", {}
                ),
                patch.object(
                    app_module, "DIAGNOSTIC_FAILURE_HISTORY", []
                ),
                patch.object(
                    app_module, "DIAGNOSTIC_SUMMARY_FIELDS", {}
                ),
            ):
                app_module.update_diagnostic_summary(
                    status="running",
                    build={"version": "2.11"},
                    mode="seven",
                )
                for _ in range(2):
                    try:
                        raise RuntimeError("same failure")
                    except RuntimeError as exc:
                        app_module.diagnostic_error("attempt_failed", exc)

                summary = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual("failed", summary["status"])
        self.assertEqual("2.11", summary["build"]["version"])
        self.assertEqual("seven", summary["mode"])
        self.assertEqual(1, len(summary["failure_counts"]))
        self.assertEqual(2, next(iter(summary["failure_counts"].values())))
        self.assertEqual(2, len(summary["recent_failures"]))


if __name__ == "__main__":
    unittest.main()
