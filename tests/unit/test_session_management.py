import tempfile
import unittest
import ast
import contextlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

import ccz_randomizer.app as app_module
from fast_randomizer import (
    EQUIPMENT_NAMES,
    INITIAL_TEAM_MEMBERS,
    DirectReloadUnsupported,
    InspectionProcessError,
    InteractionNotTriggered,
    NativeControlError,
    NativeControlTimeout,
    NormalReloadUnsupported,
    Tee,
    advance_seven_member_story,
    advance_people_info_in_game_order,
    click_dialog_button,
    close_member_dialog,
    decode_equipment_effect,
    decode_subprocess_output,
    drive_game_menu_load,
    ensure_people_roster_open,
    finish_reused_load_confirmation,
    format_user_log,
    initial_team_members,
    inspection_background_click,
    inspection_attempt_paths,
    native_background_click,
    native_control_error_hint,
    native_silent_click,
    normal_load_verified,
    open_uncaptured_member_from_roster,
    process_is_alive,
    recover_stale_windows,
    run_candidate_inspection,
    run_initial_inspection_process,
    run_initial_inspection_process_once,
    run_inspection_cli_with_diagnostics,
    run_inspection_process,
    run_native_control,
    native_control_slot_count,
    session_failure_requires_restart,
    title_load_verified,
    trigger_seven_member_story,
    trigger_random_choice_click,
)
from ccz_randomizer.runtime.concurrent import _should_forward_line


class FakeGameSession:
    def __init__(self, healthy: bool = True):
        self.healthy = healthy

    def is_healthy(self) -> bool:
        return self.healthy


class ProcessExitDiagnosticTests(unittest.TestCase):
    def test_persistent_native_controller_reuses_numeric_command_channel(self):
        class FakeStream:
            def __init__(self, first="READY\n", lines=()):
                self.first = first
                self.lines = iter(lines)

            def readline(self):
                value, self.first = self.first, ""
                return value

            def __iter__(self):
                return self

            def __next__(self):
                return next(self.lines)

            def read(self):
                return ""

        class FakeStdin:
            def __init__(self):
                self.writes = []

            def write(self, value):
                self.writes.append(value)

            def flush(self):
                return None

        class FakeProcess:
            def __init__(self):
                self.stdin = FakeStdin()
                self.stdout = FakeStream(lines=("0\n",))
                self.stderr = FakeStream(lines=())
                self.returncode = None

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = 0

            def wait(self, timeout=None):
                return self.returncode

            def kill(self):
                self.returncode = 1

        fake_process = FakeProcess()
        with (
            patch(
                "ccz_randomizer.app.subprocess.Popen",
                return_value=fake_process,
            ),
            patch(
                "ccz_randomizer.app.native_dir",
                return_value=Path("C:/native"),
            ),
        ):
            controller = app_module.PersistentNativeController(123)
            controller.execute(["status"])
            controller.close()

        self.assertEqual(
            "9 0 0 0 0 0 0\n",
            fake_process.stdin.writes[0],
        )

    def test_native_control_slot_count_is_bounded_and_configurable(self):
        with patch.dict(
            os.environ,
            {"CCZ_NATIVE_CONTROL_CONCURRENCY": "3"},
            clear=False,
        ):
            self.assertEqual(3, native_control_slot_count())
        with patch.dict(
            os.environ,
            {"CCZ_NATIVE_CONTROL_CONCURRENCY": "999"},
            clear=False,
        ):
            self.assertEqual(32, native_control_slot_count())
        with patch.dict(
            os.environ,
            {"CCZ_NATIVE_CONTROL_CONCURRENCY": "invalid"},
            clear=False,
        ):
            self.assertEqual(6, native_control_slot_count())

    def test_process_exit_code_preserves_windows_status_value(self):
        def write_exit_code(_handle, pointer):
            pointer._obj.value = 0xC0000005
            return 1

        with patch.object(
            app_module.kernel32,
            "GetExitCodeProcess",
            side_effect=write_exit_code,
        ):
            self.assertEqual(
                0xC0000005,
                app_module.process_exit_code(123),
            )


class SecuritySoftwareBlockTests(unittest.TestCase):
    def test_winerror_225_is_classified_with_blocked_file_path(self):
        blocked = OSError(
            225,
            "Operation did not complete successfully because the file "
            "contains a virus or potentially unwanted software",
            r"C:\tools\native\ccz_control.dll",
        )
        blocked.winerror = 225
        wrapper = RuntimeError("原生组件加载失败")
        wrapper.__cause__ = blocked

        details = app_module.security_software_block_details(wrapper)

        self.assertIsNotNone(details)
        self.assertEqual(225, details["winerror"])
        self.assertEqual(
            [r"C:\tools\native\ccz_control.dll"],
            details["paths"],
        )

    def test_security_block_event_round_trips_and_is_forwarded(self):
        details = {
            "winerror": 225,
            "message": "[WinError 225] blocked",
            "paths": [r"C:\tools\native\ccz_injector.exe"],
        }

        event = app_module.encode_security_software_blocked_event(details)

        self.assertEqual(
            details,
            app_module.decode_security_software_blocked_event(event),
        )
        self.assertTrue(_should_forward_line(event))
        self.assertEqual("", app_module.format_user_log(event))

    def test_other_os_errors_are_not_classified_as_security_blocks(self):
        self.assertIsNone(
            app_module.security_software_block_details(
                FileNotFoundError("missing")
            )
        )

    def test_blocked_traceback_is_logged_but_not_sent_to_ui_stream(self):
        blocked = OSError(
            225,
            "virus or potentially unwanted software",
            r"C:\tools\native\ccz_control.dll",
        )
        blocked.winerror = 225
        ui_output = io.StringIO()
        ui_error = io.StringIO()
        log_output = io.StringIO()

        with (
            contextlib.redirect_stdout(ui_output),
            contextlib.redirect_stderr(ui_error),
        ):
            app_module.report_worker_exception(blocked, log_output)

        self.assertIn(
            app_module.SECURITY_SOFTWARE_BLOCKED_EVENT,
            ui_output.getvalue(),
        )
        self.assertEqual("", ui_error.getvalue())
        self.assertIn("WinError 225", log_output.getvalue())
        self.assertIn(
            r"C:\tools\native\ccz_control.dll",
            log_output.getvalue(),
        )


class SkillTypeMatchingTests(unittest.TestCase):
    def test_effective_skills_use_configured_job_and_skill_types(self):
        rules = app_module.default_rule_config()
        profile = rules["profiles"][rules["activeProfile"]]
        profile["jobScoring"]["jobTypeOverrides"] = {
            "测试兵种": "MASTER",
        }
        profile["sevenPerson"]["skillTypeOverrides"] = {
            "先手攻击": "WARRIOR",
        }
        member = SimpleNamespace(
            job=SimpleNamespace(
                name="测试兵种",
                type="WARRIOR",
            ),
            skillList=[
                SimpleNamespace(
                    name="先手攻击",
                    type="MASTER",
                )
            ],
        )

        self.assertEqual(
            [],
            app_module.effective_member_skill_names(rules, [member]),
        )

        profile["sevenPerson"]["skillTypeOverrides"]["先手攻击"] = "NONE"
        self.assertEqual(
            ["先手攻击"],
            app_module.effective_member_skill_names(rules, [member]),
        )

        profile["sevenPerson"]["skillTypeMatchingEnabled"] = False
        self.assertEqual(
            ["先手攻击"],
            app_module.effective_member_skill_names(rules, [member]),
        )


class RandomGameExecutableTests(unittest.TestCase):
    def test_random_game_executable_is_hidden_and_removed_after_use(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / app_module.GAME_EXE_NAME
            source.write_bytes(b"game executable")

            target = app_module.prepare_random_game_executable(source)

            self.assertTrue(target.is_file())
            self.assertFalse(os.path.samefile(source, target))
            self.assertEqual(source.read_bytes(), target.read_bytes())
            attributes = app_module.kernel32.GetFileAttributesW(str(target))
            self.assertNotEqual(
                attributes,
                app_module.INVALID_FILE_ATTRIBUTES,
            )
            self.assertTrue(attributes & app_module.FILE_ATTRIBUTE_HIDDEN)
            source_attributes = app_module.kernel32.GetFileAttributesW(
                str(source)
            )
            self.assertFalse(
                source_attributes & app_module.FILE_ATTRIBUTE_HIDDEN
            )

            app_module.remove_random_game_executable(target)

            self.assertFalse(target.exists())
            self.assertEqual(source.read_bytes(), b"game executable")

    def test_old_hidden_hardlink_is_migrated_without_hiding_game(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / app_module.GAME_EXE_NAME
            target = source.with_name(app_module.RANDOM_GAME_EXE_NAME)
            source.write_bytes(b"game executable")
            os.link(source, target)
            app_module.hide_random_game_executable(target)

            prepared = app_module.prepare_random_game_executable(source)

            self.assertEqual(target, prepared)
            self.assertFalse(os.path.samefile(source, target))
            source_attributes = app_module.kernel32.GetFileAttributesW(
                str(source)
            )
            target_attributes = app_module.kernel32.GetFileAttributesW(
                str(target)
            )
            self.assertFalse(
                source_attributes & app_module.FILE_ATTRIBUTE_HIDDEN
            )
            self.assertTrue(
                target_attributes & app_module.FILE_ATTRIBUTE_HIDDEN
            )

    def test_intentionally_hidden_game_executable_stays_hidden(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / app_module.GAME_EXE_NAME
            source.write_bytes(b"game executable")
            app_module.hide_random_game_executable(source)

            target = app_module.prepare_random_game_executable(source)

            source_attributes = app_module.kernel32.GetFileAttributesW(
                str(source)
            )
            self.assertTrue(
                source_attributes & app_module.FILE_ATTRIBUTE_HIDDEN
            )
            self.assertTrue(target.is_file())

    def test_runtime_cleanup_only_terminates_random_helper_instance(self):
        game = Path("C:/game/Ekd5.exe")
        helper = game.with_name(app_module.RANDOM_GAME_EXE_NAME)
        with (
            patch(
                "ccz_randomizer.app.find_process_ids",
                return_value=(101, 202),
            ),
            patch(
                "ccz_randomizer.app.process_executable",
                side_effect=(game, helper),
            ),
            patch.object(
                app_module.kernel32,
                "OpenProcess",
                return_value=123,
            ) as open_process,
            patch.object(
                app_module.kernel32,
                "TerminateProcess",
                return_value=True,
            ) as terminate,
            patch.object(
                app_module.kernel32,
                "WaitForSingleObject",
                return_value=1,
            ),
            patch.object(app_module.kernel32, "CloseHandle"),
            patch("ccz_randomizer.app.show_file"),
            patch(
                "ccz_randomizer.app.remove_random_game_executable",
            ),
        ):
            terminated = app_module.terminate_random_game_instances(game)

        self.assertEqual((202,), terminated)
        open_process.assert_called_once()
        terminate.assert_called_once_with(123, 0)


class GameMenuSaveTests(unittest.TestCase):
    class FakeRunner:
        def __init__(self):
            self.events = []
            self.wind = None

        def initWind(self):
            self.events.append(("init", None))
            self.wind = object()

        def saveAndConfirm(self, slot):
            self.events.append(("save", slot))

    def test_rejects_slots_outside_result_range(self):
        with self.assertRaisesRegex(ValueError, "第 1–15 号"):
            app_module.save_result_via_game_menu(
                self.FakeRunner(),
                20,
            )

    def test_three_person_result_uses_game_menu_save(self):
        runner = self.FakeRunner()

        app_module.save_result_via_game_menu(runner, 3)

        self.assertEqual(
            [("init", None), ("save", 3)],
            runner.events,
        )

    def test_seven_person_publishes_initial_candidate_without_resaving_scene(
        self,
    ):
        runner = self.FakeRunner()
        candidate = b"game-created-save-at-initial-scene"
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "SV005.E5S"
            target.write_bytes(b"previous")

            with patch.object(
                app_module,
                "save_result_via_game_menu",
            ) as menu_save:
                _previous, saved, method = (
                    app_module.commit_qualified_result_save(
                        runner,
                        5,
                        target,
                        candidate_save=candidate,
                    )
                )

            self.assertFalse(menu_save.called)
            self.assertEqual(candidate, target.read_bytes())
            self.assertEqual(target.stat().st_size, saved[0])
            self.assertEqual("game_menu_candidate_copy", method)

    def test_wait_for_game_menu_save_accepts_new_file(self):
        with tempfile.TemporaryDirectory() as directory:
            save_path = Path(directory) / "SV001.E5S"

            def create_save(_interval):
                save_path.write_bytes(b"saved")

            with patch(
                "ccz_randomizer.app.time.sleep",
                side_effect=create_save,
            ):
                signature = app_module.wait_for_game_menu_save(
                    save_path,
                    None,
                    timeout=1.0,
                )

        self.assertEqual(5, signature[0])

    def test_wait_for_game_menu_save_rejects_unchanged_file(self):
        with tempfile.TemporaryDirectory() as directory:
            save_path = Path(directory) / "SV001.E5S"
            save_path.write_bytes(b"unchanged")
            signature = app_module.save_file_signature(save_path)

            with (
                patch(
                    "ccz_randomizer.app.time.perf_counter",
                    side_effect=(0.0, 0.0, 1.0),
                ),
                patch("ccz_randomizer.app.time.sleep"),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "未检测到 SV001.E5S 写入",
                ):
                    app_module.wait_for_game_menu_save(
                        save_path,
                        signature,
                        timeout=0.5,
                    )

    def test_drive_game_menu_save_waits_for_real_write(self):
        target = Path(r"C:\game\SV\SV003.E5S")
        previous = (263760, 100, 100)
        saved = (263760, 200, 200)

        class FakeControl:
            pid = 789
            returncode = 0

            def poll(self):
                return self.returncode

            def communicate(self):
                return b"", b""

            def terminate(self):
                self.returncode = 1

            def wait(self, timeout=None):
                del timeout
                return self.returncode

            def kill(self):
                self.returncode = 1

        control = FakeControl()
        with (
            patch(
                "ccz_randomizer.app.save_file_signature",
                side_effect=(previous, saved, saved),
            ),
            patch("ccz_randomizer.app.recover_stale_windows"),
            patch("ccz_randomizer.app.activate_hidden_window"),
            patch(
                "ccz_randomizer.app.wait_list_dialog",
                return_value=222,
            ),
            patch(
                "ccz_randomizer.app.start_save_list_control",
                return_value=control,
            ) as start_control,
            patch(
                "ccz_randomizer.app.visible_owned_windows",
                side_effect=(
                    [(333, "确认", (0, 0, 100, 100))],
                    [],
                ),
            ),
            patch(
                "ccz_randomizer.app.window_class",
                return_value="#32770",
            ),
            patch(
                "ccz_randomizer.app.click_leftmost_dialog_button"
            ) as click_confirm,
            patch("ccz_randomizer.app.interruptible_sleep"),
            patch("ccz_randomizer.app.check_stop_requested"),
            patch(
                "ccz_randomizer.app.save_control_resource_snapshot",
                return_value={},
            ),
            patch("ccz_randomizer.app.diagnostic_log"),
            patch.object(
                app_module.user32,
                "PostMessageW",
                return_value=True,
            ) as post_message,
            patch.object(
                app_module.user32,
                "FindWindowExW",
                return_value=0,
            ),
        ):
            result = app_module.drive_game_menu_save(
                123,
                456,
                target,
                3,
            )

        self.assertEqual(saved, result)
        post_message.assert_called_once_with(456, 0x0111, 101, 0)
        start_control.assert_called_once_with(123, 3)
        click_confirm.assert_called_once_with(333)

    def test_drive_game_menu_save_keeps_written_save_when_control_hangs(self):
        target = Path(r"C:\game\SV\SV003.E5S")
        previous = (263760, 100, 100)
        saved = (263760, 200, 200)

        class HungControl:
            pid = 789
            returncode = None

            def poll(self):
                return self.returncode

            def communicate(self):
                return b"", b""

            def terminate(self):
                self.returncode = 1

            def wait(self, timeout=None):
                del timeout
                return self.returncode

            def kill(self):
                self.returncode = 1

        control = HungControl()
        with (
            patch(
                "ccz_randomizer.app.save_file_signature",
                side_effect=(previous, saved),
            ),
            patch("ccz_randomizer.app.recover_stale_windows"),
            patch("ccz_randomizer.app.activate_hidden_window"),
            patch(
                "ccz_randomizer.app.wait_list_dialog",
                return_value=222,
            ),
            patch(
                "ccz_randomizer.app.start_save_list_control",
                return_value=control,
            ),
            patch(
                "ccz_randomizer.app.visible_owned_windows",
                return_value=[],
            ),
            patch(
                "ccz_randomizer.app.time.perf_counter",
                side_effect=(0.0, 0.0, 0.0, 1.0, 2.0),
            ),
            patch("ccz_randomizer.app.interruptible_sleep"),
            patch("ccz_randomizer.app.check_stop_requested"),
            patch(
                "ccz_randomizer.app.save_control_resource_snapshot",
                return_value={},
            ),
            patch("ccz_randomizer.app.diagnostic_log") as diagnostic,
            patch.object(
                app_module.user32,
                "PostMessageW",
                return_value=True,
            ),
        ):
            result = app_module.drive_game_menu_save(
                123,
                456,
                target,
                3,
                timeout=0.5,
            )

        self.assertEqual(saved, result)
        self.assertEqual(1, control.returncode)
        completed = [
            call
            for call in diagnostic.call_args_list
            if call.args[0] == "game_menu_save_interaction_completed"
        ]
        self.assertEqual(1, len(completed))
        self.assertTrue(completed[0].kwargs["control_forced_stop"])


class ManualRepairUiTests(unittest.TestCase):
    def test_sishui_repair_only_shows_unavailable_notice(self):
        calls = []

        app_module.notify_sishui_repair_unavailable(
            object(),
            toast=lambda parent, message, duration: calls.append(
                (parent, message, duration)
            ),
        )

        self.assertEqual(1, len(calls))
        self.assertEqual(
            app_module.SISHUI_REPAIR_UNAVAILABLE_MESSAGE,
            calls[0][1],
        )

    def test_random_start_warns_about_temporary_s00_replacement(self):
        parent = object()
        calls = []

        app_module.notify_random_s00_warning(
            parent,
            toast=lambda target, message, duration: calls.append(
                (target, message, duration)
            ),
        )

        self.assertEqual(
            [
                (
                    parent,
                    app_module.RANDOM_S00_WARNING_MESSAGE,
                    9000,
                )
            ],
            calls,
        )
        self.assertIn("请勿新开游戏或游玩第一关", calls[0][1])
        self.assertIn("其他关卡", calls[0][1])


class SessionManagementTests(unittest.TestCase):
    def test_title_load_verification_honors_stop_between_memory_checks(self):
        with tempfile.TemporaryDirectory() as temporary:
            save_path = Path(temporary) / "SV020.E5S"
            save_path.write_bytes(b"\1" * 0x30000)
            with (
                patch(
                    "fast_randomizer.find_process_window_by_class",
                    return_value=456,
                ),
                patch("fast_randomizer.drive_game_menu_load"),
                patch("fast_randomizer.check_stop_requested") as check_stop,
            ):
                check_stop.side_effect = KeyboardInterrupt
                with self.assertRaises(KeyboardInterrupt):
                    title_load_verified(123, 19, save_path)

    def test_all_runtime_loads_use_real_game_menu(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "ccz_randomizer"
            / "app.py"
        ).read_text(encoding="utf-8")
        title_load = source.split(
            "def title_load_verified(", 1
        )[1].split("def normal_load_verified(", 1)[0]
        reused_load = source.split(
            "    def robust_load_and_confirm(", 1
        )[1].split("    def menu_save_and_confirm(", 1)[0]

        self.assertNotIn('"title-load"', title_load)
        self.assertIn("drive_game_menu_load(", title_load)
        self.assertIn("from_title=True", title_load)
        self.assertIn("drive_game_menu_load(", reused_load)
        self.assertNotIn('"title-load"', reused_load)
        self.assertNotIn("native_load_dialog_item(", reused_load)

    def test_title_load_closes_progress_dialog_and_refreshes_game(self):
        with tempfile.TemporaryDirectory() as temporary:
            save_path = Path(temporary) / "SV020.E5S"
            expected = bytes(range(256)) * 768
            save_path.write_bytes(expected)

            def memory(pid, offset, size):
                self.assertEqual(123, pid)
                if offset == 0:
                    self.assertEqual(app_module.R0_MEMORY_SIZE, size)
                    return expected
                if offset == app_module.LOAD_TRANSITION_ACTIVE_OFFSET:
                    return b"\0"
                if offset == app_module.LOAD_TRANSITION_STATE_OFFSET:
                    return b"\0\0\0\0"
                raise AssertionError(f"unexpected memory read: {offset}, {size}")

            with (
                patch(
                    "fast_randomizer.drive_game_menu_load"
                ) as load_menu,
                patch(
                    "fast_randomizer.read_memory",
                    side_effect=memory,
                ),
                patch(
                    "fast_randomizer.find_process_window_by_class",
                    return_value=456,
                ),
                patch(
                    "fast_randomizer.process_windows",
                    return_value=[789],
                ),
                patch(
                    "fast_randomizer.window_class",
                    return_value="#32770",
                ),
                patch(
                    "fast_randomizer.user32.FindWindowExW",
                    return_value=900,
                ),
                patch(
                    "fast_randomizer.user32.PostMessageW"
                ) as post_message,
                patch("fast_randomizer.user32.EnableWindow") as enable,
                patch("fast_randomizer.native_wake_game") as wake,
                patch("fast_randomizer.diagnostic_log"),
            ):
                loaded = title_load_verified(
                    123,
                    19,
                    save_path,
                )

        self.assertTrue(loaded)
        load_menu.assert_called_once_with(
            pid=123,
            game=456,
            save_path=save_path,
            slot=20,
            timeout=12.0,
            from_title=True,
        )
        post_message.assert_called_once_with(789, 0x0010, 0, 0)
        enable.assert_called_once_with(456, True)
        wake.assert_called_once_with(123, 456, 80)

    def test_title_load_waits_until_scene_transition_is_settled(self):
        with tempfile.TemporaryDirectory() as temporary:
            save_path = Path(temporary) / "SV020.E5S"
            expected = bytes(range(256)) * 768
            save_path.write_bytes(expected)
            transition_reads = iter(
                (
                    b"\1",
                    (8).to_bytes(4, "little"),
                    b"\0",
                    b"\0\0\0\0",
                )
            )

            def memory(_pid, offset, _size):
                if offset == 0:
                    return expected
                return next(transition_reads)

            with (
                patch(
                    "fast_randomizer.drive_game_menu_load"
                ),
                patch(
                    "fast_randomizer.read_memory",
                    side_effect=memory,
                ),
                patch(
                    "fast_randomizer.find_process_window_by_class",
                    return_value=456,
                ),
                patch(
                    "fast_randomizer.process_windows",
                    return_value=[],
                ),
                patch(
                    "fast_randomizer.native_wake_game"
                ),
                patch(
                    "fast_randomizer.interruptible_sleep"
                ) as sleep,
                patch("fast_randomizer.diagnostic_log"),
            ):
                loaded = title_load_verified(
                    123,
                    19,
                    save_path,
                )

        self.assertTrue(loaded)
        sleep.assert_called_once_with(0.1)

    def test_game_menu_load_uses_real_list_single_click(self):
        process = unittest.mock.Mock()
        process.poll.return_value = 0
        process.returncode = 0
        with tempfile.TemporaryDirectory() as temporary:
            save_path = Path(temporary) / "SV020.E5S"
            save_path.write_bytes(b"save")
            with (
                patch("fast_randomizer.recover_stale_windows"),
                patch("fast_randomizer.wait_list_dialog", return_value=789),
                patch("fast_randomizer.visible_owned_windows", return_value=[]),
                patch("fast_randomizer.process_windows", return_value=[]),
                patch("fast_randomizer.native_dir", return_value=Path(temporary)),
                patch("fast_randomizer.subprocess.Popen", return_value=process) as popen,
                patch("fast_randomizer.user32.PostMessageW") as post_message,
                patch("fast_randomizer.user32.IsWindow", return_value=False),
                patch("fast_randomizer.user32.IsWindowEnabled", return_value=True),
                patch("fast_randomizer.native_wake_game") as wake,
                patch("fast_randomizer.diagnostic_log"),
            ):
                drive_game_menu_load(
                    123,
                    456,
                    save_path,
                    20,
                )

        post_message.assert_called_once_with(456, 0x0111, 102, 0)
        command = popen.call_args.args[0]
        self.assertEqual("list", command[3])
        self.assertEqual("19", command[4])
        wake.assert_called_once_with(123, 456, 80)

    def test_game_menu_load_does_not_wait_for_hung_injector_after_dialog_closes(
        self,
    ):
        process = unittest.mock.Mock()
        process.returncode = None
        process.poll.side_effect = (None, None, 1, 1)

        with tempfile.TemporaryDirectory() as temporary:
            save_path = Path(temporary) / "SV020.E5S"
            save_path.write_bytes(b"save")

            def terminate():
                process.returncode = 1

            process.terminate.side_effect = terminate
            with (
                patch("fast_randomizer.recover_stale_windows"),
                patch("fast_randomizer.wait_list_dialog", return_value=789),
                patch("fast_randomizer.visible_owned_windows", return_value=[]),
                patch("fast_randomizer.process_windows", return_value=[]),
                patch("fast_randomizer.native_dir", return_value=Path(temporary)),
                patch(
                    "fast_randomizer.subprocess.Popen",
                    return_value=process,
                ),
                patch("fast_randomizer.user32.PostMessageW"),
                patch("fast_randomizer.user32.IsWindow", return_value=False),
                patch("fast_randomizer.user32.IsWindowEnabled", return_value=True),
                patch("fast_randomizer.native_wake_game"),
                patch("fast_randomizer.diagnostic_log"),
            ):
                drive_game_menu_load(
                    123,
                    456,
                    save_path,
                    20,
                )

        process.terminate.assert_called_once()

    def test_native_list_action_uses_single_click(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "native"
            / "ccz_control.c"
        ).read_text(encoding="utf-8")
        list_action = source.split(
            "static DWORD run_list_item(int item_index) {", 1
        )[1].split("static DWORD notify_list_item(", 1)[0]

        self.assertIn(
            "post_synthetic_click(list, click_x, click_y, 1, FALSE);",
            list_action,
        )
        self.assertNotIn(
            "post_synthetic_click(list, click_x, click_y, 2, FALSE);",
            list_action,
        )

    def test_process_alive_checks_the_requested_pid(self):
        with (
            patch(
                "fast_randomizer.kernel32.OpenProcess",
                return_value=987,
            ) as open_process,
            patch(
                "fast_randomizer.kernel32.WaitForSingleObject",
                return_value=0x00000102,
            ) as wait_for_process,
            patch(
                "fast_randomizer.kernel32.CloseHandle",
            ) as close_handle,
        ):
            self.assertTrue(process_is_alive(456))

        open_process.assert_called_once_with(
            app_module.SYNCHRONIZE
            | app_module.PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            456,
        )
        wait_for_process.assert_called_once_with(987, 0)
        close_handle.assert_called_once_with(987)

    def test_interaction_failure_ignores_other_same_name_processes(self):
        healthy_state = {
            "game_window_valid": True,
            "game_window_enabled": True,
        }
        with patch(
            "ccz_randomizer.app.process_is_alive",
            return_value=True,
        ):
            result = app_module.interaction_failure_type(
                456,
                healthy_state,
                load_mode="normal",
                reused_session=True,
            )

        self.assertEqual("interaction:no-change:normal:reused", result)

    def test_interaction_failure_detects_target_process_exit(self):
        with patch(
            "ccz_randomizer.app.process_is_alive",
            return_value=False,
        ):
            result = app_module.interaction_failure_type(
                456,
                {
                    "game_window_valid": True,
                    "game_window_enabled": True,
                },
                load_mode="normal",
                reused_session=True,
            )

        self.assertEqual("interaction:process-exited", result)

    def test_native_control_stops_without_waiting_for_timeout(self):
        class FakeProcess:
            returncode = None

            def __init__(self):
                self.terminated = False

            def poll(self):
                return self.returncode

            def terminate(self):
                self.terminated = True
                self.returncode = 130

            def wait(self, timeout=None):
                return self.returncode

            def kill(self):
                self.returncode = 130

            def communicate(self):
                return b"", b""

        with tempfile.TemporaryDirectory() as temporary:
            native_dir = Path(temporary)
            (native_dir / "ccz_injector.exe").write_bytes(b"test")
            (native_dir / "ccz_control.dll").write_bytes(b"test")
            stop_file = native_dir / "stop"
            stop_file.write_text("stop", encoding="ascii")
            process = FakeProcess()
            with (
                patch("fast_randomizer.native_dir", return_value=native_dir),
                patch("fast_randomizer.subprocess.Popen", return_value=process),
                patch("fast_randomizer.STOP_FILE_PATH", stop_file),
                patch("fast_randomizer.diagnostic_log") as diagnostic,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    run_native_control(123, ["silent-burst"])

        self.assertTrue(process.terminated)
        self.assertTrue(
            any(
                call.args[0] == "native_control_cancelled"
                for call in diagnostic.call_args_list
            )
        )

    def test_normal_load_uses_game_menu_and_verifies_memory(self):
        with tempfile.TemporaryDirectory() as temporary:
            save_path = Path(temporary) / "SV020.E5S"
            expected = bytes(range(256)) * 768
            save_path.write_bytes(expected)
            load_action = unittest.mock.Mock()
            with (
                patch(
                    "fast_randomizer.read_memory",
                    return_value=expected,
                ),
                patch(
                    "fast_randomizer.process_executable",
                    return_value=Path("Ekd5.exe"),
                ),
                patch(
                    "fast_randomizer.user32.IsWindow",
                    return_value=True,
                ),
                patch("fast_randomizer.diagnostic_log") as diagnostic,
            ):
                loaded = normal_load_verified(
                    123,
                    456,
                    20,
                    save_path,
                    load_action,
                )

        self.assertTrue(loaded)
        load_action.assert_called_once_with(20)
        self.assertTrue(
            any(
                call.args[0] == "normal_load_verified"
                for call in diagnostic.call_args_list
            )
        )

    def test_normal_load_wraps_menu_failure_for_session_recovery(self):
        with tempfile.TemporaryDirectory() as temporary:
            save_path = Path(temporary) / "SV020.E5S"
            save_path.write_bytes(b"\0" * 0x30000)
            with (
                patch(
                    "fast_randomizer.game_state_diagnostic",
                    return_value={},
                ),
                patch("fast_randomizer.diagnostic_log"),
            ):
                with self.assertRaises(NormalReloadUnsupported):
                    normal_load_verified(
                        123,
                        456,
                        20,
                        save_path,
                        unittest.mock.Mock(
                            side_effect=RuntimeError(
                                "读取进度窗口未出现"
                            )
                        ),
                    )

    def test_stale_dialog_cleanup_restores_main_window_before_reload(self):
        existing = {456: True, 654: True, 789: True}

        def post_message(hwnd, message, _wparam, _lparam):
            self.assertEqual(0x0010, message)
            existing[hwnd] = False
            return True

        with (
            patch(
                "fast_randomizer.process_windows",
                return_value=[456, 654, 789],
            ) as process_windows_mock,
            patch(
                "fast_randomizer.window_class",
                side_effect=lambda hwnd: (
                    "#32770" if hwnd in (456, 654) else "SOUSOU"
                ),
            ),
            patch(
                "fast_randomizer.window_text",
                side_effect=lambda hwnd: {
                    456: "武将情报",
                    654: "部队情报一览",
                    789: "游戏主窗口",
                }[hwnd],
            ),
            patch(
                "fast_randomizer.user32.PostMessageW",
                side_effect=post_message,
            ) as post,
            patch(
                "fast_randomizer.user32.IsWindow",
                side_effect=lambda hwnd: existing[hwnd],
            ),
            patch(
                "fast_randomizer.user32.EnableWindow",
            ) as enable,
            patch(
                "fast_randomizer.user32.IsWindowEnabled",
                return_value=True,
            ),
            patch("fast_randomizer.diagnostic_log") as diagnostic,
        ):
            closed = recover_stale_windows(123, 789)

        self.assertEqual(2, closed)
        process_windows_mock.assert_called_once_with(
            123,
            visible_only=False,
        )
        self.assertEqual(
            [
                unittest.mock.call(456, 0x0010, 0, 0),
                unittest.mock.call(654, 0x0010, 0, 0),
            ],
            post.call_args_list,
        )
        enable.assert_called_once_with(789, True)
        self.assertEqual(
            "stale_game_windows_recovered",
            diagnostic.call_args.args[0],
        )

    def test_native_control_code_seven_with_loaded_module_is_not_security_hint(
        self,
    ):
        hint = native_control_error_hint(
            7,
            "ControlAction returned failure: action=4, result=7, "
            "remote_module=0x6DAB0000, remote_export=0x6DAB1000",
        )

        self.assertIn("后台控制组件已加载", hint)
        self.assertNotIn("安全软件", hint)
        self.assertNotIn("隔离", hint)

    def test_diagnostic_screenshots_keep_only_one_per_error_type(self):
        with patch.object(
            app_module,
            "DIAGNOSTIC_SCREENSHOT_TYPES",
            set(),
        ):
            self.assertTrue(
                app_module.reserve_diagnostic_screenshot("interaction:a")
            )
            self.assertFalse(
                app_module.reserve_diagnostic_screenshot("interaction:a")
            )

    def test_diagnostic_screenshots_are_limited_per_run(self):
        with patch.object(
            app_module,
            "DIAGNOSTIC_SCREENSHOT_TYPES",
            set(),
        ):
            for index in range(app_module.DIAGNOSTIC_SCREENSHOT_LIMIT):
                self.assertTrue(
                    app_module.reserve_diagnostic_screenshot(
                        f"interaction:{index}"
                    )
                )
            self.assertFalse(
                app_module.reserve_diagnostic_screenshot(
                    "interaction:overflow"
                )
            )

    def test_tee_ignores_missing_windowed_stream(self):
        output = tempfile.SpooledTemporaryFile(mode="w+", encoding="utf-8")
        tee = Tee(None, output)

        self.assertEqual(4, tee.write("test"))
        tee.flush()
        output.seek(0)

        self.assertEqual("test", output.read())
        output.close()

    def test_equipment_order_matches_game_numbers(self):
        self.assertEqual(("雌雄双剑", "倚天剑"), EQUIPMENT_NAMES[:2])

    def test_three_grid_penetration_effect_is_named(self):
        self.assertEqual(
            "穿透攻击-三格",
            decode_equipment_effect(0x33, 0x07),
        )

    def test_production_randomizer_does_not_use_system_mouse_api(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "ccz_randomizer"
            / "app.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden = {"SetCursorPos", "mouse_event", "SendInput"}
        used = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr in forbidden
        }
        self.assertEqual(set(), used)

    def test_random_session_uses_process_audio_without_file_hooks(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "ccz_randomizer"
            / "app.py"
        ).read_text(encoding="utf-8")
        session_source = source.split(
            "class HiddenGameSession:", 1
        )[1].split("def read_memory(", 1)[0]

        self.assertIn(
            "ProcessAudioMuteMonitor(",
            session_source,
        )
        self.assertNotIn("prepare_random_game_executable(", session_source)
        self.assertIn("self.launch_executable = self.executable", session_source)
        self.assertIn(
            'command_parts = [f\'"{self.executable}"\']',
            session_source,
        )
        self.assertIn("随机游戏实例启动后退出", session_source)
        self.assertIn('"game_process_exited"', session_source)
        self.assertIn("exit_code_hex", session_source)
        self.assertNotIn(
            'run_native_control(self.pid, ["mute-audio"])',
            session_source,
        )
        self.assertIn(
            '"random_game_audio_mute_monitor_started"',
            session_source,
        )
        self.assertLess(
            session_source.index("self.audio_mute_monitor.start()"),
            session_source.index(
                "kernel32.ResumeThread(process_info.hThread)"
            ),
        )
        self.assertNotIn("restore_process_audio_sessions(self.pid)", session_source)
        self.assertNotIn("AudioMuteRecoveryMonitor", session_source)
        self.assertNotIn(
            "recover_legacy_audio_mute(self.executable)",
            session_source,
        )
        self.assertNotIn("LegacyAudioRecoveryMonitor(", session_source)

    def test_gui_uses_sandbox_scheduler_even_with_one_worker(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "ccz_randomizer"
            / "app.py"
        ).read_text(encoding="utf-8")
        start_source = source.split("    def start() -> None:", 1)[1].split(
            "    def stop() -> None:",
            1,
        )[0]

        self.assertIn('env["CCZ_CONCURRENT_MODE"] = "1"', start_source)
        self.assertIn(
            'env["CCZ_CONCURRENT_COUNT"] = str(concurrency)',
            start_source,
        )
        self.assertNotIn(
            'if concurrency > 1:\n'
            '            env["CCZ_CONCURRENT_MODE"]',
            start_source,
        )
        self.assertIn(
            "if concurrency > 1:\n"
            "            concurrent_console_state = ConcurrentConsoleState(",
            start_source,
        )
        self.assertIn(
            'append(f"\\n========== 开始随机：{stamp} ==========")',
            start_source,
        )
        self.assertIn("notify_random_s00_warning(root)", start_source)

    def test_main_settings_keep_repair_action_on_a_separate_row(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "ccz_randomizer"
            / "app.py"
        ).read_text(encoding="utf-8")
        layout = source.split(
            "    settings_panel = tk.Frame(outer)", 1
        )[1].split(
            "    output = scrolledtext.ScrolledText(", 1
        )[0]

        self.assertIn(
            "runtime_settings_bar = tk.Frame(settings_panel)",
            layout,
        )
        self.assertIn(
            "rule_settings_bar = tk.Frame(settings_panel)",
            layout,
        )
        self.assertIn(
            "repair_button = tk.Button(\n"
            "        rule_settings_bar,",
            layout,
        )
        self.assertIn(
            "action_button = tk.Button(\n"
            "        rule_settings_bar,",
            layout,
        )
        self.assertIn('action_button.pack(side="right")', layout)
        self.assertNotIn("textvariable=status", layout)

    def test_runtime_cleanup_repairs_s00_and_scratch_save(self):
        game = Path(r"C:\game\Ekd5.exe")
        with (
            patch(
                "ccz_randomizer.app.terminate_random_game_instances",
                return_value=(),
            ),
            patch("ccz_randomizer.app.repair_runtime_s00") as repair_s00,
            patch(
                "ccz_randomizer.app.repair_runtime_scratch_save"
            ) as repair_scratch,
            patch("ccz_randomizer.app.diagnostic_log"),
        ):
            app_module.cleanup_random_runtime(game, "test_cleanup")

        repair_s00.assert_called_once_with(
            game,
            "test_cleanup_s00_repair",
        )
        repair_scratch.assert_called_once_with(
            game,
            "test_cleanup_scratch_save_repair",
        )

    def test_reused_session_uses_normal_load_and_three_interaction_attempts(
        self,
    ):
        source = (
            Path(__file__).resolve().parents[2]
            / "ccz_randomizer"
            / "app.py"
        ).read_text(encoding="utf-8")
        self.assertIn('load_mode = "normal"', source)
        self.assertIn("interaction_limit = 3", source)
        self.assertIn(
            "if not getattr(self, \"wind\", None):\n"
            "            self.initWind()",
            source,
        )
        self.assertIn("self._normal_load_succeeded = True", source)
        self.assertIn(
            "consecutive_normal_reload_failures = 0",
            source,
        )
        self.assertNotIn("native_direct_load(pid, SOURCE_TITLE_LIST_INDEX)", source)
        self.assertNotIn("interaction_compat_reload_start", source)
        self.assertNotIn("interaction_compat_reload_ready", source)
        self.assertIn("native_wake_game(pid, game, 80)", source)
        self.assertNotIn("native_wake_game(pid, game, 1800)", source)

    def test_saved_results_keep_game_created_candidate_state(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "ccz_randomizer"
            / "app.py"
        ).read_text(encoding="utf-8")
        self.assertIn("save_result_via_game_menu(", source)
        self.assertIn("wait_for_game_menu_save(", source)
        self.assertIn("drive_game_menu_save(", source)
        self.assertIn(
            "user32.PostMessageW(game, 0x0111, 101, 0)",
            source,
        )
        self.assertNotIn("def verify_saved_result(", source)
        self.assertIn("publish_candidate_save(target_path, candidate_save)", source)
        self.assertNotIn("restore_slot=scratch_slot", source)

    def test_full_inspection_uses_story_then_memory_skill_resolution(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "ccz_randomizer"
            / "app.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "advance_people_info_in_game_order(",
            source,
        )
        self.assertIn("panel_index = (", source)
        self.assertNotIn(
            'f"切换到第 {index + 2} 个武将失败"',
            source,
        )
        self.assertIn("CCZ_FORCE_ROSTER_FALLBACK", source)
        self.assertIn("CCZ_DISABLE_ROSTER_FALLBACK", source)
        self.assertIn("advance_seven_member_story(", source)
        inspection = source.split(
            "    def inspect_current_seven_members(self)", 1
        )[1].split("    def r0_only_run(self)", 1)[0]
        self.assertIn("advance_seven_member_story(", inspection)
        self.assertIn("load_member_skills_from_memory(", inspection)
        self.assertNotIn("self.openPeople()", inspection)
        self.assertNotIn("getSkillMatList()", inspection)

    def test_release_uses_result_images_and_hides_history_entry(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "ccz_randomizer"
            / "app.py"
        ).read_text(encoding="utf-8")
        accepted = source.split(
            "                    def accepted_result(", 1
        )[1].split(
            "                    def accepted_result_error(", 1
        )[0]

        self.assertIn("save_result_image(", accepted)
        self.assertIn("compose_result_grid(panel_paths)", accepted)
        self.assertNotIn('text="历史结果"', source)

    def test_same_session_skill_capture_uses_full_print_window_frame(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "ccz_randomizer"
            / "app.py"
        ).read_text(encoding="utf-8")
        robust_get_mat = source.split(
            "    def robust_get_mat(", 1
        )[1].split("    def click_relative_hwnd(", 1)[0]

        self.assertIn("strip_client=False", robust_get_mat)
        self.assertLess(
            robust_get_mat.index("print_window_mat("),
            robust_get_mat.index("original_get_mat("),
        )
        self.assertIn("skill_memory_resolved", source)

    def test_window_capture_has_recoverable_fallbacks(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "ccz_randomizer"
            / "app.py"
        ).read_text(encoding="utf-8")
        robust_get_mat = source.split(
            "    def robust_get_mat(", 1
        )[1].split("    def click_relative_hwnd(", 1)[0]

        self.assertIn("capture_window_with_fallbacks(", robust_get_mat)
        self.assertIn("native_wake_game(", robust_get_mat)
        self.assertIn("WindowCaptureUnavailable", robust_get_mat)
        self.assertTrue(
            issubclass(
                app_module.WindowCaptureUnavailable,
                InteractionNotTriggered,
            )
        )

    def test_text_panel_can_replace_failed_full_panel_capture(self):
        skills = [
            type("Skill", (), {"name": name})()
            for name in ("特技一", "特技二", "特技三", "特技四")
        ]

        panel = app_module.render_member_text_panel(
            "曹操",
            "群雄",
            skills,
        )

        self.assertEqual((130, 130, 3), panel.shape)
        self.assertGreater(float(np.std(panel)), 1.0)
        heading_pixels = np.argwhere(
            np.any(panel[3:17] != 211, axis=2)
        )
        skill_pixels = np.argwhere(
            np.any(panel[18:32] != 211, axis=2)
        )
        self.assertGreater(
            int(skill_pixels[:, 1].min()),
            int(heading_pixels[:, 1].min()),
        )

    def test_seven_member_inspection_refreshes_consumed_session_directly(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "ccz_randomizer"
            / "app.py"
        ).read_text(encoding="utf-8")

        self.assertIn("self._session_consumed = True", source)
        self.assertIn("refresh_consumed_session = False", source)
        self.assertIn(
            '"consumed_seven_member_session_refresh"',
            source,
        )
        self.assertIn(
            "and not refresh_consumed_session",
            source,
        )

    def test_inspection_npc_click_uses_injected_background_mouse(self):
        with (
            patch("fast_randomizer.native_silent_click") as native_click,
            patch("fast_randomizer.post_click") as post_click_mock,
            patch("fast_randomizer.diagnostic_log"),
        ):
            method = inspection_background_click(123, 456, 369, 234)

        self.assertEqual("injected_background_mouse", method)
        native_click.assert_called_once_with(
            123,
            456,
            369,
            234,
            tail_delay_ms=120,
        )
        post_click_mock.assert_not_called()

    def test_inspection_npc_click_falls_back_to_window_message(self):
        def set_rect(_hwnd, rect_pointer):
            rect = rect_pointer._obj
            rect.left = 10
            rect.top = 20
            rect.right = 650
            rect.bottom = 460
            return True

        with (
            patch(
                "fast_randomizer.native_silent_click",
                side_effect=NativeControlError(162),
            ),
            patch(
                "fast_randomizer.user32.GetWindowRect",
                side_effect=set_rect,
            ),
            patch("fast_randomizer.post_click") as post_click_mock,
            patch("fast_randomizer.diagnostic_log"),
        ):
            method = inspection_background_click(123, 456, 369, 234)

        self.assertEqual("post_message_fallback", method)
        post_click_mock.assert_called_once_with(
            456,
            379,
            254,
            right=False,
        )

    def test_seven_member_story_progress_is_paced(self):
        ready_state = bytearray(0x30000)
        with (
            patch("fast_randomizer.native_silent_click_burst") as click_burst,
            patch("fast_randomizer.run_native_control") as native_control,
            patch("fast_randomizer.native_wake_game") as wake_game,
            patch(
                "fast_randomizer.read_memory",
                return_value=bytes(ready_state),
            ),
            patch(
                "fast_randomizer.interruptible_sleep"
            ) as interruptible_sleep,
            patch("fast_randomizer.diagnostic_log") as diagnostic,
            patch(
                "fast_randomizer.capture_interaction_failure",
                return_value="failure.png",
            ) as capture_failure,
        ):
            ready = advance_seven_member_story(
                123,
                456,
                rounds=3,
                clicks_per_round=12,
            )

        self.assertEqual(
            [
                unittest.mock.call(
                    456,
                    360,
                    400,
                    12,
                    down_delay_ms=55,
                    up_delay_ms=80,
                ),
                unittest.mock.call(456, 360, 400, 12),
                unittest.mock.call(456, 360, 400, 12),
            ],
            click_burst.call_args_list,
        )
        native_control.assert_not_called()
        self.assertEqual(
            [
                unittest.mock.call(123, 456, 500),
                unittest.mock.call(123, 456, 500),
                unittest.mock.call(123, 456, 500),
            ],
            wake_game.call_args_list,
        )
        self.assertEqual(
            [
                unittest.mock.call(0.5),
                unittest.mock.call(0.5),
                unittest.mock.call(0.5),
            ],
            interruptible_sleep.call_args_list,
        )
        self.assertFalse(ready)
        capture_failure.assert_called_once()
        self.assertTrue(
            any(
                call.args[0] == "seven_member_story_not_ready"
                for call in diagnostic.call_args_list
            )
        )

    def test_seven_member_story_stops_when_scene_is_ready(self):
        pending = bytearray(0x30000)
        ready = bytearray(pending)
        ready[0x0FFF] = 1
        ready[0x4F64:0x4F66] = b"\x01\x00"
        for offset in range(0x5800, 0x5815, 3):
            ready[offset] = 1
        with (
            patch("fast_randomizer.native_silent_click_burst") as click_burst,
            patch("fast_randomizer.run_native_control") as native_control,
            patch("fast_randomizer.native_wake_game"),
            patch(
                "fast_randomizer.read_memory",
                side_effect=[bytes(pending), bytes(ready)],
            ),
            patch("fast_randomizer.interruptible_sleep"),
            patch("fast_randomizer.diagnostic_log") as diagnostic,
        ):
            result = advance_seven_member_story(123, 456)

        self.assertEqual(
            [
                unittest.mock.call(
                    456,
                    360,
                    400,
                    80,
                    down_delay_ms=55,
                    up_delay_ms=80,
                ),
                unittest.mock.call(456, 360, 400, 80),
            ],
            click_burst.call_args_list,
        )
        self.assertTrue(result)
        native_control.assert_not_called()
        self.assertTrue(
            any(
                call.args[0] == "seven_member_story_ready"
                for call in diagnostic.call_args_list
            )
        )

    def test_three_person_flow_uses_same_session_skill_memory(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "ccz_randomizer"
            / "app.py"
        ).read_text(encoding="utf-8")
        three_flow = source.split(
            "        if three_person_mode:", 1
        )[1].split("        else:", 1)[0]

        self.assertIn("capture_initial_member_panels(", three_flow)
        self.assertIn("evaluate_task_skill_rules(", three_flow)
        self.assertNotIn("run_candidate_inspection(", three_flow)

    def test_random_flow_enables_acceleration_before_xu_interaction(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "ccz_randomizer"
            / "app.py"
        ).read_text(encoding="utf-8")
        run_flow = source.split("    def r0_only_run(self)", 1)[1]

        self.assertLess(
            run_flow.index("enable_game_acceleration(pid)"),
            run_flow.index('"interaction_start"'),
        )

    def test_seven_member_story_clicks_xu_without_selecting_option(self):
        runner = unittest.mock.Mock()
        with (
            patch("fast_randomizer.trigger_random_choice_click") as choice,
            patch("fast_randomizer.native_silent_click") as click,
            patch("fast_randomizer.native_wake_game") as wake,
            patch(
                "fast_randomizer.print_window_mat",
                side_effect=[
                    np.zeros((4, 4, 3), dtype=np.uint8),
                    np.full((4, 4, 3), 10, dtype=np.uint8),
                ],
            ),
            patch("fast_randomizer.time.sleep"),
            patch("fast_randomizer.diagnostic_log") as diagnostic,
        ):
            method = trigger_seven_member_story(
                runner,
                123,
                456,
                click_strategy="injected_background_mouse",
            )

        self.assertEqual("silent_click", method)
        click.assert_called_once_with(123, 456, 369, 234, tail_delay_ms=350)
        choice.assert_not_called()
        wake.assert_called_once_with(123, 456, 800)
        self.assertEqual(
            "inspection_story_npc_clicked",
            diagnostic.call_args.args[0],
        )

    def test_inspection_failure_screenshot_is_kept_once_per_category(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_dir = root / "temporary-inspection"
            output_dir.mkdir()
            (output_dir / "people-window.png").write_bytes(b"image")
            child_diagnostic = (
                root / "fast_20260927_120000_inspection_slot1_diagnostic.jsonl"
            )
            parent_diagnostic = (
                root / "fast_20260927_120000_diagnostic.jsonl"
            )
            with patch.dict(
                os.environ,
                {
                    "CCZ_INSPECTION_DIAGNOSTIC_PATH": str(child_diagnostic),
                    "CCZ_PARENT_DIAGNOSTIC_PATH": str(parent_diagnostic),
                },
                clear=False,
            ):
                first = app_module.persist_inspection_failure_screenshot(
                    output_dir,
                    category="story_not_advanced",
                    slot=1,
                )
                second = app_module.persist_inspection_failure_screenshot(
                    output_dir,
                    category="story_not_advanced",
                    slot=2,
                )

        self.assertIsNotNone(first)
        self.assertIsNone(second)

    def test_full_inspection_accepts_actual_game_member_order(self):
        member_names = (
            "曹操",
            "夏侯惇",
            "曹仁",
            "夏侯渊",
            "乐进",
            "李典",
            "曹洪",
        )
        with (
            patch("fast_randomizer.click_dialog_button") as click,
            patch(
                "fast_randomizer.current_dialog_member",
                return_value="夏侯渊",
            ),
        ):
            result = advance_people_info_in_game_order(
                123,
                456,
                "夏侯惇",
                member_names,
                {"曹操", "夏侯惇"},
            )
        self.assertEqual((456, "夏侯渊"), result)
        click.assert_called_once_with(
            456,
            "下一武将",
            pid=123,
            force_coordinate=False,
        )

    def test_reused_load_delayed_confirmation_is_closed(self):
        dialog_states = iter([True, False])
        with (
            patch(
                "fast_randomizer.process_windows",
                return_value=[456],
            ),
            patch(
                "fast_randomizer.window_class",
                return_value="#32770",
            ),
            patch(
                "fast_randomizer.window_text",
                return_value="确认",
            ),
            patch(
                "fast_randomizer.user32.IsWindowVisible",
                return_value=True,
            ),
            patch(
                "fast_randomizer.user32.IsWindowEnabled",
                side_effect=[False, True, True],
            ),
            patch(
                "fast_randomizer.user32.IsWindow",
                side_effect=lambda _hwnd: next(dialog_states),
            ),
            patch(
                "fast_randomizer.click_leftmost_dialog_button",
                return_value=True,
            ) as click,
            patch("fast_randomizer.diagnostic_log"),
        ):
            closed = finish_reused_load_confirmation(123, 789)
        self.assertTrue(closed)
        click.assert_called_once_with(456)

    def test_reused_load_without_confirmation_continues_when_ready(self):
        with (
            patch(
                "fast_randomizer.process_windows",
                return_value=[],
            ),
            patch(
                "fast_randomizer.user32.IsWindowEnabled",
                return_value=True,
            ),
        ):
            self.assertFalse(
                finish_reused_load_confirmation(123, 789)
            )

    def test_reused_load_reenables_owner_after_dialog_disappears(self):
        enabled = False

        def enable_window(_hwnd, value):
            nonlocal enabled
            enabled = bool(value)
            return True

        with (
            patch(
                "fast_randomizer.process_windows",
                return_value=[456],
            ),
            patch(
                "fast_randomizer.window_class",
                return_value="#32770",
            ),
            patch(
                "fast_randomizer.window_text",
                return_value="确认",
            ),
            patch(
                "fast_randomizer.user32.IsWindowVisible",
                return_value=True,
            ),
            patch(
                "fast_randomizer.user32.IsWindowEnabled",
                side_effect=lambda _hwnd: enabled,
            ),
            patch(
                "fast_randomizer.user32.IsWindow",
                side_effect=lambda hwnd: hwnd == 789,
            ),
            patch(
                "fast_randomizer.user32.EnableWindow",
                side_effect=enable_window,
            ) as restore,
            patch(
                "fast_randomizer.click_leftmost_dialog_button",
                return_value=True,
            ),
            patch("fast_randomizer.game_state_diagnostic", return_value={}),
            patch(
                "fast_randomizer.process_executable",
                return_value=Path("Ekd5.exe"),
            ),
            patch("fast_randomizer.diagnostic_log"),
        ):
            closed = finish_reused_load_confirmation(123, 789)

        self.assertTrue(closed)
        restore.assert_called_once_with(789, True)

    def test_reused_load_detects_game_process_exit(self):
        with (
            patch(
                "fast_randomizer.process_windows",
                return_value=[456],
            ),
            patch("fast_randomizer.window_class", return_value="#32770"),
            patch("fast_randomizer.window_text", return_value="确认"),
            patch(
                "fast_randomizer.user32.IsWindowVisible",
                return_value=True,
            ),
            patch(
                "fast_randomizer.user32.IsWindowEnabled",
                return_value=False,
            ),
            patch("fast_randomizer.user32.IsWindow", return_value=False),
            patch(
                "fast_randomizer.click_leftmost_dialog_button",
                return_value=True,
            ),
            patch("fast_randomizer.process_executable", return_value=None),
            patch("fast_randomizer.diagnostic_log"),
        ):
            with self.assertRaises(DirectReloadUnsupported):
                finish_reused_load_confirmation(123, 789)

    def test_member_transition_uses_coordinate_fallback(self):
        with (
            patch("fast_randomizer.click_dialog_button") as click,
            patch(
                "fast_randomizer.current_dialog_member",
                return_value="曹仁",
            ),
            patch(
                "fast_randomizer.find_any_member_dialog",
                return_value=(0, ""),
            ),
            patch(
                "fast_randomizer.time.perf_counter",
                side_effect=[0.0, 3.0, 4.0, 4.1],
            ),
            patch("fast_randomizer.time.sleep"),
        ):
            result = advance_people_info_in_game_order(
                123,
                456,
                "夏侯渊",
                ("曹操", "夏侯惇", "夏侯渊", "曹仁"),
                {"曹操", "夏侯惇", "夏侯渊"},
            )

        self.assertEqual((456, "曹仁"), result)
        self.assertTrue(
            any(
                call.kwargs.get("force_coordinate")
                for call in click.call_args_list
            )
        )

    def test_forced_dialog_click_uses_dialog_relative_mouse(self):
        def set_rect(_hwnd, rect_pointer):
            rect = rect_pointer._obj
            rect.left = 400
            rect.top = 500
            rect.right = 418
            rect.bottom = 556
            return True

        def to_client(_hwnd, point_pointer):
            point = point_pointer._obj
            point.x -= 100
            point.y -= 200
            return True

        with (
            patch("fast_randomizer.find_dialog_button", return_value=789),
            patch(
                "fast_randomizer.user32.GetWindowRect",
                side_effect=set_rect,
            ),
            patch(
                "fast_randomizer.user32.ScreenToClient",
                side_effect=to_client,
            ),
            patch("fast_randomizer.user32.SendMessageW") as send_message,
            patch("fast_randomizer.native_silent_click") as native_click,
            patch("fast_randomizer.diagnostic_log") as diagnostic,
        ):
            method = click_dialog_button(
                456,
                "下一武将",
                pid=123,
                force_coordinate=True,
            )

        self.assertEqual("injected_dialog_button_mouse", method)
        native_click.assert_called_once_with(
            123,
            456,
            309,
            328,
            tail_delay_ms=120,
        )
        send_message.assert_not_called()
        self.assertEqual(
            "injected_dialog_button_mouse",
            diagnostic.call_args.kwargs["method"],
        )

    def test_dialog_fixed_fallback_uses_injected_mouse(self):
        def set_window_rect(_hwnd, rect_pointer):
            rect = rect_pointer._obj
            rect.left = 100
            rect.top = 200
            rect.right = 600
            rect.bottom = 700
            return True

        def to_client(_hwnd, point_pointer):
            point = point_pointer._obj
            point.x -= 108
            point.y -= 231
            return True

        with (
            patch("fast_randomizer.find_dialog_button", return_value=0),
            patch("fast_randomizer.user32.IsWindow", return_value=True),
            patch(
                "fast_randomizer.user32.GetWindowRect",
                side_effect=set_window_rect,
            ),
            patch(
                "fast_randomizer.user32.ScreenToClient",
                side_effect=to_client,
            ),
            patch("fast_randomizer.native_silent_click") as native_click,
            patch("fast_randomizer.diagnostic_log") as diagnostic,
        ):
            method = click_dialog_button(
                456,
                "下一武将",
                pid=123,
                force_coordinate=True,
            )

        self.assertEqual("injected_dialog_fallback", method)
        native_click.assert_called_once_with(
            123,
            456,
            412,
            347,
            tail_delay_ms=120,
        )
        self.assertEqual(
            "injected_dialog_fallback",
            diagnostic.call_args.kwargs["method"],
        )

    def test_roster_fallback_skips_captured_member(self):
        runner = unittest.mock.Mock()
        runner.peopleWind.isInitSuccess.return_value = True
        runner.peopleWind.hwnd = 777
        with (
            patch("fast_randomizer.close_member_dialog") as close_dialog,
            patch(
                "fast_randomizer.find_any_member_dialog",
                side_effect=[
                    (888, "夏侯渊"),
                    (999, "曹仁"),
                ],
            ),
            patch("fast_randomizer.time.sleep"),
            patch("fast_randomizer.user32.EnableWindow"),
            patch("fast_randomizer.user32.ShowWindow"),
            patch("fast_randomizer.user32.IsWindow", return_value=True),
            patch("fast_randomizer.run_native_control") as native_control,
            patch("fast_randomizer.diagnostic_log") as diagnostic,
        ):
            result = open_uncaptured_member_from_roster(
                123,
                456,
                runner,
                321,
                ("曹操", "夏侯惇", "夏侯渊", "曹仁"),
                {"曹操", "夏侯惇", "夏侯渊"},
            )

        self.assertEqual((999, "曹仁"), result)
        self.assertEqual(
            [
                unittest.mock.call(
                    123, ["list-window", "777", "3"]
                ),
                unittest.mock.call(
                    123, ["list-window", "777", "0"]
                ),
            ],
            native_control.call_args_list,
        )
        self.assertEqual(
            [
                unittest.mock.call(123, 456, 321),
                unittest.mock.call(123, 456, 888),
            ],
            close_dialog.call_args_list,
        )
        self.assertTrue(
            any(
                call.args[0] == "member_roster_fallback_succeeded"
                for call in diagnostic.call_args_list
            )
        )

    def test_roster_fallback_uses_injected_click_after_list_command_error(self):
        runner = unittest.mock.Mock()
        runner.peopleWind.isInitSuccess.return_value = True
        runner.peopleWind.hwnd = 777
        with (
            patch("fast_randomizer.close_member_dialog"),
            patch(
                "fast_randomizer.find_any_member_dialog",
                return_value=(999, "曹仁"),
            ),
            patch("fast_randomizer.user32.EnableWindow"),
            patch("fast_randomizer.user32.ShowWindow"),
            patch("fast_randomizer.user32.IsWindow", return_value=True),
            patch(
                "fast_randomizer.run_native_control",
                side_effect=NativeControlError(162),
            ),
            patch(
                "fast_randomizer.native_background_click"
            ) as background_click,
            patch("fast_randomizer.native_wake_game") as wake_game,
            patch("fast_randomizer.diagnostic_log") as diagnostic,
        ):
            result = open_uncaptured_member_from_roster(
                123,
                456,
                runner,
                321,
                ("曹操", "夏侯惇", "夏侯渊", "曹仁"),
                {"曹操", "夏侯惇", "夏侯渊"},
            )

        self.assertEqual((999, "曹仁"), result)
        background_click.assert_called_once_with(
            777,
            54,
            129 + 60 * 3,
            1,
            False,
        )
        wake_game.assert_called_once_with(123, 456, 800)
        self.assertTrue(
            any(
                call.args[0] == "member_roster_fallback_click_failed"
                and call.kwargs["method"] == "list_window_command"
                for call in diagnostic.call_args_list
            )
        )

    def test_roster_fallback_reopens_list_from_known_main_window(self):
        runner = unittest.mock.Mock()
        runner.peopleWind.isInitSuccess.side_effect = [False, True]
        runner.peopleWind.hwnd = 777
        with (
            patch(
                "fast_randomizer.user32.IsWindow",
                return_value=True,
            ),
            patch("fast_randomizer.user32.IsWindowEnabled"),
            patch("fast_randomizer.user32.EnableWindow") as enable_window,
            patch(
                "fast_randomizer.time.perf_counter",
                side_effect=[0.0, 0.1, 0.2],
            ),
            patch("fast_randomizer.time.sleep"),
            patch("fast_randomizer.diagnostic_log"),
        ):
            result = ensure_people_roster_open(123, 456, runner)

        self.assertEqual(777, result)
        enable_window.assert_called_once_with(777, True)

    def test_roster_fallback_reuses_saved_list_window(self):
        runner = unittest.mock.Mock()
        with (
            patch("fast_randomizer.user32.IsWindow", return_value=True),
            patch("fast_randomizer.user32.EnableWindow") as enable_window,
            patch("fast_randomizer.user32.ShowWindow") as show_window,
            patch("fast_randomizer.diagnostic_log"),
        ):
            result = ensure_people_roster_open(
                123,
                456,
                runner,
                preferred_list_window=777,
            )

        self.assertEqual(777, result)
        runner.initPeopleWind.assert_not_called()
        enable_window.assert_called_once_with(777, True)
        show_window.assert_called_once_with(777, 5)

    def test_closing_member_dialog_restores_its_owner(self):
        with (
            patch("fast_randomizer.user32.GetWindow", return_value=654),
            patch("fast_randomizer.user32.IsWindow", return_value=True),
            patch("fast_randomizer.user32.IsWindowEnabled", return_value=True),
            patch("fast_randomizer.user32.EnableWindow") as enable_window,
            patch("fast_randomizer.user32.ShowWindow") as show_window,
            patch("fast_randomizer.user32.PostMessageW") as post_message,
            patch("fast_randomizer.click_dialog_button") as click_button,
            patch(
                "fast_randomizer.wait_for_member_dialog_closed",
                return_value=True,
            ),
            patch("fast_randomizer.diagnostic_log"),
        ):
            close_member_dialog(123, 456, 789)

        post_message.assert_called_once_with(789, 0x0010, 0, 0)
        click_button.assert_not_called()
        self.assertEqual(
            [unittest.mock.call(654, True), unittest.mock.call(456, True)],
            enable_window.call_args_list,
        )
        show_window.assert_called_once_with(654, 5)

    def test_verified_skill_memory_reader_is_used_without_legacy_patch(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "ccz_randomizer"
            / "app.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn(
            "CczReRandTask.checkPeopleAtR1 = fast_check_people_at_r1",
            source,
        )
        self.assertNotIn(
            "CczReRandTask._getTeamSkillsInfo =",
            source,
        )
        self.assertIn("read_skill_memory(pid, record_indices)", source)

    def test_initial_roster_uses_xiahou_yuan_not_cao_ren(self):
        self.assertEqual(
            ("曹操", "夏侯惇", "夏侯渊"),
            tuple(member[0] for member in INITIAL_TEAM_MEMBERS),
        )
        self.assertEqual(
            ("member-0", "member-1", "member-3"),
            initial_team_members(
                tuple(f"member-{index}" for index in range(7))
            ),
        )

    def test_dead_game_always_requires_restart(self):
        self.assertTrue(
            session_failure_requires_restart(
                FakeGameSession(False),
                RuntimeError("unknown failure"),
            )
        )

    def test_interaction_failure_requires_restart(self):
        self.assertTrue(
            session_failure_requires_restart(
                FakeGameSession(),
                InteractionNotTriggered(
                    "点击许子将后兵种内存仍未发生变化"
                ),
            )
        )

    def test_partial_memory_read_requires_restart(self):
        error = OSError(299, "仅完成部分的 ReadProcessMemory 请求")
        error.winerror = 299

        self.assertTrue(
            session_failure_requires_restart(
                FakeGameSession(),
                error,
            )
        )

    def test_unrelated_os_error_does_not_require_restart(self):
        error = OSError(5, "拒绝访问")
        error.winerror = 5

        self.assertFalse(
            session_failure_requires_restart(
                FakeGameSession(),
                error,
            )
        )

    def test_invalid_source_save_does_not_restart(self):
        self.assertFalse(
            session_failure_requires_restart(
                FakeGameSession(),
                RuntimeError("第 20 号存档已经包含随机结果，不能作为源存档"),
            )
        )

    def test_rule_rejection_does_not_restart(self):
        self.assertFalse(
            session_failure_requires_restart(
                FakeGameSession(),
                RuntimeError("兵种综合评价未达到当前规则要求"),
            )
        )

    def test_inspection_failure_does_not_restart_healthy_main_game(self):
        error = InspectionProcessError(
            "initial",
            1,
            "ccz_randomizer.app.NativeControlError: "
            "静默控件模块执行失败，代码 207："
            "ControlAction remote thread timed out",
        )

        self.assertFalse(
            session_failure_requires_restart(FakeGameSession(), error)
        )
        self.assertEqual(207, error.return_code)
        self.assertTrue(error.native_timeout)

    def test_security_policy_failure_does_not_restart_game(self):
        self.assertFalse(
            session_failure_requires_restart(
                FakeGameSession(),
                NativeControlError(
                    5,
                    "LoadLibrary remote thread failed: "
                    "win32=5, ntstatus=0xC0000022",
                ),
            )
        )

    def test_terminating_process_native_failure_requires_restart(self):
        error = NativeControlError(
            5,
            "LoadLibrary remote thread failed: "
            "win32=5, ntstatus=0xC000010A",
        )

        self.assertTrue(
            session_failure_requires_restart(
                FakeGameSession(),
                error,
            )
        )
        self.assertIn("游戏进程正在退出", str(error))
        self.assertNotIn("360", str(error))

    def test_timeout_can_still_restart_game(self):
        self.assertTrue(
            session_failure_requires_restart(
                FakeGameSession(),
                NativeControlTimeout("静默控件模块响应超时"),
            )
        )

    def test_admin_security_hint_does_not_ask_for_admin_again(self):
        with patch("fast_randomizer.is_running_as_admin", return_value=True):
            hint = native_control_error_hint(5)
        self.assertIn("当前已使用管理员权限运行", hint)
        self.assertIn("ccz_control.dll", hint)
        self.assertIn("360", hint)
        self.assertIn("Windows 安全中心", hint)
        self.assertIn("游戏目录加入信任区", hint)

    def test_non_admin_security_hint_recommends_admin_mode(self):
        with patch("fast_randomizer.is_running_as_admin", return_value=False):
            hint = native_control_error_hint(5)
        self.assertIn("以管理员身份运行", hint)
        self.assertNotIn("无需再次尝试管理员模式", hint)

    def test_environment_guidance_is_visible_in_user_log(self):
        self.assertEqual(
            "2. 检查安全软件拦截记录",
            format_user_log("环境处理提示：2. 检查安全软件拦截记录"),
        )

    def test_restart_message_is_distinct(self):
        self.assertEqual(
            "后台游戏异常，已重新启动",
            format_user_log(
                "隐藏游戏实例已重新启动，PID=123；"
                "游戏未取得前台，系统鼠标未被程序控制。"
            ),
        )

    def test_traceback_header_is_not_shown_as_an_extra_failure(self):
        self.assertEqual("", format_user_log("Traceback (most recent call last):"))

    def test_subprocess_output_supports_utf8_and_gb18030(self):
        text = "静默控件模块响应超时"
        self.assertEqual(text, decode_subprocess_output(text.encode("utf-8")))
        self.assertEqual(text, decode_subprocess_output(text.encode("gb18030")))

    def test_background_click_timeout_is_treated_as_delivered(self):
        with (
            patch(
                "fast_randomizer.user32.GetWindowThreadProcessId",
                side_effect=lambda _hwnd, pointer: setattr(
                    pointer._obj, "value", 123
                ),
            ),
            patch(
                "fast_randomizer.run_native_control",
                side_effect=NativeControlTimeout("静默控件模块响应超时"),
            ),
            patch("fast_randomizer.diagnostic_log") as diagnostic,
        ):
            native_background_click(456, 10, 20, 1, False)
        diagnostic.assert_called_once()

    def test_timed_silent_click_passes_tail_delay_to_native_control(self):
        with patch("fast_randomizer.run_native_control") as control:
            native_silent_click(
                123,
                456,
                10,
                20,
                tail_delay_ms=0,
            )
        control.assert_called_once_with(
            123,
            ["silent-click-timed", "456", "10", "20", "0"],
        )

    def test_default_silent_click_keeps_compatible_action(self):
        with patch("fast_randomizer.run_native_control") as control:
            native_silent_click(123, 456, 10, 20)
        control.assert_called_once_with(
            123,
            ["silent-click", "456", "10", "20"],
        )

    def test_fast_choice_click_uses_result_without_fallback(self):
        with (
            patch("fast_randomizer.native_silent_click") as click,
            patch(
                "fast_randomizer.read_job_ids",
                return_value=(1, 2, 3),
            ),
        ):
            result = trigger_random_choice_click(
                123,
                456,
                (0, 1, 2),
                (0, 0, 0),
                1,
            )
        self.assertEqual((1, 2, 3), result)
        click.assert_called_once_with(
            123,
            456,
            297,
            220,
            tail_delay_ms=0,
        )

    def test_fast_choice_click_falls_back_when_state_does_not_change(self):
        with (
            patch("fast_randomizer.native_silent_click") as click,
            patch(
                "fast_randomizer.read_job_ids",
                side_effect=[(0, 0, 0), (1, 2, 3)],
            ),
            patch("fast_randomizer.diagnostic_log") as diagnostic,
        ):
            result = trigger_random_choice_click(
                123,
                456,
                (0, 1, 2),
                (0, 0, 0),
                2,
            )
        self.assertEqual((1, 2, 3), result)
        self.assertEqual(2, click.call_count)
        self.assertNotIn(
            "tail_delay_ms",
            click.call_args_list[1].kwargs,
        )
        diagnostic.assert_called_once()

    def test_inspection_process_retries_once(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "inspection"
            with patch(
                "fast_randomizer.run_inspection_process_once",
                side_effect=[
                    RuntimeError("temporary failure"),
                    {"qualified": True},
                ],
            ) as run_once:
                result = run_inspection_process(
                    Path("Ekd5.exe"),
                    16,
                    output_dir,
                    7.5,
                )
        self.assertEqual({"qualified": True}, result)
        self.assertEqual(2, run_once.call_count)
        self.assertFalse(
            run_once.call_args_list[0].kwargs[
                "force_injected_story_click"
            ]
        )
        self.assertTrue(
            run_once.call_args_list[1].kwargs[
                "force_injected_story_click"
            ]
        )
        self.assertEqual(
            1,
            run_once.call_args_list[0].kwargs["attempt"],
        )
        self.assertEqual(
            2,
            run_once.call_args_list[1].kwargs["attempt"],
        )

    def test_inspection_child_writes_complete_diagnostic_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log_path = root / "inspection.log"
            diagnostic_path = root / "inspection_diagnostic.jsonl"

            def operation():
                print("child inspection output")
                app_module.diagnostic_log(
                    "inspection_test_stage",
                    marker="complete",
                )
                return 0

            with patch.dict(
                os.environ,
                {
                    "CCZ_INSPECTION_LOG_PATH": str(log_path),
                    "CCZ_INSPECTION_DIAGNOSTIC_PATH": str(
                        diagnostic_path
                    ),
                    "CCZ_INSPECTION_ATTEMPT": "2",
                    "CCZ_INSPECTION_CLICK_STRATEGY": (
                        "injected_background_mouse"
                    ),
                },
                clear=False,
            ):
                result = run_inspection_cli_with_diagnostics(
                    "full",
                    operation,
                )

            records = [
                json.loads(line)
                for line in diagnostic_path.read_text(
                    encoding="utf-8"
                ).splitlines()
                if line.strip()
            ]
            events = [record["event"] for record in records]
            self.assertEqual(0, result)
            self.assertIn("child inspection output", log_path.read_text(
                encoding="utf-8"
            ))
            self.assertIn("inspection_child_started", events)
            self.assertIn("inspection_test_stage", events)
            self.assertIn("inspection_child_completed", events)
            self.assertEqual(
                "injected_background_mouse",
                records[0]["context"]["click_strategy"],
            )

    def test_inspection_attempt_logs_are_outside_retry_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "panels" / "save-1"
            paths = inspection_attempt_paths(output_dir, 2)
            self.assertTrue(all(path.parent == output_dir.parent for path in paths))
            self.assertTrue(all(path.is_absolute() for path in paths))
            self.assertTrue(
                all("attempt-2" in path.name for path in paths)
            )

    def test_initial_inspection_process_retries_once(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "inspection"
            with patch(
                "fast_randomizer.run_initial_inspection_process_once",
                side_effect=[
                    RuntimeError("temporary failure"),
                    {"panels": ["one", "two", "three"]},
                ],
            ) as run_once:
                result = run_initial_inspection_process(
                    Path("Ekd5.exe"),
                    1,
                    output_dir,
                    7.5,
                )
        self.assertEqual(
            {"panels": ["one", "two", "three"]},
            result,
        )
        self.assertEqual(2, run_once.call_count)

    def test_initial_inspection_wraps_native_timeout_from_child_process(self):
        child_output = (
            "ccz_randomizer.app.NativeControlError: "
            "静默控件模块执行失败，代码 207："
            "ControlAction remote thread timed out: action=2"
        ).encode("utf-8")
        process = unittest.mock.Mock()
        process.communicate.return_value = (child_output, None)
        process.returncode = 1

        with tempfile.TemporaryDirectory() as directory:
            with patch("fast_randomizer.subprocess.Popen", return_value=process):
                with self.assertRaises(InspectionProcessError) as captured:
                    run_initial_inspection_process_once(
                        Path("Ekd5.exe"),
                        16,
                        Path(directory),
                        7.5,
                    )

        error = captured.exception
        self.assertEqual(207, error.return_code)
        self.assertTrue(error.native_timeout)
        self.assertEqual("NativeControlError", error.inner_error_type)

    def test_native_timeout_candidate_is_rejected_without_propagating(self):
        error = InspectionProcessError(
            "initial",
            1,
            "ccz_randomizer.app.NativeControlError: "
            "静默控件模块执行失败，代码 207："
            "ControlAction remote thread timed out",
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            patch(
                "fast_randomizer.run_initial_inspection_process",
                side_effect=error,
            ),
            patch("fast_randomizer.diagnostic_log") as diagnostic,
        ):
            result = run_candidate_inspection(
                Path("Ekd5.exe"),
                16,
                Path(directory),
                7.5,
                mode="three",
            )

        self.assertIsNone(result)
        diagnostic.assert_called_once()
        self.assertEqual(
            "candidate_inspection_abandoned",
            diagnostic.call_args.args[0],
        )

    def test_repeated_native_timeout_keeps_inspection_error_type(self):
        error = InspectionProcessError(
            "initial",
            1,
            "ccz_randomizer.app.NativeControlError: "
            "静默控件模块执行失败，代码 207："
            "ControlAction remote thread timed out",
        )
        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "fast_randomizer.run_initial_inspection_process_once",
                side_effect=error,
            ) as run_once:
                with self.assertRaises(InspectionProcessError):
                    run_initial_inspection_process(
                        Path("Ekd5.exe"),
                        16,
                        Path(directory),
                        7.5,
                    )

        self.assertEqual(2, run_once.call_count)


if __name__ == "__main__":
    unittest.main()
