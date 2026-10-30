"""Measure repeated rejected rolls in an isolated copy; never alter source saves."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import tempfile
import time
from unittest.mock import patch

from ccz_randomizer import app
from ccz_randomizer.rules.config import default_rule_config, active_profile
from ccz_randomizer.runtime.game_sandbox import create_game_sandbox


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--attempts', type=int, default=5)
    parser.add_argument('--skip-first-npc', action='store_true', help='Verify recovery when the first NPC click is lost')
    args = parser.parse_args()
    if args.attempts < 2:
        parser.error('--attempts must be at least 2')
    source = args.game_dir.resolve()
    protected = [source / 'SV/SV020.E5S', source / 'RS/S_00.EEX']
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    timings, events, rolls = [], [], []
    with tempfile.TemporaryDirectory(prefix='ccz-speed-smoke-') as directory:
        sandbox = create_game_sandbox(source, root=Path(directory))
        os.environ.update(CCZ_GAME_EXE=str(sandbox / 'Ekd5.exe'), CCZ_GAME_VERSION='2.2', CCZ_RANDOM_MODE='three')
        app.install(app.bundle_root())
        import task.CczReRandTask as task_module
        rules = default_rule_config()
        active_profile(rules)['threePerson'].update(qualifiedMembers=['张宝'], minQualifiedCount=1, minJobAverage=20)
        def record(event, **fields):
            if event in ('source_ready', 'interaction_succeeded', 'interaction_no_change'):
                events.append(dict(event=event, **fields))
        original_click = app.native_silent_click
        skipped = False
        def click(pid, hwnd, x, y, **kwargs):
            nonlocal skipped
            if args.skip_first_npc and not skipped and (x, y) == app.XU_CLIENT_POSITION:
                skipped = True
                return
            return original_click(pid, hwnd, x, y, **kwargs)
        with app.HiddenGameSession(sandbox / 'Ekd5.exe', announce=False) as game, \
                patch.object(app, 'diagnostic_log', side_effect=record), \
                patch.object(app, 'native_silent_click', side_effect=click):
            app.patch_runtime(task_module, game.pid, three_person_mode=True, rules=rules)
            runner = task_module.CczReRandTask(0)
            runner._source_loaded = False
            for attempt in range(args.attempts):
                started = time.perf_counter()
                assert not runner.run(), '诊断门槛不应通过'
                assert runner._result_outcome == 'job_failed'
                timings.append(round((time.perf_counter() - started) * 1000, 1))
                rolls.append(runner._r0_job_ids)
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in before.items())
    assert len(set(rolls)) > 1, '多轮未观察到随机变化'
    if args.skip_first_npc:
        assert skipped and any(e['event'] == 'interaction_no_change' for e in events), '未触发预期重试'
    result = dict(attempts_ms=timings, repeated_median_ms=statistics.median(timings[1:]),
                  retries=sum(e['event'] == 'interaction_no_change' for e in events), rolls=rolls, events=events)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('attempts_ms', 'repeated_median_ms', 'retries')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
