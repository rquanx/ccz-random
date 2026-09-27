from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class AttemptResult(Generic[T]):
    accepted: bool
    source_loaded: bool
    payload: T


@dataclass(frozen=True)
class AcceptedResult(Generic[T]):
    result_slot: int
    round_index: int
    payload: T


def run_random_workflow(
    *,
    result_count: int,
    max_attempts: int,
    run_attempt: Callable[[int, int, bool], AttemptResult[T]],
    recover_session: Callable[[BaseException, int, int], None],
    should_recover: Callable[[BaseException], bool],
    on_attempt_started: Callable[[int, int], None] | None = None,
    on_accepted: Callable[[AcceptedResult[T]], None] | None = None,
    on_accepted_error: (
        Callable[[BaseException, AcceptedResult[T]], None] | None
    ) = None,
    on_attempt_error: (
        Callable[[BaseException, int, int, int, bool, bool], None] | None
    ) = None,
    on_attempt_finished: (
        Callable[[int, int, AttemptResult[T]], None] | None
    ) = None,
    check_stop: Callable[[], None] | None = None,
) -> list[AcceptedResult[T]]:
    """Run the result/attempt state machine without depending on the game."""
    if result_count < 1:
        raise ValueError("result_count must be at least 1")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    accepted_results: list[AcceptedResult[T]] = []
    source_loaded = False
    stop_check = check_stop or (lambda: None)

    for result_slot in range(1, result_count + 1):
        stop_check()
        for round_index in range(1, max_attempts + 1):
            stop_check()
            if on_attempt_started is not None:
                on_attempt_started(result_slot, round_index)

            for recovery_attempt in range(2):
                try:
                    attempt = run_attempt(
                        result_slot,
                        round_index,
                        source_loaded,
                    )
                    stop_check()
                    source_loaded = attempt.source_loaded
                    break
                except Exception as exc:
                    stop_check()
                    will_recover = (
                        recovery_attempt == 0 and should_recover(exc)
                    )
                    if on_attempt_error is not None:
                        on_attempt_error(
                            exc,
                            result_slot,
                            round_index,
                            recovery_attempt,
                            source_loaded,
                            will_recover,
                        )
                    if will_recover:
                        stop_check()
                        recover_session(exc, result_slot, round_index)
                        stop_check()
                        source_loaded = False
                        continue
                    raise
            else:
                raise RuntimeError("后台游戏恢复后仍无法继续随机")

            if on_attempt_finished is not None:
                stop_check()
                on_attempt_finished(result_slot, round_index, attempt)
            if attempt.accepted:
                accepted = AcceptedResult(
                    result_slot=result_slot,
                    round_index=round_index,
                    payload=attempt.payload,
                )
                accepted_results.append(accepted)
                if on_accepted is not None:
                    stop_check()
                    try:
                        on_accepted(accepted)
                        stop_check()
                    except Exception as exc:
                        if on_accepted_error is None:
                            raise
                        on_accepted_error(exc, accepted)
                break
        else:
            raise RuntimeError(
                f"结果 {result_slot} 连续 {max_attempts} 轮"
                "未产生满足条件的结果"
            )

    return accepted_results


def validate_reloaded_jobs(
    *,
    output_slot: int,
    expected_jobs: tuple[int, ...],
    expected_initial_three: tuple[int, ...],
    reloaded_jobs: tuple[int, ...],
    initial_three: tuple[int, ...],
    three_person_mode: bool,
) -> None:
    if not three_person_mode and reloaded_jobs != expected_jobs:
        raise RuntimeError(
            f"第 {output_slot} 号存档回读七人兵种不一致："
            f"保存前={expected_jobs}，回读后={reloaded_jobs}"
        )
    if initial_three != expected_initial_three:
        raise RuntimeError(
            f"第 {output_slot} 号存档回读初始三人兵种不一致："
            f"保存前={expected_initial_three}，回读后={initial_three}"
        )
