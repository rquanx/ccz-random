"""Window-only events, without forwarding every child Map/Destroy to Python."""
from itertools import count

_ids = count()


class _WindowEvents:
    def __init__(self, window):
        self.window = window
        self.tag = f"CczWindowEvents{next(_ids)}"
        self.callbacks = {}
        self.sequences = set()
        window.bindtags((self.tag, *window.bindtags()))
        self._install("<Destroy>")

    def _install(self, sequence):
        if sequence in self.sequences:
            return
        self.sequences.add(sequence)

        def dispatch(event):
            try:
                for callback in list(self.callbacks.get(sequence, {}).values()):
                    callback(event)
            finally:
                if sequence == "<Destroy>":
                    for name in self.sequences:
                        self.window.unbind_class(self.tag, name)
                    self.callbacks.clear()
        # bind_class registers commands on this window, so Tkinter releases
        # them with the window. The private tag is never present on children.
        self.window.bind_class(self.tag, sequence, dispatch)

    def bind(self, sequence, callback):
        self._install(sequence)
        token = object()
        callbacks = self.callbacks.setdefault(sequence, {})
        callbacks[token] = callback

        def remove():
            callbacks.pop(token, None)
        return remove


def bind_window_event(window, sequence, callback):
    events = getattr(window, "_ccz_window_events", None)
    if events is None:
        events = window._ccz_window_events = _WindowEvents(window)
    return events.bind(sequence, callback)
