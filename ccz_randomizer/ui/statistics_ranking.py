"""Searchable full frequency rankings, queried and displayed one page at a time."""
import tkinter as tk
from tkinter import ttk

from ccz_randomizer.ui.inputs import SearchEntry
from ccz_randomizer.ui.tasks import WindowTasks
from ccz_randomizer.ui.theme import COLORS, style_dialog
from ccz_randomizer.ui.window_position import centered_toplevel, show_centered

TITLES = {"jobs": "兵种频率", "skills": "特技频率", "equipment": "宝物效果频率"}


def show_ranking_window(parent, repository, kind, filters):
    window = centered_toplevel(parent)
    window.title(TITLES[kind])
    window.geometry("760x620")
    window.minsize(540, 420)
    style_dialog(window)
    filters = dict(filters)
    # The treasure picker only affects equipment statistics.
    if kind != "equipment":
        filters.pop("equipment_name", None)
    timer = None
    def cancel_timer():
        nonlocal timer
        if timer is not None:
            window.after_cancel(timer)
            timer = None
    tasks = WindowTasks(window, on_close=cancel_timer)
    top = tk.Frame(window, bg=COLORS["page"])
    top.pack(fill="x", padx=20, pady=16)
    tk.Label(top, text="搜索", bg=COLORS["page"]).pack(side="left", padx=(0, 8))
    search = tk.StringVar()
    entry = SearchEntry(top, textvariable=search)
    entry.pack(side="left", fill="x", expand=True)
    body = tk.Frame(window, bg=COLORS["page"])
    body.pack(fill="both", expand=True, padx=20)
    tree = ttk.Treeview(body, columns=("name", "count", "share"), show="headings")
    for column, title, width in (("name", "名称", 430), ("count", "次数", 100), ("share", "占比", 100)):
        tree.heading(column, text=title)
        tree.column(column, width=width, minwidth=70, anchor="w" if column == "name" else "e",
                    stretch=column == "name")
    scrollbar = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    tree.pack(fill="both", expand=True)
    footer = tk.Frame(window, bg=COLORS["page"])
    footer.pack(fill="x", padx=20, pady=16)
    status = tk.StringVar()
    tk.Label(footer, textvariable=status, bg=COLORS["page"], fg=COLORS["muted"]).pack(side="left")
    page, pages = 1, 1

    def loaded(data):
        nonlocal pages
        pages = max(1, (data["count"]+data["page_size"]-1)//data["page_size"])
        tree.delete(*tree.get_children())
        for name, count in data["rows"]:
            tree.insert("", "end", values=(name, f"{count:,}", f"{count/max(data['total'],1):.1%}"))
        status.set(f"{data['count']:,} 项 · {page}/{pages} 页")
        previous.configure(state="normal" if page > 1 else "disabled")
        following.configure(state="normal" if page < pages else "disabled")

    def failed(error):
        status.set(f"读取失败：{error}")

    def load():
        nonlocal timer
        timer = None
        query, selected_page = search.get(), page
        status.set("正在读取…")
        previous.configure(state="disabled")
        following.configure(state="disabled")
        tasks.request("ranking", lambda: repository.ranking(kind, query=query, page=selected_page,
                                                            **filters), loaded, failed)

    def move(step):
        nonlocal page
        page = min(pages, max(1, page+step))
        load()

    def changed(*_):
        nonlocal page, timer
        page = 1
        tasks.invalidate("ranking")
        cancel_timer()
        previous.configure(state="disabled")
        following.configure(state="disabled")
        timer = window.after(60, load)

    following = ttk.Button(footer, text="下一页", command=lambda: move(1))
    following.pack(side="right")
    previous = ttk.Button(footer, text="上一页", command=lambda: move(-1))
    previous.pack(side="right", padx=8)
    search.trace_add("write", changed)
    load()
    show_centered(window)
    return window
