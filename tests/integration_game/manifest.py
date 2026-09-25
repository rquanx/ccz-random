from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GameCase:
    name: str
    module: str
    description: str


CASES = (
    GameCase(
        "dialog-message",
        "case_dialog_message.py",
        "验证对话消息与隐藏窗口交互",
    ),
    GameCase(
        "direct-native-flow",
        "case_direct_native_flow.py",
        "验证原生控件驱动的完整流程",
    ),
    GameCase(
        "direct-native-random",
        "case_direct_native_random.py",
        "验证原生随机触发和内存变化",
    ),
    GameCase(
        "isolated-real-flow",
        "case_isolated_real_flow.py",
        "验证独立桌面中的真实流程",
    ),
    GameCase(
        "load-transition",
        "case_load_transition_probe.py",
        "记录读档状态切换",
    ),
    GameCase(
        "native-confirm",
        "case_native_confirm_flow.py",
        "验证确认对话流程",
    ),
    GameCase(
        "native-ui-load",
        "case_native_ui_load.py",
        "验证静默读档不抢前台和鼠标",
    ),
    GameCase(
        "repeat-sv020",
        "case_repeat_sv020_reload.py",
        "重复读取第20号源存档并触发随机",
    ),
    GameCase(
        "silent-real-flow",
        "case_silent_real_flow.py",
        "验证静默真实随机流程",
    ),
    GameCase(
        "start-game-loop",
        "case_start_game_loop.py",
        "验证游戏启动和循环状态",
    ),
    GameCase(
        "tick-transition",
        "case_tick_transition.py",
        "记录游戏主循环状态切换",
    ),
)


def select_cases(names: list[str]) -> tuple[GameCase, ...]:
    if not names:
        return CASES
    requested = set(names)
    selected = tuple(case for case in CASES if case.name in requested)
    missing = sorted(requested - {case.name for case in selected})
    if missing:
        raise ValueError("未知游戏测试：" + "、".join(missing))
    return selected
