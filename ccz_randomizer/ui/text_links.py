"""Dispatch console links through a fixed number of Tk callbacks."""


class TextLinks:
    TAG = "ccz-console-link"

    def __init__(self, widget):
        self.widget = widget
        self.actions = {}
        widget.tag_configure(self.TAG, foreground="#0563c1", underline=True)
        widget.tag_bind(self.TAG, "<Button-1>", self._click)
        widget.tag_bind(self.TAG, "<Enter>", lambda _: widget.configure(cursor="hand2"))
        widget.tag_bind(self.TAG, "<Leave>", lambda _: widget.configure(cursor=""))

    def _click(self, event):
        for tag in self.widget.tag_names("current"):
            action = self.actions.get(tag)
            if action is not None:
                action(event)
                return

    def add(self, tag, action):
        self.actions[tag] = action
        ranges = self.widget.tag_ranges(tag)
        if ranges:
            self.widget.tag_add(self.TAG, *ranges)

    def clear(self):
        if self.actions:
            self.widget.tag_delete(*self.actions)
            self.actions.clear()
        self.widget.configure(cursor="")

    def prune(self):
        for tag in tuple(self.actions):
            if not self.widget.tag_ranges(tag):
                self.widget.tag_delete(tag)
                del self.actions[tag]
