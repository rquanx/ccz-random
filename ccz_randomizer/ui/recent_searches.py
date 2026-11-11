"""At most ten compact keyword buttons, wrapped to the available width."""
import tkinter as tk
from tkinter import ttk
from ccz_randomizer.ui.tooltip import HoverTooltip


class RecentSearchesBar(ttk.Frame):
    def __init__(self, parent, on_select, on_remove=None, on_clear=None):
        super().__init__(parent)
        self.on_select = on_select
        self.buttons = []
        self.groups = []
        self.delete_buttons = []
        self.on_remove = on_remove
        ttk.Label(self, text="最近使用", foreground="#667085").pack(side="left", anchor="n", padx=(0, 10), pady=4)
        self.clear_button = ttk.Button(self, text="清空最近搜索", command=on_clear)
        if on_clear:
            self.clear_button.pack(side="right", anchor="n", padx=(10, 0))
        self.chips = ttk.Frame(self)
        self.chips.pack(side="left", fill="x", expand=True)
        self.chips.bind("<Configure>", self._layout)

    def set_items(self, items):
        for group in self.groups:
            group.destroy()
        self.buttons = []
        self.groups = []
        self.delete_buttons = []
        for word in items:
            group = ttk.Frame(self.chips)
            self.groups.append(group)
            button = tk.Button(group, text=word if len(word) <= 10 else word[:10]+"…",
                command=lambda value=word: self.on_select(value), cursor="hand2", relief="flat",
                bg="#EAF0FB", fg="#334E73", activebackground="#DCE7FA", borderwidth=0,
                font=("Microsoft YaHei UI", 9), padx=9, pady=4)
            button._keyword = word
            button._tooltip = HoverTooltip(button, word)
            self.buttons.append(button)
            button.pack(side="left")
            if self.on_remove:
                delete = tk.Button(group, text="删除", command=lambda value=word: self.on_remove(value),
                    relief="flat", borderwidth=0, cursor="hand2", bg="#EAF0FB", fg="#667085",
                    font=("Microsoft YaHei UI", 9), padx=5, pady=4)
                delete.pack(side="left")
                self.delete_buttons.append(delete)
        self._layout()

    def _layout(self, _event=None):
        width = max(1, self.chips.winfo_width())
        x = y = row_height = 0
        for button in self.groups:
            requested = min(width, button.winfo_reqwidth())
            height = button.winfo_reqheight()
            if x and x+requested > width:
                x, y = 0, y+row_height+5
                row_height = 0
            button.place(x=x, y=y, width=requested, height=height)
            x += requested+6
            row_height = max(row_height, height)
        self.chips.configure(height=y+row_height if self.buttons else 1)
