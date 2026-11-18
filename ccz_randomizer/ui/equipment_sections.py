"""Shared equipment cards; filtering reuses drawing surfaces and their fonts."""
import tkinter as tk
from ccz_randomizer.ui.text_block import TextBlock, shared_font


class EquipmentSections(tk.Frame):
    def __init__(self, parent):
        from ccz_randomizer.ui.history import COLORS, DETAIL_SPECIAL_MIN_WIDTH, _section_heading
        super().__init__(parent, bg=COLORS["page"])
        self.columnconfigure(0, weight=0, minsize=DETAIL_SPECIAL_MIN_WIDTH)
        self.columnconfigure(1, weight=1, minsize=850)
        self.panels = []
        for column, (title, color) in enumerate((("宝物特殊组合", COLORS["red"]), ("宝物列表", COLORS["green"]))):
            panel = tk.Frame(self, bg=COLORS["surface"], highlightbackground=COLORS["border"],
                             highlightthickness=1, padx=7, pady=7)
            panel.grid(row=0, column=column, sticky="nsew", padx=(0, 6) if column == 0 else (6, 0))
            _section_heading(panel, title, color=color)
            self.panels.append(panel)
        self.empty = tk.Label(self.panels[0], text="本存档没有特殊组合", fg=COLORS["muted"], bg=COLORS["surface"])
        self.grid_body = tk.Frame(self.panels[1], bg=COLORS["surface"])
        self.grid_body.pack(fill="x")
        for column in range(4):
            self.grid_body.columnconfigure(column, weight=1, uniform="equipment")
        self.specials = []
        self.categories = []

    def set_equipment(self, equipment):
        from ccz_randomizer.equipment_labels import equipment_display
        equipment = equipment_display(equipment)
        from ccz_randomizer.ui.history import COLORS, FONT, SPECIAL_COLORS, DETAIL_EQUIPMENT_COLUMNS
        title_font = shared_font(self, FONT, 9, "bold")
        body_font = shared_font(self, FONT, 8)
        specials = equipment.get("specials") or []
        if specials:
            self.empty.pack_forget()
        else:
            self.empty.pack(anchor="w", pady=6)
        for index, special in enumerate(specials):
            color = SPECIAL_COLORS[index % len(SPECIAL_COLORS)]
            if index == len(self.specials):
                block = TextBlock(self.panels[0], background=COLORS["surface_alt"], width=202)
                block.configure(highlightthickness=1)
                self.specials.append(block)
            block = self.specials[index]
            block.configure(highlightbackground=color)
            block.set(((str(special.get("title") or "特殊组合"), title_font, color, 3),
                       ("\n".join(map(str, special.get("items") or [])), body_font, COLORS["ink"], 0)))
            if not block.winfo_manager():
                block.pack(fill="x", pady=(0, 5))
        for block in self.specials[len(specials):]:
            block.pack_forget()
        categories = equipment.get("categories") or []
        for index, category in enumerate(categories):
            if index == len(self.categories):
                self.categories.append(TextBlock(self.grid_body, background=COLORS["surface_alt"], width=177))
            block = self.categories[index]
            block.set(((str(category.get("name") or "其他"), title_font, COLORS["green"], 3),
                       ("\n".join(f"{item.get('name', '')}  {item.get('effect', '')}" for item in category.get("items") or []),
                        body_font, COLORS["ink"], 0)))
            if not block.winfo_manager():
                block.grid(row=index//DETAIL_EQUIPMENT_COLUMNS, column=index%DETAIL_EQUIPMENT_COLUMNS,
                           sticky="nsew", padx=3, pady=3)
        for block in self.categories[len(categories):]:
            block.grid_remove()


def render_equipment_sections(parent, equipment):
    sections = EquipmentSections(parent)
    sections.pack(fill="x")
    sections.set_equipment(equipment)
    return sections
