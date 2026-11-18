from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from pathlib import Path

from ccz_randomizer.search_history import default_search_history_path
from ccz_randomizer.ui.inputs import SearchEntry
from ccz_randomizer.ui.search_memory import SearchMemory
from ccz_randomizer.ui.window_position import centered_toplevel, show_centered
from ccz_randomizer.ui.equipment_sections import render_equipment_sections
from ccz_randomizer.ui.theme import setup_theme, style_dialog
from ccz_randomizer.ui.window_events import bind_window_event

SEARCH_HISTORY_IDLE_MS = 1000

class EquipmentSearch:
    """Normalize the immutable result data once per dialog."""
    def __init__(self, equipment):
        from ccz_randomizer.equipment_labels import equipment_display
        equipment = equipment_display(equipment)
        self.specials = [(item, " ".join([str(item.get("title", "")),
                         *map(str, item.get("items") or [])]).casefold())
                         for item in equipment.get("specials") or []]
        self.categories = [(category, [(item,
            f'{category.get("name", "")} {item.get("name", "")} {item.get("effect", "")}'.casefold())
            for item in category.get("items") or []])
            for category in equipment.get("categories") or []]

    def search(self, query):
        terms = query.casefold().split()
        specials = [item for item, text in self.specials if all(term in text for term in terms)]
        categories = []
        for category, rows in self.categories:
            items = [item for item, text in rows if all(term in text for term in terms)]
            if items:
                categories.append({**category, "items": items})
        return {"specials": specials, "categories": categories}


def filter_equipment(equipment: dict, query: str) -> dict:
    return EquipmentSearch(equipment).search(query)


def show_equipment_window(parent, *, snapshot: dict, history_path: Path | None = None) -> None:
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
    entry = SearchEntry(filters, textvariable=query, width=32,
        hint="即时搜索宝物、效果或组合；Esc 清空，Ctrl+A 全选")
    entry.pack(side="left", padx=10)
    from ccz_randomizer.ui.effect_dictionary import show_effect_dictionary
    ttk.Button(filters, text="特效手册", command=lambda: show_effect_dictionary(dialog)).pack(side="right")
    body = ttk.Frame(outer)
    body.pack(fill="both", expand=True)
    equipment = snapshot.get("equipment")
    index = EquipmentSearch(equipment or {})
    last_view = None

    def has_matches(word):
        filtered = index.search(word)
        return bool(filtered["specials"] or filtered["categories"])

    SearchMemory(entry, query,
        history_path if history_path is not None else default_search_history_path("equipment"),
        has_matches=has_matches, parent=outer, before=body, idle_ms=SEARCH_HISTORY_IDLE_MS)
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
    pending = None
    sections = None
    empty = tk.Label(content, bg="#F4F6FA", fg="#667085")

    def resize(_event=None):
        canvas.itemconfigure(window, width=max(1100, canvas.winfo_width()))
        canvas.configure(scrollregion=canvas.bbox("all"))

    def refresh():
        nonlocal pending, last_view, sections
        pending = None
        filtered = index.search(query.get())
        has_results = bool(filtered["specials"] or filtered["categories"])
        view = (filtered, bool(query.get().strip()) if not has_results else None)
        if view == last_view:
            return
        last_view = view
        if filtered["specials"] or filtered["categories"]:
            empty.pack_forget()
            if sections is None:
                sections = render_equipment_sections(content, filtered)
            else:
                sections.set_equipment(filtered)
                if not sections.winfo_manager():
                    sections.pack(fill="x")
        else:
            if sections is not None:
                sections.pack_forget()
            text = ("本次尝试未采集宝物信息，请查看合格结果。" if equipment is None else
                    "没有符合条件的宝物信息。" if query.get().strip() else "本次结果没有宝物记录。")
            empty.configure(text=text)
            empty.pack(anchor="w", padx=12, pady=12)
        canvas.yview_moveto(0)
        resize()

    def schedule(*_args):
        nonlocal pending
        if pending:
            dialog.after_cancel(pending)
        pending = dialog.after(50, refresh)

    def wheel(event):
        if event.delta:
            canvas.yview_scroll(-int(event.delta / 120), "units")

    def destroyed(event):
        nonlocal pending
        if event.widget is dialog:
            if pending:
                dialog.after_cancel(pending)
                pending = None

    query.trace_add("write", schedule)
    canvas.bind("<Configure>", resize)
    content.bind("<Configure>", resize)
    dialog.bind("<MouseWheel>", wheel)
    bind_window_event(dialog, "<Destroy>", destroyed)
    refresh()
    show_centered(dialog)
