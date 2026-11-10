"""Shared equipment layout for history and live score details."""
from __future__ import annotations
import tkinter as tk


def render_equipment_sections(parent, equipment: dict):
    from ccz_randomizer.ui.history import (
        COLORS, FONT, SPECIAL_COLORS, DETAIL_SPECIAL_MIN_WIDTH,
        DETAIL_EQUIPMENT_COLUMNS, _section_heading,
    )
    lower = tk.Frame(parent, bg=COLORS["page"])
    lower.pack(fill="x")
    lower.columnconfigure(0, weight=0, minsize=DETAIL_SPECIAL_MIN_WIDTH)
    lower.columnconfigure(1, weight=1, minsize=850)

    special_panel = tk.Frame(
        lower,
        bg=COLORS["surface"],
        highlightbackground=COLORS["border"],
        highlightthickness=1,
        padx=7,
        pady=7,
    )
    special_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
    _section_heading(special_panel, "宝物特殊组合", color=COLORS["red"])
    specials = equipment.get("specials") or []
    if not specials:
        tk.Label(
            special_panel,
            text="本存档没有特殊组合",
            font=(FONT, 10),
            fg=COLORS["muted"],
            bg=COLORS["surface"],
        ).pack(anchor="w", pady=6)
    for index, special in enumerate(specials):
        color = SPECIAL_COLORS[index % len(SPECIAL_COLORS)]
        block = tk.Frame(
            special_panel,
            bg=COLORS["surface_alt"],
            highlightbackground=color,
            highlightthickness=1,
            padx=7,
            pady=5,
        )
        block.pack(fill="x", pady=(0, 5))
        tk.Label(
            block,
            text=str(special.get("title") or "特殊组合"),
            font=(FONT, 9, "bold"),
            fg=color,
            bg=COLORS["surface_alt"],
        ).pack(anchor="w")
        tk.Label(
            block,
            text="\n".join(str(value) for value in special.get("items") or []),
            font=(FONT, 8),
            fg=COLORS["ink"],
            bg=COLORS["surface_alt"],
            justify="left",
            wraplength=190,
        ).pack(anchor="w", fill="x", pady=(2, 0))

    equipment_panel = tk.Frame(
        lower,
        bg=COLORS["surface"],
        highlightbackground=COLORS["border"],
        highlightthickness=1,
        padx=7,
        pady=7,
    )
    equipment_panel.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
    _section_heading(equipment_panel, "宝物列表", color=COLORS["green"])
    equipment_grid = tk.Frame(equipment_panel, bg=COLORS["surface"])
    equipment_grid.pack(fill="x")
    for column in range(DETAIL_EQUIPMENT_COLUMNS):
        equipment_grid.columnconfigure(column, weight=1, uniform="equipment")
    for index, category in enumerate(equipment.get("categories") or []):
        category_frame = tk.Frame(
            equipment_grid,
            bg=COLORS["surface_alt"],
            padx=6,
            pady=4,
        )
        category_frame.grid(
            row=index // DETAIL_EQUIPMENT_COLUMNS,
            column=index % DETAIL_EQUIPMENT_COLUMNS,
            sticky="nsew",
            padx=3,
            pady=3,
        )
        tk.Label(
            category_frame,
            text=str(category.get("name") or "其他"),
            font=(FONT, 9, "bold"),
            fg=COLORS["green"],
            bg=COLORS["surface_alt"],
        ).pack(anchor="w", pady=(0, 2))
        items = category.get("items") or []
        if items:
            tk.Label(
                category_frame,
                text="\n".join(f"{item.get('name', '')}  {item.get('effect', '')}" for item in items),
                font=(FONT, 8),
                fg=COLORS["ink"],
                bg=COLORS["surface_alt"],
                justify="left",
                wraplength=165,
            ).pack(anchor="w", fill="x")
    return lower
