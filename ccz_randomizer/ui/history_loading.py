"""Keep history I/O off Tk and discard responses to superseded selections."""
from __future__ import annotations

import time
from ccz_randomizer.ui.window_events import bind_window_event


from ccz_randomizer.ui.tasks import WindowTasks


class HistoryLoader(WindowTasks):
    """Compatibility name for the serialized history task controller."""
    def __init__(self, window, **options):
        super().__init__(window, **options)
        from ccz_randomizer.ui.render_state import track_render
        track_render(window, lambda: not self.pending)


def render_in_batches(window, items, render, *, is_current=lambda: True, batch_size=3, delay_ms=1,
                      time_budget_ms=8):
    """Yield to input and paint events between small groups of cards."""
    items = iter(enumerate(items))
    timer = None
    jobs = getattr(window, '_ccz_render_jobs', None)
    if jobs is None:
        jobs = window._ccz_render_jobs = set()
        from ccz_randomizer.ui.render_state import track_render
        track_render(window, lambda: not jobs)
    token = object()
    jobs.add(token)

    def stop():
        nonlocal timer
        jobs.discard(token)
        if timer is not None:
            window.after_cancel(timer)
            timer = None
        remove_destroy_binding()

    def destroyed(event):
        if event.widget is window:
            stop()

    remove_destroy_binding = bind_window_event(window, "<Destroy>", destroyed)

    def step():
        nonlocal timer
        timer = None
        if not window.winfo_exists() or not is_current():
            stop()
            return
        started = time.perf_counter()
        for _ in range(batch_size):
            try:
                index, item = next(items)
            except StopIteration:
                stop()
                return
            render(index, item)
            if (time.perf_counter() - started) * 1000 >= time_budget_ms:
                break
        timer = window.after(delay_ms, step)

    timer = window.after(1, step)
