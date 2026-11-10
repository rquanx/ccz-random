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
from contextlib import ExitStack

from ccz_randomizer import app
from ccz_randomizer.rules.config import default_rule_config, active_profile, validate_rule_config
from ccz_randomizer.runtime.game_sandbox import create_game_sandbox


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--attempts', type=int, default=5)
    parser.add_argument('--turbo', action='store_true')
    parser.add_argument('--save-results', action='store_true', help='Accept, save and reload each result in the sandbox')
    parser.add_argument('--skip-first-npc', action='store_true', help='Verify recovery when the first NPC click is lost')
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.unlink(missing_ok=True)
    if args.attempts < 2:
        parser.error('--attempts must be at least 2')
    source = args.game_dir.resolve()
    protected = [source / 'SV/SV020.E5S', source / 'RS/S_00.EEX']
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    timings, events, rolls, saved_cases = [], [], [], []
    with tempfile.TemporaryDirectory(prefix='ccz-speed-smoke-') as directory:
        sandbox = create_game_sandbox(source, root=Path(directory))
        os.environ.update(CCZ_GAME_EXE=str(sandbox / 'Ekd5.exe'),
                          CCZ_GAME_VERSION=app.load_profile().game_version, CCZ_RANDOM_MODE='three')
        os.environ.pop('CCZ_TEST_ACCEPT_FIRST', None)
        os.environ['CCZ_TURBO_MODE'] = '1' if args.turbo else '0'
        app.load_media_modules()
        app.install(app.bundle_root())
        import task.CczReRandTask as task_module
        rules = default_rule_config()
        profile = active_profile(rules)
        profile.update(builtin=False, editorMode='advanced')
        profile['threePerson'].update(qualifiedMembers=['张宝'], jobQualificationMode='average',
                                     minQualifiedCount=1, minJobAverage=20)
        if args.save_results:
            profile['threePerson']['jobQualificationMode'] = 'none'
            profile['skillQualification']['mode'] = 'none'
        validate_rule_config(rules)
        def personnel(pid):
            fixed = list(app.fixed_member_indices().values()) + [
                row['recordIndex'] for row in app.load_catalog() if row['fixedConfiguration']]
            return app.read_personnel(pid, app.rule_member_indices(app.current_game_version()).values(),
                                      planned=True, fixed_indices=fixed)
        measured_events = {'source_load_start', 'game_menu_load_interaction_completed',
            'title_load_start', 'normal_load_start', 'title_load_verified', 'normal_load_verified',
            'source_ready', 'randomization_acceleration_enabled', 'interaction_start',
            'interaction_npc_clicked', 'fast_choice_click_no_change', 'interaction_choice_clicked',
            'interaction_succeeded', 'interaction_no_change', 'job_filter_rejected', 'turbo_fallback'}
        def record(event, **fields):
            if event in measured_events:
                events.append(dict(event=event, measured_at_ms=round(time.perf_counter()*1000, 1), **fields))
        original_click = app.native_silent_click
        original_burst = app.native_silent_click_burst
        def measured(name, function):
            def call(*positional, **kwargs):
                started = time.perf_counter()
                if name == 'recover_stale_windows':
                    events.append(dict(event='cleanup_windows', windows=[
                        dict(hwnd=hwnd, title=app.window_text(hwnd), visible=bool(app.user32.IsWindowVisible(hwnd)))
                        for hwnd in app.process_windows(positional[0], visible_only=False)
                        if app.window_class(hwnd) == '#32770']))
                try:
                    return function(*positional, **kwargs)
                finally:
                    events.append(dict(event=name, elapsed_ms=round((time.perf_counter()-started)*1000, 1)))
            return call
        skipped = False
        def click(pid, hwnd, x, y, **kwargs):
            nonlocal skipped
            if args.skip_first_npc and not skipped and (x, y) == app.XU_CLIENT_POSITION:
                skipped = True
                return
            return original_click(pid, hwnd, x, y, **kwargs)
        def burst(hwnd, x, y, count, **kwargs):
            nonlocal skipped
            if args.skip_first_npc and not skipped and (x, y) == app.XU_CLIENT_POSITION:
                skipped = True
                return
            return original_burst(hwnd, x, y, count, **kwargs)
        with app.HiddenGameSession(sandbox / 'Ekd5.exe', announce=False) as game, \
                patch.object(app, 'diagnostic_log', side_effect=record), \
                patch.object(app, 'native_silent_click', side_effect=click), \
                patch.object(app, 'native_silent_click_burst', side_effect=burst), ExitStack() as stack:
            for name in ('recover_stale_windows', 'wait_list_dialog', 'click_leftmost_dialog_button'):
                stack.enter_context(patch.object(app, name, side_effect=measured(name, getattr(app, name))))
            app.patch_runtime(task_module, game.pid, three_person_mode=True, rules=rules)
            runner = task_module.CczReRandTask(0)
            runner._source_loaded = False
            for attempt in range(args.attempts):
                started = time.perf_counter()
                runner._target_save_pos = attempt % 15 + 1
                assert runner.run() == args.save_results, '诊断筛选结果与门槛不符'
                assert runner._result_outcome == ('accepted' if args.save_results else 'job_failed')
                timings.append(round((time.perf_counter() - started) * 1000, 1))
                rolls.append(runner._r0_job_ids)
                if args.save_results:
                    assert runner._result_save_committed
                    saved = runner._result_save_path
                    saved_personnel = personnel(game.pid)
                    saved_cases.append((saved, runner._target_save_pos, runner._r0_job_ids, saved_personnel))
        for saved, slot, jobs, saved_personnel in saved_cases:
            with app.HiddenGameSession(sandbox / 'Ekd5.exe', announce=False) as reloaded:
                assert app.title_load_verified(reloaded.pid, slot - 1, saved)
                assert app.read_job_ids(reloaded.pid, app.JOB_POSITIONS_R0) == jobs
                assert personnel(reloaded.pid) == saved_personnel, '重启游戏后的人物兵种或特技不一致'
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in before.items())
    assert len(set(rolls)) > 1, '多轮未观察到随机变化'
    if args.skip_first_npc:
        assert skipped and any(e['event'] == 'interaction_no_change' for e in events), '未触发预期重试'
    result = dict(attempts_ms=timings, repeated_median_ms=statistics.median(timings[1:]),
                  turbo=args.turbo, saved_results_verified=args.save_results,
                  retries=sum(e['event'] == 'interaction_no_change' for e in events), rolls=rolls, events=events)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('attempts_ms', 'repeated_median_ms', 'retries')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
