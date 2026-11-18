"""Cancel a window's delayed callbacks before Tk deletes their commands."""
from ccz_randomizer.ui.window_events import bind_window_event


def window_after(window, delay, callback):
    timers = getattr(window, '_ccz_owned_timers', None)
    if timers is None:
        timers = window._ccz_owned_timers = set()
        def closed(_event):
            for timer in tuple(timers):
                window.after_cancel(timer)
            timers.clear()
        bind_window_event(window, '<Destroy>', closed)

    def run():
        timers.discard(timer)
        callback()
    timer = window.after(delay, run)
    timers.add(timer)
    return timer
