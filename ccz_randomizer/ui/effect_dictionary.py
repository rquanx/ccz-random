"""Reusable dictionary window; filtering reuses widgets and a prebuilt index."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ccz_randomizer.effect_dictionary import load_effect_dictionary
from ccz_randomizer.ui.inputs import SearchEntry
from ccz_randomizer.ui.theme import FONT, setup_theme, style_dialog
from ccz_randomizer.ui.window_position import centered_toplevel, show_centered


def show_effect_dictionary(parent):
    dictionary = load_effect_dictionary()
    dialog = centered_toplevel(parent)
    setup_theme(dialog)
    style_dialog(dialog)
    dialog.title("特效手册")
    dialog.geometry("1000x660")
    dialog.minsize(660, 440)
    dialog.transient(parent)
    body = ttk.Frame(dialog, padding=16)
    body.pack(fill="both", expand=True)
    body.columnconfigure(0, weight=1)
    body.rowconfigure(3, weight=1)
    ttk.Label(body, text="特效手册", font=(FONT, 16, "bold")).grid(row=0, column=0, sticky="w")
    filters = ttk.Frame(body)
    filters.grid(row=2, column=0, sticky="ew", pady=12)
    query = tk.StringVar(dialog)
    ttk.Label(filters, text="搜索名称或效果").pack(side="left", padx=(0, 8))
    search = SearchEntry(filters, textvariable=query, hint="可粘贴带数值的宝物特效名称；多个关键词用空格分隔")
    search.pack(side="left", fill="x", expand=True)
    panes = ttk.Panedwindow(body, orient="horizontal")
    panes.grid(row=3, column=0, sticky="nsew")
    left, right = ttk.Frame(panes), ttk.Frame(panes)
    panes.add(left, weight=2)
    panes.add(right, weight=3)
    table = ttk.Treeview(left, show="tree headings", selectmode="browse")
    table.heading("#0", text="特效名称")
    table.column("#0", width=280, minwidth=120)
    scrollbar = ttk.Scrollbar(left, command=table.yview)
    table.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    table.pack(fill="both", expand=True)
    detail = tk.Text(right, wrap="word", relief="flat", borderwidth=0, padx=16, pady=12,
                     font=(FONT, 11), state="disabled", width=42, height=12)
    detail_scroll = ttk.Scrollbar(right, command=detail.yview)
    detail.configure(yscrollcommand=detail_scroll.set)
    detail_scroll.pack(side="right", fill="y")
    detail.pack(fill="both", expand=True)
    detail.tag_configure("title", font=(FONT, 15, "bold"), spacing3=14)
    detail.tag_configure("muted", foreground="#667085", spacing3=12)
    count = tk.StringVar(dialog)
    ttk.Label(body, textvariable=count, foreground="#667085").grid(row=4, column=0, sticky="w", pady=(8, 4))
    if dictionary.notice:
        notice = ttk.Label(body, text=dictionary.notice, foreground="#667085", wraplength=920)
        notice.grid(row=5, column=0, sticky="ew")
        notice.bind("<Configure>", lambda event: notice.configure(wraplength=max(200, event.width)))
    ttk.Button(body, text="关闭", command=dialog.destroy).grid(row=6, column=0, sticky="e", pady=(10, 0))
    visible = {}
    pending = None

    def show_selected(_event=None):
        selection = table.selection()
        item = visible.get(selection[0]) if selection else None
        detail.configure(state="normal")
        detail.delete("1.0", "end")
        if item:
            detail.insert("end", item.name + "\n", "title")
            detail.insert("end", item.description)
        else:
            detail.insert("end", "没有匹配的特效\n", "title")
            detail.insert("end", dictionary.notice if not dictionary.entries else "试试缩短关键词，或清空搜索查看全部。")
        detail.configure(state="disabled")
        detail.yview_moveto(0)

    def refresh():
        nonlocal pending, visible
        pending = None
        previous = table.selection()
        results = dictionary.search(query.get())
        visible = {item.key: item for item in results}
        if table.get_children():
            table.delete(*table.get_children())
        for item in results:
            table.insert("", "end", iid=item.key, text=item.name)
        if results:
            key = previous[0] if previous and previous[0] in visible else results[0].key
            table.selection_set(key)
            table.see(key)
        count.set(f"找到 {len(results)} 项")
        show_selected()

    def schedule(*_args):
        nonlocal pending
        if pending is not None:
            dialog.after_cancel(pending)
        pending = dialog.after(80, refresh)

    def cleanup(event):
        nonlocal pending
        if event.widget is dialog and pending is not None:
            dialog.after_cancel(pending)
            pending = None

    query.trace_add("write", schedule)
    table.bind("<<TreeviewSelect>>", show_selected)
    dialog.bind("<Destroy>", cleanup, add="+")
    refresh()
    show_centered(dialog)
    search.focus_set()
    return dialog
