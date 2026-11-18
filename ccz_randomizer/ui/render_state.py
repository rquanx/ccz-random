"""Track actual pending content work without inspecting every native control."""
from weakref import WeakSet

from ccz_randomizer.ui.window_events import bind_window_event


def track_render(widget, ready):
    window = widget.winfo_toplevel()
    root = widget._root()
    windows = getattr(root, '_ccz_render_windows', None)
    if windows is None:
        windows = root._ccz_render_windows = WeakSet()
    windows.add(window)
    checks = getattr(window, '_ccz_render_checks', None)
    if checks is None:
        checks = window._ccz_render_checks = {}
    token = object()
    checks[token] = (widget, ready)
    bind_window_event(widget, '<Destroy>', lambda _: checks.pop(token, None))


def content_ready(root):
    for window in tuple(getattr(root, '_ccz_render_windows', ())):
        if not window.winfo_exists() or not window.winfo_ismapped():
            continue
        for widget, ready in tuple(window._ccz_render_checks.values()):
            if widget.winfo_exists() and widget.winfo_ismapped() and not ready():
                return False
    return True
