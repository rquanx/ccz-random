"""In-app quick start and module guide."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ccz_randomizer.ui.window_position import centered_toplevel, show_centered
from ccz_randomizer.ui.window_events import bind_window_event
from ccz_randomizer.ui.usage_content import MODULES, QUICK_START


def show_usage_guide(parent) -> None:
    previous_grab = parent.grab_current()
    dialog = centered_toplevel(parent)
    dialog.title("工具使用说明")
    dialog.geometry("860x650")
    dialog.minsize(700, 520)
    dialog.transient(parent)
    def restore_grab(_event):
        if previous_grab is not None and previous_grab.winfo_exists():
            previous_grab.grab_set()
    bind_window_event(dialog, '<Destroy>', restore_grab)
    body = ttk.Frame(dialog, padding=14)
    body.pack(fill="both", expand=True)
    notebook = ttk.Notebook(body)
    notebook.pack(fill="both", expand=True)

    contents = {}

    def add_page(title: str, content: str) -> None:
        page = ttk.Frame(notebook, padding=10)
        notebook.add(page, text=title)
        contents[str(page)] = (page, content)

    def populate_selected(_event=None):
        pending = contents.pop(notebook.select(), None)
        if pending is None:
            return
        page, content = pending
        text = tk.Text(page, wrap="word", relief="flat", borderwidth=0,
                       padx=10, pady=8, font=("Microsoft YaHei UI", 10))
        scroll = ttk.Scrollbar(page, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        text.insert("1.0", content)
        text.configure(state="disabled")

    add_page("快速开始", QUICK_START)
    for title, content in MODULES:
        add_page(title, content)
    notebook.bind("<<NotebookTabChanged>>", populate_selected)
    populate_selected()
    ttk.Button(body, text="关闭", command=dialog.destroy).pack(anchor="e", pady=(10, 0))
    show_centered(dialog)
    dialog.grab_set()
