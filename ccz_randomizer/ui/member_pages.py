"""Bounded widget counts for large personnel settings."""
import tkinter as tk
from tkinter import ttk

from ccz_randomizer.ui.inputs import SearchEntry
from ccz_randomizer.ui.theme import setup_theme


class MemberCheckGrid:
    """Reuse one page of checkboxes while keeping each person's own variable."""

    def __init__(self, variables, *, state=lambda: "normal", padx=4, uniform=None, columns=7):
        self.variables = variables
        self.state = state
        self.padx = padx
        self.uniform = uniform
        self.columns = columns
        self.checks = []
        self.names = []
        self.last_state = None

    def __call__(self, body, visible):
        if not self.checks:
            for column in range(self.columns):
                body.columnconfigure(column, weight=1, uniform=self.uniform or "")
        state = self.state()
        for index, name in enumerate(visible):
            if index == len(self.checks):
                check = ttk.Checkbutton(body, text=name, variable=self.variables[name], state=state)
                self.checks.append(check)
                self.names.append(name)
                check.grid(row=index // self.columns, column=index % self.columns, sticky="ew",
                           padx=self.padx, pady=4)
                continue
            check = self.checks[index]
            was_hidden = self.names[index] is None
            if self.names[index] != name:
                check.configure(text=name, variable=self.variables[name])
                self.names[index] = name
            if was_hidden or self.last_state != state:
                check.configure(state=state)
            if not check.winfo_manager():
                check.grid(row=index // self.columns, column=index % self.columns, sticky="ew",
                           padx=self.padx, pady=4)
        for index in range(len(visible), len(self.checks)):
            check = self.checks[index]
            if check.winfo_manager():
                check.grid_remove()
                check.configure(text="", variable="", state="disabled")
                self.names[index] = None
        self.last_state = state


class MemberPages(tk.Frame):
    def __init__(self, parent, names, render, *, page_size=24, reuse_widgets=False):
        super().__init__(parent)
        setup_theme(self)
        self.names = tuple(names)
        self.render = render
        self.page_size = page_size
        self.reuse_widgets = reuse_widgets
        self.empty_label = None
        self.page = 0
        self.pending = None
        self.query = tk.StringVar(self)
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 10))
        ttk.Label(toolbar, text="搜索人物").pack(side="left")
        SearchEntry(toolbar, textvariable=self.query).pack(side="left", fill="x", expand=True, padx=8)
        self.body = ttk.Frame(self)
        self.body.pack(fill="both", expand=True)
        footer = ttk.Frame(self)
        footer.pack(fill="x", pady=(10, 0))
        self.previous = ttk.Button(footer, text="上一页", command=lambda: self.move(-1))
        self.previous.pack(side="left")
        self.status = ttk.Label(footer)
        self.status.pack(side="left", expand=True)
        self.next = ttk.Button(footer, text="下一页", command=lambda: self.move(1))
        self.next.pack(side="right")
        self.query.trace_add("write", self.search)
        self.bind("<Destroy>", self.destroyed, add="+")
        from ccz_randomizer.ui.render_state import track_render
        track_render(self, lambda: self.pending is None)
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
            self.empty_label = ttk.Label(self.body, text="没有符合条件的人物。")
            self.empty_label.grid(row=999, column=0, columnspan=7, sticky="w")
        self.status.configure(text=f"{len(visible)} 人 · 第 {self.page + 1} / {pages} 页")
        self.previous.configure(state="normal" if self.page else "disabled")
        self.next.configure(state="normal" if self.page + 1 < pages else "disabled")

    def destroyed(self, event):
        if event.widget is self and self.pending is not None:
            self.after_cancel(self.pending)
            self.pending = None
