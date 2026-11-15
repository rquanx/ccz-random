"""Small native charts: consistent colors, direct labels and exact hover values."""
from tkinter import ttk
import math
import tkinter as tk
from tkinter import font as tkfont
from PIL import ImageTk

from ccz_randomizer.ui.theme import FONT, COLORS
from ccz_randomizer.ui.statistics_graphics import ChartGraphics, HitRegion

PALETTE = ("#5B8DEF", "#9B87D5", "#50B8A9", "#E8A65D", "#D97C98", "#8294AB")
STATUS = {"job_failed": "兵种淘汰", "skill_failed": "特技淘汰", "saved": "保存成功",
          "error": "执行异常", "stopped": "用户停止", "inspection_abandoned": "检查未完成",
          "incomplete": "其他未完成"}
STATUS_COLORS = dict(job_failed=PALETTE[0], skill_failed=PALETTE[1], saved=PALETTE[2],
                     error="#D97C98", stopped="#8294AB", inspection_abandoned="#E8A65D",
                     incomplete="#B0B9C7")
REASON_LABELS = {"兵种综合评价未达到当前规则要求": "兵种评价未达标",
                 "特技综合评价未达到当前规则要求": "特技评价未达标"}


class Chart(tk.Canvas):
    def __init__(self, parent, title, kind, *, subtitle="", on_expand=None, label_aliases=None):
        super().__init__(parent, background="white", highlightthickness=1,
                         highlightbackground=COLORS["border"], height=260)
        self.title, self.subtitle, self.kind = title, subtitle, kind
        self.label_aliases = label_aliases or {}
        self._label_font = tkfont.Font(root=self, font=(FONT, 9))
        self.rows = []
        self.regions = []
        self._hovered = None
        self._photo = None
        self._redraw_timer = None
        self._render_key = None
        self._revision = 0
        self._expand_button = None
        if on_expand is not None:
            self._expand_button = ttk.Button(self, text="查看全部", command=on_expand,
                cursor="hand2", state="disabled")
            self._expand_button.place(relx=1, x=-12, y=8, anchor="ne")
        self.bind("<Configure>", self._schedule_draw)
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda _: self._hide_tip())
        self.bind("<Destroy>", self._destroyed)

    def _schedule_draw(self, _event):
        if self._redraw_timer is not None:
            self.after_cancel(self._redraw_timer)
        self._redraw_timer = self.after(50, self._redraw)

    def _redraw(self):
        self._redraw_timer = None
        self.draw()

    def _destroyed(self, event):
        if event.widget is self and self._redraw_timer is not None:
            self.after_cancel(self._redraw_timer)
            self._redraw_timer = None

    def _hide_tip(self):
        self.delete("hover")
        self._hovered = None

    def _motion(self, event):
        value = next((value for region, value in reversed(self.regions)
                      if region.contains(event.x, event.y)), None)
        if value == self._hovered:
            return
        self._hide_tip()
        if value is not None:
            self._hovered = value
            item = self.text(18, 58, value, anchor="nw", tags="hover",
                             width=max(100, self.winfo_width()-36))
            x1, y1, x2, y2 = self.bbox(item)
            background = self.create_rectangle(x1-8, y1-6, x2+8, y2+6, fill="#F0F5FF",
                                                outline="#D5E2F8", tags="hover")
            self.tag_raise(item, background)

    def set(self, rows, subtitle=None):
        self.rows = rows
        if subtitle is not None:
            self.subtitle = subtitle
        self._revision += 1
        if self._expand_button is not None:
            self._expand_button.configure(state="normal")
        self.draw()

    def text(self, x, y, value, **kwargs):
        return self.create_text(x, y, text=value, fill=COLORS["muted"],
                                font=(FONT, 9), **kwargs)

    def tip(self, item, value):
        self.regions.append((item, value))

    def draw(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 80 or h < 80:
            return
        key = (w, h, self._revision)
        if key == self._render_key:
            return
        self._render_key = key
        self.delete("all")
        self.regions = []
        self._hovered = None
        self._photo = None
        self.graphics = ChartGraphics(w, h)
        self.create_text(18, 21, text=self.title, anchor="w", fill=COLORS["ink"],
                         font=(FONT, 11, "bold"))
        self.text(18, 39, self.subtitle, anchor="nw", width=w-36)
        if not self.rows:
            self.text(w/2, (h+50)/2, "暂无已采集样本", tags="empty")
            return
        if self.kind == "donut":
            self._donut(w, h)
        elif self.kind in ("bars", "percent"):
            self._bars(w, h)
        else:
            self._plot(w, h)
        self._photo = ImageTk.PhotoImage(self.graphics.render(), master=self)
        item = self.create_image(0, 0, image=self._photo, anchor="nw")
        self.tag_lower(item)

    def _donut(self, w, h):
        total = sum(row[1] for row in self.rows)
        radius = min((h-90)/2, w*0.21)
        cx, cy = w*0.27, (h+60)/2
        start = 90
        for index, (name, value) in enumerate(self.rows):
            extent = value/max(total, 1)*360
            color = STATUS_COLORS.get(name, PALETTE[index % len(PALETTE)])
            item = self.graphics.arc(cx-radius, cy-radius, cx+radius, cy+radius,
                                   start=start, extent=extent if extent < 360 else 359.999,
                                   fill=color, outline="white", width=2)
            self.tip(item, f"{STATUS.get(name, name)}  {value:,} · {value/max(total,1):.1%}")
            start += extent
            y = 83 + index*min(24, (h-90)/max(1, len(self.rows)-1))
            self.graphics.oval(w*.54, y-4, w*.54+8, y+4, fill=color, outline="")
            self.text(w*.54+17, y, STATUS.get(name, name), anchor="w")
            self.text(w-20, y, f"{value:,}", anchor="e")
        inner = radius*.72
        self.graphics.oval(cx-inner, cy-inner, cx+inner, cy+inner, fill="white", outline="white")
        self.create_text(cx, cy-8, text=f"{total:,}",
                         font=(FONT, min(20, max(11, int(radius*.25))), "bold"), fill=COLORS["ink"])
        self.text(cx, cy+20, "执行次数")

    def _bars(self, w, h, *, rows=None, maximum=None, step=None):
        rows = self.rows[:12] if rows is None else rows
        maximum = maximum or (100 if self.kind == "percent" else max((r[1] for r in rows), default=1) or 1)
        step = (h-85)/len(rows) if step is None else step
        left = min(160, w*.38)
        for index, (name, value) in enumerate(rows):
            y = 72+index*step
            label = self.label_aliases.get(name, name)
            available = max(0, left-30)
            if self._label_font.measure(label) > available:
                while label and self._label_font.measure(label+"…") > available:
                    label = label[:-1]
                label = label+"…" if label else ""
            label_item = self.text(16, y+step*.3, label, anchor="w", tags="bar-label")
            detail = f"{name}：{value:,}" if isinstance(value, int) else f"{name}：{value:.2f}%"
            bounds = self.bbox(label_item)
            if bounds:
                self.tip(HitRegion(bounds), detail)
            item = self.graphics.rectangle(left, y, left+(w-left-65)*value/maximum,
                                         y+max(3, step*.6), fill=PALETTE[index % 3], outline="")
            self.text(w-15, y+step*.3, f"{value:,}" if isinstance(value, int) else f"{value:.1f}%", anchor="e")
            self.tip(item, detail)

    def _plot(self, w, h):
        left, right, top, bottom = 48, w-24, 78, h-36
        rows = self.rows
        # Keep drawing bounded for long running collections; aggregate adjacent samples.
        if len(rows) > 60:
            size = math.ceil(len(rows)/60)
            rows = [(f"{rows[i][0]} 至 {rows[min(i+size-1, len(rows)-1)][0]}",
                     sum(r[1] for r in rows[i:i+size]),
                     sum(r[2] for r in rows[i:i+size]) if len(rows[i]) > 2 else 0)
                    for i in range(0, len(rows), size)]
        if self.kind == "line":
            from ccz_randomizer.ui.statistics_trend import draw_trend
            draw_trend(self, w, h, rows)
            return
        maximum = max(max(row[1:]) for row in rows) or 1
        for i in range(4):
            y = bottom-(bottom-top)*i/3
            self.graphics.line(left, y, right, y, fill="#EAF0F6", dash=(3, 4))
            self.text(left-8, y, f"{maximum*i/3:,.0f}", anchor="e")
        step = (right-left)/len(rows)
        for index, row in enumerate(rows):
            x = left+step*(index+.5)
            y = bottom-(bottom-top)*row[1]/maximum
            item = self.graphics.rectangle(x-step*.39, y, x+step*.39, bottom,
                                         fill=PALETTE[0], outline="")
            self.tip(item, f"{row[0]}：{row[1]:,} 人次")
            if index % max(1, math.ceil(len(rows)/6)) == 0:
                self.text(x, bottom+17, str(row[0]))
