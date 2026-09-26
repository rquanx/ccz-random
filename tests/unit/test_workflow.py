import unittest

from random_workflow import (
    AttemptResult,
    run_random_workflow,
    validate_reloaded_jobs,
)


class WorkflowTests(unittest.TestCase):
    def test_rejections_reuse_session_and_advance_after_acceptance(self):
        calls = []
        outcomes = iter([False, False, True, True])

        def run_attempt(slot, attempt, source_loaded):
            calls.append((slot, attempt, source_loaded))
            return AttemptResult(next(outcomes), True, f"{slot}-{attempt}")

        results = run_random_workflow(
            result_count=2,
            max_attempts=10,
            run_attempt=run_attempt,
            recover_session=lambda *_args: self.fail("unexpected recovery"),
            should_recover=lambda _exc: False,
        )

        self.assertEqual(
            [(1, 1, False), (1, 2, True), (1, 3, True), (2, 1, True)],
            calls,
        )
        self.assertEqual([(1, 3), (2, 1)], [
            (result.result_slot, result.round_index) for result in results
        ])

    def test_fifteen_results_are_completed_in_order(self):
        accepted = []
        results = run_random_workflow(
            result_count=15,
            max_attempts=1,
            run_attempt=lambda slot, _attempt, _loaded: AttemptResult(
                True, True, slot
            ),
            recover_session=lambda *_args: None,
            should_recover=lambda _exc: False,
            on_accepted=lambda result: accepted.append(result.result_slot),
        )
        self.assertEqual(list(range(1, 16)), accepted)
        self.assertEqual(list(range(1, 16)), [
            result.payload for result in results
        ])

    def test_recoverable_failure_restarts_once_and_resets_source_state(self):
        calls = []
        recoveries = []
        errors = []

        def run_attempt(slot, attempt, source_loaded):
            calls.append((slot, attempt, source_loaded))
            if len(calls) == 2:
                raise RuntimeError("game unavailable")
            return AttemptResult(len(calls) > 2, True, "ok")

        run_random_workflow(
            result_count=1,
            max_attempts=3,
            run_attempt=run_attempt,
            recover_session=lambda exc, slot, attempt: recoveries.append(
                (str(exc), slot, attempt)
            ),
            should_recover=lambda exc: "unavailable" in str(exc),
            on_attempt_error=lambda *args: errors.append(args[1:]),
        )

        self.assertEqual(
            [(1, 1, False), (1, 2, True), (1, 2, False)],
            calls,
        )
        self.assertEqual([("game unavailable", 1, 2)], recoveries)
        self.assertEqual([(1, 2, 0, True, True)], errors)

    def test_attempt_finished_reports_rejected_and_accepted_results(self):
        finished = []
        outcomes = iter([False, True])

        run_random_workflow(
            result_count=1,
            max_attempts=2,
            run_attempt=lambda *_args: AttemptResult(
                next(outcomes), True, "payload"
            ),
            recover_session=lambda *_args: None,
            should_recover=lambda _exc: False,
            on_attempt_finished=lambda slot, attempt, result: finished.append(
                (slot, attempt, result.accepted, result.source_loaded)
            ),
        )

        self.assertEqual(
            [(1, 1, False, True), (1, 2, True, True)],
            finished,
        )

    def test_second_failure_after_recovery_is_raised(self):
        recoveries = []

        def fail(*_args):
            raise RuntimeError("game unavailable")

        with self.assertRaisesRegex(RuntimeError, "game unavailable"):
            run_random_workflow(
                result_count=1,
                max_attempts=1,
                run_attempt=fail,
                recover_session=lambda *_args: recoveries.append("restart"),
                should_recover=lambda _exc: True,
            )
        self.assertEqual(["restart"], recoveries)

    def test_nonrecoverable_failure_is_raised_without_restart(self):
        recoveries = []

        with self.assertRaisesRegex(RuntimeError, "invalid source"):
            run_random_workflow(
                result_count=1,
                max_attempts=1,
                run_attempt=lambda *_args: (_ for _ in ()).throw(
                    RuntimeError("invalid source")
                ),
                recover_session=lambda *_args: recoveries.append("restart"),
                should_recover=lambda _exc: False,
            )
        self.assertEqual([], recoveries)

    def test_accepted_callback_failure_stops_without_error_handler(self):
        with self.assertRaisesRegex(RuntimeError, "save failed"):
            run_random_workflow(
                result_count=2,
                max_attempts=1,
                run_attempt=lambda slot, *_args: AttemptResult(
                    True, True, slot
                ),
                recover_session=lambda *_args: None,
                should_recover=lambda _exc: False,
                on_accepted=lambda _result: (_ for _ in ()).throw(
                    RuntimeError("save failed")
                ),
            )

    def test_accepted_callback_failure_keeps_result_and_advances(self):
        errors = []
        calls = []
        results = run_random_workflow(
            result_count=2,
            max_attempts=1,
            run_attempt=lambda slot, *_args: AttemptResult(
                True, True, slot
            ),
            recover_session=lambda *_args: None,
            should_recover=lambda _exc: False,
            on_accepted=lambda result: (
                (_ for _ in ()).throw(RuntimeError("image failed"))
                if result.result_slot == 1
                else calls.append(result.result_slot)
            ),
            on_accepted_error=lambda exc, result: errors.append(
                (str(exc), result.result_slot)
            ),
        )

        self.assertEqual([("image failed", 1)], errors)
        self.assertEqual([2], calls)
        self.assertEqual([1, 2], [result.result_slot for result in results])

    def test_stop_request_interrupts_before_next_attempt(self):
        checks = 0

        def check_stop():
            nonlocal checks
            checks += 1
            if checks == 3:
                raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            run_random_workflow(
                result_count=1,
                max_attempts=10,
                run_attempt=lambda *_args: AttemptResult(False, True, None),
                recover_session=lambda *_args: None,
                should_recover=lambda _exc: False,
                check_stop=check_stop,
            )

    def test_attempt_limit_has_clear_error(self):
        with self.assertRaisesRegex(
            RuntimeError,
            "结果 1 连续 2 轮未产生满足条件的结果",
        ):
            run_random_workflow(
                result_count=1,
                max_attempts=2,
                run_attempt=lambda *_args: AttemptResult(False, True, None),
                recover_session=lambda *_args: None,
                should_recover=lambda _exc: False,
            )

    def test_invalid_limits_are_rejected(self):
        common = {
            "run_attempt": lambda *_args: AttemptResult(True, True, None),
            "recover_session": lambda *_args: None,
            "should_recover": lambda _exc: False,
        }
        with self.assertRaises(ValueError):
            run_random_workflow(result_count=0, max_attempts=1, **common)
        with self.assertRaises(ValueError):
            run_random_workflow(result_count=1, max_attempts=0, **common)

    def test_seven_person_reload_mismatch_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "回读七人兵种不一致"):
            validate_reloaded_jobs(
                output_slot=2,
                expected_jobs=(1, 2, 3, 4, 5, 6, 7),
                expected_initial_three=(1, 2, 4),
                reloaded_jobs=(1, 2, 3, 4, 5, 6, 8),
                initial_three=(1, 2, 4),
                three_person_mode=False,
            )

    def test_three_person_mode_only_validates_initial_members(self):
        validate_reloaded_jobs(
            output_slot=1,
            expected_jobs=(),
            expected_initial_three=(1, 2, 4),
            reloaded_jobs=(1, 2, 4),
            initial_three=(1, 2, 4),
            three_person_mode=True,
        )
        with self.assertRaisesRegex(RuntimeError, "回读初始三人兵种不一致"):
            validate_reloaded_jobs(
                output_slot=1,
                expected_jobs=(),
                expected_initial_three=(1, 2, 4),
                reloaded_jobs=(1, 2, 5),
                initial_three=(1, 2, 5),
                three_person_mode=True,
            )


if __name__ == "__main__":
    unittest.main()
