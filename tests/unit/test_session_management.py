import tempfile
import unittest
import ast
import json
import os
from pathlib import Path
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
    run_candidate_inspection,
    run_initial_inspection_process,
    run_initial_inspection_process_once,
    run_inspection_cli_with_diagnostics,
    run_inspection_process,
    session_failure_requires_restart,
    trigger_seven_member_story,
    trigger_random_choice_click,
)


class FakeGameSession:
    def __init__(self, healthy: bool = True):
        self.healthy = healthy

    def is_healthy(self) -> bool:
        return self.healthy


class SessionManagementTests(unittest.TestCase):
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

    def test_saved_result_verification_uses_normal_game_load(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "ccz_randomizer"
            / "app.py"
        ).read_text(encoding="utf-8")
        verification_source = source.split(
            "def verify_saved_result(", 1
        )[1].split("for output_slot,", 1)[0]
        self.assertIn("normal_load_verified(", verification_source)
        self.assertIn("verifier.loadAndConfirm", verification_source)
        self.assertNotIn("direct_load_verified(", verification_source)

    def test_full_inspection_uses_resilient_member_transition(self):
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
        with (
            patch("fast_randomizer.native_silent_click_burst") as click_burst,
            patch("fast_randomizer.run_native_control") as native_control,
            patch("fast_randomizer.native_wake_game") as wake_game,
            patch("fast_randomizer.time.sleep") as sleep,
            patch("fast_randomizer.diagnostic_log") as diagnostic,
        ):
            advance_seven_member_story(
                123,
                456,
                rounds=3,
                clicks_per_round=12,
            )

        self.assertEqual(3, click_burst.call_count)
        click_burst.assert_called_with(456, 360, 400, 12)
        self.assertEqual(3, native_control.call_count)
        native_control.assert_called_with(
            123,
            ["frame-click", "466", "418"],
        )
        self.assertEqual(
            [
                unittest.mock.call(123, 456, 1000),
                unittest.mock.call(123, 456, 1000),
                unittest.mock.call(123, 456, 1000),
            ],
            wake_game.call_args_list,
        )
        self.assertEqual(
            [
                unittest.mock.call(0.8),
                unittest.mock.call(0.8),
                unittest.mock.call(0.8),
                unittest.mock.call(1.0),
            ],
            sleep.call_args_list,
        )
        self.assertEqual(3, diagnostic.call_count)

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

    def test_unverified_skill_memory_reader_is_not_patched_into_runtime(self):
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
