import tempfile
import unittest
import ast
from pathlib import Path
from unittest.mock import patch

from fast_randomizer import (
    EQUIPMENT_NAMES,
    INITIAL_TEAM_MEMBERS,
    Tee,
    decode_equipment_effect,
    decode_subprocess_output,
    format_user_log,
    initial_team_members,
    native_background_click,
    run_initial_inspection_process,
    run_inspection_process,
    session_failure_requires_restart,
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
                RuntimeError(
                    "连续 3 次点击许子将并选择第一项后，兵种内存仍未发生变化"
                ),
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
                side_effect=RuntimeError("静默控件模块响应超时"),
            ),
            patch("fast_randomizer.diagnostic_log") as diagnostic,
        ):
            native_background_click(456, 10, 20, 1, False)
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
