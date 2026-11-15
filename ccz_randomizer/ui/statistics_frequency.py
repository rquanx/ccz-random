"""Complete frequency lists rendered only for the currently visible rows."""
import tkinter as tk
from tkinter import ttk

from ccz_randomizer.ui.statistics_charts import Chart
from ccz_randomizer.ui.inputs import SearchEntry


class FrequencyChart(Chart):
    def __init__(self, parent, title):
        super().__init__(parent, title, "bars")
        self._offset = 0
        self._visible_count = 1
        self._maximum = 1
        self._wheel_remainder = 0
        self._row_height = max(32, self._label_font.metrics("linespace")+14)
        self._all_rows = []
        self._source_subtitle = ""
        self._query = tk.StringVar(self)
        search = tk.Frame(self, bg="white")
        tk.Label(search, text="搜索", bg="white", font=self._label_font).pack(side="left", padx=(0, 5))
        self.search_entry = SearchEntry(search, textvariable=self._query, width=10,
                                        font=self._label_font, hint="按名称搜索当前频率列表，Esc 清空")
        self.search_entry.pack(side="left")
        search.place(relx=1, x=-12, y=8, anchor="ne")
        self._query.trace_add("write", self._filter)
        self._scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.yview)
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Button-4>", lambda _: self.yview_scroll(-1, "units"))
        self.bind("<Button-5>", lambda _: self.yview_scroll(1, "units"))

    def set(self, rows, subtitle=None):
        self._all_rows = [(name, count) for name, count in rows if count > 0]
        self._source_subtitle = subtitle or ""
        self._filter()

    def _filter(self, *_args):
        query = self._query.get().strip().casefold()
        rows = [(name, count) for name, count in self._all_rows if query in name.casefold()]
        self._offset = 0
        self._wheel_remainder = 0
        self._maximum = max((count for _, count in rows), default=1)
        summary = f"{len(rows):,} / {len(self._all_rows):,} 项" if query else f"共 {len(rows):,} 项 · 滚动查看"
        super().set(rows, f"{self._source_subtitle} · {summary}" if self._source_subtitle else summary)

    def draw(self):
        height = self.winfo_height()
        self._visible_count = max(1, int((height-85)/self._row_height))
        self._offset = min(self._offset, max(0, len(self.rows)-self._visible_count))
        if len(self.rows) > self._visible_count:
            self._scrollbar.place(relx=1, x=-2, y=64, anchor="ne", width=14, height=max(20, height-78))
        else:
            self._scrollbar.place_forget()
        self._scrollbar.set(*self.yview())
        super().draw()
        if not self.rows and self._query.get().strip():
            self.itemconfigure("empty", text="没有匹配的项目")

    def _bars(self, w, h):
        super()._bars(w-18, h, rows=self.rows[self._offset:self._offset+self._visible_count],
                      maximum=self._maximum, step=self._row_height)

    def yview(self, *args):
        count = len(self.rows)
        if not args:
            return (self._offset/max(1, count), min(1, (self._offset+self._visible_count)/max(1, count)))
        if args[0] == "moveto":
            offset = int(float(args[1])*count)
        else:
            offset = self._offset + int(args[1])*(max(1, self._visible_count-1) if args[2] == "pages" else 1)
        offset = max(0, min(offset, count-self._visible_count))
        if offset != self._offset:
            self._offset = offset
            self._render_key = None
            self.draw()

    def yview_scroll(self, number, what):
        self.yview("scroll", number, what)
        return "break"

    def yview_moveto(self, fraction):
        self.yview("moveto", fraction)

    def _wheel(self, event):
        self._wheel_remainder += event.delta
        steps = int(self._wheel_remainder/120)
        if steps:
            self._wheel_remainder -= steps*120
            self.yview_scroll(-steps*3, "units")
        return "break"
