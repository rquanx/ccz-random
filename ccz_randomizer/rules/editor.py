from __future__ import annotations

from ccz_randomizer.ui.window_position import centered_toplevel
from ccz_randomizer.rule_members import RULE_MEMBER_NAMES
from ccz_randomizer.rules.help_content import ADVANCED_HELP_SECTIONS
from ccz_randomizer.rules.legacy_import import LegacyModeRequired, read_legacy_mode
from ccz_randomizer.ui.member_pages import MemberPages
from ccz_randomizer.ui.theme import COLORS, FONT, setup_theme, style_dialog

import copy
import json
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable
from ccz_randomizer.runtime.skill_memory import normalize_skill_name


from ccz_randomizer.rules.config import (
    AFFINITY_TYPES,
    DEFAULT_PROFILE_NAME,
    JOB_AFFINITY_TYPES,
    SKILL_AFFINITY_TYPES,
    SIMPLE_PRESET_OPTIONS,
    THREE_MEMBER_NAMES,
    apply_simple_settings,
    build_rule_export,
    default_rule_config,
    merge_rule_export,
    save_rule_config,
    validate_rule_config,
)


def skill_override(overrides: dict, name: str, fallback):
    """Resolve saved settings using the same 2.2 names as live scoring."""
    if name in overrides:
        return overrides[name]
    normalized = normalize_skill_name(name)
    return next(
        (value for key, value in reversed(tuple(overrides.items()))
         if normalize_skill_name(key) == normalized),
        fallback,
    )


TYPE_LABELS = {
    "ALL_ROUNDER": "全能型",
    "WARRIOR": "武将型",
    "MASTER": "文官型",
    "NONE": "无",
}
TYPE_VALUES = {label: value for value, label in TYPE_LABELS.items()}
class ScrollableFrame(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(
            self, orient="vertical", command=self.canvas.yview
        )
        self.body = tk.Frame(self.canvas)
        self.window = self.canvas.create_window(
            (0, 0), window=self.body, anchor="nw"
        )
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.body.bind(
            "<Configure>",
            lambda _event: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            ),
        )
        self.canvas.bind(
            "<Configure>",
            lambda event: self.canvas.itemconfigure(
                self.window, width=event.width
            ),
        )
        self.winfo_toplevel().bind(
            "<MouseWheel>", self._on_mousewheel, add="+"
        )

    def _contains(self, widget: tk.Widget) -> bool:
        current = widget
        while current is not None:
            if current == self:
                return True
            current = getattr(current, "master", None)
        return False

    def _on_mousewheel(self, event) -> None:
        if not self.winfo_ismapped() or not self._contains(event.widget):
            return
        units = int(event.delta / 120)
        if units:
            self.canvas.yview_scroll(-units, "units")


class ScoreGrid(tk.Frame):
    COLUMN_COUNT = 4
    CARD_HEIGHT = 66
    GAP = 8
    SCORE_HEIGHT = 24

    def __init__(
        self,
        parent,
        items: list[tuple[str, tk.StringVar, str]],
        category_resolver: Callable[[str, str, str], str] | None = None,
        type_variables: dict[str, tk.StringVar] | None = None,
        type_options: tuple[str, ...] = SKILL_AFFINITY_TYPES,
        type_label: str = "匹配类型",
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self.items = items
        self.category_resolver = category_resolver
        self.type_variables = type_variables or {}
        self.type_options = type_options
        self.type_label = type_label
        self.card_height = 88 if self.type_variables else self.CARD_HEIGHT
        self.enabled = True
        self.editor: tk.Widget | None = None
        self.editor_window: int | None = None
        self.editing_index: int | None = None
        self.editing_kind = ""
        self.hit_boxes: list[tuple[int, int, int, int, int]] = []
        self.type_hit_boxes: list[tuple[int, int, int, int, int]] = []
        self.score_editor_boxes: dict[int, tuple[int, int, int, int]] = {}
        self.type_editor_boxes: dict[int, tuple[int, int, int, int]] = {}
        self.category_text_items: dict[int, int] = {}
        self.category_bar_items: dict[int, int] = {}
        self.value_text_items: dict[int, int] = {}
        self.type_text_items: dict[int, int] = {}
        self.search_var = tk.StringVar()
        self.result_text = tk.StringVar()
        search_bar = tk.Frame(self, background="#f5f5f5")
        search_bar.pack(fill="x", pady=(0, 8))
        tk.Label(
            search_bar,
            text="搜索",
            background="#f5f5f5",
            foreground="#555555",
        ).pack(side="left")
        self.search_entry = tk.Entry(
            search_bar,
            textvariable=self.search_var,
        )
        self.search_entry.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(8, 6),
        )
        tk.Button(
            search_bar,
            text="清空",
            command=lambda: self.search_var.set(""),
            width=6,
        ).pack(side="left")
        tk.Label(
            search_bar,
            textvariable=self.result_text,
            background="#f5f5f5",
            foreground="#777777",
            width=10,
            anchor="e",
        ).pack(side="right", padx=(10, 0))
        canvas_frame = tk.Frame(self, background="#f5f5f5")
        canvas_frame.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(
            canvas_frame,
            highlightthickness=0,
            background="#f5f5f5",
        )
        scrollbar = ttk.Scrollbar(
            canvas_frame, orient="vertical", command=self.canvas.yview
        )
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.canvas.bind("<Configure>", lambda _event: self.refresh())
        self.canvas.bind("<Button-1>", self._start_edit)
        self.canvas.bind("<Motion>", self._update_cursor)
        self.canvas.bind(
            "<Leave>",
            lambda _event: self.canvas.configure(cursor=""),
        )
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.bind("<Destroy>", self._destroy_editor, add="+")
        self.search_var.trace_add("write", self._search_changed)
        self.after_idle(self.refresh)

    def _visible_items(
        self,
    ) -> list[tuple[int, tuple[str, tk.StringVar, str]]]:
        terms = tuple(
            term.casefold()
            for term in self.search_var.get().split()
            if term
        )
        if not terms:
            return list(enumerate(self.items))
        return [
            (index, item)
            for index, item in enumerate(self.items)
            if all(
                term
                in (
                    f"{item[0]} {item[2]} "
                    f"{TYPE_LABELS.get(self.type_variables[item[0]].get(), '')}"
                    if item[0] in self.type_variables
                    else f"{item[0]} {item[2]}"
                ).casefold()
                for term in terms
            )
        ]

    def _search_changed(self, *_args) -> None:
        self.canvas.yview_moveto(0)
        self.refresh()

    def refresh(self) -> None:
        self.commit_pending(refresh=False)
        self.canvas.delete("all")
        self.hit_boxes.clear()
        self.type_hit_boxes.clear()
        self.score_editor_boxes.clear()
        self.type_editor_boxes.clear()
        self.category_text_items.clear()
        self.category_bar_items.clear()
        self.value_text_items.clear()
        self.type_text_items.clear()
        visible_items = self._visible_items()
        self.result_text.set(f"{len(visible_items)} 项")
        viewport_width = max(760, self.canvas.winfo_width())
        content_width = viewport_width - self.GAP
        # Use the available width instead of fixing the settings cards at
        # four columns.  This keeps names readable while allowing 6–7 cards
        # on a normal wide editor window.
        column_count = max(4, min(7, content_width // 170))
        card_width = (
            content_width - self.GAP * (column_count - 1)
        ) // column_count
        rows = (
            len(visible_items) + column_count - 1
        ) // column_count
        for visible_index, (
            item_index,
            (name, variable, category),
        ) in enumerate(visible_items):
            display_category = (
                self.category_resolver(name, variable.get(), category)
                if self.category_resolver is not None
                else category
            )
            row, column = divmod(visible_index, column_count)
            x1 = self.GAP + column * (card_width + self.GAP)
            y1 = self.GAP + row * (self.card_height + self.GAP)
            x2 = x1 + card_width
            y2 = y1 + self.card_height
            self.canvas.create_rectangle(
                x1,
                y1,
                x2,
                y2,
                fill="#ffffff",
                outline="#d8d8d8",
            )
            if display_category:
                category_bar = self.canvas.create_rectangle(
                    x1,
                    y1,
                    x1 + 3,
                    y2,
                    fill=self._category_color(display_category),
                    outline="",
                )
                self.category_bar_items[item_index] = category_bar
            self.canvas.create_text(
                x1 + 9,
                y1 + 16,
                text=name,
                anchor="w",
                fill="#222222",
                font=("Microsoft YaHei UI", 9),
            )
            if name in self.type_variables:
                type_x1 = x1 + 8
                type_y1 = y1 + 30
                type_x2 = x2 - 8
                type_y2 = type_y1 + 20
                type_value_x1 = max(type_x1 + 88, type_x2 - 70)
                self.canvas.create_rectangle(
                    type_x1,
                    type_y1,
                    type_x2,
                    type_y2,
                    fill="#fafafa" if self.enabled else "#f0f0f0",
                    outline="#d0d0d0",
                )
                self.canvas.create_line(
                    type_value_x1,
                    type_y1,
                    type_value_x1,
                    type_y2,
                    fill="#d0d0d0",
                )
                self.canvas.create_text(
                    type_x1 + 8,
                    (type_y1 + type_y2) / 2,
                    text=self.type_label,
                    anchor="w",
                    fill="#777777",
                    font=("Microsoft YaHei UI", 8),
                )
                type_text = self.canvas.create_text(
                    type_x2 - 8,
                    (type_y1 + type_y2) / 2,
                    text=TYPE_LABELS[
                        self.type_variables[name].get()
                    ],
                    anchor="e",
                    fill="#222222" if self.enabled else "#888888",
                    font=("Microsoft YaHei UI", 8),
                )
                self.type_text_items[item_index] = type_text
                self.type_editor_boxes[item_index] = (
                    type_value_x1,
                    type_y1,
                    type_x2,
                    type_y2,
                )
                self.type_hit_boxes.append(
                    (
                        type_x1,
                        type_y1,
                        type_x2,
                        type_y2,
                        item_index,
                    )
                )
            score_x1 = x1 + 8
            score_y1 = y2 - self.SCORE_HEIGHT - 7
            score_x2 = x2 - 8
            score_y2 = y2 - 7
            value_x1 = max(score_x1 + 92, score_x2 - 58)
            self.canvas.create_rectangle(
                score_x1,
                score_y1,
                score_x2,
                score_y2,
                fill="#fafafa" if self.enabled else "#f0f0f0",
                outline="#b8b8b8",
            )
            self.canvas.create_line(
                value_x1,
                score_y1,
                value_x1,
                score_y2,
                fill="#d0d0d0",
            )
            category_text = self.canvas.create_text(
                score_x1 + 8,
                (score_y1 + score_y2) / 2,
                text=(
                    f"{display_category} · 基础分"
                    if display_category
                    else "基础分"
                ),
                anchor="w",
                fill="#777777",
                font=("Microsoft YaHei UI", 8),
            )
            self.category_text_items[item_index] = category_text
            value_text = self.canvas.create_text(
                score_x2 - 8,
                (score_y1 + score_y2) / 2,
                text=variable.get(),
                anchor="e",
                fill="#222222" if self.enabled else "#888888",
                font=("Microsoft YaHei UI", 9, "bold"),
            )
            self.value_text_items[item_index] = value_text
            self.score_editor_boxes[item_index] = (
                value_x1,
                score_y1,
                score_x2,
                score_y2,
            )
            self.hit_boxes.append(
                (
                    x1 if name not in self.type_variables else score_x1,
                    y1 if name not in self.type_variables else score_y1,
                    x2 if name not in self.type_variables else score_x2,
                    y2 if name not in self.type_variables else score_y2,
                    item_index,
                )
            )
        if not visible_items:
            self.canvas.create_text(
                viewport_width / 2,
                72,
                text="没有匹配的项目",
                fill="#777777",
                font=("Microsoft YaHei UI", 10),
            )
        total_height = (
            self.GAP + rows * (self.card_height + self.GAP)
            if rows
            else 144
        )
        self.canvas.configure(
            scrollregion=(0, 0, viewport_width, total_height)
        )

    @staticmethod
    def _category_color(category: str) -> str:
        return {
            "特殊": "#b24747",
            "强力": "#496fa8",
            "优质": "#4d8560",
            "其他": "#888888",
        }.get(category, "#888888")

    def _preview_score(self, _event=None) -> None:
        if (
            self.editing_kind != "score"
            or self.editor is None
            or self.editing_index is None
            or self.category_resolver is None
        ):
            return
        name, _variable, original_category = self.items[
            self.editing_index
        ]
        display_category = self.category_resolver(
            name,
            self.editor.get(),
            original_category,
        )
        text_item = self.category_text_items.get(self.editing_index)
        if text_item is not None:
            self.canvas.itemconfigure(
                text_item,
                text=(
                    f"{display_category} · 基础分"
                    if display_category
                    else "基础分"
                ),
            )
        bar_item = self.category_bar_items.get(self.editing_index)
        if bar_item is not None:
            self.canvas.itemconfigure(
                bar_item,
                fill=self._category_color(display_category),
            )

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if not enabled:
            self.commit_pending()
        self.refresh()

    def commit_pending(self, refresh: bool = True) -> None:
        if self.editor is None or self.editing_index is None:
            return
        editing_kind = self.editing_kind
        editing_index = self.editing_index
        try:
            value = self.editor.get()
            if editing_kind == "type":
                skill_name = self.items[editing_index][0]
                self.type_variables[skill_name].set(TYPE_VALUES[value])
                text_item = self.type_text_items.get(editing_index)
                if text_item is not None:
                    self.canvas.itemconfigure(text_item, text=value)
            else:
                self.items[editing_index][1].set(value)
                text_item = self.value_text_items.get(editing_index)
                if text_item is not None:
                    self.canvas.itemconfigure(text_item, text=value)
        finally:
            self._destroy_editor()
        if (
            refresh
            and editing_kind == "type"
            and self.search_var.get().strip()
        ):
            self.refresh()

    def _matches_at(
        self,
        canvas_x: int,
        canvas_y: int,
    ) -> tuple[
        tuple[int, int, int, int, int] | None,
        tuple[int, int, int, int, int] | None,
    ]:
        type_match = next(
            (
                box
                for box in self.type_hit_boxes
                if box[0] <= canvas_x <= box[2]
                and box[1] <= canvas_y <= box[3]
            ),
            None,
        )
        score_match = next(
            (
                box
                for box in self.hit_boxes
                if box[0] <= canvas_x <= box[2]
                and box[1] <= canvas_y <= box[3]
            ),
            None,
        )
        return type_match, score_match

    def _update_cursor(self, event) -> None:
        if not self.enabled:
            self.canvas.configure(cursor="")
            return
        canvas_x = int(self.canvas.canvasx(event.x))
        canvas_y = int(self.canvas.canvasy(event.y))
        type_match, score_match = self._matches_at(canvas_x, canvas_y)
        self.canvas.configure(
            cursor=(
                "hand2"
                if type_match is not None
                else ("xterm" if score_match is not None else "")
            )
        )

    def _start_edit(self, event) -> None:
        if not self.enabled:
            return
        canvas_x = int(self.canvas.canvasx(event.x))
        canvas_y = int(self.canvas.canvasy(event.y))
        type_match, match = self._matches_at(canvas_x, canvas_y)
        if type_match is None and match is None:
            return
        self.commit_pending()
        if type_match is not None:
            item_index = type_match[4]
            x1, y1, x2, y2 = self.type_editor_boxes[item_index]
            skill_name = self.items[item_index][0]
            variable = self.type_variables[skill_name]
            self.editor = ttk.Combobox(
                self.canvas,
                values=tuple(
                    TYPE_LABELS[value] for value in self.type_options
                ),
                state="readonly",
            )
            self.editor.set(TYPE_LABELS[variable.get()])
            self.editing_kind = "type"
        else:
            assert match is not None
            item_index = match[4]
            x1, y1, x2, y2 = self.score_editor_boxes[item_index]
            variable = self.items[item_index][1]
            self.editor = tk.Entry(
                self.canvas,
                justify="center",
            )
            self.editor.insert(0, variable.get())
            self.editing_kind = "score"
        self.editing_index = item_index
        self.editor_window = self.canvas.create_window(
            x1,
            y1,
            anchor="nw",
            width=x2 - x1,
            height=y2 - y1,
            window=self.editor,
        )
        if isinstance(self.editor, tk.Entry):
            self.editor.select_range(0, "end")
        self.editor.focus_set()
        self.editor.bind("<Return>", lambda _event: self.commit_pending())
        if isinstance(self.editor, tk.Entry):
            self.editor.bind("<KeyRelease>", self._preview_score)
        if isinstance(self.editor, ttk.Combobox):
            self.editor.bind(
                "<<ComboboxSelected>>",
                lambda _event: self.commit_pending(),
            )
        self.editor.bind("<FocusOut>", lambda _event: self.commit_pending())
        self.editor.bind("<Escape>", lambda _event: self._destroy_editor())

    def _on_mousewheel(self, event) -> None:
        units = int(event.delta / 120)
        if units:
            self.canvas.yview_scroll(-units, "units")

    def _destroy_editor(self, _event=None) -> None:
        editor = self.editor
        editor_window = self.editor_window
        self.editor = None
        self.editor_window = None
        self.editing_index = None
        self.editing_kind = ""
        if editor_window is not None:
            self.canvas.delete(editor_window)
        if editor is not None:
            editor.destroy()


def show_advanced_help(parent, selected_index: int) -> None:
    dialog = centered_toplevel(parent)
    setup_theme(dialog)
    style_dialog(dialog)
    dialog.withdraw()
    dialog.title("规则说明")
    dialog.geometry("760x560")
    dialog.minsize(680, 480)
    dialog.transient(parent)

    book = ttk.Notebook(dialog)
    book.pack(fill="both", expand=True, padx=14, pady=(14, 8))
    tabs = []
    for title, content in ADVANCED_HELP_SECTIONS:
        tab = tk.Frame(book, padx=18, pady=16)
        book.add(tab, text=title)
        tabs.append(tab)
        text = tk.Text(
            tab,
            wrap="word",
            relief="flat",
            padx=4,
            pady=4,
            font=("Microsoft YaHei UI", 10),
            spacing1=3,
            spacing3=8,
        )
        text.tag_configure(
            "heading",
            font=("Microsoft YaHei UI", 10, "bold"),
            foreground="#1f4e79",
            spacing1=8,
            spacing3=3,
        )
        text.tag_configure(
            "tip",
            foreground="#555555",
            lmargin1=8,
            lmargin2=8,
            spacing1=8,
        )
        for line in content.splitlines():
            tag = None
            if line.startswith("【") and line.endswith("】"):
                tag = "heading"
            elif line.startswith("提示："):
                tag = "tip"
            text.insert("end", line + "\n", tag)
        text.configure(state="disabled")
        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    help_index = selected_index + 1
    if 0 <= help_index < len(tabs):
        book.select(tabs[help_index])

    footer = tk.Frame(dialog, padx=14)
    footer.pack(fill="x", pady=(0, 12))
    tk.Button(
        footer,
        text="关闭",
        command=dialog.destroy,
        width=10,
    ).pack(side="right")

    dialog.update_idletasks()
    width = max(760, dialog.winfo_reqwidth())
    height = max(560, dialog.winfo_reqheight())
    dialog.geometry(f"{width}x{height}")
    dialog.deiconify()
    dialog.lift()
    dialog.grab_set()


def show_member_affinity_editor(
    parent,
    member_names: tuple[str, ...],
    current_values: dict[str, tuple[str, str]],
    editable: bool,
    on_apply: Callable[[dict[str, tuple[str, str]]], None],
) -> None:
    dialog = centered_toplevel(parent)
    setup_theme(dialog)
    style_dialog(dialog)
    dialog.title("人物倾向设置")
    dialog.geometry("660x640")
    dialog.minsize(600, 540)
    dialog.transient(parent)
    frame = tk.Frame(dialog, padx=20, pady=16)
    frame.pack(fill="both", expand=True)
    tk.Label(frame, text="人物倾向仅影响兵种适配加分。" +
        ("" if editable else "内置规则仅供查看，请先新建副本再修改。"),
        anchor="w").pack(fill="x", pady=(0, 12))
    variables = {name: (tk.StringVar(value=TYPE_LABELS[current_values[name][0]]),
                        tk.StringVar(value=TYPE_LABELS[current_values[name][1]]))
                 for name in member_names}
    options = tuple(TYPE_LABELS[value] for value in AFFINITY_TYPES)

    row_widgets = []

    def render(body, visible):
        # Keep native controls alive; each page only rebinds them to its people.
        if not row_widgets:
            for column, title in enumerate(("人物", "主要倾向", "次要倾向")):
                tk.Label(body, text=title, anchor="w").grid(row=0, column=column, sticky="w", pady=(0, 6))
            for row in range(1, 11):
                label = tk.Label(body, anchor="w", width=12)
                label.grid(row=row, column=0, sticky="w", pady=4)
                combos = []
                for column in (1, 2):
                    combo = ttk.Combobox(body, values=options,
                        state="readonly" if editable else "disabled", width=14)
                    combo.grid(row=row, column=column, sticky="w", padx=(12, 0), pady=4)
                    combos.append(combo)
                row_widgets.append((label, *combos))
        for index, widgets in enumerate(row_widgets):
            if index >= len(visible):
                for widget in widgets:
                    if widget.winfo_manager():
                        widget.grid_remove()
                continue
            name = visible[index]
            label, primary, secondary = widgets
            label.configure(text=name)
            primary.configure(textvariable=variables[name][0])
            secondary.configure(textvariable=variables[name][1])
            for widget in widgets:
                if not widget.winfo_manager():
                    widget.grid()

    actions = tk.Frame(frame)
    actions.pack(side="bottom", fill="x", pady=(12, 0))
    pages = MemberPages(frame, member_names, render, page_size=10, reuse_widgets=True)
    pages.pack(fill="both", expand=True)

    def apply_changes():
        on_apply({name: (TYPE_VALUES[primary.get()], TYPE_VALUES[secondary.get()])
                  for name, (primary, secondary) in variables.items()})
        dialog.destroy()

    tk.Button(actions, text="取消" if editable else "关闭", command=dialog.destroy, width=10).pack(side="right")
    if editable:
        tk.Button(actions, text="确定", command=apply_changes, width=10).pack(side="right", padx=(0, 8))
    dialog.lift()
    dialog.grab_set()


def show_toast(parent, message: str, duration_ms: int = 1800) -> None:
    toast = tk.Toplevel(parent)
    toast.withdraw()
    toast.overrideredirect(True)
    toast.transient(parent)
    toast.configure(bg="#242424")
    tk.Label(
        toast,
        text=message,
        bg="#242424",
        fg="#ffffff",
        padx=18,
        pady=10,
        font=("Microsoft YaHei UI", 10),
        justify="center",
        wraplength=520,
    ).pack()
    toast.update_idletasks()
    width = toast.winfo_reqwidth()
    height = toast.winfo_reqheight()
    x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
    x = max(0, min(x, toast.winfo_screenwidth() - width))
    y = max(0, min(y, toast.winfo_screenheight() - height))
    toast.geometry(f"{width}x{height}+{x}+{y}")
    toast.deiconify()
    toast.lift()
    after_id: str | None = None

    def close_toast() -> None:
        try:
            if toast.winfo_exists():
                toast.destroy()
        except tk.TclError:
            pass

    def cancel_close(event) -> None:
        if event.widget is not toast or after_id is None:
            return
        try:
            toast.after_cancel(after_id)
        except tk.TclError:
            pass

    toast.bind("<Destroy>", cancel_close, add="+")
    after_id = toast.after(duration_ms, close_toast)


def show_rule_editor(
    parent,
    base_dir: Path,
    config: dict,
    job_map: dict,
    team_members: tuple,
    skill_catalog: tuple,
    on_saved: Callable[[dict], None],
    save_notice: Callable[[dict], str | None] | None = None,
) -> None:
    setup_theme(parent)
    working = copy.deepcopy(validate_rule_config(config))
    saved_snapshot = json.dumps(
        working,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    editor = centered_toplevel(parent)
    editor.withdraw()
    editor.title("规则设置")
    editor.geometry("980x760")
    editor.minsize(860, 660)
    editor.transient(parent)

    selected_name = working["activeProfile"]
    loading = False
    editable_widgets: list[tk.Widget] = []

    top = tk.Frame(editor, padx=14, pady=12)
    top.pack(fill="x")
    tk.Label(top, text="规则方案").pack(side="left")
    profile_var = tk.StringVar(value=selected_name)
    profile_combo = ttk.Combobox(
        top,
        textvariable=profile_var,
        values=tuple(working["profiles"]),
        state="readonly",
        width=24,
    )
    profile_combo.pack(side="left", padx=(8, 12))

    action_frame = tk.Frame(editor, padx=14)
    action_frame.pack(fill="x", pady=(0, 10))

    notebook = ttk.Notebook(editor)
    notebook.pack(fill="both", expand=True, padx=14)
    simple_tab = tk.Frame(notebook, padx=18, pady=16)
    advanced_tab = tk.Frame(notebook, padx=12, pady=12)
    notebook.add(simple_tab, text="简单模式")
    notebook.add(advanced_tab, text="高级模式")

    simple_vars: dict[str, tk.StringVar] = {}
    simple_rows = (
        (
            "jobQuality",
            "兵种质量要求",
            "控制进入后续检查所需的整体兵种质量。",
        ),
        (
            "affinityImportance",
            "人物适配重视程度",
            "越高越重视兵种类型是否符合人物倾向。",
        ),
        (
            "skillQuality",
            "特技质量要求",
            "控制所选人物需要达到的特技总分。",
        ),

    )
    for row, (key, label, description) in enumerate(simple_rows):
        tk.Label(
            simple_tab,
            text=label,
            anchor="w",
            font=("Microsoft YaHei UI", 10, "bold"),
        ).grid(row=row * 2, column=0, sticky="w", pady=(5, 0))
        options = tuple(SIMPLE_PRESET_OPTIONS[key])
        variable = tk.StringVar(value=options[0])
        simple_vars[key] = variable
        combo = ttk.Combobox(
            simple_tab,
            textvariable=variable,
            values=options,
            state="readonly",
            width=14,
        )
        combo.grid(
            row=row * 2,
            column=1,
            sticky="w",
            padx=(24, 0),
            pady=(5, 0),
        )
        editable_widgets.append(combo)
        tk.Label(
            simple_tab,
            text=description,
            fg="#666666",
            anchor="w",
        ).grid(
            row=row * 2 + 1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(2, 8),
        )
    simple_tab.columnconfigure(0, weight=1)

    advanced_book = ttk.Notebook(advanced_tab)
    advanced_book.pack(fill="both", expand=True)
    threshold_tab = tk.Frame(advanced_book, padx=16, pady=14)
    base_score_tab = tk.Frame(advanced_book, padx=8, pady=8)
    skill_score_tab = tk.Frame(advanced_book, padx=8, pady=8)
    collection_tab = tk.Frame(advanced_book, padx=18, pady=16)
    advanced_book.add(threshold_tab, text="阶段门槛")
    advanced_book.add(base_score_tab, text="兵种基础设置")
    advanced_book.add(skill_score_tab, text="特技基础设置")
    advanced_book.add(collection_tab, text="人物数据")
    job_tab = tk.LabelFrame(threshold_tab, text="兵种评分", padx=12, pady=8)
    job_tab.grid(row=4, column=0, columnspan=7, sticky="ew", pady=(16, 0))
    skill_tab = tk.LabelFrame(threshold_tab, text="特技评分", padx=12, pady=8)
    skill_tab.grid(row=5, column=0, columnspan=7, sticky="ew", pady=(12, 0))

    number_vars: dict[str, tk.StringVar] = {}
    bool_vars: dict[str, tk.BooleanVar] = {}
    collection_vars = {
        "recruitment": tk.BooleanVar(value=False),
        "jobTalents": tk.BooleanVar(value=False),
        "allRandomPersonnel": tk.BooleanVar(value=False),
    }
    tk.Label(
        collection_tab,
        text="默认关闭。开启后只在合格结果保存时采集对应附加信息，可能增加少量运行时间。",
        anchor="w",
        fg="#666666",
        justify="left",
    ).pack(anchor="w", pady=(0, 14))
    for key, label, description in (
        ("allRandomPersonnel", "启用所有人物随机能力", "开启后，选择人物、人物倾向和结果图人物可使用全部入队人员；关闭时仅显示初始三人。"),
        ("recruitment", "采集入队人员信息", "采集可招募人员和固定入队人员的兵种、兵种天赋及人物天赋。"),
        ("jobTalents", "采集兵种天赋", "采集本次随机后的全部兵种天赋，用于“兵种天赋”弹窗查看。"),
    ):
        tk.Checkbutton(
            collection_tab,
            text=label,
            variable=collection_vars[key],
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            collection_tab,
            text=description,
            fg="#666666",
            anchor="w",
        ).pack(anchor="w", padx=(24, 0), pady=(1, 12))
    collection_tab.columnconfigure(0, weight=1)
    qualification_mode_vars: dict[str, tk.StringVar] = {}
    qualification_count_vars: dict[str, tk.StringVar] = {}
    qualification_member_values: dict[str, list[str]] = {
        "three": list(THREE_MEMBER_NAMES),
    }
    qualification_controls: dict[
        str,
        tuple[ttk.Combobox, ttk.Combobox, tk.Label, tk.Button],
    ] = {}

    def available_member_names() -> tuple[str, ...]:
        return tuple(RULE_MEMBER_NAMES if collection_vars["allRandomPersonnel"].get() else THREE_MEMBER_NAMES)

    def add_number(
        tab,
        row: int,
        key: str,
        label: str,
        hint: str = "",
    ) -> None:
        tk.Label(tab, text=label, anchor="w").grid(
            row=row, column=0, sticky="w", pady=5
        )
        variable = tk.StringVar()
        number_vars[key] = variable
        entry = tk.Entry(tab, textvariable=variable, width=16)
        entry.grid(row=row, column=1, sticky="w", padx=(18, 10), pady=5)
        editable_widgets.append(entry)
        if hint:
            tk.Label(tab, text=hint, fg="#666666", anchor="w").grid(
                row=row, column=2, sticky="w", pady=5
            )

    add_number(
        threshold_tab,
        1,
        "three_min",
        "兵种合格分",
        "",
    )
    qualification_mode_labels = {
        "指定人数达标": "count",
        "平均分达标": "average",
        "总分达标": "total",
    }
    qualification_mode_values = {
        value: label for label, value in qualification_mode_labels.items()
    }

    def add_qualification_control(
        row: int,
        key: str,
        member_names: tuple[str, ...],
    ) -> None:
        mode_var = tk.StringVar()
        count_var = tk.StringVar()
        qualification_mode_vars[key] = mode_var
        qualification_count_vars[key] = count_var
        mode_combo = ttk.Combobox(
            threshold_tab,
            textvariable=mode_var,
            values=tuple(qualification_mode_labels),
            state="readonly",
            width=18,
        )
        mode_combo.grid(
            row=row,
            column=3,
            sticky="w",
            padx=(20, 8),
            pady=5,
        )
        count_combo = ttk.Combobox(
            threshold_tab,
            textvariable=count_var,
            values=tuple(
                str(value) for value in range(1, len(member_names) + 1)
            ),
            state="readonly",
            width=4,
        )
        count_combo.grid(row=row, column=4, sticky="w", pady=5)
        count_label = tk.Label(
            threshold_tab,
            text="人达到门槛",
            anchor="w",
        )
        count_label.grid(row=row, column=5, sticky="w", padx=(5, 0), pady=5)
        member_button = tk.Button(
            threshold_tab,
            text=f"选择人物（{len(member_names)}/{len(member_names)}）",
            width=18,
        )
        member_button.grid(
            row=0,
            column=1,
            sticky="w",
            padx=(18, 10),
            pady=5,
        )
        qualification_controls[key] = (
            mode_combo,
            count_combo,
            count_label,
            member_button,
        )
        editable_widgets.extend((mode_combo, count_combo, member_button))

        def refresh_member_button() -> None:
            selected_count = len(qualification_member_values[key])
            available = available_member_names()
            member_button.configure(
                text=f"选择人物（{selected_count}/{len(available)}）"
            )

        def choose_members() -> None:
            member_names = available_member_names()
            selected = set(qualification_member_values[key])
            dialog = centered_toplevel(editor)
            dialog.withdraw()
            dialog.title("选择人物")
            dialog.resizable(True, True)
            dialog.transient(editor)
            frame = tk.Frame(dialog, padx=20, pady=16)
            frame.pack(fill="both", expand=True)
            tk.Label(
                frame,
                text="所选人物同时参与兵种和特技判断",
                anchor="w",
            ).pack(fill="x", pady=(0, 10))
            member_vars = {
                member: tk.BooleanVar(value=member in selected)
                for member in member_names
            }
            def render_members(body, visible):
                for column in range(7):
                    body.columnconfigure(column, weight=1, uniform="member-choice")
                for index, member in enumerate(visible):
                    tk.Checkbutton(body, text=member, variable=member_vars[member], anchor="w").grid(
                        row=index // 7, column=index % 7, sticky="ew", padx=(0, 12), pady=4)

            pages = MemberPages(frame, member_names, render_members, page_size=42)
            pages.pack(fill="both", expand=True)

            button_frame = tk.Frame(frame)
            button_frame.pack(fill="x", pady=(14, 0))

            def select_all() -> None:
                for variable in member_vars.values():
                    variable.set(True)

            def clear_selection() -> None:
                for variable in member_vars.values():
                    variable.set(False)

            def confirm() -> None:
                chosen = [
                    member
                    for member in member_names
                    if member_vars[member].get()
                ]
                if not chosen:
                    messagebox.showwarning(
                        "至少选择一人",
                        "请至少选择一名参与判断的人物。",
                        parent=dialog,
                    )
                    return
                qualification_member_values[key] = chosen
                count_combo.configure(
                    values=tuple(
                        str(value)
                        for value in range(1, len(chosen) + 1)
                    )
                )
                current_count = int(count_var.get() or "1")
                if current_count > len(chosen):
                    count_var.set(str(len(chosen)))
                skill_count_combo.configure(values=tuple(str(i) for i in range(1, len(chosen) + 1)))
                if int(skill_count_var.get() or "1") > len(chosen):
                    skill_count_var.set(str(len(chosen)))
                refresh_member_button()
                dialog.destroy()

            tk.Button(
                button_frame,
                text="全选",
                command=select_all,
                width=10,
            ).pack(side="left")
            tk.Button(button_frame, text="清空选择", command=clear_selection, width=10).pack(side="left", padx=(8, 0))
            tk.Button(
                button_frame,
                text="取消",
                command=dialog.destroy,
                width=10,
            ).pack(side="right", padx=(8, 0))
            tk.Button(
                button_frame,
                text="确定",
                command=confirm,
                width=10,
            ).pack(side="right")

            dialog.update_idletasks()
            width = max(840, dialog.winfo_reqwidth())
            height = max(430, dialog.winfo_reqheight())
            dialog.minsize(width, height)
            # centered_toplevel owns initial placement; only set the size here.
            dialog.geometry(f"{width}x{height}")
            dialog.deiconify()
            dialog.lift()
            dialog.grab_set()

        member_button.configure(command=choose_members)

        def refresh_count_control(_event=None) -> None:
            enabled = (
                mode_var.get() == "指定人数达标"
                and str(mode_combo.cget("state")) != "disabled"
            )
            count_combo.configure(state="readonly" if enabled else "disabled")
            count_label.configure(fg="#222222" if enabled else "#999999")
            member_button.configure(state="normal" if str(mode_combo.cget("state")) != "disabled" else "disabled")

        mode_combo.bind(
            "<<ComboboxSelected>>",
            refresh_count_control,
            add="+",
        )

    tk.Label(threshold_tab, text="人物设置", anchor="w").grid(row=0, column=0, sticky="w", pady=5)
    add_qualification_control(1, "three", THREE_MEMBER_NAMES)
    add_number(threshold_tab, 2, "skill_threshold", "特技合格分")
    for row in (1, 2):
        tk.Label(threshold_tab, text="算分模式").grid(row=row, column=2, padx=(12, 0))
    skill_mode_labels = qualification_mode_labels
    skill_mode_var = tk.StringVar()
    skill_count_var = tk.StringVar()
    skill_mode_combo = ttk.Combobox(threshold_tab, textvariable=skill_mode_var,
        values=tuple(skill_mode_labels), state="readonly", width=18)
    skill_mode_combo.grid(row=2, column=3, padx=(20, 8), sticky="w")
    skill_count_combo = ttk.Combobox(threshold_tab, textvariable=skill_count_var,
        values=tuple(str(i) for i in range(1, len(THREE_MEMBER_NAMES) + 1)), width=4, state="readonly")
    skill_count_combo.grid(row=2, column=4, sticky="w")
    skill_count_label = tk.Label(threshold_tab, text="人达到门槛")
    skill_count_label.grid(row=2, column=5, padx=(5, 0), sticky="w")
    editable_widgets.extend((skill_mode_combo, skill_count_combo))
    def refresh_skill_count(*_):
        enabled = skill_mode_var.get() == "指定人数达标" and str(skill_mode_combo.cget("state")) != "disabled"
        skill_count_combo.configure(state="readonly" if enabled else "disabled")
        skill_count_label.configure(fg="#222222" if enabled else "#999999")
    skill_mode_combo.bind("<<ComboboxSelected>>", refresh_skill_count)
    tk.Label(threshold_tab, text="兵种与特技均通过才会保留结果；特技分包含个人天赋和兵种天赋。",
        fg="#666666", anchor="w").grid(row=3, column=0, columnspan=7, sticky="w", pady=(16, 0))
    # Legacy fields stay available for reading old exports, but no longer gate this workflow.
    for key in ("normal_average", "high_average", "medium_skills", "low_skills"):
        number_vars[key] = tk.StringVar()

    add_number(job_tab, 0, "base_weight", "兵种基础分权重")
    add_number(
        job_tab,
        1,
        "affinity_min",
        "适配加成最低基础分",
        "低于此分数不计算人物适配",
    )
    add_number(
        job_tab,
        2,
        "primary_bonus",
        "主要倾向加成比例",
        "0.06 表示增加6%",
    )
    add_number(
        job_tab,
        3,
        "secondary_bonus",
        "次要倾向加成比例",
        "0.03 表示增加3%",
    )
    affinity_enabled = tk.BooleanVar()
    bool_vars["affinity_enabled"] = affinity_enabled
    affinity_check = tk.Checkbutton(
        job_tab,
        text="启用人物兵种适配加成",
        variable=affinity_enabled,
        anchor="w",
    )
    affinity_check.grid(row=4, column=0, columnspan=2, sticky="w", pady=5)
    editable_widgets.append(affinity_check)

    affinity_vars: dict[str, tuple[tk.StringVar, tk.StringVar]] = {}
    affinity_member_names = RULE_MEMBER_NAMES
    for member_name in affinity_member_names:
        affinity_vars[member_name] = (tk.StringVar(), tk.StringVar())

    def apply_affinity_values(
        values: dict[str, tuple[str, str]],
    ) -> None:
        for member_name, (primary, secondary) in values.items():
            primary_var, secondary_var = affinity_vars[member_name]
            primary_var.set(TYPE_LABELS[primary])
            secondary_var.set(TYPE_LABELS[secondary])

    def open_affinity_editor() -> None:
        show_member_affinity_editor(
            editor,
            available_member_names(),
            {
                member_name: (
                    TYPE_VALUES[primary.get()],
                    TYPE_VALUES[secondary.get()],
                )
                for member_name, (primary, secondary)
                in affinity_vars.items()
            },
            not is_builtin(selected_name),
            apply_affinity_values,
        )

    tk.Button(
        threshold_tab,
        text="设置人物倾向",
        command=open_affinity_editor,
        width=16,
    ).grid(row=0, column=2, columnspan=2, sticky="w", pady=5)
    result_image_settings = {"mode": "selected", "members": []}

    def refresh_result_image_button():
        suffix = "跟随评分" if result_image_settings["mode"] == "selected" else f"{len(result_image_settings['members'])}人"
        result_image_button.configure(text=f"结果图人物（{suffix}）")

    def open_result_image_members():
        from ccz_randomizer.rules.result_image_editor import show_result_image_members
        def apply_settings(value):
            nonlocal result_image_settings
            result_image_settings = value
            refresh_result_image_button()
        show_result_image_members(editor, result_image_settings,
                                  available_member_names(), apply_settings)

    result_image_button = tk.Button(threshold_tab, command=open_result_image_members)
    result_image_button.grid(row=0, column=4, columnspan=2, sticky="w", pady=5)
    editable_widgets.append(result_image_button)

    def refresh_personnel_scope(*_args) -> None:
        allowed = set(available_member_names())
        current = qualification_member_values["three"]
        qualification_member_values["three"] = [m for m in current if m in allowed] or list(THREE_MEMBER_NAMES)
        _mode_combo, count_combo, _label, member_button = qualification_controls["three"]
        count_combo.configure(values=tuple(str(i) for i in range(1, len(qualification_member_values["three"]) + 1)))
        if int(qualification_count_vars["three"].get() or "1") > len(qualification_member_values["three"]):
            qualification_count_vars["three"].set(str(len(qualification_member_values["three"])))
        member_button.configure(text=f"选择人物（{len(qualification_member_values['three'])}/{len(allowed)}）")
        if result_image_settings.get("mode") == "custom":
            result_image_settings["members"] = [m for m in result_image_settings.get("members", []) if m in allowed]
            if not result_image_settings["members"]:
                result_image_settings["mode"] = "selected"
        refresh_result_image_button()

    collection_vars["allRandomPersonnel"].trace_add("write", refresh_personnel_scope)
    job_default_types = {
        job_name: job_type
        for job_name, _score, job_type in job_map.values()
    }
    job_type_vars = {
        job_name: tk.StringVar(value=job_type)
        for job_name, job_type in job_default_types.items()
    }
    job_score_vars: dict[str, tk.StringVar] = {}
    job_score_items = []
    for _job_id, job in sorted(job_map.items()):
        job_name, default_score, _job_type = job
        variable = tk.StringVar(value=str(default_score))
        job_score_vars[job_name] = variable
        job_score_items.append((job_name, variable, ""))
    job_score_grid = ScoreGrid(base_score_tab, job_score_items,
        type_variables=job_type_vars, type_options=JOB_AFFINITY_TYPES, type_label="兵种类型")
    job_score_grid.pack(fill="both", expand=True)

    for key in ("ordinary_weight", "strong_weight", "special_weight"):
        number_vars[key] = tk.StringVar()
    special_auto = tk.BooleanVar(value=False)
    high_auto = tk.BooleanVar(value=False)
    skill_type_matching = tk.BooleanVar()
    bool_vars["skill_type_matching"] = skill_type_matching
    skill_type_check = tk.Checkbutton(
        skill_tab,
        text="启用特技类型匹配",
        variable=skill_type_matching,
        anchor="w",
    )
    skill_type_check.grid(
        row=3,
        column=0,
        columnspan=2,
        sticky="w",
        pady=5,
    )
    editable_widgets.append(skill_type_check)

    skill_score_vars: dict[str, tk.StringVar] = {}
    skill_type_vars: dict[str, tk.StringVar] = {}
    skill_defaults: dict[str, float] = {}
    skill_default_types: dict[str, str] = {}
    skill_score_items = []
    for skill_item in skill_catalog:
        skill_name, default_score, category = skill_item[:3]
        default_type = (
            skill_item[3]
            if len(skill_item) >= 4
            else "ALL_ROUNDER"
        )
        variable = tk.StringVar(value=f"{default_score:g}")
        skill_score_vars[skill_name] = variable
        skill_type_vars[skill_name] = tk.StringVar(value=default_type)
        skill_defaults[skill_name] = float(default_score)
        skill_default_types[skill_name] = default_type
        skill_score_items.append((skill_name, variable, ""))

    skill_score_grid = ScoreGrid(
        skill_score_tab,
        skill_score_items,
        type_variables=skill_type_vars,
    )
    skill_score_grid.pack(fill="both", expand=True)
    score_grids = (job_score_grid, skill_score_grid)

    def is_builtin(name: str) -> bool:
        return bool(working["profiles"][name].get("builtin"))

    def refresh_qualification_controls(enabled: bool) -> None:
        for key, (mode_combo, count_combo, count_label, member_button) in (
            qualification_controls.items()
        ):
            count_enabled = (
                enabled
                and qualification_mode_vars[key].get()
                == "指定人数达标"
            )
            mode_combo.configure(state="readonly" if enabled else "disabled")
            count_combo.configure(
                state="readonly" if count_enabled else "disabled"
            )
            count_label.configure(
                fg="#222222" if count_enabled else "#999999"
            )
            member_button.configure(
                state="normal" if enabled else "disabled"
            )

    def set_editable(enabled: bool) -> None:
        for widget in editable_widgets:
            try:
                if isinstance(widget, ttk.Combobox):
                    widget.configure(state="readonly" if enabled else "disabled")
                else:
                    widget.configure(state="normal" if enabled else "disabled")
            except tk.TclError:
                pass
        refresh_qualification_controls(enabled)
        refresh_skill_count()
        for score_grid in score_grids:
            score_grid.set_enabled(enabled)
        reset_button.configure(state="normal" if enabled else "disabled")
        rename_button.configure(state="normal" if enabled else "disabled")
        delete_button.configure(state="normal" if enabled else "disabled")

    loaded_form = None

    def form_values():
        # Compare editable values, not rendered defaults expanded into the file.
        mappings = (simple_vars, number_vars, qualification_mode_vars,
                    qualification_count_vars, job_score_vars, job_type_vars,
                    skill_score_vars, skill_type_vars)
        return (
            json.dumps(result_image_settings, sort_keys=True),
            notebook.index(notebook.select()),
            tuple(tuple((key, value.get()) for key, value in mapping.items())
                  for mapping in mappings),
            tuple((key, tuple(value)) for key, value in qualification_member_values.items()),
            tuple((key, primary.get(), secondary.get())
                  for key, (primary, secondary) in affinity_vars.items()),
            tuple((key, variable.get()) for key, variable in collection_vars.items()),
            tuple(value.get() for value in (skill_mode_var, skill_count_var,
                  special_auto, high_auto, skill_type_matching, affinity_enabled)),
        )

    def store_profile(name: str, *, force: bool = False) -> None:
        if loading or is_builtin(name):
            return
        for score_grid in score_grids:
            score_grid.commit_pending()
        if not force and form_values() == loaded_form:
            return
        profile = working["profiles"][name]
        profile["resultImage"] = copy.deepcopy(result_image_settings)
        profile["dataCollection"] = {
            key: bool(variable.get())
            for key, variable in collection_vars.items()
        }
        profile["editorMode"] = (
            "simple" if notebook.index(notebook.select()) == 0 else "advanced"
        )
        for key, variable in simple_vars.items():
            profile["simpleSettings"][key] = variable.get()
        profile["threePerson"]["minJobAverage"] = float(
            number_vars["three_min"].get()
        )
        profile["threePerson"]["jobQualificationMode"] = (
            qualification_mode_labels[qualification_mode_vars["three"].get()]
        )
        profile["threePerson"]["minQualifiedCount"] = int(
            qualification_count_vars["three"].get()
        )
        profile["threePerson"]["qualifiedMembers"] = list(
            qualification_member_values["three"]
        )
        profile["skillQualification"] = dict(mode=skill_mode_labels[skill_mode_var.get()],
            threshold=float(number_vars["skill_threshold"].get()), requiredCount=int(skill_count_var.get()))
        profile["sevenPerson"].update(
            {
                "normalJobAverage": float(
                    number_vars["normal_average"].get()
                ),
                "highJobAverage": float(number_vars["high_average"].get()),
                "mediumMinSkillScore": float(
                    number_vars["medium_skills"].get()
                ),
                "lowMinSkillScore": float(number_vars["low_skills"].get()),
                "ordinarySkillWeight": float(
                    number_vars["ordinary_weight"].get()
                ),
                "strongSkillWeight": float(
                    number_vars["strong_weight"].get()
                ),
                "specialSkillWeight": float(
                    number_vars["special_weight"].get()
                ),
                "skillBaseScores": {
                    **profile["sevenPerson"]["skillBaseScores"],
                    **{skill_name: float(variable.get())
                       for skill_name, variable in skill_score_vars.items()},
                },
                "skillTypeMatchingEnabled": bool(
                    skill_type_matching.get()
                ),
                "skillTypeOverrides": {
                    **profile["sevenPerson"]["skillTypeOverrides"],
                    **{skill_name: variable.get()
                       for skill_name, variable in skill_type_vars.items()},
                },
                "specialSkillAutoPass": bool(special_auto.get()),
                "highJobAutoPass": bool(high_auto.get()),
            }
        )
        profile["jobScoring"].update(
            {
                "baseScoreWeight": float(number_vars["base_weight"].get()),
                "affinityEnabled": bool(affinity_enabled.get()),
                "affinityMinBaseScore": float(
                    number_vars["affinity_min"].get()
                ),
                "primaryBonusRate": float(
                    number_vars["primary_bonus"].get()
                ),
                "secondaryBonusRate": float(
                    number_vars["secondary_bonus"].get()
                ),
                "jobBaseScores": {
                    job_name: float(variable.get())
                    for job_name, variable in job_score_vars.items()
                },
                "jobTypeOverrides": {
                    job_name: variable.get()
                    for job_name, variable in job_type_vars.items()
                    if variable.get() != job_default_types[job_name]
                },
            }
        )
        profile["memberAffinity"].update({
            member: {
                "primaryType": TYPE_VALUES[primary.get()],
                "secondaryType": TYPE_VALUES[secondary.get()],
            }
            for member, (primary, secondary) in affinity_vars.items()
        })
        if profile["editorMode"] == "simple":
            apply_simple_settings(profile)

    def load_profile(name: str) -> None:
        nonlocal loading, selected_name, loaded_form, result_image_settings
        loading = True
        try:
            selected_name = name
            profile = working["profiles"][name]
            result_image_settings = copy.deepcopy(profile["resultImage"])
            refresh_result_image_button()
            for key, variable in collection_vars.items():
                variable.set(profile["dataCollection"][key])
            for key, variable in simple_vars.items():
                variable.set(profile["simpleSettings"][key])
            three = dict(profile["threePerson"])
            if three["jobQualificationMode"] == "all":
                three.update(jobQualificationMode="count", qualifiedMembers=list(THREE_MEMBER_NAMES), minQualifiedCount=len(THREE_MEMBER_NAMES))
            seven = profile["sevenPerson"]
            scoring = profile["jobScoring"]
            values = {
                "three_min": three["minJobAverage"],
                "skill_threshold": profile["skillQualification"]["threshold"],
                "normal_average": seven["normalJobAverage"],
                "high_average": seven["highJobAverage"],
                "medium_skills": seven["mediumMinSkillScore"],
                "low_skills": seven["lowMinSkillScore"],
                "ordinary_weight": seven["ordinarySkillWeight"],
                "strong_weight": seven["strongSkillWeight"],
                "special_weight": seven["specialSkillWeight"],
                "base_weight": scoring["baseScoreWeight"],
                "affinity_min": scoring["affinityMinBaseScore"],
                "primary_bonus": scoring["primaryBonusRate"],
                "secondary_bonus": scoring["secondaryBonusRate"],
            }
            for key, value in values.items():
                number_vars[key].set(f"{value:g}")
            for key, settings in (("three", three),):
                allowed_members = available_member_names()
                qualification_member_values[key] = list(
                    member for member in settings["qualifiedMembers"]
                    if member in allowed_members
                )
                if not qualification_member_values[key]:
                    qualification_member_values[key] = list(allowed_members)
                qualification_mode_vars[key].set(
                    qualification_mode_values[
                        settings["jobQualificationMode"]
                    ]
                )
                qualification_count_vars[key].set(
                    str(settings["minQualifiedCount"])
                )
                _mode_combo, count_combo, _label, member_button = (
                    qualification_controls[key]
                )
                count_combo.configure(
                    values=tuple(
                        str(value)
                        for value in range(
                            1,
                            len(qualification_member_values[key]) + 1,
                        )
                    )
                )
                member_button.configure(
                    text=(
                        "选择人物"
                        f"（{len(qualification_member_values[key])}/"
                        f"{len(allowed_members)}）"
                    )
                )
            skill_mode_var.set(next(label for label, value in skill_mode_labels.items()
                                    if value == profile["skillQualification"]["mode"]))
            skill_count_var.set(str(profile["skillQualification"]["requiredCount"]))
            skill_count_combo.configure(values=tuple(str(i) for i in range(1, len(three["qualifiedMembers"]) + 1)))
            special_auto.set(False)
            high_auto.set(False)
            skill_type_matching.set(seven["skillTypeMatchingEnabled"])
            affinity_enabled.set(scoring["affinityEnabled"])
            for member, (primary, secondary) in affinity_vars.items():
                row = profile["memberAffinity"][member]
                primary.set(TYPE_LABELS[row["primaryType"]])
                secondary.set(TYPE_LABELS[row["secondaryType"]])
            overrides = scoring["jobBaseScores"]
            type_overrides = scoring["jobTypeOverrides"]
            defaults = {
                job[0]: job[1] for job in job_map.values()
            }
            for job_name, variable in job_score_vars.items():
                variable.set(f"{overrides.get(job_name, defaults[job_name]):g}")
            for job_name, variable in job_type_vars.items():
                variable.set(
                    type_overrides.get(
                        job_name,
                        job_default_types[job_name],
                    )
                )
            skill_overrides = seven["skillBaseScores"]
            skill_type_overrides = seven["skillTypeOverrides"]
            for skill_name, variable in skill_score_vars.items():
                fallback_score = skill_defaults[skill_name]
                variable.set(
                    f"{skill_override(skill_overrides, skill_name, fallback_score):g}"
                )
                skill_type_vars[skill_name].set(
                    skill_override(
                        skill_type_overrides,
                        skill_name,
                        skill_default_types[skill_name],
                    )
                )
            for score_grid in score_grids:
                score_grid.refresh()
            notebook.select(
                simple_tab
                if profile["editorMode"] == "simple"
                else advanced_tab
            )
            set_editable(not is_builtin(name))
            loaded_form = form_values()
        finally:
            loading = False

    def refresh_profiles(select_name: str) -> None:
        profile_combo.configure(values=tuple(working["profiles"]))
        profile_var.set(select_name)
        load_profile(select_name)

    def switch_profile(_event=None) -> None:
        new_name = profile_var.get()
        if new_name == selected_name:
            return
        try:
            store_profile(selected_name)
        except Exception as exc:
            profile_var.set(selected_name)
            messagebox.showerror(
                "当前规则无法切换",
                f"请先修正当前页面中的数值。\n\n{exc}",
                parent=editor,
            )
            return
        load_profile(new_name)

    def unique_name(base: str) -> str:
        if base not in working["profiles"]:
            return base
        index = 2
        while f"{base} {index}" in working["profiles"]:
            index += 1
        return f"{base} {index}"

    def copy_profile() -> None:
        try:
            store_profile(selected_name)
        except Exception as exc:
            messagebox.showerror("无法复制", str(exc), parent=editor)
            return
        name = unique_name(f"{selected_name}副本")
        profile = copy.deepcopy(working["profiles"][selected_name])
        profile["builtin"] = False
        working["profiles"][name] = profile
        refresh_profiles(name)

    def new_profile() -> None:
        copy_profile()

    def rename_profile() -> None:
        nonlocal selected_name
        if is_builtin(selected_name):
            return
        name = simpledialog.askstring(
            "重命名规则",
            "输入新的规则名称：",
            initialvalue=selected_name,
            parent=editor,
        )
        if not name:
            return
        name = name.strip()
        if name in working["profiles"] and name != selected_name:
            messagebox.showerror(
                "名称已存在", "请换一个规则名称。", parent=editor
            )
            return
        profile = working["profiles"].pop(selected_name)
        old_name = selected_name
        working["profiles"][name] = profile
        if working["activeProfile"] == old_name:
            working["activeProfile"] = name
        refresh_profiles(name)

    def delete_profile() -> None:
        if is_builtin(selected_name):
            return
        if not messagebox.askyesno(
            "删除规则",
            f"确定删除“{selected_name}”吗？",
            parent=editor,
        ):
            return
        was_active = working["activeProfile"] == selected_name
        del working["profiles"][selected_name]
        target = DEFAULT_PROFILE_NAME
        if was_active:
            working["activeProfile"] = target
        refresh_profiles(target)

    def reset_profile() -> None:
        if is_builtin(selected_name):
            return
        name = selected_name
        profile = copy.deepcopy(
            default_rule_config()["profiles"][DEFAULT_PROFILE_NAME]
        )
        profile["builtin"] = False
        working["profiles"][name] = profile
        load_profile(name)

    def choose_export_scope() -> str | None:
        choice = {"value": None}
        dialog = centered_toplevel(editor)
        dialog.withdraw()
        dialog.title("导出规则")
        dialog.resizable(False, False)
        dialog.transient(editor)
        frame = tk.Frame(dialog, padx=18, pady=16)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="选择要导出的规则：", anchor="w").pack(
            fill="x"
        )
        values = ("全部规则", *working["profiles"].keys())
        scope_var = tk.StringVar(value=selected_name)
        combo = ttk.Combobox(
            frame,
            textvariable=scope_var,
            values=values,
            state="readonly",
            width=30,
        )
        combo.pack(fill="x", pady=(8, 16))
        actions = tk.Frame(frame)
        actions.pack(fill="x")

        def confirm() -> None:
            choice["value"] = scope_var.get()
            dialog.destroy()

        tk.Button(
            actions, text="取消", command=dialog.destroy, width=10
        ).pack(side="right", padx=(8, 0))
        tk.Button(
            actions, text="下一步", command=confirm, width=10
        ).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.update_idletasks()
        width = dialog.winfo_reqwidth()
        height = dialog.winfo_reqheight()
        dialog.geometry(f"{width}x{height}")
        dialog.deiconify()
        dialog.lift()
        dialog.grab_set()
        combo.focus_set()
        dialog.wait_window()
        return choice["value"]

    def export_rules() -> None:
        try:
            store_profile(selected_name)
        except Exception as exc:
            messagebox.showerror(
                "规则无法导出",
                f"请先修正当前页面中的数值。\n\n{exc}",
                parent=editor,
            )
            return
        scope = choose_export_scope()
        if not scope:
            return
        names = None if scope == "全部规则" else (scope,)
        try:
            payload = build_rule_export(working, names)
        except Exception as exc:
            messagebox.showerror("规则无法导出", str(exc), parent=editor)
            return
        safe_scope = "全部" if scope == "全部规则" else scope
        default_name = (
            f"随机规则-{safe_scope}-{datetime.now():%Y%m%d}.json"
        )
        path = filedialog.asksaveasfilename(
            parent=editor,
            title="保存规则文件",
            defaultextension=".json",
            filetypes=(("规则文件", "*.json"), ("所有文件", "*.*")),
            initialfile=default_name,
        )
        if not path:
            return
        try:
            Path(path).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception as exc:
            messagebox.showerror(
                "规则无法导出", f"文件保存失败：{exc}", parent=editor
            )
            return
        messagebox.showinfo(
            "规则已导出",
            f"已导出到：\n{path}",
            parent=editor,
        )

    def import_rules() -> None:
        nonlocal working, saved_snapshot
        try:
            store_profile(selected_name)
        except Exception as exc:
            messagebox.showerror(
                "规则无法导入",
                f"请先修正当前页面中的数值。\n\n{exc}",
                parent=editor,
            )
            return
        path = filedialog.askopenfilename(
            parent=editor,
            title="选择规则文件",
            filetypes=(("规则文件", "*.json"), ("所有文件", "*.*")),
        )
        if not path:
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
            legacy_mode = read_legacy_mode(path)
            try:
                merged, imported_names = merge_rule_export(working, payload, legacy_mode=legacy_mode)
            except LegacyModeRequired:
                choice = messagebox.askyesnocancel(
                    "选择旧版运行模式",
                    "规则文件未记录当时使用3人还是7人，同目录也没有可用的 randomizer_settings.json。\n\n"
                    "请按旧版主界面使用的模式选择：\n是：3人\n否：7人\n取消：不导入",
                    parent=editor)
                if choice is None:
                    return
                legacy_mode = "three" if choice else "seven"
                merged, imported_names = merge_rule_export(working, payload, legacy_mode=legacy_mode)
            save_rule_config(base_dir, merged)
        except Exception as exc:
            messagebox.showerror(
                "规则无法导入",
                f"所选文件无法使用：\n{exc}",
                parent=editor,
            )
            return
        working = merged
        saved_snapshot = json.dumps(
            validate_rule_config(working),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        on_saved(working)
        refresh_profiles(imported_names[0])
        migration_note = ""
        if any(merged["profiles"][name].get("legacyImport") for name in imported_names):
            migration_note = (
                "\n\n旧版规则已自动迁移：沿用原运行模式的人物名单和兵种门槛，保留基础分、类型和人物倾向。"
                "\n特技改用原较低兵种档的特技分数要求作为总分门槛；取消高兵种／特殊特技直接通过及文官扣分。"
                "\n迁移规则以高级模式打开，请检查门槛后使用。")
        messagebox.showinfo(
            "规则已导入",
            f"已追加并保存 {len(imported_names)} 套规则。" + migration_note,
            parent=editor,
        )

    def has_unsaved_changes() -> bool:
        try:
            store_profile(selected_name)
            current_snapshot = json.dumps(
                validate_rule_config(working),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except Exception:
            return True
        return current_snapshot != saved_snapshot

    def request_close() -> None:
        if has_unsaved_changes() and not messagebox.askyesno(
            "放弃未保存的修改",
            "当前规则有尚未保存的修改，确定关闭吗？",
            parent=editor,
        ):
            return
        editor.destroy()

    def save_all() -> None:
        try:
            store_profile(selected_name, force=True)
            normalized = validate_rule_config(working)
            save_rule_config(base_dir, normalized)
        except Exception as exc:
            messagebox.showerror(
                "规则无法保存",
                f"请检查填写内容。\n\n{exc}",
                parent=editor,
            )
            return
        notice = save_notice(normalized) if save_notice is not None else None
        on_saved(normalized)
        editor.destroy()
        if notice:
            show_toast(
                parent,
                f"规则已保存\n{notice}",
                3600,
            )
        else:
            show_toast(parent, "规则已保存")

    new_button = tk.Button(action_frame, text="新建副本", command=new_profile)
    rename_button = tk.Button(
        action_frame, text="重命名", command=rename_profile
    )
    delete_button = tk.Button(
        action_frame, text="删除", command=delete_profile
    )
    reset_button = tk.Button(
        action_frame, text="恢复默认参数", command=reset_profile
    )
    help_button = tk.Button(
        action_frame,
        text="规则说明",
        command=lambda: show_advanced_help(
            editor,
            (
                -1
                if notebook.index(notebook.select()) == 0
                else advanced_book.index(advanced_book.select())
            ),
        ),
        width=10,
    )
    export_button = tk.Button(
        action_frame,
        text="导出规则",
        command=export_rules,
        width=10,
    )
    import_button = tk.Button(
        action_frame,
        text="导入规则",
        command=import_rules,
        width=10,
    )
    new_button.pack(side="left")
    rename_button.pack(side="left", padx=(8, 0))
    delete_button.pack(side="left", padx=(8, 0))
    reset_button.pack(side="left", padx=(8, 0))
    help_button.pack(side="right", padx=(0, 8))
    export_button.pack(side="right", padx=(0, 8))
    import_button.pack(side="right", padx=(0, 8))

    footer = tk.Frame(editor, padx=14, pady=12)
    footer.pack(fill="x")
    tk.Label(
        footer,
        text="内置默认规则只读。需要调整时，请先创建副本。",
        fg="#555555",
    ).pack(side="left")
    tk.Button(
        footer, text="取消", command=request_close, width=10
    ).pack(side="right", padx=(8, 0))
    tk.Button(
        footer, text="保存规则", command=save_all, width=12
    ).pack(side="right")

    profile_combo.bind("<<ComboboxSelected>>", switch_profile)
    editor.protocol("WM_DELETE_WINDOW", request_close)
    load_profile(selected_name)
    editor.update_idletasks()
    width = max(980, editor.winfo_reqwidth())
    height = max(760, editor.winfo_reqheight())
    editor.geometry(f"{width}x{height}")
    editor.deiconify()
    editor.lift()
    editor.grab_set()
