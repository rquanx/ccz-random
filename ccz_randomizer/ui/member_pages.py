"""Bounded widget counts for large personnel settings."""
import tkinter as tk
from tkinter import ttk


class MemberPages(tk.Frame):
    def __init__(self, parent, names, render, *, page_size=24, reuse_widgets=False):
        super().__init__(parent)
        self.names = tuple(names)
        self.render = render
        self.page_size = page_size
        self.reuse_widgets = reuse_widgets
        self.empty_label = None
        self.page = 0
        self.pending = None
        self.query = tk.StringVar(self)
        toolbar = tk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 10))
        tk.Label(toolbar, text="搜索人物").pack(side="left")
        ttk.Entry(toolbar, textvariable=self.query).pack(side="left", fill="x", expand=True, padx=8)
        self.body = tk.Frame(self)
        self.body.pack(fill="both", expand=True)
        footer = tk.Frame(self)
        footer.pack(fill="x", pady=(10, 0))
        self.previous = tk.Button(footer, text="上一页", command=lambda: self.move(-1))
        self.previous.pack(side="left")
        self.status = tk.Label(footer)
        self.status.pack(side="left", expand=True)
        self.next = tk.Button(footer, text="下一页", command=lambda: self.move(1))
        self.next.pack(side="right")
        self.query.trace_add("write", self.search)
        self.bind("<Destroy>", self.destroyed, add="+")
        self.refresh()

    def search(self, *_):
        self.page = 0
        if self.pending is None:
            self.pending = self.after_idle(self.refresh)

    def move(self, delta):
        self.page += delta
        self.refresh()

    def refresh(self):
        if self.pending is not None:
            self.after_cancel(self.pending)
            self.pending = None
        terms = self.query.get().casefold().split()
        visible = [name for name in self.names if all(term in name.casefold() for term in terms)]
        pages = max(1, (len(visible) + self.page_size - 1) // self.page_size)
        self.page = max(0, min(self.page, pages - 1))
        if self.empty_label is not None:
            self.empty_label.destroy()
            self.empty_label = None
        if not self.reuse_widgets:
            for child in self.body.winfo_children():
                child.destroy()
        self.render(self.body, visible[self.page * self.page_size:(self.page + 1) * self.page_size])
        if not visible:
            self.empty_label = tk.Label(self.body, text="没有符合条件的人物。")
            self.empty_label.grid(row=999, column=0, columnspan=7, sticky="w")
        self.status.configure(text=f"{len(visible)} 人 · 第 {self.page + 1} / {pages} 页")
        self.previous.configure(state="normal" if self.page else "disabled")
        self.next.configure(state="normal" if self.page + 1 < pages else "disabled")

    def destroyed(self, event):
        if event.widget is self and self.pending is not None:
            self.after_cancel(self.pending)
            self.pending = None
