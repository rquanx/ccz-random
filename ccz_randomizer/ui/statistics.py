from __future__ import annotations

import calendar
import datetime as dt
import os
import tkinter as tk
from dataclasses import replace
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageTk

from ccz_randomizer.catalogs import (
    job_catalog_rows,
    skill_catalog_rows,
    treasure_property_catalog_rows,
)
from ccz_randomizer.statistics import StatisticsFilters, StatisticsRepository
from ccz_randomizer.ui.history import show_result_snapshot_detail


COLORS = {
    "page": "#F4F5F7",
    "surface": "#FFFFFF",
    "ink": "#182230",
    "muted": "#667085",
    "border": "#DDE1E7",
    "blue": "#2563EB",
    "blue_soft": "#EAF1FF",
    "chart_text": "#253247",
    "chart_secondary": "#3F4E63",
    "chart_primary": "#79A7F2",
    "chart_line": "#5689DE",
    "red": "#B42318",
}
CHART_PALETTE = (
    "#79A7F2",
    "#69BEA7",
    "#F0B667",
    "#D98CAB",
    "#9287D8",
    "#70BDD2",
)
FONT = "Microsoft YaHei UI"


def _lucide_icon(
    master: tk.Misc,
    name: str,
    *,
    color: str = "#344054",
    size: int = 16,
) -> ImageTk.PhotoImage:
    scale = size / 24
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    width = max(1, round(2 * scale))

    def point(x: float, y: float) -> tuple[int, int]:
        return round(x * scale), round(y * scale)

    def line(*points: tuple[float, float]) -> None:
        draw.line(
            [point(x, y) for x, y in points],
            fill=color,
            width=width,
            joint="curve",
        )

    if name == "refresh-cw":
        draw.arc(
            (*point(4, 4), *point(20, 20)),
            35,
            205,
            fill=color,
            width=width,
        )
        draw.arc(
            (*point(4, 4), *point(20, 20)),
            215,
            385,
            fill=color,
            width=width,
        )
        line((18, 3), (21, 6), (18, 8))
        line((6, 16), (3, 18), (6, 21))
    elif name == "download":
        line((12, 3), (12, 15))
        line((7, 10), (12, 15), (17, 10))
        line((5, 18), (5, 21), (19, 21), (19, 18))
    elif name == "database":
        draw.ellipse(
            (*point(4, 3), *point(20, 9)),
            outline=color,
            width=width,
        )
        draw.arc(
            (*point(4, 7), *point(20, 15)),
            0,
            180,
            fill=color,
            width=width,
        )
        draw.arc(
            (*point(4, 13), *point(20, 21)),
            0,
            180,
            fill=color,
            width=width,
        )
        line((4, 6), (4, 18))
        line((20, 6), (20, 18))
    elif name in {"filter", "filter-x"}:
        line((4, 5), (20, 5), (14, 12), (14, 19), (10, 21), (10, 12), (4, 5))
        if name == "filter-x":
            line((16, 16), (22, 22))
            line((22, 16), (16, 22))
    elif name == "check":
        line((4, 12), (9, 17), (20, 6))
    elif name == "x":
        line((5, 5), (19, 19))
        line((19, 5), (5, 19))
    elif name == "history":
        draw.arc(
            (*point(4, 4), *point(20, 20)),
            35,
            330,
            fill=color,
            width=width,
        )
        line((4, 4), (4, 9), (9, 9))
        line((12, 7), (12, 12), (16, 14))
    elif name == "layers":
        line((12, 3), (21, 8), (12, 13), (3, 8), (12, 3))
        line((3, 12), (12, 17), (21, 12))
        line((3, 16), (12, 21), (21, 16))
    elif name == "archive":
        line((4, 7), (20, 7), (19, 21), (5, 21), (4, 7))
        line((3, 3), (21, 3), (21, 7), (3, 7), (3, 3))
        line((9, 12), (15, 12))
    elif name == "calendar":
        line((5, 5), (19, 5), (19, 20), (5, 20), (5, 5))
        line((8, 3), (8, 7))
        line((16, 3), (16, 7))
        line((5, 10), (19, 10))
    elif name == "image":
        line((4, 4), (20, 4), (20, 20), (4, 20), (4, 4))
        draw.ellipse(
            (*point(7, 7), *point(10, 10)),
            outline=color,
            width=width,
        )
        line((4, 17), (9, 12), (13, 16), (16, 13), (20, 17))
    elif name == "chevron-left":
        line((15, 5), (8, 12), (15, 19))
    elif name == "chevron-right":
        line((9, 5), (16, 12), (9, 19))
    elif name == "chevron-down":
        line((5, 9), (12, 16), (19, 9))
    elif name == "trash":
        line((4, 7), (20, 7))
        line((9, 3), (15, 3), (16, 7))
        line((6, 7), (7, 21), (17, 21), (18, 7))
        line((10, 11), (10, 17))
        line((14, 11), (14, 17))
    elif name == "chart-bar":
        line((4, 20), (20, 20))
        line((6, 17), (6, 11), (10, 11), (10, 17))
        line((12, 17), (12, 5), (16, 5), (16, 17))
        line((18, 17), (18, 8), (21, 8), (21, 17))
    else:
        draw.ellipse(
            (*point(4, 4), *point(20, 20)),
            outline=color,
            width=width,
        )
    return ImageTk.PhotoImage(image, master=master)


def _icon_button(
    parent: tk.Misc,
    *,
    text: str,
    icon: str,
    command: Callable[[], None],
    foreground: str = COLORS["ink"],
    background: str = COLORS["surface"],
    **options,
) -> tk.Button:
    image = _lucide_icon(parent, icon, color=foreground)
    button = tk.Button(
        parent,
        text=text,
        image=image,
        compound="left",
        command=command,
        fg=foreground,
        bg=background,
        activeforeground=foreground,
        activebackground=background,
        relief="flat",
        cursor="hand2",
        padx=10,
        pady=5,
        **options,
    )
    button._lucide_image = image
    return button


def _center(window: tk.Toplevel, parent: tk.Misc, width: int, height: int):
    window.update_idletasks()
    parent.update_idletasks()
    width = min(width, max(720, window.winfo_screenwidth() - 32))
    height = min(height, max(600, window.winfo_screenheight() - 64))
    x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
    window.geometry(f"{width}x{height}+{max(8, x)}+{max(8, y)}")


def _scroll_canvas(canvas: tk.Canvas, event: tk.Event) -> str | None:
    widget: tk.Misc | None = event.widget
    while widget is not None:
        if isinstance(widget, (ttk.Treeview, tk.Listbox)):
            return None
        widget = getattr(widget, "master", None)
    delta = int(getattr(event, "delta", 0))
    if not delta:
        return None
    canvas.yview_scroll(-3 if delta > 0 else 3, "units")
    return "break"


def _release_entry_focus(window: tk.Misc, event: tk.Event) -> None:
    focused = window.focus_get()
    target = event.widget
    if (
        isinstance(focused, (tk.Entry, ttk.Entry))
        and target is not focused
        and not isinstance(target, (tk.Entry, ttk.Entry))
    ):
        window.focus_set()


def _include_zero_rows(
    rows: list[dict[str, Any]],
    universe: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    existing = {
        (
            str(row.get("rule_snapshot_hash") or ""),
            str(row.get("value") or ""),
        ): dict(row)
        for row in rows
    }
    result = list(existing.values())
    for template in universe:
        key = (
            str(template.get("rule_snapshot_hash") or ""),
            str(template.get("value") or ""),
        )
        if key in existing:
            continue
        result.append(
            {
                **template,
                "count": 0,
                "attempt_count": 0,
                "save_count": 0,
                "member_count": 0,
                "ratio": 0.0,
            }
        )
    return result


def _scrollable_tab(notebook: ttk.Notebook, title: str) -> tk.Frame:
    container = tk.Frame(notebook, bg=COLORS["page"])
    notebook.add(container, text=title)
    canvas = tk.Canvas(
        container,
        bg=COLORS["page"],
        highlightthickness=0,
    )
    scrollbar = ttk.Scrollbar(
        container,
        orient="vertical",
        command=canvas.yview,
    )
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    content = tk.Frame(canvas, bg=COLORS["page"])
    window_id = canvas.create_window((0, 0), window=content, anchor="nw")
    content.bind(
        "<Configure>",
        lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
    )
    canvas.bind(
        "<Configure>",
        lambda event: canvas.itemconfigure(window_id, width=event.width),
    )

    def scroll(event: tk.Event) -> str | None:
        return _scroll_canvas(canvas, event)

    container.bind(
        "<Enter>",
        lambda _event: container.bind_all("<MouseWheel>", scroll),
    )
    container.bind(
        "<Leave>",
        lambda _event: container.unbind_all("<MouseWheel>"),
    )
    canvas.bind("<MouseWheel>", scroll)
    content.bind("<MouseWheel>", scroll)
    return content


def _choice_picker(
    parent: tk.Misc,
    variable: tk.StringVar,
    values: tuple[str, ...],
    *,
    command: Callable[[], None],
    requested_width: int | None = None,
) -> tk.Button:
    icon = _lucide_icon(parent, "chevron-down", color=COLORS["muted"], size=14)
    display_width = requested_width or max(
        14,
        min(
            36,
            max(
                (
                    sum(2 if ord(character) > 127 else 1 for character in value)
                    for value in values
                ),
                default=12,
            )
            + 3,
        ),
    )
    picker = tk.Button(
        parent,
        textvariable=variable,
        anchor="w",
        relief="flat",
        borderwidth=0,
        highlightthickness=1,
        highlightbackground=COLORS["border"],
        highlightcolor=COLORS["blue"],
        bg="#F8FAFC",
        fg=COLORS["ink"],
        activebackground=COLORS["blue_soft"],
        activeforeground=COLORS["ink"],
        font=(FONT, 9),
        cursor="hand2",
        width=display_width,
        padx=15,
        pady=7,
    )
    picker._lucide_image = icon
    arrow = tk.Label(
        picker,
        image=icon,
        bg="#F8FAFC",
        borderwidth=0,
        cursor="hand2",
    )
    arrow.place(relx=1.0, x=-10, rely=0.5, anchor="e")
    arrow.bind("<Button-1>", lambda _event: picker.invoke())
    picker._choice_arrow = arrow

    def open_popup() -> None:
        existing = getattr(picker, "_choice_popup", None)
        if existing is not None and existing.winfo_exists():
            existing.destroy()
            return
        picker.update_idletasks()
        popup = tk.Toplevel(picker)
        picker._choice_popup = popup
        popup.withdraw()
        popup.overrideredirect(True)
        popup.transient(picker.winfo_toplevel())
        popup.configure(bg=COLORS["border"])
        outer = tk.Frame(
            popup,
            bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
        )
        outer.pack(fill="both", expand=True)
        visible_rows = min(10, max(1, len(values)))
        canvas = tk.Canvas(
            outer,
            bg=COLORS["surface"],
            height=visible_rows * 36 + 8,
            highlightthickness=0,
        )
        canvas.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(4, 0),
            pady=4,
        )
        scrollbar = ttk.Scrollbar(
            outer,
            orient="vertical",
            command=canvas.yview,
        )
        if len(values) > visible_rows:
            scrollbar.pack(side="right", fill="y", pady=4, padx=(0, 3))
        canvas.configure(yscrollcommand=scrollbar.set)
        options = tk.Frame(canvas, bg=COLORS["surface"])
        option_window = canvas.create_window(
            (0, 0),
            window=options,
            anchor="nw",
        )
        blank_icon = ImageTk.PhotoImage(
            Image.new("RGBA", (14, 14), (0, 0, 0, 0)),
            master=popup,
        )
        check_icon = _lucide_icon(
            popup,
            "check",
            color=COLORS["blue"],
            size=14,
        )

        def close_popup() -> None:
            if not popup.winfo_exists():
                return
            try:
                popup.grab_release()
            except tk.TclError:
                pass
            popup.destroy()

        def choose(value: str) -> None:
            variable.set(value)
            close_popup()
            command()

        for value in values:
            selected = value == variable.get()
            option = tk.Button(
                options,
                text=value,
                image=check_icon if selected else blank_icon,
                compound="left",
                anchor="w",
                relief="flat",
                borderwidth=0,
                bg=COLORS["blue_soft"] if selected else COLORS["surface"],
                fg=COLORS["blue"] if selected else COLORS["ink"],
                activebackground=COLORS["blue_soft"],
                activeforeground=COLORS["blue"],
                font=(FONT, 9, "bold" if selected else "normal"),
                cursor="hand2",
                padx=10,
                pady=7,
                command=lambda selected_value=value: choose(selected_value),
            )
            option._choice_icon = check_icon if selected else blank_icon
            option.pack(fill="x", padx=2, pady=1)

            def enter(_event, target=option) -> None:
                target.configure(bg=COLORS["blue_soft"], fg=COLORS["blue"])

            def leave(_event, target=option, active=selected) -> None:
                target.configure(
                    bg=COLORS["blue_soft"] if active else COLORS["surface"],
                    fg=COLORS["blue"] if active else COLORS["ink"],
                )

            option.bind("<Enter>", enter)
            option.bind("<Leave>", leave)

        def resize_options(event: tk.Event) -> None:
            canvas.itemconfigure(option_window, width=event.width)

        options.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind("<Configure>", resize_options)
        def scroll_options(event: tk.Event) -> str:
            canvas.yview_scroll(
                -3 if int(event.delta) > 0 else 3,
                "units",
            )
            return "break"

        canvas.bind("<MouseWheel>", scroll_options)
        popup.bind("<MouseWheel>", scroll_options, add="+")
        popup.bind("<Escape>", lambda _event: close_popup())

        def close_when_clicked_outside(event: tk.Event) -> str | None:
            if not popup.winfo_exists():
                return None
            left = popup.winfo_rootx()
            top = popup.winfo_rooty()
            right = left + popup.winfo_width()
            bottom = top + popup.winfo_height()
            if not (
                left <= int(event.x_root) < right
                and top <= int(event.y_root) < bottom
            ):
                close_popup()
                return "break"
            return None

        popup.bind("<ButtonPress-1>", close_when_clicked_outside, add="+")
        popup.update_idletasks()
        width = max(picker.winfo_width(), 280)
        height = min(
            visible_rows * 36 + 10,
            popup.winfo_screenheight() - 24,
        )
        x = picker.winfo_rootx()
        y = picker.winfo_rooty() + picker.winfo_height() + 4
        if x + width > popup.winfo_screenwidth() - 8:
            x = popup.winfo_screenwidth() - width - 8
        if y + height > popup.winfo_screenheight() - 8:
            y = picker.winfo_rooty() - height - 4
        popup.geometry(f"{width}x{height}+{max(8, x)}+{max(8, y)}")
        popup.deiconify()
        popup.lift()
        popup.focus_force()
        popup.grab_set()

    picker.configure(command=open_popup)
    return picker


def _show_calendar(
    parent: tk.Misc,
    *,
    title: str,
    initial: dt.date,
    on_select: Callable[[dt.date], None],
) -> tk.Toplevel:
    popup = tk.Toplevel(parent)
    popup.title(title)
    popup.transient(parent.winfo_toplevel())
    popup.configure(bg=COLORS["surface"])
    popup.resizable(False, False)
    _center(popup, parent, 360, 340)
    shown_year = initial.year
    shown_month = initial.month
    body = tk.Frame(popup, bg=COLORS["surface"], padx=14, pady=12)
    body.pack(fill="both", expand=True)
    header = tk.Frame(body, bg=COLORS["surface"])
    header.pack(fill="x", pady=(0, 10))
    month_label = tk.Label(
        header,
        bg=COLORS["surface"],
        fg=COLORS["ink"],
        font=(FONT, 12, "bold"),
    )
    grid = tk.Frame(body, bg=COLORS["surface"])
    grid.pack(fill="both", expand=True)
    for column in range(7):
        grid.columnconfigure(column, weight=1, uniform="calendar_day")

    def render_month() -> None:
        for child in grid.winfo_children():
            child.destroy()
        month_label.configure(text=f"{shown_year} 年 {shown_month} 月")
        for column, weekday in enumerate(("一", "二", "三", "四", "五", "六", "日")):
            tk.Label(
                grid,
                text=weekday,
                bg=COLORS["surface"],
                fg=COLORS["muted"],
                font=(FONT, 8),
            ).grid(row=0, column=column, sticky="nsew", pady=(0, 5))
        weeks = calendar.monthcalendar(shown_year, shown_month)
        for row_index, week in enumerate(weeks, 1):
            for column, day in enumerate(week):
                if not day:
                    tk.Label(grid, bg=COLORS["surface"]).grid(
                        row=row_index,
                        column=column,
                        sticky="nsew",
                    )
                    continue
                value = dt.date(shown_year, shown_month, day)
                selected = value == initial
                today = value == dt.date.today()
                button = tk.Button(
                    grid,
                    text=str(day),
                    relief="flat",
                    borderwidth=0,
                    highlightthickness=1 if today and not selected else 0,
                    highlightbackground=COLORS["blue"],
                    bg=COLORS["blue"] if selected else COLORS["surface"],
                    fg="#FFFFFF" if selected else COLORS["ink"],
                    activebackground=COLORS["blue_soft"],
                    activeforeground=COLORS["blue"],
                    font=(FONT, 9, "bold" if selected else "normal"),
                    cursor="hand2",
                    width=3,
                    pady=6,
                    command=lambda chosen=value: (
                        on_select(chosen),
                        popup.destroy(),
                    ),
                )
                button.grid(
                    row=row_index,
                    column=column,
                    sticky="nsew",
                    padx=2,
                    pady=2,
                )

    def move_month(delta: int) -> None:
        nonlocal shown_year, shown_month
        month_index = shown_year * 12 + shown_month - 1 + delta
        shown_year, month_zero = divmod(month_index, 12)
        shown_month = month_zero + 1
        render_month()

    previous_button = _icon_button(
        header,
        text="",
        icon="chevron-left",
        command=lambda: move_month(-1),
    )
    previous_button.pack(side="left")
    next_button = _icon_button(
        header,
        text="",
        icon="chevron-right",
        command=lambda: move_month(1),
    )
    next_button.pack(side="right")
    month_label.pack(side="left", fill="x", expand=True)
    render_month()
    popup.bind("<Escape>", lambda _event: popup.destroy())
    popup.grab_set()
    return popup


def _ranked_distribution(
    parent: tk.Misc,
    rows: list[dict[str, Any]],
    *,
    title: str,
    subtitle: str = "",
    columns: int = 1,
    searchable: bool = True,
    picker: tuple[
        str,
        tk.StringVar,
        tuple[str, ...],
        Callable[[], None],
    ]
    | None = None,
) -> tk.Frame:
    holder = tk.Frame(
        parent,
        bg=COLORS["surface"],
        highlightbackground=COLORS["border"],
        highlightthickness=1,
    )
    heading = tk.Frame(holder, bg=COLORS["surface"])
    heading.pack(fill="x", padx=14, pady=(12, 8))
    title_area = tk.Frame(heading, bg=COLORS["surface"])
    title_area.pack(side="left", fill="x", expand=True)
    tk.Label(
        title_area,
        text=title,
        font=(FONT, 12, "bold"),
        fg=COLORS["ink"],
        bg=COLORS["surface"],
        anchor="w",
    ).pack(anchor="w")
    if subtitle:
        tk.Label(
            title_area,
            text=subtitle,
            font=(FONT, 9),
            fg=COLORS["muted"],
            bg=COLORS["surface"],
            anchor="w",
        ).pack(anchor="w", pady=(3, 0))

    search_var = tk.StringVar()
    show_search = searchable and len(rows) > 12
    actions = tk.Frame(heading, bg=COLORS["surface"])
    actions.pack(side="right", anchor="n", padx=(12, 0))
    if picker is not None:
        picker_label, picker_var, picker_values, picker_command = picker
        if picker_values and picker_var.get() not in picker_values:
            picker_var.set(picker_values[0])
        picker_area = tk.Frame(actions, bg=COLORS["surface"])
        picker_area.pack(side="right", padx=(8, 0))
        tk.Label(
            picker_area,
            text=picker_label,
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=(FONT, 8),
        ).pack(anchor="w", pady=(0, 3))
        _choice_picker(
            picker_area,
            picker_var,
            picker_values,
            command=picker_command,
        ).pack()
    if show_search:
        search_frame = tk.Frame(
            actions,
            bg="#F8FAFC",
            highlightbackground=COLORS["border"],
            highlightthickness=1,
        )
        search_frame.pack(side="right", anchor="n")
        search_icon = _lucide_icon(
            search_frame,
            "filter",
            color=COLORS["muted"],
            size=14,
        )
        icon_label = tk.Label(
            search_frame,
            image=search_icon,
            bg="#F8FAFC",
        )
        icon_label._lucide_image = search_icon
        icon_label.pack(side="left", padx=(8, 4))
        search_entry = tk.Entry(
            search_frame,
            textvariable=search_var,
            relief="flat",
            borderwidth=0,
            bg="#F8FAFC",
            fg=COLORS["ink"],
            insertbackground=COLORS["ink"],
            font=(FONT, 9),
            width=16,
        )
        search_entry.pack(side="left", padx=(0, 8), pady=6)

    table = tk.Frame(holder, bg=COLORS["surface"])
    table.pack(fill="x", padx=14, pady=(0, 12))

    def render_column(
        target: tk.Misc,
        items: list[tuple[int, dict[str, Any]]],
        maximum: int,
    ) -> None:
        header = tk.Frame(target, bg=COLORS["surface"])
        header.pack(fill="x", pady=(0, 4))
        tk.Label(
            header,
            text="排名",
            width=5,
            anchor="center",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=(FONT, 8),
        ).pack(side="left")
        tk.Label(
            header,
            text="名称",
            width=18,
            anchor="w",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=(FONT, 8),
        ).pack(side="left")
        tk.Label(
            header,
            text="占比",
            width=9,
            anchor="e",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=(FONT, 8),
        ).pack(side="right", padx=(8, 4))
        tk.Label(
            header,
            text="出现次数",
            width=9,
            anchor="e",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=(FONT, 8),
        ).pack(side="right")
        for index, row in items:
            line_frame = tk.Frame(
                target,
                bg="#FAFBFC" if index % 2 else COLORS["surface"],
            )
            line_frame.pack(fill="x", pady=1)
            tk.Label(
                line_frame,
                text=f"{index:02d}",
                width=5,
                anchor="center",
                bg=line_frame["bg"],
                fg=COLORS["muted"],
                font=(FONT, 9),
            ).pack(side="left", pady=7)
            name_area = tk.Frame(line_frame, bg=line_frame["bg"])
            name_area.pack(side="left", fill="x", expand=True)
            tk.Label(
                name_area,
                text=str(row.get("label") or "未知"),
                anchor="w",
                bg=line_frame["bg"],
                fg=COLORS["ink"],
                font=(FONT, 9, "bold" if index <= 3 else "normal"),
            ).pack(fill="x")
            meter = tk.Canvas(
                name_area,
                height=3,
                bg=line_frame["bg"],
                highlightthickness=0,
            )
            meter.pack(fill="x", pady=(3, 0))

            def draw_meter(
                event: tk.Event,
                *,
                canvas: tk.Canvas = meter,
                count: int = int(row.get("count") or 0),
                color: str = CHART_PALETTE[(index - 1) % len(CHART_PALETTE)],
            ) -> None:
                canvas.delete("all")
                width = max(1, int(event.width))
                canvas.create_rectangle(
                    0,
                    0,
                    width,
                    3,
                    fill="#E9EEF4",
                    outline="",
                )
                fill_width = int(width * count / maximum) if count else 0
                if fill_width:
                    canvas.create_rectangle(
                        0,
                        0,
                        max(2, fill_width),
                        3,
                        fill=color,
                        outline="",
                    )

            meter.bind("<Configure>", draw_meter)
            tk.Label(
                line_frame,
                text=f"{float(row.get('ratio') or 0):.1%}",
                width=9,
                anchor="e",
                bg=line_frame["bg"],
                fg=COLORS["chart_secondary"],
                font=(FONT, 9),
            ).pack(side="right", padx=(8, 4))
            tk.Label(
                line_frame,
                text=str(int(row.get("count") or 0)),
                width=9,
                anchor="e",
                bg=line_frame["bg"],
                fg=COLORS["ink"],
                font=(FONT, 9, "bold"),
            ).pack(side="right")

    def draw() -> None:
        for child in table.winfo_children():
            child.destroy()
        query = search_var.get().strip().casefold()
        visible = [
            row
            for row in rows
            if not query or query in str(row.get("label") or "").casefold()
        ]
        visible.sort(
            key=lambda row: (
                -int(row.get("count") or 0),
                str(row.get("label") or ""),
            )
        )
        if not visible:
            tk.Label(
                table,
                text="暂无符合条件的数据",
                bg=COLORS["surface"],
                fg=COLORS["muted"],
                font=(FONT, 9),
            ).pack(anchor="w", pady=12)
            return
        column_count = max(1, min(columns, len(visible)))
        maximum = max(int(row.get("count") or 0) for row in visible) or 1
        indexed = list(enumerate(visible, 1))
        chunk_size = (len(indexed) + column_count - 1) // column_count
        for column in range(column_count):
            table.columnconfigure(
                column,
                weight=1,
                uniform="ranked_distribution_columns",
            )
            column_frame = tk.Frame(table, bg=COLORS["surface"])
            column_frame.grid(
                row=0,
                column=column,
                sticky="nsew",
                padx=(0 if column == 0 else 10, 0),
            )
            start = column * chunk_size
            render_column(
                column_frame,
                indexed[start : start + chunk_size],
                maximum,
            )

    if show_search:
        search_var.trace_add("write", lambda *_args: draw())
    draw()
    return holder


def _bar_chart(
    parent: tk.Misc,
    rows: list[dict[str, Any]],
    *,
    title: str,
    on_click: Callable[[dict[str, Any]], None] | None = None,
) -> tk.Frame:
    holder = tk.Frame(
        parent,
        bg=COLORS["surface"],
        highlightbackground=COLORS["border"],
        highlightthickness=1,
    )
    tk.Label(
        holder,
        text=title,
        font=(FONT, 12, "bold"),
        fg=COLORS["ink"],
        bg=COLORS["surface"],
        anchor="w",
    ).pack(fill="x", padx=12, pady=(10, 4))
    search_var = tk.StringVar()
    sort_var = tk.StringVar(value="次数")
    if len(rows) > 12:
        tools = tk.Frame(holder, bg=COLORS["surface"])
        tools.pack(fill="x", padx=12, pady=(0, 6))
        tk.Label(
            tools,
            text="搜索",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=(FONT, 9),
        ).pack(side="left")
        search_entry = tk.Entry(
            tools,
            textvariable=search_var,
            width=22,
        )
        search_entry.pack(side="left", padx=(6, 12))
        tk.Label(
            tools,
            text="排序",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=(FONT, 9),
        ).pack(side="left")
        sort_combo = ttk.Combobox(
            tools,
            textvariable=sort_var,
            values=("次数", "名称"),
            state="readonly",
            width=8,
        )
        sort_combo.pack(side="left", padx=(6, 0))
    canvas = tk.Canvas(
        holder,
        height=130,
        bg=COLORS["surface"],
        highlightthickness=0,
    )
    canvas.pack(fill="both", expand=True, padx=12, pady=(0, 10))

    def draw(_event=None) -> None:
        canvas.delete("all")
        query = search_var.get().strip().casefold()
        visible = [
            row
            for row in rows
            if not query
            or query in str(row.get("label") or "").casefold()
        ]
        if sort_var.get() == "名称":
            visible.sort(key=lambda row: str(row.get("label") or ""))
        else:
            visible.sort(
                key=lambda row: (
                    -int(row.get("count") or 0),
                    str(row.get("label") or ""),
                )
            )
        canvas.configure(
            height=max(130, 34 * max(1, len(visible)) + 20)
        )
        if not visible:
            canvas.create_text(
                12,
                24,
                text="暂无符合条件的数据",
                anchor="w",
                fill=COLORS["chart_secondary"],
                font=(FONT, 10),
            )
            return
        max_count = max(int(row.get("count") or 0) for row in visible) or 1
        width = max(320, canvas.winfo_width())
        label_width = min(220, max(120, width // 3))
        for index, row in enumerate(visible):
            y = 22 + index * 32
            label = str(row.get("label") or "未知")
            if row.get("rule_snapshot_hash"):
                label = f"{str(row['rule_snapshot_hash'])[:10]} · {label}"
            count = int(row.get("count") or 0)
            ratio = float(row.get("ratio") or 0)
            tag = f"bar-{index}"
            canvas.create_text(
                0,
                y,
                text=label[:36],
                anchor="w",
                fill=COLORS["chart_text"],
                font=(FONT, 9),
                tags=(tag,),
            )
            left = label_width
            track_right = width - 112
            right = left + int(
                (track_right - left) * count / max_count
            )
            canvas.create_rectangle(
                left,
                y - 8,
                track_right,
                y + 8,
                fill="#EDF1F6",
                outline="",
            )
            canvas.create_rectangle(
                left,
                y - 8,
                max(left + 2, right),
                y + 8,
                fill=CHART_PALETTE[index % len(CHART_PALETTE)],
                outline="",
                tags=(tag,),
            )
            canvas.create_text(
                width - 4,
                y,
                text=(
                    f"{count}  {ratio:.1%}"
                    + (
                        f"  存档{int(row.get('save_count') or 0)}"
                        if row.get("save_count") is not None
                        else ""
                    )
                    + (
                        f"  武将{int(row.get('member_count') or 0)}"
                        if row.get("member_count") is not None
                        else ""
                    )
                ),
                anchor="e",
                fill=COLORS["chart_text"],
                font=(FONT, 9),
                tags=(tag,),
            )
            if on_click is not None:
                canvas.tag_bind(
                    tag,
                    "<Button-1>",
                    lambda _event, value=row: on_click(value),
                )
                canvas.tag_bind(
                    tag,
                    "<Enter>",
                    lambda _event: canvas.configure(cursor="hand2"),
                )
                canvas.tag_bind(
                    tag,
                    "<Leave>",
                    lambda _event: canvas.configure(cursor=""),
                )

    if len(rows) > 12:
        search_entry.bind("<KeyRelease>", lambda _event: draw())
        sort_combo.bind("<<ComboboxSelected>>", lambda _event: draw())
    canvas.bind("<Configure>", draw)
    draw()
    return holder


def _line_chart(
    parent: tk.Misc,
    rows: list[dict[str, Any]],
    *,
    title: str,
    value_field: str = "accepted",
    value_label: str = "合格",
    x_label: str = "日期",
    picker: tuple[
        tk.StringVar,
        tuple[str, ...],
        Callable[[], None],
    ]
    | None = None,
    on_click: Callable[[dict[str, Any]], None] | None = None,
) -> tk.Frame:
    holder = tk.Frame(
        parent,
        bg=COLORS["surface"],
        highlightbackground=COLORS["border"],
        highlightthickness=1,
    )
    heading = tk.Frame(holder, bg=COLORS["surface"])
    heading.pack(fill="x", padx=12, pady=(10, 4))
    tk.Label(
        heading,
        text=title,
        font=(FONT, 12, "bold"),
        fg=COLORS["ink"],
        bg=COLORS["surface"],
        anchor="w",
    ).pack(side="left", fill="x", expand=True)
    if picker is not None:
        picker_var, picker_values, picker_command = picker
        _choice_picker(
            heading,
            picker_var,
            picker_values,
            command=picker_command,
            requested_width=12,
        ).pack(side="right")
    canvas = tk.Canvas(
        holder,
        height=180,
        bg=COLORS["surface"],
        highlightthickness=0,
    )
    canvas.pack(fill="x", padx=12, pady=(0, 10))
    def draw(_event=None) -> None:
        canvas.delete("all")
        if not rows:
            canvas.create_text(
                12,
                24,
                text="暂无趋势数据",
                anchor="w",
                fill=COLORS["chart_secondary"],
                font=(FONT, 10),
            )
            return
        values = [float(row.get(value_field) or 0) for row in rows]
        maximum = max(values + [1])
        left, top = 38, 15
        width = max(320, canvas.winfo_width())
        height = max(130, canvas.winfo_height() - 20)
        usable_width = width - left - 10
        usable_height = height - top - 32
        for step in range(4):
            grid_y = top + usable_height * step / 3
            canvas.create_line(
                left,
                grid_y,
                width - 8,
                grid_y,
                fill="#E7EBF0",
                width=1,
            )
            canvas.create_text(
                left - 6,
                grid_y,
                text=f"{maximum * (1 - step / 3):.1f}".rstrip("0").rstrip("."),
                anchor="e",
                fill=COLORS["chart_secondary"],
                font=(FONT, 8),
            )
        points = []
        for index, value in enumerate(values):
            x = left if len(values) == 1 else (
                left + usable_width * index / (len(values) - 1)
            )
            y = top + usable_height * (1 - value / maximum)
            points.append((x, y))
        if len(points) > 1:
            canvas.create_line(
                *[value for point in points for value in point],
                fill=COLORS["chart_line"],
                width=3,
            )
        for index, (x, y) in enumerate(points):
            canvas.create_oval(
                x - 4,
                y - 4,
                x + 4,
                y + 4,
                fill=COLORS["surface"],
                outline=COLORS["chart_line"],
                width=2,
                tags=(f"point-{index}",),
            )
            if on_click is not None:
                canvas.tag_bind(
                    f"point-{index}",
                    "<Button-1>",
                    lambda _event, value=rows[index]: on_click(value),
                )
        tick_count = min(len(rows), max(2, min(6, width // 90)))
        tick_indices = (
            list(range(len(rows)))
            if len(rows) <= tick_count
            else sorted(
                {
                    round(index * (len(rows) - 1) / (tick_count - 1))
                    for index in range(tick_count)
                }
            )
        )
        for index in tick_indices:
            x = points[index][0]
            raw_label = str(rows[index].get("date") or "")
            try:
                tick_label = dt.date.fromisoformat(raw_label).strftime("%m-%d")
            except ValueError:
                tick_label = raw_label
            canvas.create_line(
                x,
                top + usable_height,
                x,
                top + usable_height + 4,
                fill=COLORS["chart_secondary"],
            )
            canvas.create_text(
                x,
                top + usable_height + 8,
                text=tick_label,
                anchor="n",
                fill=COLORS["chart_text"],
                font=(FONT, 8),
            )
        canvas.create_text(
            width - 6,
            height - 2,
            text=f"横轴：{x_label}",
            anchor="se",
            fill=COLORS["muted"],
            font=(FONT, 8),
        )
        canvas.create_text(
            width - 4,
            top,
            text=(
                f"{value_label} "
                f"{sum(values):.1f}".rstrip("0").rstrip(".")
            ),
            anchor="e",
            fill=COLORS["chart_text"],
            font=(FONT, 9),
        )

    canvas.bind("<Configure>", draw)
    draw()
    return holder


def _pie_chart(
    parent: tk.Misc,
    rows: list[dict[str, Any]],
    *,
    title: str,
    on_click: Callable[[dict[str, Any]], None] | None = None,
) -> tk.Frame:
    holder = tk.Frame(
        parent,
        bg=COLORS["surface"],
        highlightbackground=COLORS["border"],
        highlightthickness=1,
    )
    tk.Label(
        holder,
        text=title,
        font=(FONT, 12, "bold"),
        fg=COLORS["ink"],
        bg=COLORS["surface"],
        anchor="w",
    ).pack(fill="x", padx=12, pady=(10, 4))
    canvas = tk.Canvas(
        holder,
        width=360,
        height=220,
        bg=COLORS["surface"],
        highlightthickness=0,
    )
    canvas.pack(fill="both", expand=True, padx=12, pady=(0, 10))
    def draw(_event=None) -> None:
        canvas.delete("all")
        total = sum(int(row.get("count") or 0) for row in rows)
        if not total:
            canvas.create_text(
                12,
                24,
                text="暂无符合条件的数据",
                anchor="w",
                fill=COLORS["chart_secondary"],
                font=(FONT, 10),
            )
            return
        width = max(320, canvas.winfo_width())
        diameter = min(180, max(120, width // 2 - 30))
        label_x = diameter + 40
        start = 0.0
        for index, row in enumerate(rows):
            count = int(row.get("count") or 0)
            extent = 360.0 * count / total
            tag = f"slice-{index}"
            if count == total:
                canvas.create_oval(
                    20,
                    20,
                    20 + diameter,
                    20 + diameter,
                    fill=CHART_PALETTE[index % len(CHART_PALETTE)],
                    outline=COLORS["surface"],
                    width=1,
                    tags=(tag,),
                )
            else:
                canvas.create_arc(
                    20,
                    20,
                    20 + diameter,
                    20 + diameter,
                    start=start,
                    extent=extent,
                    fill=CHART_PALETTE[index % len(CHART_PALETTE)],
                    outline=COLORS["surface"],
                    width=1,
                    tags=(tag,),
                )
            label = str(row.get("label") or "")
            canvas.create_text(
                label_x,
                38 + index * 25,
                text=f"{label}  {count} ({count / total:.1%})",
                anchor="w",
                fill=COLORS["chart_text"],
                font=(FONT, 9),
                tags=(tag,),
            )
            if on_click is not None:
                canvas.tag_bind(
                    tag,
                    "<Button-1>",
                    lambda _event, value=row: on_click(value),
                )
            start += extent
        inner_margin = max(28, diameter // 4)
        canvas.create_oval(
            20 + inner_margin,
            20 + inner_margin,
            20 + diameter - inner_margin,
            20 + diameter - inner_margin,
            fill=COLORS["surface"],
            outline=COLORS["surface"],
        )
        canvas.create_text(
            20 + diameter / 2,
            20 + diameter / 2 - 8,
            text=str(total),
            fill=COLORS["chart_text"],
            font=(FONT, 15, "bold"),
        )
        canvas.create_text(
            20 + diameter / 2,
            20 + diameter / 2 + 13,
            text="总计",
            fill=COLORS["chart_secondary"],
            font=(FONT, 8),
        )

    canvas.bind("<Configure>", draw)
    draw()
    return holder


def _metric_card(
    parent,
    label: str,
    value: Any,
    *,
    row: int,
    column: int,
    accent: bool = False,
):
    card = tk.Frame(
        parent,
        bg=COLORS["blue_soft"] if accent else COLORS["surface"],
        highlightbackground=COLORS["blue"] if accent else COLORS["border"],
        highlightthickness=1,
    )
    card.grid(
        row=row,
        column=column,
        sticky="nsew",
        padx=(0 if column == 0 else 6, 0),
        pady=(0 if row == 0 else 6, 0),
    )
    tk.Label(
        card,
        text=label,
        bg=COLORS["blue_soft"] if accent else COLORS["surface"],
        fg=COLORS["blue"] if accent else COLORS["muted"],
        font=(FONT, 9),
    ).pack(anchor="w", padx=10, pady=(8, 2))
    tk.Label(
        card,
        text=str(value),
        bg=COLORS["blue_soft"] if accent else COLORS["surface"],
        fg=COLORS["ink"],
        font=(FONT, 15, "bold"),
    ).pack(anchor="w", padx=10, pady=(0, 8))
    return card


def _snapshot_text(snapshot: dict[str, Any], key: str) -> str:
    values: list[str] = []
    for member in snapshot.get("members") or []:
        if not isinstance(member, dict):
            continue
        if key == "job":
            value = member.get("jobName") or member.get("job")
            if value:
                values.append(f"{member.get('name', '未知')}:{value}")
        elif key == "member":
            value = member.get("name") or member.get("memberName")
            if value:
                values.append(str(value))
        elif key in {"personalSkills", "jobSkills"}:
            names = []
            for skill in member.get(key) or []:
                if isinstance(skill, dict):
                    names.append(
                        str(skill.get("name") or skill.get("skillName") or "未知")
                    )
            if names:
                values.append(f"{member.get('name', '未知')}:{'、'.join(names)}")
    return "；".join(values) or "无"


def _treasure_text(snapshot: dict[str, Any]) -> str:
    names = []
    for item in snapshot.get("treasures") or []:
        if isinstance(item, dict):
            names.append(str(item.get("treasureName") or item.get("name") or "未知"))
            for value in item.get("setNames") or item.get("setIds") or []:
                names.append(str(value))
    return "、".join(names) or "无"


def _treasure_property_text(snapshot: dict[str, Any]) -> str:
    values: list[str] = []
    for item in snapshot.get("treasures") or []:
        if not isinstance(item, dict):
            continue
        for prop in item.get("properties") or []:
            if isinstance(prop, dict):
                name = prop.get("propertyName") or prop.get("name")
            else:
                name = prop
            if name:
                values.append(str(name))
    return "、".join(values) or "无"


def show_statistics_window(
    parent: tk.Misc,
    repository: StatisticsRepository,
    *,
    current_run_id: str | None = None,
    current_round_id: int | None = None,
    current_rule_hash: str | None = None,
) -> None:
    if current_round_id is None:
        current_round_id = repository.latest_round_id(current_run_id)
    dialog = tk.Toplevel(parent)
    dialog.title("统计")
    dialog.minsize(1000, 680)
    dialog.transient(parent)
    dialog.configure(bg=COLORS["page"])
    dialog.bind(
        "<Button-1>",
        lambda event: _release_entry_focus(dialog, event),
        add="+",
    )
    _center(dialog, parent, 1280, 840)
    style = ttk.Style(dialog)
    style.configure(
        "Statistics.TNotebook",
        background=COLORS["page"],
        borderwidth=0,
        tabmargins=(0, 0, 0, 0),
    )
    style.configure(
        "Statistics.TNotebook.Tab",
        background="#E9EDF2",
        foreground=COLORS["chart_secondary"],
        padding=(16, 8),
        font=(FONT, 9),
        borderwidth=0,
    )
    style.map(
        "Statistics.TNotebook.Tab",
        background=[("selected", COLORS["surface"])],
        foreground=[("selected", COLORS["blue"])],
        font=[("selected", (FONT, 9, "bold"))],
    )
    style.configure(
        "Statistics.Treeview",
        rowheight=28,
        background=COLORS["surface"],
        fieldbackground=COLORS["surface"],
        foreground=COLORS["ink"],
        borderwidth=0,
    )
    style.configure(
        "Statistics.Treeview.Heading",
        background="#EEF2F6",
        foreground=COLORS["chart_text"],
        font=(FONT, 9, "bold"),
        relief="flat",
    )

    metric_var = tk.StringVar(value="全部")
    mode_var = tk.StringVar(value="全部")
    rule_var = tk.StringVar(value="全部规则")
    time_var = tk.StringVar(value="全部时间")
    custom_after_var = tk.StringVar()
    custom_before_var = tk.StringVar()
    status_var = tk.StringVar(value="正在加载统计数据…")
    trend_metric_var = tk.StringVar(value="合格数")
    job_member_var = tk.StringVar()
    job_target_var = tk.StringVar()
    skill_member_var = tk.StringVar()
    skill_target_var = tk.StringVar()
    job_skill_member_var = tk.StringVar()
    job_skill_target_var = tk.StringVar()
    treasure_item_var = tk.StringVar()
    treasure_property_var = tk.StringVar()
    detail_filter: dict[str, str] = {}
    detail_page = 0
    detail_page_size = 100
    render_after_id: str | None = None

    header = tk.Frame(dialog, bg=COLORS["page"], padx=16, pady=12)
    header.pack(fill="x")
    title_holder = tk.Frame(header, bg=COLORS["page"])
    title_holder.pack(side="left")
    title_icon = _lucide_icon(
        title_holder,
        "chart-bar",
        color=COLORS["blue"],
        size=22,
    )
    title_icon_label = tk.Label(
        title_holder,
        image=title_icon,
        bg=COLORS["page"],
    )
    title_icon_label._lucide_image = title_icon
    title_icon_label.pack(side="left", padx=(0, 8), anchor="n")
    title_text = tk.Frame(title_holder, bg=COLORS["page"])
    title_text.pack(side="left")
    tk.Label(
        title_text,
        text="结果统计",
        bg=COLORS["page"],
        fg=COLORS["ink"],
        font=(FONT, 17, "bold"),
    ).pack(anchor="w")
    tk.Label(
        title_text,
        textvariable=status_var,
        bg=COLORS["page"],
        fg=COLORS["muted"],
        font=(FONT, 9),
        anchor="w",
    ).pack(anchor="w", pady=(2, 0))
    action_bar = tk.Frame(header, bg=COLORS["page"])
    action_bar.pack(side="right", anchor="n")

    controls = tk.Frame(
        dialog,
        bg=COLORS["surface"],
        padx=12,
        pady=8,
        highlightbackground=COLORS["border"],
        highlightthickness=1,
    )
    controls.pack(fill="x", padx=16, pady=(0, 10))
    filter_grid = tk.Frame(controls, bg=COLORS["surface"])
    filter_grid.pack(fill="x")
    for column in range(4):
        filter_grid.columnconfigure(
            column,
            weight=1,
            uniform="statistics_filters",
        )
    context_bar = tk.Frame(controls, bg=COLORS["surface"])
    context_bar.pack(fill="x", pady=(8, 0))
    rule_options = repository.list_rule_options()
    member_options = repository.list_member_options()
    rule_name_counts: dict[str, int] = {}
    rule_display_to_hash: dict[str, str] = {}
    for item in rule_options:
        name = str(item.get("rule_name") or "未命名规则")
        rule_name_counts[name] = rule_name_counts.get(name, 0) + 1
        number = rule_name_counts[name]
        display = name if number == 1 else f"{name}（历史版本 {number}）"
        rule_display_to_hash[display] = str(item["rule_snapshot_hash"])
    hash_to_rule_display = {
        value: key for key, value in rule_display_to_hash.items()
    }

    def open_custom_time() -> None:
        chooser = tk.Toplevel(dialog)
        chooser.title("自定义时间范围")
        chooser.transient(dialog)
        chooser.configure(bg=COLORS["page"])
        _center(chooser, dialog, 470, 220)
        today = dt.date.today()
        pending_after_var = tk.StringVar(
            value=custom_after_var.get().strip()
            or today.replace(day=1).isoformat()
        )
        pending_before_var = tk.StringVar(
            value=custom_before_var.get().strip()
            or (today + dt.timedelta(days=1)).isoformat()
        )
        tk.Label(
            chooser,
            text="点击选择开始和结束日期；结束日期不包含当天。",
            bg=COLORS["page"],
            fg=COLORS["muted"],
        ).pack(anchor="w", padx=16, pady=(14, 8))
        form = tk.Frame(chooser, bg=COLORS["page"])
        form.pack(fill="x", padx=16)
        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)

        def date_field(
            column: int,
            label: str,
            variable: tk.StringVar,
        ) -> None:
            field = tk.Frame(form, bg=COLORS["page"])
            field.grid(
                row=0,
                column=column,
                sticky="ew",
                padx=(0, 8) if column == 0 else (8, 0),
            )
            tk.Label(
                field,
                text=label,
                bg=COLORS["page"],
                fg=COLORS["muted"],
                font=(FONT, 9),
            ).pack(anchor="w", pady=(0, 4))
            calendar_icon = _lucide_icon(
                field,
                "calendar",
                color=COLORS["muted"],
                size=15,
            )
            button = tk.Button(
                field,
                textvariable=variable,
                image=calendar_icon,
                compound="left",
                anchor="w",
                relief="flat",
                borderwidth=0,
                highlightthickness=1,
                highlightbackground=COLORS["border"],
                highlightcolor=COLORS["blue"],
                bg=COLORS["surface"],
                fg=COLORS["ink"],
                activebackground=COLORS["blue_soft"],
                activeforeground=COLORS["blue"],
                font=(FONT, 10),
                cursor="hand2",
                padx=10,
                pady=7,
            )
            button._calendar_icon = calendar_icon
            button.configure(
                command=lambda: _show_calendar(
                    chooser,
                    title=f"选择{label}",
                    initial=dt.date.fromisoformat(variable.get()),
                    on_select=lambda value: variable.set(value.isoformat()),
                )
            )
            button.pack(fill="x")

        date_field(0, "开始日期", pending_after_var)
        date_field(1, "结束日期", pending_before_var)

        def apply() -> None:
            try:
                after = dt.date.fromisoformat(pending_after_var.get())
                before = dt.date.fromisoformat(pending_before_var.get())
                if after >= before:
                    raise ValueError
            except ValueError:
                messagebox.showerror(
                    "时间范围错误",
                    "开始日期必须早于结束日期。",
                    parent=chooser,
                )
                return
            custom_after_var.set(after.isoformat())
            custom_before_var.set(before.isoformat())
            chooser.destroy()
            schedule_render()

        actions = tk.Frame(chooser, bg=COLORS["page"])
        actions.pack(fill="x", padx=16, pady=18)
        _icon_button(
            actions,
            text="取消",
            icon="x",
            command=chooser.destroy,
        ).pack(
            side="right", padx=(8, 0)
        )
        _icon_button(
            actions,
            text="应用",
            icon="check",
            command=apply,
            foreground="#FFFFFF",
            background=COLORS["blue"],
        ).pack(side="right")

    def handle_filter_change(variable: tk.StringVar) -> None:
        if variable is time_var and time_var.get() == "自定义":
            open_custom_time()
            return
        reset_page_and_render()

    options = (
        (
            "统计内容",
            metric_var,
            ("全部", "合格", "不合格", "其他"),
        ),
        ("随机模式", mode_var, ("全部", "3人", "7人")),
        (
            "规则配置",
            rule_var,
            ("全部规则",) + tuple(rule_display_to_hash),
        ),
        ("时间", time_var, ("全部时间", "今天", "本周", "本月", "自定义")),
    )
    pickers: list[tk.Menubutton] = []
    for index, (label, variable, values) in enumerate(options):
        field = tk.Frame(filter_grid, bg=COLORS["surface"])
        field.grid(
            row=0,
            column=index,
            sticky="ew",
            padx=(0 if index == 0 else 8, 0),
        )
        tk.Label(
            field,
            text=label,
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=(FONT, 9),
        ).pack(anchor="w")
        picker = _choice_picker(
            field,
            variable,
            values,
            command=lambda selected=variable: handle_filter_change(selected),
            requested_width=16,
        )
        picker.pack(fill="x", pady=(3, 0))
        pickers.append(picker)
    clear_filter_button = _icon_button(
        context_bar,
        text="清除图表筛选",
        icon="filter-x",
        command=lambda: clear_detail_filter(),
    )

    notebook = ttk.Notebook(dialog, style="Statistics.TNotebook")
    notebook.pack(fill="both", expand=True, padx=16, pady=(0, 14))
    overview = _scrollable_tab(notebook, "总览")
    jobs = _scrollable_tab(notebook, "兵种分布")
    skills = _scrollable_tab(notebook, "特技分布")
    treasures = _scrollable_tab(notebook, "宝物分布")

    def build_filters() -> StatisticsFilters:
        mode = {"3人": "three", "7人": "seven"}.get(mode_var.get(), "all")
        content = metric_var.get()
        metric = "attempts" if content == "其他" else "completed"
        content_status = {
            "合格": "accepted",
            "不合格": "rejected",
        }.get(content)
        status_group = "other" if content == "其他" else None
        selected_rule_hash = rule_display_to_hash.get(rule_var.get())
        rule_mode = "selected" if selected_rule_hash else "all_summary"
        started_after = None
        started_before = None
        if time_var.get() != "全部时间":
            today = dt.datetime.now().astimezone().date()
            if time_var.get() == "自定义":
                started_after = (
                    dt.datetime.fromisoformat(custom_after_var.get())
                    .astimezone()
                    .isoformat(timespec="seconds")
                    if custom_after_var.get().strip()
                    else None
                )
                started_before = (
                    dt.datetime.fromisoformat(custom_before_var.get())
                    .astimezone()
                    .isoformat(timespec="seconds")
                    if custom_before_var.get().strip()
                    else None
                )
            elif time_var.get() == "今天":
                first = today
            elif time_var.get() == "本周":
                first = today - dt.timedelta(days=today.weekday())
            else:
                first = today.replace(day=1)
            if time_var.get() != "自定义":
                started_after = dt.datetime.combine(
                    first,
                    dt.time.min,
                ).astimezone().isoformat(timespec="seconds")
                started_before_date = today + dt.timedelta(days=1)
                started_before = dt.datetime.combine(
                    started_before_date,
                    dt.time.min,
                ).astimezone().isoformat(timespec="seconds")
        if detail_filter.get("kind") == "date":
            chart_date = dt.date.fromisoformat(detail_filter["value"])
            started_after = dt.datetime.combine(
                chart_date,
                dt.time.min,
            ).astimezone().isoformat(timespec="seconds")
            started_before = dt.datetime.combine(
                chart_date + dt.timedelta(days=1),
                dt.time.min,
            ).astimezone().isoformat(timespec="seconds")
        return StatisticsFilters(
            scope="history",
            metric=metric,
            mode=mode,
            rule_mode=rule_mode,
            rule_hashes=(
                (selected_rule_hash,)
                if selected_rule_hash
                else ()
            ),
            current_rule_hash=current_rule_hash,
            run_id=None,
            round_id=None,
            member_id=detail_filter.get("member_id"),
            started_after=started_after,
            started_before=started_before,
            status=detail_filter.get("status") or content_status,
            status_group=status_group,
            failure_reason=detail_filter.get("failure_reason"),
            attempt_id=(
                int(detail_filter["attempt_id"])
                if detail_filter.get("attempt_id")
                else None
            ),
            content_kind=detail_filter.get("content_kind"),
            content_value=detail_filter.get("content_value"),
        )

    def clear(frame: tk.Misc) -> None:
        for child in frame.winfo_children():
            child.destroy()

    def filtered_details(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return rows

    def set_detail_filter(kind: str, row: dict[str, Any]) -> None:
        value = str(
            row.get("value")
            if row.get("value") not in {None, ""}
            else row.get("label") or ""
        )
        if value:
            detail_filter.clear()
            detail_filter.update(kind=kind, value=value)
            if kind == "status":
                detail_filter["status"] = value
            elif kind == "failure":
                detail_filter["failure_reason"] = value
            elif kind == "attempt":
                detail_filter["attempt_id"] = value
            elif kind == "member":
                detail_filter["member_id"] = value
            elif kind not in {"date"}:
                detail_filter["content_kind"] = kind
                detail_filter["content_value"] = value
            reset_page_and_render()

    def clear_detail_filter() -> None:
        detail_filter.clear()
        reset_page_and_render()

    def reset_page_and_render() -> None:
        nonlocal detail_page
        detail_page = 0
        schedule_render()

    def change_detail_page(delta: int) -> None:
        nonlocal detail_page
        detail_page = max(0, detail_page + delta)
        schedule_render()

    def open_snapshot_image(snapshot: dict[str, Any]) -> None:
        for key in ("resultImagePath", "resultGridPath"):
            value = snapshot.get(key)
            if value and Path(value).is_file():
                os.startfile(value)
                return
        messagebox.showinfo("结果图", "当前记录没有可用的结果图文件。", parent=dialog)

    def render_tree(
        frame: tk.Misc,
        rows: list[dict[str, Any]],
        *,
        total: int,
        page: int,
    ) -> None:
        holder = tk.Frame(frame, bg=COLORS["surface"])
        holder.pack(fill="both", expand=True)
        columns = (
            "time", "round", "slot", "member", "job", "personal",
            "job_skill", "treasure", "property", "status", "attempts",
        )
        tree = ttk.Treeview(
            holder,
            columns=columns,
            show="headings",
            style="Statistics.Treeview",
        )
        headings = {
            "time": "运行时间", "round": "轮次", "slot": "存档",
            "member": "武将", "job": "兵种", "personal": "个人天赋",
            "job_skill": "兵种技能", "treasure": "宝物",
            "property": "宝物特性", "status": "最终状态",
            "attempts": "尝试",
        }
        widths = {
            "time": 145, "round": 55, "slot": 55, "member": 220,
            "job": 220, "personal": 240, "job_skill": 240,
            "treasure": 180, "property": 200, "status": 90,
            "attempts": 55,
        }
        vertical = ttk.Scrollbar(holder, orient="vertical", command=tree.yview)
        horizontal = ttk.Scrollbar(
            holder,
            orient="horizontal",
            command=tree.xview,
        )
        tree.configure(
            yscrollcommand=vertical.set,
            xscrollcommand=horizontal.set,
        )
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        for column in columns:
            tree.heading(column, text=headings[column])
            tree.column(column, width=widths[column], stretch=False)
        for row in rows:
            snapshot = row.get("snapshot") or {}
            item_id = tree.insert(
                "",
                "end",
                values=(
                    str(row.get("run_started_at") or "")[:19],
                    row.get("round_number", ""),
                    row.get("slot", ""),
                    _snapshot_text(snapshot, "member"),
                    _snapshot_text(snapshot, "job"),
                    _snapshot_text(snapshot, "personalSkills"),
                    _snapshot_text(snapshot, "jobSkills"),
                    _treasure_text(snapshot),
                    _treasure_property_text(snapshot),
                    row.get("status", ""),
                    row.get("attempt_number", ""),
                ),
            )
            tree.item(item_id, tags=(str(row.get("attempt_id", "")),))

        def open_selected(_event=None) -> None:
            selection = tree.selection()
            if not selection:
                return
            tags = tree.item(selection[0], "tags")
            for row in rows:
                if tags and str(row.get("attempt_id")) == tags[0]:
                    show_result_snapshot_detail(dialog, row.get("snapshot") or {})
                    return

        def image_selected() -> None:
            selection = tree.selection()
            if not selection:
                return
            tags = tree.item(selection[0], "tags")
            for row in rows:
                if tags and str(row.get("attempt_id")) == tags[0]:
                    open_snapshot_image(row.get("snapshot") or {})
                    return

        tree.bind("<Double-1>", open_selected)
        _icon_button(
            frame,
            text="打开结果图",
            icon="image",
            command=image_selected,
        ).pack(side="right", pady=(6, 0))
        page_count = max(1, (total + detail_page_size - 1) // detail_page_size)
        pager = tk.Frame(frame, bg=COLORS["surface"])
        pager.pack(side="left", fill="x", pady=(6, 0))
        _icon_button(
            pager,
            text="上一页",
            icon="chevron-left",
            command=lambda: change_detail_page(-1),
            state="normal" if page > 0 else "disabled",
        ).pack(side="left")
        tk.Label(
            pager,
            text=f"第 {page + 1}/{page_count} 页，共 {total} 条",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
        ).pack(side="left", padx=8)
        _icon_button(
            pager,
            text="下一页",
            icon="chevron-right",
            command=lambda: change_detail_page(1),
            state="normal" if page + 1 < page_count else "disabled",
        ).pack(side="left")

    def render_grouped(
        frame: tk.Misc,
        rows: list[dict[str, Any]],
        *,
        title: str,
        subtitle: str = "",
        columns: int = 1,
        searchable: bool = True,
        picker: tuple[
            str,
            tk.StringVar,
            tuple[str, ...],
            Callable[[], None],
        ]
        | None = None,
    ) -> None:
        if not rows:
            _ranked_distribution(
                frame,
                [],
                title=title,
                subtitle=subtitle,
                columns=columns,
                searchable=searchable,
                picker=picker,
            ).pack(fill="x", padx=12, pady=12)
            return
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(str(row.get("rule_snapshot_hash") or ""), []).append(row)
        for rule_hash, group_rows in grouped.items():
            group_title = title
            if rule_hash:
                group_title += f" · {hash_to_rule_display.get(rule_hash, rule_hash)}"
            _ranked_distribution(
                frame,
                group_rows,
                title=group_title,
                subtitle=subtitle,
                columns=columns,
                searchable=searchable,
                picker=picker,
            ).pack(fill="x", padx=12, pady=6)

    def distribution_grid(frame: tk.Misc) -> tk.Frame:
        grid = tk.Frame(frame, bg=COLORS["page"])
        grid.pack(fill="both", expand=True, padx=6, pady=(4, 12))
        for column in range(2):
            grid.columnconfigure(
                column,
                weight=1,
                uniform="statistics_distribution_columns",
            )
        return grid

    def render_distribution_panel(
        grid: tk.Misc,
        *,
        row: int,
        column: int,
        rows: list[dict[str, Any]],
        title: str,
        subtitle: str,
        picker: tuple[
            str,
            tk.StringVar,
            tuple[str, ...],
            Callable[[], None],
        ]
        | None = None,
        columnspan: int = 1,
        columns: int = 1,
        searchable: bool = True,
    ) -> tk.Frame:
        panel = tk.Frame(grid, bg=COLORS["page"])
        panel.grid(
            row=row,
            column=column,
            columnspan=columnspan,
            sticky="nsew",
            padx=6,
            pady=6,
        )
        render_grouped(
            panel,
            rows,
            title=title,
            subtitle=subtitle,
            columns=columns,
            searchable=searchable,
            picker=picker,
        )
        return panel

    def create_distribution_panel(
        grid: tk.Misc,
        *,
        row: int,
        column: int,
        columnspan: int = 1,
    ) -> tk.Frame:
        panel = tk.Frame(grid, bg=COLORS["page"])
        panel.grid(
            row=row,
            column=column,
            columnspan=columnspan,
            sticky="nsew",
            padx=6,
            pady=6,
        )
        return panel

    def member_id_for_name(name: str) -> str | None:
        for item in member_options:
            if item["member_name"] == name:
                return str(item["member_id"])
        return None

    def option_map(
        rows: list[dict[str, Any]],
    ) -> tuple[tuple[str, ...], dict[str, str]]:
        values: list[str] = []
        mapping: dict[str, str] = {}
        counts: dict[str, int] = {}
        for row in rows:
            label = str(row.get("label") or "未知")
            counts[label] = counts.get(label, 0) + 1
            display = (
                label
                if counts[label] == 1
                else f"{label}（{counts[label]}）"
            )
            values.append(display)
            mapping[display] = str(row.get("value") or "")
        return tuple(values), mapping

    def schedule_render(delay: int = 60) -> None:
        nonlocal render_after_id
        if render_after_id is not None:
            try:
                dialog.after_cancel(render_after_id)
            except tk.TclError:
                pass

        def run() -> None:
            nonlocal render_after_id
            render_after_id = None
            if dialog.winfo_exists():
                render()

        render_after_id = dialog.after(delay, run)

    def render() -> None:
        nonlocal detail_page
        clear_filter_button.pack_forget()
        if detail_filter:
            clear_filter_button.pack(side="right")
        filters = build_filters()
        selected_tab = notebook.select()
        active_tab = {
            str(overview.master.master): "overview",
            str(jobs.master.master): "jobs",
            str(skills.master.master): "skills",
            str(treasures.master.master): "treasures",
        }.get(selected_tab, "overview")
        if active_tab == "jobs":
            clear(jobs)
            job_rows = repository.get_job_distribution(filters)
            job_rows = _include_zero_rows(
                job_rows,
                list(job_catalog_rows()),
            )
            job_names, job_ids = option_map(job_rows)
            member_names = tuple(
                str(item["member_name"]) for item in member_options
            )
            if member_names and job_member_var.get() not in member_names:
                job_member_var.set(member_names[0])
            if job_names and job_target_var.get() not in job_names:
                job_target_var.set(job_names[0])
            grid = distribution_grid(jobs)
            render_distribution_panel(
                grid,
                row=0,
                column=0,
                rows=job_rows,
                title="兵种出现分布",
                subtitle="汇总所有武将位置随机出的兵种次数与占比。",
                columnspan=2,
                columns=2,
            )
            member_panel = create_distribution_panel(
                grid,
                row=1,
                column=0,
            )
            assigned_panel = create_distribution_panel(
                grid,
                row=1,
                column=1,
            )

            def refresh_member_panel() -> None:
                clear(member_panel)
                selected_member = job_member_var.get()
                member_id = member_id_for_name(selected_member)
                member_rows = (
                    repository.get_job_distribution(
                        replace(filters, member_id=member_id)
                    )
                    if member_id
                    else []
                )
                render_grouped(
                    member_panel,
                    member_rows,
                    title=f"{selected_member or '指定武将'}的兵种分布",
                    subtitle="查看该武将在统计结果中被分配到的兵种。",
                    searchable=False,
                    picker=(
                        "武将",
                        job_member_var,
                        member_names,
                        refresh_member_panel,
                    ),
                )

            def refresh_assigned_panel() -> None:
                clear(assigned_panel)
                selected_job = job_target_var.get()
                job_id = job_ids.get(selected_job)
                assigned_rows = (
                    repository.get_members_for_job(filters, job_id)
                    if job_id
                    else []
                )
                render_grouped(
                    assigned_panel,
                    assigned_rows,
                    title=(
                        f"{selected_job or '指定兵种'}"
                        "分配给不同武将的分布"
                    ),
                    subtitle="查看该兵种在不同武将之间的分配情况。",
                    picker=(
                        "兵种",
                        job_target_var,
                        job_names,
                        refresh_assigned_panel,
                    ),
                )

            refresh_member_panel()
            refresh_assigned_panel()
            return
        if active_tab == "skills":
            clear(skills)
            skill_notebook = ttk.Notebook(
                skills,
                style="Statistics.TNotebook",
            )
            skill_notebook.pack(fill="both", expand=True, padx=12, pady=10)

            def render_skill_tab(
                scope: str,
                scope_label: str,
            ) -> tk.Frame:
                tab = tk.Frame(skill_notebook, bg=COLORS["page"])
                skill_rows = repository.get_skill_distribution(
                    filters,
                    scope=scope,
                )
                skill_rows = _include_zero_rows(
                    skill_rows,
                    list(skill_catalog_rows()),
                )
                target_skill_rows = [
                    row
                    for row in skill_rows
                    if str(row.get("label") or "") != "无"
                ]
                skill_names, skill_ids = option_map(target_skill_rows)
                member_names = tuple(
                    str(item["member_name"]) for item in member_options
                )
                member_var = (
                    skill_member_var
                    if scope == "personal"
                    else job_skill_member_var
                )
                target_var = (
                    skill_target_var
                    if scope == "personal"
                    else job_skill_target_var
                )
                if member_names and member_var.get() not in member_names:
                    member_var.set(member_names[0])
                if skill_names and target_var.get() not in skill_names:
                    target_var.set(skill_names[0])
                grid = distribution_grid(tab)
                render_distribution_panel(
                    grid,
                    row=0,
                    column=0,
                    rows=skill_rows,
                    title=f"{scope_label}出现分布",
                    subtitle=(
                        f"汇总所有武将位置出现的{scope_label}，多项特技分别计数。"
                    ),
                    columnspan=2,
                    columns=2,
                )
                member_panel = create_distribution_panel(
                    grid,
                    row=1,
                    column=0,
                )
                assigned_panel = create_distribution_panel(
                    grid,
                    row=1,
                    column=1,
                )

                def refresh_member_panel() -> None:
                    clear(member_panel)
                    selected_member = member_var.get()
                    member_id = member_id_for_name(selected_member)
                    member_rows = (
                        repository.get_skill_distribution(
                            replace(filters, member_id=member_id),
                            scope=scope,
                        )
                        if member_id
                        else []
                    )
                    render_grouped(
                        member_panel,
                        member_rows,
                        title=(
                            f"{selected_member or '指定武将'}"
                            f"的{scope_label}分布"
                        ),
                        subtitle=f"查看该武将被分配到的{scope_label}。",
                        searchable=False,
                        picker=(
                            "武将",
                            member_var,
                            member_names,
                            refresh_member_panel,
                        ),
                    )

                def refresh_assigned_panel() -> None:
                    clear(assigned_panel)
                    selected_skill = target_var.get()
                    skill_id = skill_ids.get(selected_skill)
                    assigned_rows = (
                        repository.get_members_for_skill(
                            filters,
                            scope=scope,
                            skill_id=skill_id,
                        )
                        if skill_id
                        else []
                    )
                    render_grouped(
                        assigned_panel,
                        assigned_rows,
                        title=(
                            f"{selected_skill or '指定特技'}"
                            "分配给不同武将的分布"
                        ),
                        subtitle="查看该特技在不同武将之间的分配情况。",
                        picker=(
                            "特技",
                            target_var,
                            skill_names,
                            refresh_assigned_panel,
                        ),
                    )

                refresh_member_panel()
                refresh_assigned_panel()
                return tab

            personal_tab = render_skill_tab("personal", "个人天赋")
            job_skill_tab = render_skill_tab("job", "兵种技能")
            skill_notebook.add(personal_tab, text="个人")
            skill_notebook.add(job_skill_tab, text="兵种")
            return
        if active_tab == "treasures":
            clear(treasures)
            property_rows = repository.get_treasure_property_distribution(
                filters
            )
            property_rows = _include_zero_rows(
                property_rows,
                list(treasure_property_catalog_rows()),
            )
            treasure_rows = repository.get_treasure_distribution(filters)
            target_property_rows = [
                row
                for row in property_rows
                if str(row.get("label") or "") != "无"
            ]
            property_names, property_ids = option_map(target_property_rows)
            treasure_names, treasure_ids = option_map(treasure_rows)
            if (
                treasure_names
                and treasure_item_var.get() not in treasure_names
            ):
                treasure_item_var.set(treasure_names[0])
            if (
                property_names
                and treasure_property_var.get() not in property_names
            ):
                treasure_property_var.set(property_names[0])
            grid = distribution_grid(treasures)
            render_distribution_panel(
                grid,
                row=0,
                column=0,
                rows=property_rows,
                title="宝物特性出现分布",
                subtitle="汇总所有宝物被分配到的特性次数与占比。",
                columnspan=2,
                columns=2,
            )
            treasure_panel = create_distribution_panel(
                grid,
                row=1,
                column=0,
            )
            assigned_panel = create_distribution_panel(
                grid,
                row=1,
                column=1,
            )

            def refresh_treasure_panel() -> None:
                clear(treasure_panel)
                selected_treasure = treasure_item_var.get()
                treasure_id = treasure_ids.get(selected_treasure)
                property_rows_for_treasure = (
                    repository.get_properties_for_treasure(
                        filters,
                        treasure_id,
                    )
                    if treasure_id
                    else []
                )
                render_grouped(
                    treasure_panel,
                    property_rows_for_treasure,
                    title=(
                        f"{selected_treasure or '指定宝物'}的特性分布"
                    ),
                    subtitle="查看该宝物在统计结果中被分配到的特性。",
                    searchable=False,
                    picker=(
                        "宝物",
                        treasure_item_var,
                        treasure_names,
                        refresh_treasure_panel,
                    ),
                )

            def refresh_assigned_panel() -> None:
                clear(assigned_panel)
                selected_property = treasure_property_var.get()
                property_id = property_ids.get(selected_property)
                assigned_rows = (
                    repository.get_treasures_for_property(
                        filters,
                        property_id,
                    )
                    if property_id
                    else []
                )
                render_grouped(
                    assigned_panel,
                    assigned_rows,
                    title=(
                        f"{selected_property or '指定特性'}"
                        "分配给不同宝物的分布"
                    ),
                    subtitle="查看该特性在不同宝物之间的分配情况。",
                    picker=(
                        "特性",
                        treasure_property_var,
                        property_names,
                        refresh_assigned_panel,
                    ),
                )

            refresh_treasure_panel()
            refresh_assigned_panel()
            return
        summary = repository.get_summary(filters)
        category_filters = replace(
            filters,
            status=None,
            status_group=None,
        )
        accepted_count = int(
            repository.get_summary(
                replace(
                    category_filters,
                    metric="completed",
                    status="accepted",
                )
            ).get("attempt_count", 0)
        )
        rejected_count = int(
            repository.get_summary(
                replace(
                    category_filters,
                    metric="completed",
                    status="rejected",
                )
            ).get("attempt_count", 0)
        )
        other_count = int(
            repository.get_summary(
                replace(
                    category_filters,
                    metric="attempts",
                    status_group="other",
                )
            ).get("attempt_count", 0)
        )
        scored_count = accepted_count + rejected_count
        clear(overview)
        metric_grid = tk.Frame(overview, bg=COLORS["page"])
        metric_grid.pack(fill="x", padx=12, pady=12)
        for column in range(4):
            metric_grid.columnconfigure(
                column,
                weight=1,
                uniform="statistics_metrics",
            )
        cards = (
            ("全部", scored_count),
            ("合格", accepted_count),
            ("不合格", rejected_count),
            ("其他", other_count),
        )
        for index, (label, value) in enumerate(cards):
            _metric_card(
                metric_grid,
                label,
                value,
                row=0,
                column=index,
                accent=False,
            )
        if filters.rule_mode == "all_grouped":
            grouped_holder = tk.Frame(overview, bg=COLORS["surface"])
            grouped_holder.pack(fill="x", padx=12, pady=(0, 10))
            tk.Label(
                grouped_holder,
                text="规则分组汇总",
                bg=COLORS["surface"],
                fg=COLORS["ink"],
                font=(FONT, 11, "bold"),
                anchor="w",
            ).pack(fill="x", padx=10, pady=(8, 4))
            grouped_rows = repository.get_grouped_summary(filters)
            for grouped in grouped_rows:
                rate = grouped.get("qualification_rate")
                rate_text = f"{rate:.1%}" if rate is not None else "-"
                label = (
                    f"{grouped.get('rule_name') or '未知规则'} · "
                    f"{str(grouped.get('rule_snapshot_hash') or '')[:12]}"
                )
                tk.Label(
                    grouped_holder,
                    text=(
                        f"{label}  存档 {grouped.get('save_count', 0)}  "
                        f"合格 {grouped.get('accepted', 0)}  "
                        f"不合格 {grouped.get('rejected', 0)}  "
                        f"合格率 {rate_text}"
                    ),
                    bg=COLORS["surface"],
                    fg=COLORS["muted"],
                    anchor="w",
                    font=(FONT, 9),
                ).pack(fill="x", padx=10, pady=2)
        chart_row = tk.Frame(overview, bg=COLORS["page"])
        chart_row.pack(fill="x", padx=12)
        for column in range(2):
            chart_row.columnconfigure(
                column,
                weight=1,
                uniform="statistics_overview_charts",
            )
        _pie_chart(
            chart_row,
            [
                {"label": "合格", "value": "accepted", "count": accepted_count},
                {"label": "不合格", "value": "rejected", "count": rejected_count},
                {"label": "其他", "value": "other", "count": other_count},
            ],
            title="结果分布",
        ).grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        trend_options = {
            "已评分": ("completed", "已评分"),
            "合格数": ("accepted", "合格"),
            "不合格数": ("rejected", "不合格"),
            "合格率": ("qualification_rate", "合格率"),
            "平均尝试次数": ("average_attempts", "平均尝试"),
        }
        trend_rows = repository.get_trend(filters)
        trend_panel = tk.Frame(chart_row, bg=COLORS["page"])
        trend_panel.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        def refresh_trend_panel() -> None:
            clear(trend_panel)
            trend_field, trend_label = trend_options.get(
                trend_metric_var.get(),
                ("accepted", "合格"),
            )
            _line_chart(
                trend_panel,
                trend_rows,
                title=f"历史趋势 · 每日{trend_label}",
                value_field=trend_field,
                value_label=trend_label,
                x_label="日期",
                picker=(
                    trend_metric_var,
                    tuple(trend_options),
                    refresh_trend_panel,
                ),
            ).pack(fill="both", expand=True)

        refresh_trend_panel()
        details = tk.Frame(overview, bg=COLORS["surface"])
        details.pack(fill="both", expand=True, padx=12, pady=12)
        detail_total = repository.count_detail_rows(filters)
        page_count = max(
            1,
            (detail_total + detail_page_size - 1) // detail_page_size,
        )
        detail_page = min(detail_page, page_count - 1)
        render_tree(
            details,
            repository.get_detail_rows(
                filters,
                limit=detail_page_size,
                offset=detail_page * detail_page_size,
            ),
            total=detail_total,
            page=detail_page,
        )
        report = repository.validate_statistics(filters)
        recognition = repository.get_recognition_summary(filters)
        rule_notice = {
            "current": "当前规则",
            "selected": "指定规则",
            "all_grouped": "全部规则分组",
            "all_summary": "全部规则",
        }[filters.rule_mode]
        status_var.set(
            f"{rule_notice} · {summary.get('rule_count', 0)}规则 · "
            f"{summary.get('save_count', 0)}存档 · "
            f"平均{summary.get('average_attempts', 0):.2f}次 · "
            f"识别{recognition['known_positions']}/"
            f"{recognition['total_positions']}"
            + (" · 已筛选图表明细" if detail_filter else "")
            + (
                " · 数据不完整：" + "；".join(report.issues)
                if not report.valid
                else ""
            )
        )

    def export_csv() -> None:
        target = filedialog.asksaveasfilename(
            parent=dialog,
            title="导出统计 CSV",
            defaultextension=".csv",
            filetypes=(("CSV 文件", "*.csv"),),
        )
        if target:
            repository.export_csv(build_filters(), Path(target))
            messagebox.showinfo("导出完成", "CSV 已导出。", parent=dialog)

    def export_json() -> None:
        target = filedialog.asksaveasfilename(
            parent=dialog,
            title="导出统计 JSON",
            defaultextension=".json",
            filetypes=(("JSON 文件", "*.json"),),
        )
        if target:
            repository.export_json(build_filters(), Path(target))
            messagebox.showinfo("导出完成", "JSON 已导出。", parent=dialog)

    def export_png() -> None:
        target = filedialog.asksaveasfilename(
            parent=dialog,
            title="导出统计 PNG",
            defaultextension=".png",
            filetypes=(("PNG 文件", "*.png"),),
        )
        if not target:
            return
        try:
            from PIL import ImageGrab

            dialog.update_idletasks()
            box = (
                dialog.winfo_rootx(),
                dialog.winfo_rooty(),
                dialog.winfo_rootx() + dialog.winfo_width(),
                dialog.winfo_rooty() + dialog.winfo_height(),
            )
            ImageGrab.grab(bbox=box).save(target)
        except Exception as exc:
            messagebox.showerror("导出失败", f"当前系统无法导出窗口图像：{exc}", parent=dialog)
            return
        messagebox.showinfo("导出完成", "PNG 已导出。", parent=dialog)

    def clear_statistics() -> None:
        if not messagebox.askyesno(
            "清空统计",
            "只隐藏统计历史，不删除存档、结果图或日志。确定继续吗？",
            parent=dialog,
        ):
            return
        repository.clear_statistics()
        schedule_render()

    def rebuild_statistics() -> None:
        repository.rebuild_statistics()
        schedule_render()

    def delete_run() -> None:
        runs = repository.history.list_runs(page_size=100)
        if not runs:
            messagebox.showinfo("删除运行", "没有可删除的运行记录。", parent=dialog)
            return
        chooser = tk.Toplevel(dialog)
        chooser.title("删除运行记录")
        chooser.transient(dialog)
        _center(chooser, dialog, 760, 430)
        listbox = tk.Listbox(chooser, selectmode="browse", font=(FONT, 9))
        listbox.pack(fill="both", expand=True, padx=14, pady=14)
        for item in runs:
            listbox.insert(
                "end",
                f"{item['started_at']} · {item['rule_name']} · "
                f"{item['mode']} · {item['id']}",
            )

        def confirm_delete() -> None:
            selection = listbox.curselection()
            if not selection:
                return
            run = runs[selection[0]]
            if not messagebox.askyesno(
                "确认删除",
                "只删除该运行的统计事实和历史快照，不删除游戏存档、结果图或日志。\n"
                "确定继续吗？",
                parent=chooser,
            ):
                return
            repository.delete_run(str(run["id"]))
            chooser.destroy()
            schedule_render()

        actions = tk.Frame(chooser)
        actions.pack(fill="x", padx=14, pady=(0, 14))
        _icon_button(
            actions,
            text="取消",
            icon="x",
            command=chooser.destroy,
        ).pack(
            side="right", padx=(8, 0)
        )
        _icon_button(
            actions,
            text="删除",
            icon="trash",
            command=confirm_delete,
            foreground=COLORS["red"],
        ).pack(side="right")

    _icon_button(
        action_bar,
        text="刷新",
        icon="refresh-cw",
        command=lambda: schedule_render(0),
        foreground="#FFFFFF",
        background=COLORS["blue"],
    ).pack(side="left")
    export_icon = _lucide_icon(
        action_bar,
        "download",
        color=COLORS["ink"],
    )
    export_button = tk.Menubutton(
        action_bar,
        text="导出",
        image=export_icon,
        compound="left",
        relief="flat",
        padx=12,
        pady=5,
        cursor="hand2",
    )
    export_button._lucide_image = export_icon
    export_menu = tk.Menu(export_button, tearoff=False)
    export_menu.add_command(label="当前窗口 PNG", command=export_png)
    export_menu.add_command(label="明细 CSV", command=export_csv)
    export_menu.add_command(label="完整数据 JSON", command=export_json)
    export_button.configure(menu=export_menu)
    export_button.pack(side="left", padx=(6, 0))
    manage_icon = _lucide_icon(
        action_bar,
        "database",
        color=COLORS["ink"],
    )
    manage_button = tk.Menubutton(
        action_bar,
        text="数据管理",
        image=manage_icon,
        compound="left",
        relief="flat",
        padx=12,
        pady=5,
        cursor="hand2",
    )
    manage_button._lucide_image = manage_icon
    manage_menu = tk.Menu(manage_button, tearoff=False)
    manage_menu.add_command(label="重建统计", command=rebuild_statistics)
    manage_menu.add_command(label="删除指定运行", command=delete_run)
    manage_menu.add_separator()
    manage_menu.add_command(label="清空统计", command=clear_statistics)
    manage_button.configure(menu=manage_menu)
    manage_button.pack(side="left", padx=(6, 0))
    clear_filter_button.configure(command=clear_detail_filter)
    notebook.bind(
        "<<NotebookTabChanged>>",
        lambda _event: schedule_render(20),
    )
    dialog.after_idle(lambda: schedule_render(0))
