"""Measure real Tk dialogs offscreen using fixtures or a read-only history copy.

Run with the project's Windows Python: python -m tools.diagnostics.benchmark_ui
No game process, live history writes, downloads or uploads are involved.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import gc
import json
from pathlib import Path
import sqlite3
import statistics
import tempfile
import time
import tkinter as tk
from unittest.mock import patch

from ccz_randomizer.history import HistoryRepository
from ccz_randomizer.history_members import history_members
from ccz_randomizer.ui import equipment, history, recruitment
from ccz_randomizer.ui.history_cards import SummaryCard
from ccz_randomizer.ui.theme import setup_theme


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def offscreen(window):
    window.geometry("+5000+5000")
    window.deiconify()
    window.update_idletasks()


def benchmark(directory: Path, *, history_db: Path | None = None, repeats=3):
    target = directory / "ccz_fast_data/history.sqlite3"
    target.parent.mkdir(parents=True, exist_ok=True)
    if history_db is not None:
        with closing(sqlite3.connect(history_db.resolve().as_uri() + "?mode=ro", uri=True)) as source, \
             closing(sqlite3.connect(target)) as destination:
            source.backup(destination)
    repository = HistoryRepository(directory)
    if history_db is None:
        fixture = Path(__file__).resolve().parents[2] / "tests/fixtures/personnel_220_1104/randomized-result.json"
        snapshot = json.loads(fixture.read_text(encoding="utf-8"))
        repository.start_run("benchmark", mode="three", loop_random=True, rule_name="性能测量", rule={}, build={})
        for number in range(1, 11):
            rid = repository.start_round("benchmark", number)
            for slot in range(1, 16):
                repository.save_result(rid, dict(snapshot, slot=slot, acceptedAttempt=1))
    rounds = repository.list_rounds()
    if not rounds:
        raise ValueError("历史记录中没有可用于测量的结果")
    snapshot = repository.get_round_results(rounds[0]["id"])[0]
    result_count = rounds[0]["result_count"]
    samples = []
    for case in ("recruitment", "detail", "equipment", "history"):
        for repeat in range(repeats):
            gc.collect()  # Release prior Tk objects on their owning thread.
            root = tk.Tk()
            root.geometry("1280x800+5000+5000")
            root.attributes("-alpha", 0)
            setup_theme(root)
            root.update()
            errors = []
            root.report_callback_exception = lambda *args: errors.append(str(args))
            lags = []
            heartbeat_timer = [None]
            expected_tick = [time.perf_counter() + .008]
            def heartbeat():
                now = time.perf_counter()
                lags.append(max(0, now-expected_tick[0]))
                expected_tick[0] = now + .008
                heartbeat_timer[0] = root.after(8, heartbeat)
            heartbeat_timer[0] = root.after(8, heartbeat)
            try:
                with patch.object(history, "show_centered", offscreen), \
                     patch.object(recruitment, "show_centered", offscreen), \
                     patch.object(equipment, "show_centered", offscreen):
                    expected_names = {str(row["name"]) for row in
                        [*(snapshot.get("personnel") or []), *(snapshot.get("fixedPersonnel") or [])]}
                    started = time.perf_counter()
                    if case == "recruitment":
                        recruitment.show_recruit_window(root, snapshot=snapshot, history_path=directory / "search.json")
                    elif case == "detail":
                        history._show_detail(root, snapshot)
                    elif case == "equipment":
                        equipment.show_equipment_window(root, snapshot=snapshot, history_path=directory / "eq-search.json")
                    else:
                        history.show_history_window(root, repository)
                    constructed = time.perf_counter()
                    steps = []
                    ready_at = None
                    deadline = constructed + 5
                    while time.perf_counter() < deadline:
                        tick = time.perf_counter()
                        root.update()
                        steps.append(time.perf_counter() - tick)
                        widgets = list(descendants(root))
                        if case == "history":
                            ready = sum(isinstance(w, SummaryCard) and bool(w.snapshot) for w in widgets) >= result_count
                        elif case == "detail":
                            texts = {w.cget("text") for w in widgets if isinstance(w, tk.Label)}
                            for widget in widgets:
                                if isinstance(widget, tk.Canvas):
                                    texts.update(widget.itemcget(item, "text") for item in widget.find_all()
                                                 if widget.type(item) == "text")
                            ready = all(str(member.get("name") or "未知") in texts for member in history_members(snapshot))
                        elif case == "recruitment":
                            canvas = next(w for w in widgets if isinstance(w, tk.Canvas))
                            rectangles = [canvas.coords(item) for item in canvas.find_all()
                                          if canvas.type(item) == "rectangle"]
                            columns = max(1, (canvas.winfo_width()-28+12)//258)
                            card_width = max(100, (canvas.winfo_width()-28-(columns-1)*12)//columns)
                            names = {canvas.itemcget(item, "text").split(" · ", 1)[0]
                                     for item in canvas.find_all() if canvas.type(item) == "text"}
                            ready = (bool(rectangles) and expected_names <= names
                                     and abs(rectangles[0][2]-rectangles[0][0]-card_width) < 1)
                        else:
                            ready = True
                        if ready and ready_at is None:
                            ready_at = time.perf_counter()
                        if ready_at is not None and time.perf_counter() - ready_at > .2:
                            break
                        time.sleep(.001)
                    if ready_at is None:
                        raise RuntimeError(f"{case} 未在 5 秒内完成读取")
                    samples.append(dict(case=case, repeat=repeat + 1,
                        construct_ms=round((constructed-started)*1000, 2),
                        ready_ms=round((ready_at-started)*1000, 2),
                        max_drain_ms=round(max(steps)*1000, 2),
                        max_lag_ms=round(max(lags, default=0)*1000, 2), widgets=len(widgets), errors=errors))
            finally:
                root.after_cancel(heartbeat_timer[0])
                root.destroy()
                widgets = []
                canvas = None
                root = None
                gc.collect()
    summary = {case: {metric: round(statistics.median(s[metric] for s in samples if s["case"] == case), 2)
                      for metric in ("construct_ms", "ready_ms", "max_lag_ms", "widgets")}
               for case in ("recruitment", "detail", "equipment", "history")}
    return dict(rounds=repository.count_rounds(), results_in_first_round=result_count,
                personnel=len(snapshot.get("personnel") or []),
                fixed=len(snapshot.get("fixedPersonnel") or []), summary=summary, samples=samples)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-db", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/ui-performance/current.json"))
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 20:
        parser.error("repeats must be between 1 and 20")
    with tempfile.TemporaryDirectory(prefix="ccz-ui-benchmark-") as directory:
        result = benchmark(Path(directory), history_db=args.history_db, repeats=args.repeats)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"界面性能测量完成：{args.output}")


if __name__ == "__main__":
    main()
