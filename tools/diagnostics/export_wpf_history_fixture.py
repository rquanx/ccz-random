"""Create a SQLite compatibility fixture with the existing Python repository."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from ccz_randomizer.history import HistoryRepository


def main():
    root = Path(__file__).resolve().parents[2]
    personnel = json.loads((root / 'tests/fixtures/personnel_22/randomized-personnel.json').read_text(encoding='utf-8'))
    person = next(p for p in personnel if p['name'] == '张宝')
    snapshot = dict(slot=1, acceptedAttempt=2, mode='three', members=[dict(name='曹操')],
        personnel=[person], detail=dict(job=dict(metrics=dict(eligibleMembers=['张宝'], average=7),
        members=[dict(name='张宝', score=7)])), save=dict(path='fixture/SV001.E5S', verified=True))
    with TemporaryDirectory() as directory:
        repository = HistoryRepository(Path(directory))
        repository.start_run('python-fixture', mode='three', loop_random=True, rule_name='张宝规则', rule={}, build={})
        number = repository.start_round('python-fixture', 1)
        repository.save_result(number, snapshot)
        repository.finish_round(number, 'completed')
        repository.start_round('python-fixture', 2)  # An unfinished empty round must stay hidden.
        target = root / 'tests/fixtures/history_22/python-history.sqlite3'
        target.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(repository.path)) as source, closing(sqlite3.connect(target)) as destination:
            source.backup(destination)


if __name__ == '__main__':
    main()
