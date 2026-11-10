"""Conventional interaction timings, independent of optional fast strategies."""
from __future__ import annotations


class NormalRandomInteraction:
    def __init__(self, services, pid):
        self.services = services
        self.pid = pid

    def scene_delay(self, regular_delay):
        return regular_delay

    def click_npc(self, hwnd, position, attempt):
        self.services.native_silent_click(
            self.pid, hwnd, *position, tail_delay_ms=0 if attempt == 1 else None,
        )

    def settle_npc(self):
        self.services.interruptible_sleep(.5)

    def select_choice(self, hwnd, positions, before, attempt):
        return self.services.trigger_random_choice_click(self.pid, hwnd, positions, before, attempt)

    def wait_for_result(self, positions, before, current):
        services = self.services
        deadline = services.time.perf_counter() + 3
        while services.time.perf_counter() < deadline:
            services.check_stop_requested()
            current = services.read_job_ids(self.pid, positions)
            if current != before and any(current):
                break
            services.interruptible_sleep(.05)
        return current
