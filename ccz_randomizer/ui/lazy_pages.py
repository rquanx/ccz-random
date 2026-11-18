"""Build notebook page contents on first selection, keeping model state outside."""
from ccz_randomizer.ui.window_events import bind_window_event


class LazyPages:
    def __init__(self, notebook):
        self.notebook = notebook
        self.pending = {}
        self.built = set()
        notebook.bind("<<NotebookTabChanged>>", self._selected, add="+")
        bind_window_event(notebook, "<Destroy>", lambda _event: self.pending.clear())

    def add(self, page, build):
        self.pending[str(page)] = build

    def _selected(self, _event=None):
        self.ensure(self.notebook.select())

    def ensure(self, page):
        key = str(page)
        build = self.pending.pop(key, None)
        if build is not None:
            try:
                build()
            except Exception:
                self.pending[key] = build
                raise
            self.built.add(key)
