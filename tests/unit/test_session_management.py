import tempfile
import unittest
import ast
from pathlib import Path
from unittest.mock import patch

from fast_randomizer import (
    EQUIPMENT_NAMES,
    INITIAL_TEAM_MEMBERS,
    DirectReloadUnsupported,
    InteractionNotTriggered,
    NativeControlError,
    NativeControlTimeout,
    Tee,
    advance_people_info_in_game_order,
    decode_equipment_effect,
    decode_subprocess_output,
    finish_reused_load_confirmation,
    format_user_log,
    initial_team_members,
    native_background_click,
    native_control_error_hint,
    native_silent_click,
    run_initial_inspection_process,
    run_inspection_process,
    session_failure_requires_restart,
    trigger_random_choice_click,
)


class FakeGameSession:
    def __init__(self, healthy: bool = True):
        self.healthy = healthy

    def is_healthy(self) -> bool:
        return self.healthy


class SessionManagementTests(unittest.TestCase):
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

    def test_reused_session_failure_restarts_without_in_process_retry(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "ccz_randomizer"
            / "app.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "interaction_limit = 1 if reused_session else 3",
            source,
        )
        self.assertNotIn("interaction_compat_reload_start", source)
        self.assertNotIn("interaction_compat_reload_ready", source)

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


if __name__ == "__main__":
    unittest.main()
