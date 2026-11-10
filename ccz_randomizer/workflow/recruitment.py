"""Finish 2.2's post-randomization choice using its recorded game state."""
from __future__ import annotations

from ccz_randomizer.profiles import load_profile
RECRUITMENT_ENABLED_MARKER = load_profile().script_rules["recruitmentEnabledMarker"].encode("gb18030")


def recruitment_enabled(state: bytes) -> bool:
    return RECRUITMENT_ENABLED_MARKER in state


def enable_recruitment(*, read_state, start_dialogue, advance_first_choice, check_stop,
                       max_steps: int = 40) -> None:
    check_stop()
    if recruitment_enabled(read_state()):
        return
    start_dialogue()
    for _ in range(max_steps):
        check_stop()
        if recruitment_enabled(read_state()):
            return
        advance_first_choice()
    if not recruitment_enabled(read_state()):
        raise RuntimeError("未确认招募模式已开启，本次结果不保存")
