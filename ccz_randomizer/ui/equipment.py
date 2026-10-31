from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ccz_randomizer.ui.window_position import centered_toplevel
from ccz_randomizer.ui.equipment_sections import render_equipment_sections
from ccz_randomizer.ui.theme import setup_theme, style_dialog


def filter_equipment(equipment: dict, query: str) -> dict:
    terms = query.casefold().split()
    specials = [special for special in equipment.get("specials") or []
                if all(term in " ".join([str(special.get("title", "")),
                    *map(str, special.get("items") or [])]).casefold() for term in terms)]
    categories = []
    for category in equipment.get("categories") or []:
        items = [item for item in category.get("items") or []
                 if all(term in f'{category.get("name", "")} {item.get("name", "")} {item.get("effect", "")}'.casefold()
                        for term in terms)]
        if items:
            categories.append({**category, "items": items})
    return {"specials": specials, "categories": categories}


def show_equipment_window(parent, *, snapshot: dict) -> None:
    dialog = centered_toplevel(parent)
    setup_theme(dialog)
    style_dialog(dialog)
    dialog.title("宝物信息")
    dialog.geometry("1180x720")
    dialog.minsize(640, 440)
    dialog.transient(parent)
    outer = ttk.Frame(dialog, padding=14)
    outer.pack(fill="both", expand=True)
    filters = ttk.Frame(outer)
    filters.pack(fill="x", pady=(0, 12))
    ttk.Label(filters, text="搜索宝物、效果或组合").pack(side="left")
    query = tk.StringVar()
    ttk.Entry(filters, textvariable=query, width=32).pack(side="left", padx=10)
    ttk.Button(filters, text="清空", command=lambda: query.set("")).pack(side="left")
    body = ttk.Frame(outer)
    body.pack(fill="both", expand=True)
    body.rowconfigure(0, weight=1)
    body.columnconfigure(0, weight=1)
    canvas = tk.Canvas(body, bg="#F4F6FA", highlightthickness=0)
    canvas.grid(row=0, column=0, sticky="nsew")
    vertical = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
    vertical.grid(row=0, column=1, sticky="ns")
    horizontal = ttk.Scrollbar(body, orient="horizontal", command=canvas.xview)
    horizontal.grid(row=1, column=0, sticky="ew")
    canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    content = tk.Frame(canvas, bg="#F4F6FA")
    window = canvas.create_window(0, 0, window=content, anchor="nw")
    equipment = snapshot.get("equipment")
    pending = None

    def resize(_event=None):
        canvas.itemconfigure(window, width=max(1100, canvas.winfo_width()))
        canvas.configure(scrollregion=canvas.bbox("all"))

    def refresh():
        nonlocal pending
        pending = None
        for child in content.winfo_children():
            child.destroy()
        filtered = filter_equipment(equipment or {}, query.get())
        if filtered["specials"] or filtered["categories"]:
            render_equipment_sections(content, filtered)
        else:
            text = ("本次尝试未采集宝物信息，请查看合格结果。" if equipment is None else
                    "没有符合条件的宝物信息。" if query.get().strip() else "本次结果没有宝物记录。")
            tk.Label(content, text=text, bg="#F4F6FA", fg="#667085").pack(anchor="w", padx=12, pady=12)
        canvas.yview_moveto(0)
        resize()

    def schedule(*_args):
        nonlocal pending
        if pending:
            dialog.after_cancel(pending)
        pending = dialog.after(120, refresh)

    def wheel(event):
        if event.delta:
            canvas.yview_scroll(-int(event.delta / 120), "units")

    def destroyed(event):
        nonlocal pending
        if event.widget is dialog and pending:
            dialog.after_cancel(pending)
            pending = None

    query.trace_add("write", schedule)
    canvas.bind("<Configure>", resize)
    content.bind("<Configure>", resize)
    dialog.bind("<MouseWheel>", wheel)
    dialog.bind("<Destroy>", destroyed, add="+")
    refresh()
