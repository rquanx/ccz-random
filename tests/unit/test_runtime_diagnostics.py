import unittest
from unittest.mock import patch

from ccz_randomizer.diagnostics.runtime import (
    build_diagnostic_record,
    classify_exception,
    exception_diagnostic,
    start_diagnostic_run,
    update_diagnostic_context,
)


class FakeNativeError(RuntimeError):
    def __init__(self, return_code, details=""):
        self.return_code = return_code
        self.details = details
        super().__init__(details)


FakeNativeError.__name__ = "NativeControlError"


class RuntimeDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        start_diagnostic_run(mode="seven")

    def test_records_include_sequence_context_and_elapsed_time(self):
        update_diagnostic_context(phase="randomize", result_slot=2, attempt=4)
        first = build_diagnostic_record("attempt_started")
        second = build_diagnostic_record("attempt_finished")

        self.assertEqual(1, first["sequence"])
        self.assertEqual(2, second["sequence"])
        self.assertEqual("randomize", second["context"]["phase"])
        self.assertEqual(2, second["context"]["result_slot"])
        self.assertGreaterEqual(second["elapsed_ms"], first["elapsed_ms"])

    def test_native_transport_error_is_classified(self):
        result = classify_exception(FakeNativeError(207, "timeout"))

        self.assertEqual("native_control", result["layer"])
        self.assertEqual("native_failure", result["category"])
        self.assertEqual(207, result["code"])

    def test_exception_contains_chain_and_recent_events(self):
        build_diagnostic_record("load_started")
        try:
            try:
                raise OSError(32, "file busy")
            except OSError as cause:
                raise RuntimeError("save failed") from cause
        except RuntimeError as exc:
            result = exception_diagnostic(exc)

        self.assertEqual("RuntimeError", result["exception"]["type"])
        self.assertEqual(2, len(result["chain"]))
        self.assertEqual("load_started", result["recent_events"][-1]["event"])
        self.assertTrue(result["error_id"])
        self.assertIn("RuntimeError", result["traceback"])

    def test_missing_required_file_is_environment_failure(self):
        result = classify_exception(FileNotFoundError("missing Ekd5.exe"))

        self.assertEqual("environment", result["layer"])
        self.assertEqual("required_file_missing", result["category"])

    @patch("ccz_randomizer.diagnostics.runtime.uuid.uuid4")
    def test_start_creates_stable_run_id(self, uuid4):
        uuid4.return_value.hex = "1234567890abcdef"
        run_id = start_diagnostic_run()
        first = build_diagnostic_record("one")
        second = build_diagnostic_record("two")

        self.assertEqual("1234567890ab", run_id)
        self.assertEqual(run_id, first["run_id"])
        self.assertEqual(run_id, second["run_id"])


if __name__ == "__main__":
    unittest.main()
