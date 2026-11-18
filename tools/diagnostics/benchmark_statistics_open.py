"""Measure first statistics data using a private copy of an existing database.

Runs on a private Windows desktop. --main-window includes real startup catalogue
preloading; network profile updates and first-use notices are disabled. No game
process or source database is modified. --eager-baseline measures the previous
all-pages query using the same current data and widgets.
"""
import argparse
from contextlib import closing
import gc
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def measure(root, base):
    import tkinter as tk
    from ccz_randomizer.ui.statistics import show_statistics_window

    errors, gaps = [], []
    root.report_callback_exception = lambda *args: errors.append(str(args))
    last = started = time.perf_counter()
    timer = None

    def heartbeat():
        nonlocal last, timer
        now = time.perf_counter()
        gaps.append((now-last)*1000)
        last = now
        timer = root.after(8, heartbeat)

    timer = root.after(8, heartbeat)
    window = show_statistics_window(root, base)
    built = time.perf_counter()
    ready = None
    try:
        while time.perf_counter()-started < 15:
            root.update()
            labels = [widget for widget in window.winfo_children()
                      if isinstance(widget, tk.Label) and widget.cget("textvariable")]
            statuses = [str(root.getvar(widget.cget("textvariable"))) for widget in labels]
            if any(value.startswith(("兵种 ", "暂无符合")) for value in statuses):
                ready = time.perf_counter()
                break
            time.sleep(.001)
    finally:
        root.after_cancel(timer)
        window.destroy()
        root.update()
    if ready is None or errors:
        raise RuntimeError(errors or "Statistics did not finish")
    return dict(build_ms=(built-started)*1000, ready_ms=(ready-started)*1000,
                max_heartbeat_gap_ms=max(gaps, default=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--main-window", action="store_true")
    parser.add_argument("--eager-baseline", action="store_true")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.child:
        from tests.helpers.desktop import background_desktop
        with background_desktop() as startup:
            subprocess.run([sys.executable, __file__, *sys.argv[1:], "--child"],
                           startupinfo=startup, cwd=ROOT, check=True)
        return
    import tkinter as tk
    from ccz_randomizer.rules.config import rule_file_path
    from ccz_randomizer.statistics_store import StatisticsRepository
    from ccz_randomizer.ui.theme import setup_theme

    original_query = StatisticsRepository.query
    query_times = []

    def query(repository, **options):
        if args.eager_baseline:
            options["view"] = "all"
        started = time.perf_counter()
        result = original_query(repository, **options)
        query_times.append(dict(view=options.get("view", "all"),
                                elapsed_ms=(time.perf_counter()-started)*1000))
        return result

    samples = []
    with tempfile.TemporaryDirectory() as folder:
        base = Path(folder)
        target = base / "ccz_fast_data/statistics.sqlite3"
        target.parent.mkdir()
        source_path = (args.base / "ccz_fast_data/statistics.sqlite3").resolve()
        with closing(sqlite3.connect(source_path.as_uri()+"?mode=ro", uri=True)) as source, \
                closing(sqlite3.connect(target)) as destination:
            source.backup(destination)
        if rule_file_path(args.base).exists():
            shutil.copy2(rule_file_path(args.base), rule_file_path(base))
        with patch.object(StatisticsRepository, "query", query):
            if args.main_window:
                from ccz_randomizer import app
                from ccz_randomizer.profile_session import ProfileUpdateSession
                original_mainloop = tk.Tk.mainloop

                def mainloop(root, *positional, **keywords):
                    def run():
                        try:
                            samples.append(measure(root, base))
                        finally:
                            root.after(0, root.destroy)
                    # Competes with the real 250ms startup catalogue preloader.
                    root.after(300, run)
                    return original_mainloop(root, *positional, **keywords)

                with patch.object(app, "app_dir", return_value=base), \
                        patch.object(app, "first_use_notice_acknowledged", return_value=True), \
                        patch.object(app, "locate_game_executable", side_effect=FileNotFoundError), \
                        patch.object(ProfileUpdateSession, "start"), \
                        patch.object(tk.Tk, "mainloop", mainloop):
                    app.gui_main()
            else:
                root = tk.Tk()
                setup_theme(root)
                root.geometry("980x680")
                root.update()
                try:
                    for _ in range(3):
                        samples.append(measure(root, base))
                        gc.collect()
                finally:
                    root.destroy()
    if not samples:
        raise RuntimeError("No measurements completed")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(main_window=args.main_window,
        eager_baseline=args.eager_baseline, samples=samples, queries=query_times), indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
