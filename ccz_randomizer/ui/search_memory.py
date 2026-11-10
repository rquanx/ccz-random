"""Optional per-module keyword memory, independent of result rendering."""
from ccz_randomizer.search_history import SearchHistory, SearchSession, normalize_keyword
from ccz_randomizer.ui.recent_searches import RecentSearchesBar


class SearchMemory:
    def __init__(self, entry, query, path, *, has_matches, parent, before, idle_ms=1000):
        self.entry, self.query = entry, query
        self.has_matches, self.before, self.idle_ms = has_matches, before, idle_ms
        self.history = SearchHistory(path)
        self.session = SearchSession(self.history)
        self.pending = None
        self.bar = RecentSearchesBar(parent, self.reuse)
        self._render()
        self.trace = query.trace_add("write", self._changed)
        entry.bind("<Return>", self.remember, add="+")
        entry.bind("<KP_Enter>", self.remember, add="+")
        entry.bind("<FocusOut>", self.remember, add="+")
        entry.bind("<Destroy>", self._destroy, add="+")

    def _cancel(self):
        if self.pending is not None:
            self.entry.after_cancel(self.pending)
            self.pending = None

    def _render(self):
        self.bar.set_items(self.history.items)
        if self.history.items and not self.bar.winfo_manager():
            self.bar.pack(fill="x", before=self.before, pady=(0, 12))

    def _changed(self, *_args):
        self._cancel()
        if not normalize_keyword(self.query.get()):
            self.session.reset()
        else:
            self.pending = self.entry.after(self.idle_ms, lambda: self.remember(automatic=True))

    def remember(self, _event=None, *, automatic=False, render=True):
        self._cancel()
        word = normalize_keyword(self.query.get())
        if not word or not self.has_matches(word):
            if not automatic:
                self.session.reset()
            return
        if self.session.remember(word, finalize=not automatic) and render:
            self._render()

    def reuse(self, word):
        self.query.set(word)
        self.entry.focus_set()
        self.remember()

    def _destroy(self, event):
        if event.widget is self.entry:
            self.remember(render=False)
            self.query.trace_remove("write", self.trace)
