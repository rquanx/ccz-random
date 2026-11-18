"""Reuse native cards for visible rows without laying out offscreen widgets."""
from bisect import bisect_left, bisect_right
from time import perf_counter
from ccz_randomizer.ui.window_events import bind_window_event


class ViewportRows:
    def __init__(self, canvas, content, render, release, *, columns=4, origin=lambda: 0,
                 manage_scrollregion=True):
        self.canvas, self.content = canvas, content
        self.render, self.release = render, release
        self.columns = columns
        self.origin = origin
        self.manage_scrollregion = manage_scrollregion
        self.offsets = [0]
        self.count = 0
        self.shown = set()
        self.timer = None
        self.visible_indices = set()
        self.closed = False
        self.width = None
        self.dirty = set()
        previous = canvas.cget("yscrollcommand")

        def scroll(first, last):
            if previous:
                canvas.tk.call(*canvas.tk.splitlist(previous), first, last)
            self.schedule()

        canvas.configure(yscrollcommand=scroll)
        canvas.bind("<Configure>", lambda _event: self.schedule(), add="+")
        bind_window_event(content, "<Destroy>", lambda _event: self.close())
        from ccz_randomizer.ui.render_state import track_render
        track_render(canvas, lambda: not self.count or self.ready)

    def replace(self, heights, count):
        self.clear()
        self.count = count
        self._set_heights(heights)
        self.schedule()

    def _set_heights(self, heights):
        self.offsets = [0]
        for height in heights:
            self.offsets.append(self.offsets[-1] + height)
        self.content.grid_propagate(False)
        self.content.pack_propagate(False)
        self.content.configure(height=max(1, self.offsets[-1]))
        if self.manage_scrollregion:
            self.canvas.configure(scrollregion=(0, 0, max(1, self.canvas.winfo_width()), max(1, self.offsets[-1])))

    def clear(self):
        if self.timer is not None:
            self.canvas.after_cancel(self.timer)
            self.timer = None
        for index in self.shown:
            self.release(index)
        self.shown.clear()
        self.visible_indices.clear()
        self.dirty.clear()
        self.offsets = [0]
        self.count = 0
        self.content.grid_propagate(True)
        self.content.pack_propagate(True)
        self.content.configure(height=1)
        if self.manage_scrollregion:
            self.canvas.configure(scrollregion=(0, 0, max(1, self.canvas.winfo_width()), 1))
            self.canvas.yview_moveto(0)

    def schedule(self):
        if not self.closed and self.count and self.timer is None:
            self.timer = self.canvas.after_idle(self._step)

    def _step(self):
        self.timer = None
        raw_top = self.canvas.canvasy(0)-self.origin()
        top = max(0, raw_top)
        width = self.canvas.winfo_width()
        resized = width != self.width
        bottom = raw_top + max(1, self.canvas.winfo_height())
        start = max(0, bisect_right(self.offsets, top) - 1)
        end = min(len(self.offsets) - 1, bisect_left(self.offsets, bottom))
        self.visible_indices = set(range(start * self.columns, min(self.count, end * self.columns)))
        if bottom <= 0:
            self.visible_indices.clear()
        for index in self.shown - self.visible_indices:
            self.release(index)
        self.shown.intersection_update(self.visible_indices)
        self.dirty.intersection_update(self.visible_indices)
        if resized:
            self.width = width
            self.dirty.update(self.shown)
        pending = sorted((self.visible_indices - self.shown) | self.dirty)
        started = perf_counter()
        for index in pending:
            row = index // self.columns
            self.render(index, self.offsets[row], self.offsets[row + 1] - self.offsets[row])
            self.shown.add(index)
            self.dirty.discard(index)
            # Yield by elapsed work, not once per card: Windows timers can have
            # a whole clock tick of latency even for after(1).
            if perf_counter() - started >= .006:
                break
        if (self.visible_indices - self.shown) or self.dirty:
            self.timer = self.canvas.after(1, self._step)

    @property
    def ready(self):
        return bool(self.count) and self.visible_indices == self.shown and not self.dirty and self.timer is None

    def close(self):
        self.closed = True
        if self.timer is not None:
            self.canvas.after_cancel(self.timer)
            self.timer = None
        self.shown.clear()
        self.visible_indices.clear()
        self.dirty.clear()
