"""Reusable history cards with one drawing surface and native action buttons."""
from tkinter import ttk
import tkinter as tk


class SummaryCard(tk.Frame):
    def __init__(self, parent, *, colors, font):
        super().__init__(parent, width=224, bg=colors["surface"],
                         highlightbackground=colors["border"], highlightthickness=1)
        self.snapshot = {}
        self.colors = colors
        self.callbacks = {}
        self.values = {}
        self.view = None
        self._suspended = False
        self.canvas = tk.Canvas(self, width=222, height=240, highlightthickness=0, bg=colors["surface"])
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_rectangle(0, 0, 224, 34, fill=colors["ink"], outline="")
        self.texts = {}
        for key, size, color, anchor in (
            ("slot", 10, "#FFFFFF", "w"),
            ("job", 9, colors["blue"], "w"), ("skill", 9, colors["purple"], "e"),
            ("members", 8, colors["ink"], "nw"),
        ):
            self.texts[key] = self.canvas.create_text(0, 0, anchor=anchor, fill=color,
                font=(font, size, "bold" if key in ("slot", "job", "skill") else "normal"),
                width=208 if anchor == "nw" else 0)
        self.backup_dot = self.canvas.create_oval(204, 11, 216, 23, fill=colors["muted"], outline="")
        self._tip = None
        self.canvas.tag_bind(self.backup_dot, "<Enter>", self._show_tip)
        self.canvas.tag_bind(self.backup_dot, "<Leave>", self._hide_tip)
        # A card can be released when paging/filtering.  Close its transient
        # tooltip with it so hidden rounds do not leave orphaned top-level
        # windows or retain the card through Tk callbacks.
        self.bind("<Destroy>", lambda _event: self._hide_tip(), add="+")
        self.separator = self.canvas.create_line(0, 0, 224, 0, fill=colors["border"])
        self.detail = ttk.Button(self, text="查看完整详情", command=lambda: self.invoke("detail"),
            cursor="hand2")
        self.detail.pack(fill="x", padx=9, pady=7)
        self.canvas.tag_bind(self.backup_dot, "<Button-1>", lambda _event: self.invoke("export"))

    def invoke(self, key):
        if key == "export" and not (self.view and self.view.get("backed_up")):
            return
        callback = self.callbacks.get(key)
        if callback is not None:
            callback(self.snapshot)

    def _apply(self, widget, **options):
        previous = self.values.setdefault(widget, {})
        changed = {key: value for key, value in options.items() if previous.get(key) != value}
        if changed:
            widget.configure(**changed)
            previous.update(changed)

    def _paint(self, view):
        for key, item in self.texts.items():
            value = view[key]
            if self.view is None or self.view.get(key) != view[key]:
                self.canvas.itemconfigure(item, text=value)
        self.canvas.coords(self.texts["slot"], 9, 17)
        self.canvas.itemconfigure(self.backup_dot, fill=self.colors["green"] if view["backed_up"] else self.colors["muted"])
        y = 42
        self.canvas.coords(self.texts["job"], 9, y + 16)
        self.canvas.coords(self.texts["skill"], 215, y + 16)
        self.canvas.coords(self.separator, 0, y + 32, 224, y + 32)
        self.canvas.coords(self.texts["members"], 9, y + 38)
        bottom = self.canvas.bbox(self.texts["members"])
        self._apply(self.canvas, height=max(205, (bottom[3] if bottom else y + 38) + 8))
        self.view = dict(view)

    def update_content(self, snapshot, view, *, show_detail, edit_metadata=None, export_save=None):
        self.snapshot = snapshot
        self.callbacks = dict(detail=show_detail, export=export_save)
        if view != self.view:
            self._paint(view)
        if self._suspended:
            self.canvas.itemconfigure(self.backup_dot, state="normal")
            self._suspended = False
        self._apply(self.detail, state="normal")

    def suspend(self):
        if self._suspended:
            return
        self._suspended = True
        self.grid_remove()
        self.canvas.itemconfigure(self.backup_dot, state="disabled")
        self._apply(self.detail, state="disabled")

    def _show_tip(self, _event=None):
        if self._tip is not None and self._tip.winfo_exists():
            return
        self._tip = tk.Toplevel(self)
        self._tip.wm_overrideredirect(True)
        self._tip.attributes("-topmost", True)
        self._tip.configure(bg="#182230")
        status = "已备份：点击导出存档" if self.view and self.view["backed_up"] else "未备份：当前没有独立存档副本"
        tk.Label(self._tip, text=status, fg="#FFFFFF", bg="#182230", padx=8, pady=5).pack()
        self._tip.update_idletasks()
        self._tip.geometry(f"+{self.winfo_rootx() + 190}+{self.winfo_rooty() + 28}")

    def _hide_tip(self, _event=None):
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None
