"""Measure dialog opening on a private desktop using a read-only history copy."""
import argparse
import cProfile
from contextlib import closing
import gc
import json
from pathlib import Path
import pstats
import sqlite3
import subprocess
import sys
import tempfile
import time
import tkinter as tk

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-db", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.child:
        from tests.helpers.desktop import background_desktop
        with background_desktop() as startup:
            subprocess.run([sys.executable, __file__, *sys.argv[1:], "--child"],
                           startupinfo=startup, check=True, cwd=ROOT)
        return
    from ccz_randomizer import app
    from ccz_randomizer.history import HistoryRepository
    from ccz_randomizer.rules.config import default_rule_config
    from ccz_randomizer.rules.editor import show_rule_editor
    from ccz_randomizer.ui.effect_dictionary import show_effect_dictionary
    from ccz_randomizer.ui.history import show_history_window
    from ccz_randomizer.ui.support_menu import show_support_menu
    from ccz_randomizer.ui.theme import setup_theme
    from ccz_randomizer.ui.usage_guide import show_usage_guide
    args.output.parent.mkdir(parents=True, exist_ok=True)
    samples, errors = [], []
    with tempfile.TemporaryDirectory() as folder:
        base = Path(folder)
        if args.history_db:
            target = base / "ccz_fast_data/history.sqlite3"
            target.parent.mkdir(parents=True)
            with closing(sqlite3.connect(args.history_db.resolve().as_uri()+"?mode=ro", uri=True)) as source, closing(sqlite3.connect(target)) as destination:
                source.backup(destination)
        HistoryRepository(base)
        root = tk.Tk()
        root.geometry("980x680")
        root.report_callback_exception = lambda *args: errors.append(str(args))
        setup_theme(root)
        root.update()
        actions = {key: lambda parent: None for key in ("guide", "effects", "diagnostics", "sound", "logs", "update", "cleanup")}
        factories = {
            "history": lambda: show_history_window(root, base),
            "rules": lambda: show_rule_editor(root, base, default_rule_config(), app.JOB_MAP, app.TEAM_MEMBERS, (), lambda _: None),
            "guide": lambda: show_usage_guide(root),
            "effects": lambda: show_effect_dictionary(root),
            "support": lambda: show_support_menu(root, actions, "3"),
        }
        try:
            for case, factory in factories.items():
                for repetition in range(4):
                    lags = []
                    last = time.perf_counter()
                    timer = None
                    def beat():
                        nonlocal last, timer
                        now = time.perf_counter()
                        lags.append((now-last)*1000)
                        last = now
                        timer = root.after(8, beat)
                    timer = root.after(8, beat)
                    started = time.perf_counter()
                    factory()
                    built = time.perf_counter()
                    while time.perf_counter()-built < .45:
                        root.update()
                        time.sleep(.001)
                    root.after_cancel(timer)
                    samples.append(dict(case=case, repetition=repetition, build_ms=round((built-started)*1000, 2), max_heartbeat_gap_ms=round(max(lags, default=0), 2)))
                    for child in list(root.winfo_children()):
                        child.destroy()
                    root.update()
                    gc.collect()
                profile = cProfile.Profile()
                profile.enable()
                factory()
                until = time.perf_counter()+.45
                while time.perf_counter()<until:
                    root.update()
                    time.sleep(.001)
                profile.disable()
                with args.output.with_name(args.output.stem+"-"+case+".txt").open("w", encoding="utf-8") as stream:
                    pstats.Stats(profile, stream=stream).sort_stats("cumulative").print_stats(40)
                for child in list(root.winfo_children()):
                    child.destroy()
                root.update()
                gc.collect()
        finally:
            root.destroy()
    args.output.write_text(json.dumps(dict(samples=samples, errors=errors), indent=2), encoding="utf-8")
    if errors:
        raise RuntimeError(errors)


if __name__ == "__main__":
    main()
