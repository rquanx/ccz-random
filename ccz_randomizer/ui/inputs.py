"""Shared input affordances; editing and searching keep different semantics."""
from tkinter import ttk

from ccz_randomizer.ui.theme import FONT, setup_theme
from ccz_randomizer.ui.tooltip import HoverTooltip


class TextEntry(ttk.Entry):
    """Consistent presentation and selection, without changing commit rules."""

    def __init__(self, parent, **kwargs):
        setup_theme(parent)
        kwargs.setdefault("font", (FONT, 10))
        super().__init__(parent, **kwargs)
        # ttk clears the displayed text when a short-lived StringVar is freed.
        self._textvariable = kwargs.get("textvariable")
        self.bind("<Control-a>", self._select_all)
        self.bind("<Control-A>", self._select_all)

    def _select_all(self, _event=None):
        self.selection_range(0, "end")
        self.icursor("end")
        return "break"

    def configure(self, cnf=None, **kwargs):
        options = dict(cnf) if isinstance(cnf, dict) else {}
        options.update(kwargs)
        if "textvariable" in options:
            self._textvariable = options["textvariable"]
        return super().configure(cnf, **kwargs)

    config = configure


class SearchEntry(TextEntry):
    """A filter query: Escape clears text; selection never submits the form."""

    def __init__(self, parent, *, hint="", **kwargs):
        super().__init__(parent, **kwargs)
        self.bind("<Escape>", self._clear_query)
        if hint:
            self._tooltip = HoverTooltip(self, hint)

    def _clear_query(self, _event=None):
        if self.get() and not (self.instate(("disabled",)) or self.instate(("readonly",))):
            self.delete(0, "end")
            return "break"
