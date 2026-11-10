"""Select a session-local interaction strategy and coordinate one-way fallback."""
from __future__ import annotations

from ccz_randomizer.runtime.normal_random import NormalRandomInteraction


class RandomInteractionSession:
    def __init__(self, services, pid, *, turbo_enabled=False):
        self.services = services
        self.normal = NormalRandomInteraction(services, pid)
        self.selected = self.normal
        if turbo_enabled:
            # Normal sessions do not construct or consult the turbo policy.
            from ccz_randomizer.runtime.turbo import TurboRandomPolicy
            turbo = TurboRandomPolicy(services, pid, enabled=True)
            if turbo.enabled:
                self.selected = turbo

    def scene_delay(self, regular_delay):
        return self.for_attempt(1).scene_delay(regular_delay)

    def for_attempt(self, attempt):
        if self.selected is not self.normal and not self.selected.enabled:
            self.selected = self.normal
        return self.selected if attempt == 1 else self.normal

    def on_no_change(self, strategy, regular_scene_delay):
        if strategy is self.normal:
            return
        self.selected = self.normal
        strategy.disable('interaction_not_completed')
        self.services.interruptible_sleep(regular_scene_delay)
