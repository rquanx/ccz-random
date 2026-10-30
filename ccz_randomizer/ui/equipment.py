from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ccz_randomizer.ui.window_position import centered_toplevel


def show_equipment_window(parent, *, snapshot: dict) -> None:
    dialog = centered_toplevel(parent)
    dialog.title("宝物信息")
    dialog.geometry("940x680")
    dialog.minsize(640, 440)
    dialog.transient(parent)
    outer = ttk.Frame(dialog, padding=18)
    outer.pack(fill="both", expand=True)
    filters = ttk.Frame(outer)
    filters.pack(fill="x", pady=(0, 12))
    ttk.Label(filters, text="搜索宝物、效果或组合").pack(side="left")
    query = tk.StringVar()
    ttk.Entry(filters, textvariable=query, width=32).pack(side="left", padx=10)
    body = ttk.Frame(outer)
    body.pack(fill="both", expand=True)
    body.rowconfigure(0, weight=1)
    body.columnconfigure(0, weight=1)
    canvas = tk.Canvas(body, bg="#F4F6FA", highlightthickness=0)
    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
    scrollbar.grid(row=0, column=1, sticky="ns")
    canvas.configure(yscrollcommand=scrollbar.set)
    equipment = snapshot.get("equipment")
    pending = None

    def refresh():
        nonlocal pending
        pending = None
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        columns = max(1, (width - 24) // 280)
        card_width = max(100, (width - 24 - 12 * (columns - 1)) // columns)
        terms = query.get().casefold().split()
        groups = []
        if equipment:
            special_cards = []
            for special in equipment.get("specials") or []:
                title = str(special.get("title") or "特殊组合")
                lines = [str(item) for item in special.get("items") or []]
                if all(term in " ".join([title, *lines]).casefold() for term in terms):
                    special_cards.append((title, [(line, "") for line in lines]))
            if special_cards:
                groups.append(("宝物特殊组合", special_cards))
            categories = []
            for category in equipment.get("categories") or []:
                title = str(category.get("name") or "其他")
                items = [(str(item.get("name") or ""), str(item.get("effect") or ""))
                         for item in category.get("items") or []
                         if all(term in f'{title} {item.get("name", "")} {item.get("effect", "")}'.casefold()
                                for term in terms)]
                if items:
                    categories.append((title, items))
            if categories:
                groups.append(("宝物列表", categories))
        y = 12
        for heading, cards in groups:
            canvas.create_text(12, y, anchor="nw", text=heading, fill="#182230",
                               font=("Microsoft YaHei UI", 12, "bold"))
            y += 32
            for start in range(0, len(cards), columns):
                backgrounds = []
                bottoms = []
                for column, (title, items) in enumerate(cards[start:start + columns]):
                    x = 12 + column * (card_width + 12)
                    bg = canvas.create_rectangle(x, y, x + card_width, y + 1, fill="white", outline="#D9E0EA")
                    backgrounds.append(bg)
                    cursor = y + 12
                    for text, indent, bold in [(title, 0, True), *[
                        line for name, effect in items
                        for line in ((name, 0, True), (effect, 12, False)) if line[0]
                    ]]:
                        item = canvas.create_text(x + 12 + indent, cursor, anchor="nw", text=text,
                            width=max(1, card_width - 24 - indent), fill="#182230" if bold else "#667085",
                            font=("Microsoft YaHei UI", 10, "bold" if bold else "normal"))
                        cursor = canvas.bbox(item)[3] + 8
                    bottoms.append(cursor + 4)
                bottom = max(bottoms)
                for bg in backgrounds:
                    left, top, right, _ = canvas.coords(bg)
                    canvas.coords(bg, left, top, right, bottom)
                y = bottom + 12
        if not groups:
            text = ("本次尝试未采集宝物信息，请查看合格结果。" if equipment is None else
                    "没有符合条件的宝物信息。" if terms else "本次结果没有宝物记录。")
            canvas.create_text(16, y, anchor="nw", text=text, fill="#667085", font=("Microsoft YaHei UI", 10))
            y += 40
        canvas.configure(scrollregion=(0, 0, width, y))

    def schedule(*_args):
        nonlocal pending
        if pending:
            dialog.after_cancel(pending)
        pending = dialog.after(120, refresh)

    def destroyed(event):
        nonlocal pending
        if event.widget is dialog and pending:
            dialog.after_cancel(pending)
            pending = None
    query.trace_add("write", schedule)
    canvas.bind("<Configure>", schedule)
    canvas.bind("<MouseWheel>", lambda event: canvas.yview_scroll(-int(event.delta / 120), "units"))
    dialog.bind("<Destroy>", destroyed, add="+")
    refresh()
