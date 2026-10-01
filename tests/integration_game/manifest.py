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
        "验证原生直接读档后的游戏状态",
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
        "randomizer-three-normal-load",
        "case_randomizer_three_normal_load.py",
        "验证三人随机与正常读档复用",
    ),
    GameCase(
        "three-member-inspection",
        "case_three_member_inspection.py",
        "验证初始三人同实例特技检查与保存",
    ),
    GameCase(
        "randomizer-seven-normal-load",
        "case_randomizer_seven_normal_load.py",
        "验证七人随机与正常读档复用",
    ),
    GameCase(
        "seven-result-save-stage",
        "case_seven_result_save_stage.py",
        "验证七人结果保存的是剧情推进前的初始场景存档",
    ),
    GameCase(
        "statistics-real-flow",
        "case_statistics_real_flow.py",
        "验证真实三人和七人流程写入统计历史并通过校验",
    ),
    GameCase(
        "statistics-concurrent-flow",
        "case_statistics_concurrent_flow.py",
        "验证真实并发和循环流程写入统计历史并通过校验",
    ),
    GameCase(
        "seven-member-inspection",
        "case_seven_member_inspection.py",
        "验证七人候选存档的剧情推进与能力读取",
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
        "silent-click-tail-benchmark",
        "case_silent_click_tail_benchmark.py",
        "基准测试第二次随机点击的尾部等待",
    ),
    GameCase(
        "scene-wait-benchmark",
        "case_scene_wait_benchmark.py",
        "分别基准测试读档前后的场景等待",
    ),
    GameCase(
        "story-burst-benchmark",
        "case_story_burst_benchmark.py",
        "基准测试七人剧情连点间隔和就绪提前停止",
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
        "stop-during-randomization",
        "case_stop_during_randomization.py",
        "验证停止请求可中断当前步骤且不会触发异常重启",
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
