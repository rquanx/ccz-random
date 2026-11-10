"""The scheduler owns shared history; slot workers only attach and write results."""
from __future__ import annotations

from ccz_randomizer.history import HistoryRepository


class HistoryLifecycle:
    def __init__(self, repository: HistoryRepository, run_id: str, *,
                 owner: bool = True, expected_results: int = 15):
        self.repository = repository
        self.run_id = run_id
        self.owner = owner
        self.expected_results = expected_results
        self._rounds: dict[int, int] = {}
        self._finished: set[int] = set()

    def start_run(self, **metadata) -> None:
        if self.owner:
            self.repository.start_run(self.run_id, **metadata)

    def start_round(self, round_number: int) -> int:
        if not self.owner:
            return self.repository.require_round(self.run_id, round_number)
        if round_number not in self._rounds:
            self._rounds[round_number] = self.repository.start_round(self.run_id, round_number)
        return self._rounds[round_number]

    def finish_round(self, round_id: int, status: str) -> None:
        if self.owner:
            self.repository.finish_round(round_id, status)
            self._finished.add(round_id)

    def finish_run(self, status: str) -> None:
        if not self.owner:
            return
        # Called only after all slot workers have exited. Empty rounds are
        # safe to prune now; a participant must never perform this cleanup.
        for round_id in self._rounds.values():
            if round_id not in self._finished:
                complete = len(self.repository.get_round_summaries(round_id)) == self.expected_results
                self.finish_round(round_id, 'completed' if complete else status)
        self.repository.finish_run(self.run_id, status)
