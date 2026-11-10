"""Opt-in short input pulses with verified results and a per-session fallback."""
from __future__ import annotations


class TurboRandomPolicy:
    # Input timing is measured against this layout; new layouts start normally.
    SUPPORTED_VERSIONS = frozenset({'2.20-1104-night'})

    def __init__(self, services, pid, *, enabled=False):
        self.services = services
        self.pid = pid
        self.enabled = bool(enabled and services.current_game_version() in self.SUPPORTED_VERSIONS)

    def scene_delay(self, regular_delay):
        return .05 if self.enabled and regular_delay == 1.0 else regular_delay

    def click(self, hwnd, position):
        self.services.check_stop_requested()
        self.services.native_silent_click_burst(
            hwnd, *position, 1, down_delay_ms=100, up_delay_ms=0,
        )

    def click_npc(self, hwnd, position, attempt):
        self.click(hwnd, position)

    def settle_npc(self):
        self.services.interruptible_sleep(.05)

    def wait_for_result(self, positions, before, current):
        # select_choice owns the turbo result/stability deadline.
        return current

    def select_choice(self, hwnd, positions, before, attempt=1):
        """Wait for the changed save state to settle before filtering it."""
        services = self.services
        self.click(hwnd, services.CONFIRM_FIRST_CLIENT_POSITION)
        # Shorter menu input can expose a still-running game update. This is
        # an upper bound only; stable results return immediately as before.
        deadline = services.time.perf_counter() + 1.5
        previous = None
        current = before
        changed = False
        while services.time.perf_counter() < deadline:
            services.check_stop_requested()
            current = services.read_job_ids(self.pid, positions)
            if current != before and any(current):
                changed = True
                snapshot = services.read_memory(self.pid, 0, services.R0_MEMORY_SIZE)
                if len(snapshot) != services.R0_MEMORY_SIZE:
                    self.disable('incomplete_result')
                    raise services.InteractionNotTriggered('极速随机结果内存不完整，重新读取源存档后再试')
                if snapshot == previous:
                    return current
                previous = snapshot
            else:
                previous = None
            services.interruptible_sleep(.05)
        if changed:
            self.disable('unstable_result')
            raise services.InteractionNotTriggered('极速随机结果尚未稳定，重新读取源存档后再试')
        return before

    def disable(self, reason):
        self.enabled = False
        self.services.diagnostic_log('turbo_fallback', pid=self.pid, reason=reason)
