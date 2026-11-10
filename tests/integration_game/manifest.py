from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GameCase:
    name: str
    module: str
    description: str
    default: bool = True


CASES = (
    GameCase("loop-history-rules", "case_loop_history_rules.py",
             "切换规则后普通随机与循环随机，核对历史轮次、规则快照、归档及存档副本", default=False),
    GameCase("normal-save-readback", "case_normal_save_readback.py",
             "常规主流程三轮筛选保存，重启读取全部人物兵种和特技"),
    GameCase("turbo-save-readback", "case_turbo_save_readback.py",
             "极速主流程三轮筛选保存，重启读取全部人物兵种和特技"),
    GameCase("turbo-fallback-readback", "case_turbo_fallback_readback.py",
             "极速首次 NPC 输入失效后回退，后续保存和重启读回"),
    GameCase(
        "dialog-message",
        "case_dialog_message.py",
        "验证对话消息与隐藏窗口交互",
        default=False,
    ),
    GameCase(
        "direct-native-flow",
        "case_direct_native_flow.py",
        "验证原生直接读档后的游戏状态",
        default=False,
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
        default=False,
    ),
    GameCase(
        "randomizer-three-normal-load",
        "case_randomizer_three_normal_load.py",
        "验证三人随机与正常读档复用",
        default=False,  # Legacy low-level diagnostic; production runner is tested by readback cases.
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
        default=False,  # Legacy low-level diagnostic; production runner is tested by readback cases.
    ),
    GameCase(
        "seven-result-save-stage",
        "case_seven_result_save_stage.py",
        "验证七人结果保存的是剧情推进前的初始场景存档",
        default=False,  # Legacy engine path; the current app only exposes three-person mode.
    ),
    GameCase(
        "result-save-stage",
        "case_result_save_stage.py",
        "验证当前随机流程通过游戏菜单保存到指定结果槽位",
    ),
    GameCase(
        "seven-member-inspection",
        "case_seven_member_inspection.py",
        "验证七人候选存档的剧情推进与能力读取",
        default=False,
    ),
    GameCase(
        "native-confirm",
        "case_native_confirm_flow.py",
        "验证确认对话流程",
    ),
    GameCase(
        "native-ui-load",
        "case_native_ui_load.py",
        "验证静默读档结束后前台窗口保持不变",
    ),
    GameCase(
        "repeat-sv020",
        "case_repeat_sv020_reload.py",
        "重复读取第20号源存档并触发随机",
        default=False,
    ),
    GameCase(
        "silent-click-tail-benchmark",
        "case_silent_click_tail_benchmark.py",
        "基准测试第二次随机点击的尾部等待",
        default=False,
    ),
    GameCase(
        "scene-wait-benchmark",
        "case_scene_wait_benchmark.py",
        "分别基准测试读档前后的场景等待",
        default=False,
    ),
    GameCase(
        "story-burst-benchmark",
        "case_story_burst_benchmark.py",
        "基准测试七人剧情连点间隔和就绪提前停止",
        default=False,
    ),
    GameCase(
        "silent-real-flow",
        "case_silent_real_flow.py",
        "验证静默真实随机流程",
        default=False,  # Legacy low-level diagnostic; production runner is tested by readback cases.
    ),
    GameCase(
        "start-game-loop",
        "case_start_game_loop.py",
        "验证游戏启动和循环状态",
        default=False,  # Legacy low-level diagnostic; production runner is tested by readback cases.
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
        default=False,
    ),
)


def select_cases(names: list[str]) -> tuple[GameCase, ...]:
    if not names:
        return tuple(case for case in CASES if case.default)
    requested = set(names)
    selected = tuple(case for case in CASES if case.name in requested)
    missing = sorted(requested - {case.name for case in selected})
    if missing:
        raise ValueError("未知游戏测试：" + "、".join(missing))
    return selected
