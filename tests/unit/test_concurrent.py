from __future__ import annotations

import contextlib
import io
import tempfile
import threading
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from ccz_randomizer.runtime.concurrent import (
    CONCURRENT_COMPATIBILITY_FALLBACK_CODE,
    CONCURRENT_HEARTBEAT_LINE,
    DynamicSlotQueue,
    _run_concurrent_batch,
    _run_continuous_loop,
    _TimingRecorder,
    _is_worker_progress_line,
    _should_forward_line,
    decode_concurrent_event,
    encode_concurrent_event,
    partition_slots,
    run_concurrent_workers,
    start_concurrent_worker_heartbeat,
)
from ccz_randomizer.ui.concurrent_console import (
    ConcurrentConsoleState,
    build_console_render_signature,
    extract_result_image_path,
    format_round_heading,
    is_completion_console_line,
)
from ccz_randomizer.ui.result_details import (
    decode_result_detail,
    encode_result_detail,
    format_result_detail,
)


class ConcurrentSchedulingTests(unittest.TestCase):
    def test_timing_recorder_writes_success_and_error_records(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = _TimingRecorder(
                Path(directory),
                mode="seven",
                worker_count=1,
            )
            try:
                with recorder.phase("success", result_slot=1):
                    pass
                with self.assertRaisesRegex(RuntimeError, "expected"):
                    with recorder.phase("failure", result_slot=2):
                        raise RuntimeError("expected")
            finally:
                recorder.close()

            records = [
                json.loads(line)
                for line in recorder.path.read_text(encoding="utf-8").splitlines()
            ]
            finished = {
                record["phase"]: record
                for record in records
                if record["event"] == "timing_finished"
            }
            self.assertEqual("ok", finished["success"]["outcome"])
            self.assertEqual("error", finished["failure"]["outcome"])
            self.assertGreaterEqual(finished["success"]["elapsed_ms"], 0)
            self.assertIn("expected", finished["failure"]["error"])

    def _run_single_slot_scheduler(
        self,
        process_factory,
        *,
        stop_file_enabled: bool = False,
        result_count: int = 1,
    ) -> int:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game_dir = root / "game"
            (game_dir / "SV").mkdir(parents=True)
            game_executable = game_dir / "Ekd5.exe"
            game_executable.write_bytes(b"game")
            (game_dir / "SV" / "SV001.E5S").write_bytes(b"original")
            (game_dir / "SV" / "SV020.E5S").write_bytes(b"source")
            stop_file = root / "stop" if stop_file_enabled else None

            def fake_sandbox(
                _game_dir,
                *,
                root,
                worker_name,
                save_names,
            ):
                del _game_dir, worker_name, save_names
                sandbox = root / "sandbox-1"
                (sandbox / "SV").mkdir(parents=True)
                (sandbox / "Ekd5.exe").write_bytes(b"game")
                (sandbox / "SV" / "SV001.E5S").write_bytes(b"original")
                return sandbox

            with (
                patch(
                    "ccz_randomizer.runtime.concurrent.create_game_sandbox",
                    side_effect=fake_sandbox,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent.subprocess.Popen",
                    side_effect=process_factory,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent._collect_result_images",
                    return_value=None,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent.time.sleep",
                    return_value=None,
                ),
            ):
                return _run_concurrent_batch(
                    game_executable=game_executable,
                    result_count=result_count,
                    mode="three",
                    stop_file=stop_file,
                    base_dir=root,
                    worker_count=1,
                    round_number=1,
                )

    def test_partitions_slots_by_display_batch(self):
        self.assertEqual(
            [[1, 4, 7], [2, 5], [3, 6]],
            partition_slots(7, 3),
        )

    def test_worker_count_cannot_exceed_slot_count(self):
        self.assertEqual(
            [[1], [2]],
            partition_slots(2, 15),
        )

    def test_invalid_parallelism_is_rejected(self):
        with self.assertRaises(ValueError):
            partition_slots(15, 0)

    def test_partition_accepts_more_workers_than_one_round(self):
        self.assertEqual(
            [[slot] for slot in range(1, 16)],
            partition_slots(15, 30),
        )

    def test_console_render_signature_changes_only_for_visible_output(self):
        state = ConcurrentConsoleState(3, 2)
        rounds = {1: state}
        images: dict[int, Path] = {}

        initial = build_console_render_signature(
            rounds,
            images,
            active_round=1,
            footer="",
            mode="three",
            loop_enabled=False,
        )
        self.assertEqual(
            initial,
            build_console_render_signature(
                rounds,
                images,
                active_round=1,
                footer="",
                mode="three",
                loop_enabled=False,
            ),
        )

        state.consume_line(1, "@@CCZ_SLOT_ASSIGNED@@1")
        assigned = build_console_render_signature(
            rounds,
            images,
            active_round=1,
            footer="",
            mode="three",
            loop_enabled=False,
        )
        self.assertNotEqual(initial, assigned)

        state.slots[1].history.append("仅详情窗口显示的诊断")
        self.assertEqual(
            assigned,
            build_console_render_signature(
                rounds,
                images,
                active_round=1,
                footer="",
                mode="three",
                loop_enabled=False,
            ),
        )

        state.slots[1].stage = "正在检查特技条件"
        progressed = build_console_render_signature(
            rounds,
            images,
            active_round=1,
            footer="",
            mode="three",
            loop_enabled=False,
        )
        self.assertNotEqual(assigned, progressed)

        images[1] = Path("round-1.png")
        with_image = build_console_render_signature(
            rounds,
            images,
            active_round=1,
            footer="",
            mode="three",
            loop_enabled=False,
        )
        self.assertNotEqual(progressed, with_image)

        self.assertNotEqual(
            with_image,
            build_console_render_signature(
                rounds,
                images,
                active_round=1,
                footer="本次流程已完成。",
                mode="three",
                loop_enabled=False,
            ),
        )

    def test_concurrent_console_extracts_incremental_result_image_path(self):
        path = extract_result_image_path(
            "第 3 号结果图已生成，总图已更新：C:\\results\\random.png"
        )

        self.assertEqual(Path("C:\\results\\random.png"), path)
        self.assertTrue(
            is_completion_console_line(
                "第 3 号结果图已生成，总图已更新："
                "C:\\results\\random.png"
            )
        )
        self.assertTrue(
            is_completion_console_line(
                "第 3 号结果存档已通过游戏菜单保存"
            )
        )
        self.assertFalse(is_completion_console_line("正在执行随机流程……"))

    def test_concurrent_console_extracts_final_partial_result_image_path(self):
        path = extract_result_image_path(
            "@@CCZ_RESULT_IMAGE@@C:\\results\\partial-random.png"
        )

        self.assertEqual(Path("C:\\results\\partial-random.png"), path)
        self.assertTrue(
            is_completion_console_line(
                "@@CCZ_RESULT_IMAGE@@C:\\results\\partial-random.png"
            )
        )

    def test_dynamic_queue_gives_next_slot_to_first_free_worker(self):
        slots = DynamicSlotQueue(9)

        self.assertEqual(1, slots.claim(1))
        self.assertEqual(2, slots.claim(2))
        self.assertEqual(3, slots.claim(3))
        self.assertEqual(4, slots.claim(4))

        self.assertEqual(2, slots.finish(2))
        self.assertEqual(5, slots.claim(2))
        self.assertEqual(5, slots.finish(2))
        self.assertEqual(6, slots.claim(2))

        with self.assertRaises(ValueError):
            slots.claim(1)

    def test_dynamic_queue_cancels_unclaimed_slots(self):
        slots = DynamicSlotQueue(3)
        self.assertEqual(1, slots.claim(1))
        slots.cancel_pending()

        self.assertTrue(slots.has_active)
        self.assertFalse(slots.has_pending)
        self.assertEqual(1, slots.finish(1))
        self.assertFalse(slots.has_active)

    def test_failed_slot_can_be_taken_over_by_another_worker(self):
        slots = DynamicSlotQueue(5)

        self.assertEqual(1, slots.claim(1))
        self.assertEqual(2, slots.claim(2))
        self.assertEqual(1, slots.finish(1, retry=True))
        self.assertEqual(1, slots.claim(3))

    def test_console_marks_worker_failure_as_retry_or_final_failure(self):
        state = ConcurrentConsoleState(result_count=3, concurrency=2)
        state.consume_line(2, "@@CCZ_SLOT_ASSIGNED@@2")

        self.assertTrue(state.consume_line(2, "@@CCZ_SLOT_RETRY@@2"))
        self.assertEqual(
            "后台实例异常，等待重试",
            state.slots[2].stage,
        )
        self.assertFalse(state.slots[2].completed)

        self.assertTrue(state.consume_line(2, "@@CCZ_SLOT_FAILED@@2"))
        self.assertEqual("执行失败", state.slots[2].stage)
        self.assertTrue(state.slots[2].completed)

    def test_worker_heartbeat_is_emitted_on_independent_thread(self):
        written = threading.Event()

        class SignalingStream(io.StringIO):
            def write(self, text):
                result = super().write(text)
                written.set()
                return result

        stream = SignalingStream()
        stop = start_concurrent_worker_heartbeat(stream, interval=0.001)
        try:
            self.assertTrue(written.wait(timeout=0.5))
        finally:
            stop.set()

        self.assertIn(CONCURRENT_HEARTBEAT_LINE, stream.getvalue())

    def test_worker_heartbeat_does_not_count_as_business_progress(self):
        self.assertFalse(_is_worker_progress_line(None))
        self.assertFalse(
            _is_worker_progress_line(CONCURRENT_HEARTBEAT_LINE)
        )
        self.assertTrue(
            _is_worker_progress_line("正在执行随机流程")
        )

    def test_unresponsive_worker_is_restarted_and_slot_is_retried(self):
        launches = 0

        class FakeProcess:
            def __init__(self, _command, *, env, **_kwargs):
                nonlocal launches
                launches += 1
                self.stdout = io.StringIO("")
                self.returncode = None
                self._hung = launches == 1
                if not self._hung:
                    save = (
                        Path(env["CCZ_GAME_EXE"]).parent
                        / "SV"
                        / "SV001.E5S"
                    )
                    save.write_bytes(b"result")
                    self.stdout = io.StringIO(
                        "第 1 号结果存档已通过游戏菜单保存\n"
                    )
                    self.returncode = 0

            def poll(self):
                return None if self._hung else self.returncode

            def terminate(self):
                self._hung = False
                self.returncode = 1

            def kill(self):
                self.terminate()

            def wait(self, timeout=None):
                del timeout
                return self.returncode

        with patch(
            "ccz_randomizer.runtime.concurrent."
            "CONCURRENT_WORKER_TIMEOUT_SECONDS",
            -1.0,
        ):
            code = self._run_single_slot_scheduler(FakeProcess)

        self.assertEqual(0, code)
        self.assertEqual(2, launches)

    def test_repeated_worker_failure_stops_after_three_attempts(self):
        launches = 0

        class FakeProcess:
            def __init__(self, _command, **_kwargs):
                nonlocal launches
                launches += 1
                self.stdout = io.StringIO("")
                self.returncode = 1

            def poll(self):
                return self.returncode

            def terminate(self):
                pass

            def kill(self):
                pass

            def wait(self, timeout=None):
                del timeout
                return self.returncode

        code = self._run_single_slot_scheduler(FakeProcess)

        self.assertEqual(1, code)
        self.assertEqual(3, launches)

    def test_saved_result_is_not_retried_when_file_bytes_match_baseline(self):
        launches = 0

        class FakeProcess:
            def __init__(self, _command, *, env, **_kwargs):
                nonlocal launches
                launches += 1
                slot = int(env["CCZ_CONCURRENT_SLOT_LIST"])
                self.stdout = io.StringIO(
                    f"第 {slot} 号结果存档已通过游戏菜单保存\n"
                )
                self.returncode = 0

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = 130

            def kill(self):
                self.terminate()

            def wait(self, timeout=None):
                del timeout
                return self.returncode

        code = self._run_single_slot_scheduler(FakeProcess)

        self.assertEqual(0, code)
        self.assertEqual(1, launches)

    def test_loop_archives_saved_result_when_file_bytes_match_baseline(self):
        launches = 0

        class FakeProcess:
            def __init__(self, _command, *, env, **_kwargs):
                nonlocal launches
                launches += 1
                slot = int(env["CCZ_CONCURRENT_SLOT_LIST"])
                Path(env["CCZ_STOP_FILE"]).write_text(
                    "stop",
                    encoding="ascii",
                )
                self.stdout = io.StringIO(
                    f"第 {slot} 号结果存档已通过游戏菜单保存\n"
                )
                self.returncode = 0

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = 130

            def kill(self):
                self.terminate()

            def wait(self, timeout=None):
                del timeout
                return self.returncode

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game_dir = root / "game"
            (game_dir / "SV").mkdir(parents=True)
            game_executable = game_dir / "Ekd5.exe"
            game_executable.write_bytes(b"game")
            (game_dir / "SV" / "SV001.E5S").write_bytes(b"source")
            (game_dir / "SV" / "SV020.E5S").write_bytes(b"source")
            stop_file = root / "stop"

            def fake_sandbox(
                _game_dir,
                *,
                root,
                worker_name,
                save_names,
            ):
                del _game_dir, worker_name, save_names
                sandbox = root / "sandbox-1"
                (sandbox / "SV").mkdir(parents=True)
                (sandbox / "Ekd5.exe").write_bytes(b"game")
                (sandbox / "SV" / "SV001.E5S").write_bytes(b"source")
                (sandbox / "SV" / "SV020.E5S").write_bytes(b"source")
                return sandbox

            with (
                patch(
                    "ccz_randomizer.runtime.concurrent."
                    "create_game_sandbox",
                    side_effect=fake_sandbox,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent.subprocess.Popen",
                    side_effect=FakeProcess,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent.time.sleep",
                    return_value=None,
                ),
            ):
                code = _run_continuous_loop(
                    game_executable=game_executable,
                    result_count=1,
                    mode="three",
                    stop_file=stop_file,
                    base_dir=root,
                    worker_count=1,
                )

            loop_roots = list(
                (root / "randResult" / "loop").iterdir()
            )

            self.assertEqual(0, code)
            self.assertEqual(1, launches)
            self.assertEqual(1, len(loop_roots))
            self.assertEqual(
                b"source",
                (
                    loop_roots[0]
                    / "round-000001"
                    / "SV"
                    / "SV001.E5S"
                ).read_bytes(),
            )

    def test_loop_can_fill_workers_from_multiple_rounds(self):
        assignments: list[tuple[int, int, int]] = []

        class FakeProcess:
            def __init__(self, _command, *, env, **_kwargs):
                worker = int(env["CCZ_CONCURRENT_WORKER"])
                slot = int(env["CCZ_CONCURRENT_SLOT_LIST"])
                round_number = int(env["CCZ_RUN_STAMP"].rsplit("-r", 1)[1])
                assignments.append((worker, round_number, slot))
                if worker == 16:
                    Path(env["CCZ_STOP_FILE"]).write_text(
                        "stop",
                        encoding="ascii",
                    )
                self.stdout = io.StringIO(
                    "游戏原生随机已触发: (0,)->(1,)\n"
                    f"第 {slot} 号结果存档已通过游戏菜单保存\n"
                )
                self.returncode = 0

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = 130

            def kill(self):
                self.terminate()

            def wait(self, timeout=None):
                del timeout
                return self.returncode

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game_dir = root / "game"
            (game_dir / "SV").mkdir(parents=True)
            game_executable = game_dir / "Ekd5.exe"
            game_executable.write_bytes(b"game")
            (game_dir / "SV" / "SV020.E5S").write_bytes(b"source")
            stop_file = root / "stop"

            def fake_sandbox(
                _game_dir,
                *,
                root,
                worker_name,
                save_names,
            ):
                del _game_dir, save_names
                sandbox = root / worker_name
                (sandbox / "SV").mkdir(parents=True)
                (sandbox / "Ekd5.exe").write_bytes(b"game")
                (sandbox / "SV" / "SV020.E5S").write_bytes(b"source")
                return sandbox

            with (
                patch(
                    "ccz_randomizer.runtime.concurrent.create_game_sandbox",
                    side_effect=fake_sandbox,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent.subprocess.Popen",
                    side_effect=FakeProcess,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent.time.sleep",
                    return_value=None,
                ),
            ):
                code = _run_continuous_loop(
                    game_executable=game_executable,
                    result_count=15,
                    mode="three",
                    stop_file=stop_file,
                    base_dir=root,
                    worker_count=30,
                )

        self.assertEqual(0, code)
        self.assertIn((15, 1, 15), assignments)
        self.assertIn((16, 2, 1), assignments)

    def test_loop_entry_accepts_more_than_fifteen_workers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game_executable = root / "Ekd5.exe"
            game_executable.write_bytes(b"game")
            with patch(
                "ccz_randomizer.runtime.concurrent._run_continuous_loop",
                return_value=0,
            ) as run_loop:
                code = run_concurrent_workers(
                    game_executable=game_executable,
                    result_count=15,
                    mode="seven",
                    stop_file=None,
                    base_dir=root,
                    worker_count=30,
                    loop_random=True,
                )

        self.assertEqual(0, code)
        self.assertEqual(30, run_loop.call_args.kwargs["worker_count"])

    def test_non_loop_entry_rejects_more_than_fifteen_workers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game_executable = root / "Ekd5.exe"
            game_executable.write_bytes(b"game")
            with self.assertRaisesRegex(ValueError, "非循环模式"):
                run_concurrent_workers(
                    game_executable=game_executable,
                    result_count=15,
                    mode="seven",
                    stop_file=None,
                    base_dir=root,
                    worker_count=16,
                    loop_random=False,
                )

    def test_startup_failures_request_original_directory_fallback(self):
        launches: list[int] = []

        class FakeProcess:
            def __init__(self, _command, *, env, **_kwargs):
                launches.append(int(env["CCZ_CONCURRENT_WORKER"]))
                self.stdout = io.StringIO(
                    "RuntimeError: 随机游戏实例启动后退出，"
                    "退出码：3221225477 (0xC0000005)，"
                    "阶段：等待主窗口。\n"
                )
                self.returncode = 1
                self.remaining_polls = 2

            def poll(self):
                if self.remaining_polls:
                    self.remaining_polls -= 1
                    return None
                return self.returncode

            def terminate(self):
                self.returncode = 1

            def kill(self):
                self.returncode = 1

            def wait(self, timeout=None):
                del timeout
                return self.returncode

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game_dir = root / "game"
            (game_dir / "SV").mkdir(parents=True)
            game_executable = game_dir / "Ekd5.exe"
            game_executable.write_bytes(b"game")
            (game_dir / "SV" / "SV020.E5S").write_bytes(b"source")
            for slot in range(1, 16):
                (game_dir / "SV" / f"SV{slot:03}.E5S").write_bytes(
                    b"original"
                )

            def fake_sandbox(
                _game_dir,
                *,
                root,
                worker_name,
                save_names,
            ):
                del _game_dir, save_names
                sandbox = root / worker_name
                (sandbox / "SV").mkdir(parents=True)
                (sandbox / "Ekd5.exe").write_bytes(b"game")
                (sandbox / "SV" / "SV020.E5S").write_bytes(b"source")
                for slot in range(1, 16):
                    (sandbox / "SV" / f"SV{slot:03}.E5S").write_bytes(
                        b"original"
                    )
                return sandbox

            with (
                patch(
                    "ccz_randomizer.runtime.concurrent.create_game_sandbox",
                    side_effect=fake_sandbox,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent.subprocess.Popen",
                    side_effect=FakeProcess,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent."
                    "_collect_result_images",
                    return_value=None,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent.time.sleep",
                    return_value=None,
                ),
            ):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = _run_concurrent_batch(
                        game_executable=game_executable,
                        result_count=15,
                        mode="seven",
                        stop_file=None,
                        base_dir=root,
                        worker_count=15,
                        round_number=1,
                    )

        self.assertEqual(CONCURRENT_COMPATIBILITY_FALLBACK_CODE, code)
        self.assertGreaterEqual(len(launches), 1)
        self.assertLessEqual(len(launches), 3)
        self.assertEqual({1}, set(launches))
        self.assertIn("避免反复重启", output.getvalue())

    def test_compatibility_mode_launches_original_exe_with_sandbox_data(
        self,
    ):
        captured_env = {}

        class FakeProcess:
            def __init__(self, _command, *, env, **_kwargs):
                captured_env.update(env)
                runtime_dir = Path(env["CCZ_GAME_RUNTIME_DIR"])
                save = runtime_dir / "SV" / "SV001.E5S"
                save.write_bytes(b"result")
                self.stdout = io.StringIO(
                    "游戏原生随机已触发: (0,)->(1,)\n"
                    "第 1 号结果存档已通过游戏菜单保存\n"
                )
                self.returncode = 0

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = 130

            def kill(self):
                self.terminate()

            def wait(self, timeout=None):
                del timeout
                return self.returncode

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game_dir = root / "game"
            (game_dir / "SV").mkdir(parents=True)
            game_executable = game_dir / "Ekd5.exe"
            game_executable.write_bytes(b"game")
            (game_dir / "SV" / "SV001.E5S").write_bytes(b"original")
            (game_dir / "SV" / "SV020.E5S").write_bytes(b"source")

            def fake_sandbox(
                _game_dir,
                *,
                root,
                worker_name,
                include_executable,
                save_names,
            ):
                self.assertFalse(include_executable)
                self.assertEqual({"SV020.E5S"}, set(save_names))
                sandbox = root / worker_name
                (sandbox / "SV").mkdir(parents=True)
                (sandbox / "SV" / "SV001.E5S").write_bytes(b"original")
                (sandbox / "SV" / "SV020.E5S").write_bytes(b"source")
                return sandbox

            with (
                patch(
                    "ccz_randomizer.runtime.concurrent.create_game_sandbox",
                    side_effect=fake_sandbox,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent.subprocess.Popen",
                    side_effect=FakeProcess,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent."
                    "_collect_result_images",
                    return_value=None,
                ),
            ):
                code = _run_concurrent_batch(
                    game_executable=game_executable,
                    result_count=1,
                    mode="three",
                    stop_file=None,
                    base_dir=root,
                    worker_count=1,
                    round_number=1,
                    compatibility_mode=True,
                )

        self.assertEqual(0, code)
        self.assertEqual(
            str(game_executable),
            captured_env["CCZ_GAME_EXE"],
        )
        self.assertNotEqual(
            game_executable.parent,
            Path(captured_env["CCZ_GAME_RUNTIME_DIR"]),
        )

    def test_compatibility_startup_failure_falls_back_to_original_dir(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game_executable = root / "Ekd5.exe"
            game_executable.write_bytes(b"game")
            with (
                patch(
                    "ccz_randomizer.runtime.concurrent."
                    "_run_concurrent_batch",
                    return_value=CONCURRENT_COMPATIBILITY_FALLBACK_CODE,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent."
                    "_run_original_directory_worker",
                    return_value=0,
                ) as fallback,
            ):
                code = run_concurrent_workers(
                    game_executable=game_executable,
                    result_count=15,
                    mode="seven",
                    stop_file=None,
                    base_dir=root,
                    worker_count=10,
                    compatibility_mode=True,
                )

        self.assertEqual(0, code)
        fallback.assert_called_once_with(
            game_executable=game_executable,
            result_count=15,
            mode="seven",
            stop_file=None,
            base_dir=root,
            loop_random=False,
        )

    def test_compatibility_mode_tries_original_exe_with_sandbox_data(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game_executable = root / "Ekd5.exe"
            game_executable.write_bytes(b"game")
            with (
                patch(
                    "ccz_randomizer.runtime.concurrent."
                    "_run_concurrent_batch",
                    return_value=0,
                ) as run_batch,
                patch(
                    "ccz_randomizer.runtime.concurrent."
                    "_run_original_directory_worker",
                    return_value=0,
                ) as fallback,
            ):
                code = run_concurrent_workers(
                    game_executable=game_executable,
                    result_count=15,
                    mode="seven",
                    stop_file=None,
                    base_dir=root,
                    worker_count=3,
                    compatibility_mode=True,
                )

        self.assertEqual(0, code)
        run_batch.assert_called_once_with(
            game_executable=game_executable,
            result_count=15,
            mode="seven",
            stop_file=None,
            base_dir=root,
            worker_count=3,
            round_number=1,
            compatibility_mode=True,
        )
        fallback.assert_not_called()

    def test_normal_mode_startup_failure_tries_compatibility_multi_instance(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game_executable = root / "Ekd5.exe"
            game_executable.write_bytes(b"game")
            with (
                patch(
                    "ccz_randomizer.runtime.concurrent."
                    "_run_concurrent_batch",
                    side_effect=[
                        CONCURRENT_COMPATIBILITY_FALLBACK_CODE,
                        0,
                    ],
                ) as run_batch,
                patch(
                    "ccz_randomizer.runtime.concurrent."
                    "_run_original_directory_worker",
                    return_value=0,
                ) as fallback,
            ):
                code = run_concurrent_workers(
                    game_executable=game_executable,
                    result_count=15,
                    mode="seven",
                    stop_file=None,
                    base_dir=root,
                    worker_count=3,
                    compatibility_mode=False,
                )

        self.assertEqual(0, code)
        self.assertEqual(2, run_batch.call_count)
        self.assertFalse(
            run_batch.call_args_list[0].kwargs["compatibility_mode"]
        )
        self.assertTrue(
            run_batch.call_args_list[1].kwargs["compatibility_mode"]
        )
        fallback.assert_not_called()

    def test_normal_and_compatibility_startup_failure_falls_back_to_original_dir(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game_executable = root / "Ekd5.exe"
            game_executable.write_bytes(b"game")
            with (
                patch(
                    "ccz_randomizer.runtime.concurrent."
                    "_run_concurrent_batch",
                    return_value=CONCURRENT_COMPATIBILITY_FALLBACK_CODE,
                ) as run_batch,
                patch(
                    "ccz_randomizer.runtime.concurrent."
                    "_run_original_directory_worker",
                    return_value=0,
                ) as fallback,
            ):
                code = run_concurrent_workers(
                    game_executable=game_executable,
                    result_count=15,
                    mode="seven",
                    stop_file=None,
                    base_dir=root,
                    worker_count=3,
                    compatibility_mode=False,
                )

        self.assertEqual(0, code)
        self.assertEqual(2, run_batch.call_count)
        fallback.assert_called_once_with(
            game_executable=game_executable,
            result_count=15,
            mode="seven",
            stop_file=None,
            base_dir=root,
            loop_random=False,
        )

    def test_compatibility_probe_does_not_expand_on_startup_line_only(
        self,
    ):
        launches: list[int] = []

        class FakeProcess:
            def __init__(self, _command, *, env, **_kwargs):
                launches.append(int(env["CCZ_CONCURRENT_WORKER"]))
                self.stdout = io.StringIO(
                    "游戏原生随机已触发: (0,)->(1,)\n"
                    "RuntimeError: 随机流程执行失败\n"
                )
                self.returncode = 1
                self.remaining_polls = 2

            def poll(self):
                if self.remaining_polls:
                    self.remaining_polls -= 1
                    return None
                return self.returncode

            def terminate(self):
                self.returncode = 1
                self.remaining_polls = 0

            def kill(self):
                self.terminate()

            def wait(self, timeout=None):
                del timeout
                return self.returncode

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game_dir = root / "game"
            (game_dir / "SV").mkdir(parents=True)
            game_executable = game_dir / "Ekd5.exe"
            game_executable.write_bytes(b"game")
            (game_dir / "SV" / "SV020.E5S").write_bytes(b"source")

            def fake_sandbox(
                _game_dir,
                *,
                root,
                worker_name,
                include_executable,
                save_names,
            ):
                self.assertFalse(include_executable)
                self.assertEqual({"SV020.E5S"}, set(save_names))
                sandbox = root / worker_name
                (sandbox / "SV").mkdir(parents=True)
                (sandbox / "SV" / "SV020.E5S").write_bytes(b"source")
                return sandbox

            with (
                patch(
                    "ccz_randomizer.runtime.concurrent."
                    "create_game_sandbox",
                    side_effect=fake_sandbox,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent.subprocess.Popen",
                    side_effect=FakeProcess,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent.time.sleep",
                    return_value=None,
                ),
            ):
                code = _run_concurrent_batch(
                    game_executable=game_executable,
                    result_count=3,
                    mode="three",
                    stop_file=None,
                    base_dir=root,
                    worker_count=3,
                    round_number=1,
                    compatibility_mode=True,
                )

        self.assertEqual(CONCURRENT_COMPATIBILITY_FALLBACK_CODE, code)
        self.assertEqual([1], launches)

    def test_compatibility_probe_expands_after_result_detail(
        self,
    ):
        launches: list[int] = []

        class FakeProcess:
            def __init__(self, _command, *, env, **_kwargs):
                worker = int(env["CCZ_CONCURRENT_WORKER"])
                slot = int(env["CCZ_CONCURRENT_SLOT_LIST"])
                launches.append(worker)
                save = (
                    Path(env["CCZ_GAME_RUNTIME_DIR"])
                    / "SV"
                    / f"SV{slot:03}.E5S"
                )
                save.write_bytes(f"result-{slot}".encode())
                self.stdout = io.StringIO(
                    '@@CCZ_RESULT_DETAIL@@{"qualified":true}\n'
                    f"第 {slot} 号结果存档已通过游戏菜单保存\n"
                )
                self.returncode = 0
                self.remaining_polls = 2 if worker == 1 else 0

            def poll(self):
                if self.remaining_polls:
                    self.remaining_polls -= 1
                    return None
                return self.returncode

            def terminate(self):
                self.returncode = 1
                self.remaining_polls = 0

            def kill(self):
                self.terminate()

            def wait(self, timeout=None):
                del timeout
                return self.returncode

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game_dir = root / "game"
            (game_dir / "SV").mkdir(parents=True)
            game_executable = game_dir / "Ekd5.exe"
            game_executable.write_bytes(b"game")
            (game_dir / "SV" / "SV020.E5S").write_bytes(b"source")
            for slot in range(1, 4):
                (game_dir / "SV" / f"SV{slot:03}.E5S").write_bytes(
                    b"original"
                )

            def fake_sandbox(
                _game_dir,
                *,
                root,
                worker_name,
                include_executable,
                save_names,
            ):
                self.assertFalse(include_executable)
                self.assertEqual({"SV020.E5S"}, set(save_names))
                sandbox = root / worker_name
                (sandbox / "SV").mkdir(parents=True)
                (sandbox / "SV" / "SV020.E5S").write_bytes(b"source")
                for slot in range(1, 4):
                    (sandbox / "SV" / f"SV{slot:03}.E5S").write_bytes(
                        b"original"
                    )
                return sandbox

            with (
                patch(
                    "ccz_randomizer.runtime.concurrent."
                    "create_game_sandbox",
                    side_effect=fake_sandbox,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent.subprocess.Popen",
                    side_effect=FakeProcess,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent."
                    "_collect_result_images",
                    return_value=None,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent.time.sleep",
                    return_value=None,
                ),
            ):
                code = _run_concurrent_batch(
                    game_executable=game_executable,
                    result_count=3,
                    mode="three",
                    stop_file=None,
                    base_dir=root,
                    worker_count=3,
                    round_number=1,
                    compatibility_mode=True,
                )

        self.assertEqual(0, code)
        self.assertEqual({1, 2, 3}, set(launches))

    def test_compatibility_does_not_fallback_after_result_is_published(
        self,
    ):
        launches: list[int] = []

        class FakeProcess:
            def __init__(self, _command, *, env, **_kwargs):
                slot = int(env["CCZ_CONCURRENT_SLOT_LIST"])
                launches.append(slot)
                if slot == 1:
                    save = (
                        Path(env["CCZ_GAME_RUNTIME_DIR"])
                        / "SV"
                        / "SV001.E5S"
                    )
                    save.write_bytes(b"result")
                    self.returncode = 0
                    self.stdout = io.StringIO(
                        "第 1 号结果存档已通过游戏菜单保存\n"
                    )
                else:
                    self.returncode = 1
                    self.stdout = io.StringIO("")

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = 1

            def kill(self):
                self.terminate()

            def wait(self, timeout=None):
                del timeout
                return self.returncode

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game_dir = root / "game"
            (game_dir / "SV").mkdir(parents=True)
            game_executable = game_dir / "Ekd5.exe"
            game_executable.write_bytes(b"game")
            (game_dir / "SV" / "SV020.E5S").write_bytes(b"source")
            for slot in range(1, 3):
                (game_dir / "SV" / f"SV{slot:03}.E5S").write_bytes(
                    b"original"
                )

            def fake_sandbox(
                _game_dir,
                *,
                root,
                worker_name,
                include_executable,
                save_names,
            ):
                self.assertFalse(include_executable)
                self.assertEqual({"SV020.E5S"}, set(save_names))
                sandbox = root / worker_name
                (sandbox / "SV").mkdir(parents=True)
                (sandbox / "SV" / "SV020.E5S").write_bytes(b"source")
                for slot in range(1, 3):
                    (sandbox / "SV" / f"SV{slot:03}.E5S").write_bytes(
                        b"original"
                    )
                return sandbox

            with (
                patch(
                    "ccz_randomizer.runtime.concurrent."
                    "create_game_sandbox",
                    side_effect=fake_sandbox,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent.subprocess.Popen",
                    side_effect=FakeProcess,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent."
                    "_collect_result_images",
                    return_value=None,
                ),
            ):
                code = _run_concurrent_batch(
                    game_executable=game_executable,
                    result_count=2,
                    mode="three",
                    stop_file=None,
                    base_dir=root,
                    worker_count=1,
                    round_number=1,
                    compatibility_mode=True,
                )

        self.assertEqual(1, code)
        self.assertEqual([1, 2, 2, 2], launches)

    def test_loop_compatibility_probe_failure_requests_fallback(
        self,
    ):
        launches: list[int] = []

        class FakeProcess:
            def __init__(self, _command, *, env, **_kwargs):
                launches.append(int(env["CCZ_CONCURRENT_WORKER"]))
                self.stdout = io.StringIO(
                    "RuntimeError: 随机游戏实例启动后退出\n"
                )
                self.returncode = 1

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = 1

            def kill(self):
                self.terminate()

            def wait(self, timeout=None):
                del timeout
                return self.returncode

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game_dir = root / "game"
            (game_dir / "SV").mkdir(parents=True)
            game_executable = game_dir / "Ekd5.exe"
            game_executable.write_bytes(b"game")
            (game_dir / "SV" / "SV020.E5S").write_bytes(b"source")

            def fake_sandbox(
                _game_dir,
                *,
                root,
                worker_name,
                include_executable,
                save_names,
            ):
                self.assertFalse(include_executable)
                self.assertEqual({"SV020.E5S"}, set(save_names))
                sandbox = root / worker_name
                (sandbox / "SV").mkdir(parents=True)
                (sandbox / "SV" / "SV020.E5S").write_bytes(b"source")
                return sandbox

            with (
                patch(
                    "ccz_randomizer.runtime.concurrent."
                    "create_game_sandbox",
                    side_effect=fake_sandbox,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent.subprocess.Popen",
                    side_effect=FakeProcess,
                ),
            ):
                code = _run_continuous_loop(
                    game_executable=game_executable,
                    result_count=3,
                    mode="three",
                    stop_file=None,
                    base_dir=root,
                    worker_count=3,
                    compatibility_mode=True,
                )

        self.assertEqual(CONCURRENT_COMPATIBILITY_FALLBACK_CODE, code)
        self.assertEqual([1], launches)

    def test_loop_startup_failures_request_original_directory_fallback(
        self,
    ):
        launches: list[int] = []

        class FakeProcess:
            def __init__(self, _command, *, env, **_kwargs):
                launches.append(int(env["CCZ_CONCURRENT_WORKER"]))
                self.stdout = io.StringIO(
                    "RuntimeError: 随机游戏实例启动后退出，"
                    "退出码：3221225477 (0xC0000005)，"
                    "阶段：等待主窗口。\n"
                )
                self.returncode = 1
                self.remaining_polls = 2

            def poll(self):
                if self.remaining_polls:
                    self.remaining_polls -= 1
                    return None
                return self.returncode

            def terminate(self):
                self.returncode = 1

            def kill(self):
                self.returncode = 1

            def wait(self, timeout=None):
                del timeout
                return self.returncode

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game_dir = root / "game"
            (game_dir / "SV").mkdir(parents=True)
            game_executable = game_dir / "Ekd5.exe"
            game_executable.write_bytes(b"game")
            (game_dir / "SV" / "SV020.E5S").write_bytes(b"source")

            def fake_sandbox(
                _game_dir,
                *,
                root,
                worker_name,
                save_names,
            ):
                del _game_dir, save_names
                sandbox = root / worker_name
                (sandbox / "SV").mkdir(parents=True)
                (sandbox / "Ekd5.exe").write_bytes(b"game")
                (sandbox / "SV" / "SV020.E5S").write_bytes(b"source")
                return sandbox

            with (
                patch(
                    "ccz_randomizer.runtime.concurrent.create_game_sandbox",
                    side_effect=fake_sandbox,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent.subprocess.Popen",
                    side_effect=FakeProcess,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent.time.sleep",
                    return_value=None,
                ),
            ):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = _run_continuous_loop(
                        game_executable=game_executable,
                        result_count=15,
                        mode="seven",
                        stop_file=None,
                        base_dir=root,
                        worker_count=15,
                    )

        self.assertEqual(CONCURRENT_COMPATIBILITY_FALLBACK_CODE, code)
        self.assertEqual([1, 1, 1], launches)
        self.assertIn("已停止循环随机", output.getvalue())
        self.assertIn("避免反复重启", output.getvalue())

    def test_stop_file_terminates_active_worker_without_waiting_for_task(self):
        processes = []

        class FakeProcess:
            def __init__(self, _command, *, env, **_kwargs):
                self.stdout = io.StringIO("")
                self.returncode = None
                self.terminated = False
                Path(env["CCZ_STOP_FILE"]).write_text(
                    "stop",
                    encoding="ascii",
                )
                processes.append(self)

            def poll(self):
                return self.returncode

            def terminate(self):
                self.terminated = True
                self.returncode = 130

            def kill(self):
                self.terminate()

            def wait(self, timeout=None):
                del timeout
                return self.returncode

        with patch(
            "ccz_randomizer.runtime.concurrent."
            "CONCURRENT_STOP_GRACE_SECONDS",
            -1.0,
        ):
            code = self._run_single_slot_scheduler(
                FakeProcess,
                stop_file_enabled=True,
            )

        self.assertEqual(0, code)
        self.assertEqual(1, len(processes))
        self.assertTrue(processes[0].terminated)

    def test_stop_file_allows_cooperative_worker_exit_before_force_stop(self):
        processes = []

        class FakeProcess:
            def __init__(self, _command, *, env, **_kwargs):
                self.stdout = io.StringIO("")
                self.returncode = 130
                self.terminated = False
                Path(env["CCZ_STOP_FILE"]).write_text(
                    "stop",
                    encoding="ascii",
                )
                processes.append(self)

            def poll(self):
                return self.returncode

            def terminate(self):
                self.terminated = True

            def kill(self):
                self.terminated = True

            def wait(self, timeout=None):
                del timeout
                return self.returncode

        code = self._run_single_slot_scheduler(
            FakeProcess,
            stop_file_enabled=True,
        )

        self.assertEqual(0, code)
        self.assertEqual(1, len(processes))
        self.assertFalse(processes[0].terminated)

    def test_stop_file_clears_unclaimed_batch_tasks(self):
        processes = []

        class FakeProcess:
            def __init__(self, _command, *, env, **_kwargs):
                self.stdout = io.StringIO("")
                self.returncode = None
                self.terminated = False
                Path(env["CCZ_STOP_FILE"]).write_text(
                    "stop",
                    encoding="ascii",
                )
                processes.append(self)

            def poll(self):
                return self.returncode

            def terminate(self):
                self.terminated = True
                self.returncode = 130

            def kill(self):
                self.terminate()

            def wait(self, timeout=None):
                del timeout
                return self.returncode

        with patch(
            "ccz_randomizer.runtime.concurrent.CONCURRENT_STOP_GRACE_SECONDS",
            -1.0,
        ):
            code = self._run_single_slot_scheduler(
                FakeProcess,
                stop_file_enabled=True,
                result_count=3,
            )

        self.assertEqual(0, code)
        self.assertEqual(1, len(processes))
        self.assertTrue(processes[0].terminated)

    def test_stop_waits_for_critical_save_to_finish_cooperatively(self):
        processes = []

        class FakeProcess:
            def __init__(self, _command, *, env, **_kwargs):
                self.stdout = io.StringIO("")
                self.returncode = None
                self.terminated = False
                self.remaining_polls = 4
                Path(env["CCZ_STOP_FILE"]).write_text(
                    "stop",
                    encoding="ascii",
                )
                Path(env["CCZ_CRITICAL_OPERATION_FILE"]).write_text(
                    "qualified-result-save",
                    encoding="ascii",
                )
                processes.append(self)

            def poll(self):
                if self.remaining_polls > 0:
                    self.remaining_polls -= 1
                    return None
                self.returncode = 130
                return self.returncode

            def terminate(self):
                self.terminated = True
                self.returncode = 130

            def kill(self):
                self.terminate()

            def wait(self, timeout=None):
                del timeout
                return self.returncode

        with (
            patch(
                "ccz_randomizer.runtime.concurrent."
                "CONCURRENT_STOP_GRACE_SECONDS",
                -1.0,
            ),
            patch(
                "ccz_randomizer.runtime.concurrent."
                "CONCURRENT_CRITICAL_STOP_GRACE_SECONDS",
                30.0,
            ),
        ):
            code = self._run_single_slot_scheduler(
                FakeProcess,
                stop_file_enabled=True,
            )

        self.assertEqual(0, code)
        self.assertEqual(1, len(processes))
        self.assertFalse(processes[0].terminated)

    def test_completed_batch_result_is_published_before_stop_cleanup(self):
        class FakeProcess:
            def __init__(self, _command, *, env, **_kwargs):
                result_base = Path(env["CCZ_RESULT_BASE_DIR"])
                slot = int(env["CCZ_CONCURRENT_SLOT_LIST"])
                save = result_base / "SV" / f"SV{slot:03}.E5S"
                save.write_bytes(b"completed-save")
                panel = (
                    result_base
                    / "randResult"
                    / "panels"
                    / "worker"
                    / f"save{slot}.png"
                )
                panel.parent.mkdir(parents=True)
                panel.write_bytes(b"completed-panel")
                Path(env["CCZ_STOP_FILE"]).write_text(
                    "stop",
                    encoding="ascii",
                )
                self.stdout = io.StringIO(
                    f"第 {slot} 号结果存档已通过游戏菜单保存\n"
                )
                self.returncode = 0

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = 130

            def kill(self):
                self.terminate()

            def wait(self, timeout=None):
                del timeout
                return self.returncode

        def fake_compose(_panels, grid_path):
            grid_path.parent.mkdir(parents=True, exist_ok=True)
            grid_path.write_bytes(b"updated-grid")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game_dir = root / "game"
            (game_dir / "SV").mkdir(parents=True)
            game_executable = game_dir / "Ekd5.exe"
            game_executable.write_bytes(b"game")
            for slot in range(1, 3):
                (game_dir / "SV" / f"SV{slot:03}.E5S").write_bytes(
                    b"original"
                )
            stop_file = root / "stop"

            def fake_sandbox(
                _game_dir,
                *,
                root,
                worker_name,
                save_names,
            ):
                del _game_dir, save_names
                sandbox = root / worker_name
                (sandbox / "SV").mkdir(parents=True)
                (sandbox / "Ekd5.exe").write_bytes(b"game")
                for slot in range(1, 3):
                    (sandbox / "SV" / f"SV{slot:03}.E5S").write_bytes(
                        b"original"
                    )
                return sandbox

            with (
                patch(
                    "ccz_randomizer.runtime.concurrent."
                    "create_game_sandbox",
                    side_effect=fake_sandbox,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent.subprocess.Popen",
                    side_effect=FakeProcess,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent."
                    "_compose_result_grid",
                    side_effect=fake_compose,
                ),
            ):
                code = _run_concurrent_batch(
                    game_executable=game_executable,
                    result_count=2,
                    mode="three",
                    stop_file=stop_file,
                    base_dir=root,
                    worker_count=1,
                    round_number=1,
                )

            panels = list(
                (root / "randResult" / "panels").glob("*/save1.png")
            )
            grids = list((root / "randResult").glob("*-random.png"))

            self.assertEqual(0, code)
            self.assertEqual(
                b"completed-save",
                (game_dir / "SV" / "SV001.E5S").read_bytes(),
            )
            self.assertEqual(1, len(panels))
            self.assertEqual(b"completed-panel", panels[0].read_bytes())
            self.assertEqual(1, len(grids))
            self.assertEqual(b"updated-grid", grids[0].read_bytes())

    def test_loop_result_is_archived_incrementally_before_stop(self):
        class FakeProcess:
            def __init__(self, _command, *, env, **_kwargs):
                result_base = Path(env["CCZ_RESULT_BASE_DIR"])
                slot = int(env["CCZ_CONCURRENT_SLOT_LIST"])
                save = result_base / "SV" / f"SV{slot:03}.E5S"
                save.write_bytes(b"loop-save")
                panel = (
                    result_base
                    / "randResult"
                    / "panels"
                    / "worker"
                    / f"save{slot}.png"
                )
                panel.parent.mkdir(parents=True)
                panel.write_bytes(b"loop-panel")
                Path(env["CCZ_STOP_FILE"]).write_text(
                    "stop",
                    encoding="ascii",
                )
                self.stdout = io.StringIO(
                    f"第 {slot} 号结果存档已通过游戏菜单保存\n"
                )
                self.returncode = 0

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = 130

            def kill(self):
                self.terminate()

            def wait(self, timeout=None):
                del timeout
                return self.returncode

        def fake_compose(_panels, grid_path):
            grid_path.parent.mkdir(parents=True, exist_ok=True)
            grid_path.write_bytes(b"loop-grid")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game_dir = root / "game"
            (game_dir / "SV").mkdir(parents=True)
            game_executable = game_dir / "Ekd5.exe"
            game_executable.write_bytes(b"game")
            (game_dir / "SV" / "SV020.E5S").write_bytes(b"source")
            for slot in range(1, 3):
                (game_dir / "SV" / f"SV{slot:03}.E5S").write_bytes(
                    b"original"
                )
            stop_file = root / "stop"

            def fake_sandbox(
                _game_dir,
                *,
                root,
                worker_name,
                save_names,
            ):
                del _game_dir, save_names
                sandbox = root / worker_name
                (sandbox / "SV").mkdir(parents=True)
                (sandbox / "Ekd5.exe").write_bytes(b"game")
                (sandbox / "SV" / "SV020.E5S").write_bytes(b"source")
                for slot in range(1, 3):
                    (sandbox / "SV" / f"SV{slot:03}.E5S").write_bytes(
                        b"original"
                    )
                return sandbox

            with (
                patch(
                    "ccz_randomizer.runtime.concurrent."
                    "create_game_sandbox",
                    side_effect=fake_sandbox,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent.subprocess.Popen",
                    side_effect=FakeProcess,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent."
                    "_compose_result_grid",
                    side_effect=fake_compose,
                ),
            ):
                code = _run_continuous_loop(
                    game_executable=game_executable,
                    result_count=2,
                    mode="three",
                    stop_file=stop_file,
                    base_dir=root,
                    worker_count=1,
                )

            loop_roots = list((root / "randResult" / "loop").iterdir())
            self.assertEqual(0, code)
            self.assertEqual(1, len(loop_roots))
            round_dir = loop_roots[0] / "round-000001"
            self.assertEqual(
                b"loop-save",
                (round_dir / "SV" / "SV001.E5S").read_bytes(),
            )
            self.assertEqual(
                b"loop-panel",
                (round_dir / "panels" / "save1.png").read_bytes(),
            )
            self.assertEqual(
                b"loop-grid",
                (round_dir / "random.png").read_bytes(),
            )
            self.assertEqual(
                b"original",
                (game_dir / "SV" / "SV001.E5S").read_bytes(),
            )

    def test_runtime_scheduler_lets_fast_worker_take_more_slots(self):
        assignments: list[tuple[int, int]] = []

        class FakeProcess:
            def __init__(self, _command, *, env, **_kwargs):
                worker = int(env["CCZ_CONCURRENT_WORKER"])
                slot = int(env["CCZ_CONCURRENT_SLOT_LIST"])
                assignments.append((worker, slot))
                save = (
                    Path(env["CCZ_GAME_EXE"]).parent
                    / "SV"
                    / f"SV{slot:03}.E5S"
                )
                save.write_bytes(f"result-{slot}".encode())
                self.stdout = io.StringIO(
                    f"========== 结果 {slot}/6，原生随机第 1 轮 ==========\n"
                    f"第 {slot} 号结果存档已通过游戏菜单保存\n"
                )
                self.returncode = 0
                self._remaining_polls = 12 if slot == 1 else 0

            def poll(self):
                if self._remaining_polls:
                    self._remaining_polls -= 1
                    return None
                return self.returncode

            def terminate(self):
                self.returncode = 1
                self._remaining_polls = 0

            def kill(self):
                self.terminate()

            def wait(self, timeout=None):
                del timeout
                self._remaining_polls = 0
                return self.returncode

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game_dir = root / "game"
            (game_dir / "SV").mkdir(parents=True)
            game_executable = game_dir / "Ekd5.exe"
            game_executable.write_bytes(b"game")
            (game_dir / "SV" / "SV020.E5S").write_bytes(b"source")
            for slot in range(1, 7):
                (game_dir / "SV" / f"SV{slot:03}.E5S").write_bytes(
                    b"original"
                )

            sandbox_index = 0

            def fake_sandbox(
                _game_dir,
                *,
                root,
                worker_name,
                save_names,
            ):
                nonlocal sandbox_index
                del _game_dir, worker_name, save_names
                sandbox_index += 1
                sandbox = root / f"sandbox-{sandbox_index}"
                (sandbox / "SV").mkdir(parents=True)
                (sandbox / "Ekd5.exe").write_bytes(b"game")
                for slot in range(1, 7):
                    (sandbox / "SV" / f"SV{slot:03}.E5S").write_bytes(
                        b"original"
                    )
                return sandbox

            with (
                patch(
                    "ccz_randomizer.runtime.concurrent.create_game_sandbox",
                    side_effect=fake_sandbox,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent.subprocess.Popen",
                    side_effect=FakeProcess,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent._collect_result_images",
                    return_value=None,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent.time.sleep",
                    return_value=None,
                ),
            ):
                code = _run_concurrent_batch(
                    game_executable=game_executable,
                    result_count=6,
                    mode="three",
                    stop_file=None,
                    base_dir=root,
                    worker_count=2,
                    round_number=1,
                )

        self.assertEqual(0, code)
        self.assertEqual([(1, 1)], [
            item for item in assignments if item[0] == 1
        ])
        self.assertEqual(
            [(2, 2), (2, 3), (2, 4), (2, 5), (2, 6)],
            [item for item in assignments if item[0] == 2],
        )

    def test_loop_keeps_opening_rounds_after_each_round_is_claimed(self):
        assignments: list[tuple[int, int, int, bool]] = []
        round_three_started = False

        class FakeProcess:
            def __init__(self, _command, *, env, **_kwargs):
                nonlocal round_three_started
                worker = int(env["CCZ_CONCURRENT_WORKER"])
                slot = int(env["CCZ_CONCURRENT_SLOT_LIST"])
                round_number = int(
                    env["CCZ_RUN_STAMP"].rsplit("-r", 1)[1]
                )
                assignments.append(
                    (
                        worker,
                        round_number,
                        slot,
                        round_three_started,
                    )
                )
                save = (
                    Path(env["CCZ_GAME_EXE"]).parent
                    / "SV"
                    / f"SV{slot:03}.E5S"
                )
                save.write_bytes(
                    f"round-{round_number}-slot-{slot}".encode()
                )
                self.stdout = io.StringIO(
                    f"第 {slot} 号结果存档已通过游戏菜单保存\n"
                )
                self.returncode = 0
                self.worker = worker
                self.round_number = round_number
                self.slot = slot
                if round_number == 3:
                    round_three_started = True
                    Path(env["CCZ_STOP_FILE"]).write_text(
                        "stop",
                        encoding="ascii",
                    )

            def poll(self):
                if (
                    self.worker == 1
                    and self.round_number == 1
                    and self.slot == 1
                    and not round_three_started
                ):
                    return None
                return self.returncode

            def terminate(self):
                self.returncode = 130

            def kill(self):
                self.terminate()

            def wait(self, timeout=None):
                del timeout
                return self.returncode

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game_dir = root / "game"
            (game_dir / "SV").mkdir(parents=True)
            game_executable = game_dir / "Ekd5.exe"
            game_executable.write_bytes(b"game")
            (game_dir / "SV" / "SV020.E5S").write_bytes(b"source")
            for slot in range(1, 4):
                (game_dir / "SV" / f"SV{slot:03}.E5S").write_bytes(
                    b"original"
                )
            stop_file = root / "stop"
            sandbox_index = 0

            def fake_sandbox(
                _game_dir,
                *,
                root,
                worker_name,
                save_names,
            ):
                nonlocal sandbox_index
                del _game_dir, worker_name, save_names
                sandbox_index += 1
                sandbox = root / f"sandbox-{sandbox_index}"
                (sandbox / "SV").mkdir(parents=True)
                (sandbox / "Ekd5.exe").write_bytes(b"game")
                (sandbox / "SV" / "SV020.E5S").write_bytes(b"source")
                for slot in range(1, 4):
                    (sandbox / "SV" / f"SV{slot:03}.E5S").write_bytes(
                        b"original"
                    )
                return sandbox

            with (
                patch(
                    "ccz_randomizer.runtime.concurrent.create_game_sandbox",
                    side_effect=fake_sandbox,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent.subprocess.Popen",
                    side_effect=FakeProcess,
                ),
                patch(
                    "ccz_randomizer.runtime.concurrent.time.sleep",
                    return_value=None,
                ),
            ):
                code = _run_continuous_loop(
                    game_executable=game_executable,
                    result_count=3,
                    mode="three",
                    stop_file=stop_file,
                    base_dir=root,
                    worker_count=2,
                )

        self.assertEqual(0, code)
        third_round = [
            item for item in assignments if item[1] == 3
        ]
        self.assertTrue(third_round)
        self.assertFalse(third_round[0][3])
        self.assertEqual(
            {1, 2, 3},
            {
                slot
                for _, round_number, slot, _ in assignments
                if round_number == 1
            },
        )
        self.assertEqual(
            {1, 2, 3},
            {
                slot
                for _, round_number, slot, _ in assignments
                if round_number == 2
            },
        )

    def test_console_reveals_each_slot_when_worker_claims_it(self):
        state = ConcurrentConsoleState(result_count=6, concurrency=3)

        self.assertEqual((), state.visible_slots())

        state.consume_line(
            1,
            "@@CCZ_SLOT_ASSIGNED@@1",
        )
        self.assertEqual((1,), state.visible_slots())
        self.assertEqual("正在启动随机流程", state.slots[1].stage)

        state.consume_line(2, "@@CCZ_SLOT_ASSIGNED@@2")
        self.assertEqual((1, 2), state.visible_slots())

        state.consume_line(1, "@@CCZ_SLOT_ASSIGNED@@3")
        self.assertEqual(
            (1, 2, 3),
            state.visible_slots(),
        )

    def test_console_formats_loop_round_heading_without_batches(self):
        self.assertEqual("第一轮", format_round_heading(1))
        self.assertEqual("第十二轮", format_round_heading(12))

    def test_console_keeps_one_slot_run_history(self):
        state = ConcurrentConsoleState(result_count=6, concurrency=3)

        self.assertTrue(
            state.consume_line(
                1,
                "========== 结果 1/6，原生随机第 4 轮 ==========",
            )
        )
        self.assertTrue(
            state.consume_line(
                1,
                "R0 七人兵种筛选: 曹操:勇将; 结果=通过",
            )
        )

        progress = state.slots[1]
        self.assertEqual(4, progress.attempt)
        self.assertEqual("兵种合格，正在检查特技", progress.stage)
        self.assertEqual("等待开始", state.slots[2].stage)
        self.assertEqual(
            [
                "========== 结果 1/6，原生随机第 4 轮 ==========",
                "R0 七人兵种筛选: 曹操:勇将; 结果=通过",
            ],
            progress.history,
        )
        self.assertEqual(1, len(progress.attempts))
        self.assertEqual(4, progress.attempts[0].attempt)
        self.assertEqual(
            "R0 七人兵种筛选: 曹操:勇将; 结果=通过",
            progress.attempts[0].member_summary,
        )

    def test_console_deduplicates_repeated_progress_history(self):
        state = ConcurrentConsoleState(result_count=3, concurrency=2)

        state.consume_line(1, "@@CCZ_SLOT_ASSIGNED@@1")
        state.consume_line(1, "后台游戏运行异常，正在重新启动")
        state.consume_line(1, "后台游戏运行异常，正在重新启动")

        self.assertEqual(
            [
                "已领取任务，正在启动随机流程",
                "后台游戏运行异常，正在重新启动",
            ],
            state.slots[1].history,
        )

    def test_console_history_keeps_score_link_data(self):
        state = ConcurrentConsoleState(result_count=3, concurrency=2)
        detail = {
            "resultSlot": 1,
            "attempt": 2,
            "status": "accepted",
            "label": "合格",
        }

        state.consume_result(detail)

        self.assertEqual(["结果：合格"], state.slots[1].history)
        self.assertEqual(detail, state.slots[1].detail)
        self.assertEqual([detail], state.slots[1].result_details)

    def test_console_keeps_failed_score_details_for_dialog(self):
        state = ConcurrentConsoleState(result_count=3, concurrency=2)
        failed = {
            "resultSlot": 1,
            "attempt": 1,
            "status": "skill_failed",
            "label": "特技不合格",
        }
        accepted = {
            "resultSlot": 1,
            "attempt": 2,
            "status": "accepted",
            "label": "合格",
        }

        state.consume_result(failed)
        state.consume_result(accepted)

        self.assertEqual(
            [failed, accepted],
            state.slots[1].result_details,
        )
        self.assertEqual(2, len(state.slots[1].attempts))
        self.assertEqual(failed, state.slots[1].attempts[0].detail)
        self.assertEqual(accepted, state.slots[1].attempts[1].detail)

    def test_console_attempt_keeps_formatted_member_summary(self):
        state = ConcurrentConsoleState(result_count=3, concurrency=2)
        state.consume_line(
            1,
            "========== 结果 1/3，原生随机第 1 轮 ==========",
        )

        state.consume_line(
            1,
            "R0 三人兵种筛选: 曹操:道士; 夏侯惇:策士; "
            "夏侯渊:弓骑兵; 结果=通过",
            history_line="曹操:道士，夏侯惇:策士，夏侯渊:弓骑兵",
        )

        self.assertEqual(
            "曹操:道士，夏侯惇:策士，夏侯渊:弓骑兵",
            state.slots[1].attempts[0].member_summary,
        )

    def test_console_records_formatted_single_instance_output(self):
        state = ConcurrentConsoleState(result_count=3, concurrency=2)
        state.consume_line(1, "@@CCZ_SLOT_ASSIGNED@@1")

        consumed = state.consume_line(
            1,
            "曹操传加强版-自动Re随机 原生随机内存快筛流程 start",
            history_line="正在执行随机流程……",
        )

        self.assertTrue(consumed)
        self.assertEqual(
            [
                "已领取任务，正在启动随机流程",
                "正在执行随机流程……",
            ],
            state.slots[1].history,
        )

    def test_console_keeps_accepted_detail_while_waiting_for_save(self):
        state = ConcurrentConsoleState(result_count=3, concurrency=3)
        state.consume_line(
            1,
            "========== 结果 1/3，原生随机第 2 轮 ==========",
        )

        state.consume_result(
            {
                "resultSlot": 1,
                "attempt": 2,
                "status": "job_failed",
                "label": "兵种不合格",
            }
        )
        self.assertIsNone(state.slots[1].detail)

        accepted = {
            "resultSlot": 1,
            "attempt": 3,
            "status": "accepted",
            "label": "合格",
        }
        state.consume_result(accepted)

        self.assertFalse(state.slots[1].completed)
        self.assertEqual("条件合格，正在保存", state.slots[1].stage)
        self.assertEqual(accepted, state.slots[1].detail)

        self.assertTrue(
            state.consume_line(
                1,
                "第 1 号结果存档已通过游戏菜单保存",
            )
        )
        self.assertTrue(state.slots[1].completed)
        self.assertEqual("已完成：合格", state.slots[1].stage)

    def test_console_marks_only_started_incomplete_slots_as_stopped(self):
        state = ConcurrentConsoleState(result_count=4, concurrency=2)
        state.consume_line(1, "@@CCZ_SLOT_ASSIGNED@@1")
        state.consume_line(2, "@@CCZ_SLOT_ASSIGNED@@2")
        state.consume_line(2, "第 2 号结果存档已通过游戏菜单保存")

        state.mark_stopped()

        self.assertEqual("已停止", state.slots[1].stage)
        self.assertEqual("已完成：合格", state.slots[2].stage)
        self.assertFalse(state.slots[3].started)
        self.assertEqual((1, 2), state.visible_slots())

    def test_console_distinguishes_stopping_from_stopped(self):
        state = ConcurrentConsoleState(result_count=4, concurrency=2)
        state.consume_line(1, "@@CCZ_SLOT_ASSIGNED@@1")
        state.consume_line(2, "@@CCZ_SLOT_ASSIGNED@@2")
        state.consume_line(2, "第 2 号结果存档已通过游戏菜单保存")

        state.mark_stopping()

        self.assertEqual("正在停止", state.slots[1].stage)
        self.assertEqual("已完成：合格", state.slots[2].stage)

        state.mark_stopped()

        self.assertEqual("已停止", state.slots[1].stage)

    def test_stopped_slot_keeps_late_accepted_score_without_resuming(self):
        state = ConcurrentConsoleState(result_count=3, concurrency=2)
        state.consume_line(1, "@@CCZ_SLOT_ASSIGNED@@1")
        state.mark_stopping()
        accepted = {
            "resultSlot": 1,
            "attempt": 1,
            "status": "accepted",
            "label": "合格",
        }

        state.consume_result(accepted, preserve_stopped=True)

        self.assertEqual("正在停止", state.slots[1].stage)
        self.assertEqual(accepted, state.slots[1].detail)
        self.assertEqual(accepted, state.slots[1].attempts[-1].detail)

    def test_save_updates_slot_independent_of_worker_current_slot(self):
        state = ConcurrentConsoleState(result_count=6, concurrency=3)
        state.consume_line(
            1,
            "========== 结果 4/6，原生随机第 1 轮 ==========",
        )
        state.consume_result(
            {
                "resultSlot": 1,
                "attempt": 2,
                "status": "accepted",
                "label": "合格",
            }
        )

        self.assertTrue(
            state.consume_line(
                1,
                "第 1 号结果存档已通过游戏菜单保存",
            )
        )
        self.assertTrue(state.slots[1].completed)
        self.assertEqual("已完成：合格", state.slots[1].stage)
        self.assertEqual("正在执行随机流程", state.slots[4].stage)

    def test_console_preserves_loop_concurrency_above_one_round(self):
        state = ConcurrentConsoleState(result_count=15, concurrency=30)

        self.assertEqual(30, state.concurrency)

    def test_result_image_generation_does_not_regress_saved_slot(self):
        state = ConcurrentConsoleState(result_count=3, concurrency=3)
        state.consume_line(
            1,
            "========== 结果 1/3，原生随机第 1 轮 ==========",
        )
        state.consume_result(
            {
                "resultSlot": 1,
                "attempt": 1,
                "status": "accepted",
                "label": "合格",
            }
        )
        state.consume_line(1, "第 1 号结果存档已通过游戏菜单保存")

        state.consume_line(
            1,
            "第 1 号结果图已生成，总图已更新：C:\\result.png",
        )

        self.assertEqual("已完成：合格", state.slots[1].stage)
        self.assertTrue(state.slots[1].completed)

    def test_late_accepted_detail_does_not_regress_saved_slot(self):
        state = ConcurrentConsoleState(result_count=3, concurrency=3)
        state.consume_line(
            1,
            "========== 结果 1/3，原生随机第 1 轮 ==========",
        )
        state.consume_line(
            1,
            "第 1 号结果存档已通过游戏菜单保存",
        )
        detail = {
            "resultSlot": 1,
            "attempt": 1,
            "status": "accepted",
            "label": "合格",
        }

        state.consume_result(detail)
        state.consume_line(
            1,
            "第 1 号结果图已生成，总图已更新：C:\\result.png",
        )

        self.assertEqual("已完成：合格", state.slots[1].stage)
        self.assertTrue(state.slots[1].completed)
        self.assertEqual(detail, state.slots[1].detail)

    def test_loop_round_states_keep_completed_history_independent(self):
        first_round = ConcurrentConsoleState(result_count=3, concurrency=3)
        second_round = ConcurrentConsoleState(result_count=3, concurrency=3)
        first_round.consume_result(
            {
                "resultSlot": 1,
                "attempt": 2,
                "status": "accepted",
                "label": "合格",
            }
        )

        second_round.consume_line(
            1,
            "========== 结果 1/3，原生随机第 1 轮 ==========",
        )

        self.assertFalse(first_round.slots[1].completed)
        self.assertEqual(
            "条件合格，正在保存",
            first_round.slots[1].stage,
        )
        self.assertFalse(second_round.slots[1].completed)
        self.assertEqual("正在执行随机流程", second_round.slots[1].stage)

    def test_parent_forwards_round_events_but_hides_child_total_image(self):
        self.assertTrue(_should_forward_line("并发轮次开始：第 2 轮"))
        self.assertFalse(
            _should_forward_line("本轮总图路径：C:\\results\\round2.png")
        )

    def test_concurrent_event_round_trip_preserves_worker_and_line(self):
        line = "========== 结果 4/15，原生随机第 7 轮 =========="

        encoded = encode_concurrent_event(
            2,
            line,
            round_number=7,
        )

        self.assertTrue(encoded.isascii())
        self.assertEqual((2, 7, line), decode_concurrent_event(encoded))
        self.assertIsNone(decode_concurrent_event(line))

    def test_concurrent_result_detail_preserves_chinese_end_to_end(self):
        detail = {
            "resultSlot": 2,
            "attempt": 2,
            "status": "accepted",
            "label": "合格",
            "mode": "three",
            "job": {
                "qualified": True,
                "metrics": {
                    "average": 6.51,
                    "threshold": 3,
                    "qualificationMode": "average",
                },
                "members": [
                    {"name": "曹操", "job": "校尉", "score": 6},
                    {"name": "夏侯惇", "job": "游牧骑", "score": 9.54},
                    {"name": "夏侯渊", "job": "水贼", "score": 4},
                ],
            },
            "skill": {
                "qualified": True,
                "metrics": {
                    "skillScore": 5,
                    "requiredSkillScore": 5,
                },
                "members": [
                    {
                        "name": "曹操",
                        "skills": ["辅助地形状态"],
                        "score": 1,
                    }
                ],
            },
        }
        wrapped = encode_concurrent_event(2, encode_result_detail(detail))

        worker_index, round_number, result_line = decode_concurrent_event(
            wrapped
        )
        decoded = decode_result_detail(result_line)
        view = format_result_detail(decoded)

        self.assertEqual(2, worker_index)
        self.assertIsNone(round_number)
        self.assertEqual("合格", view["status"])
        self.assertIn("曹操：校尉", view["sections"][0]["rows"][0])
        self.assertIn("辅助地形状态", view["sections"][1]["rows"][0])
