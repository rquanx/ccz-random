"""At most ten compact keyword buttons, wrapped to the available width."""
import tkinter as tk
from tkinter import ttk
from ccz_randomizer.ui.tooltip import HoverTooltip


class RecentSearchesBar(ttk.Frame):
    def __init__(self, parent, on_select):
        super().__init__(parent)
        self.on_select = on_select
        self.buttons = []
        ttk.Label(self, text="最近使用", foreground="#667085").pack(side="left", anchor="n", padx=(0, 10), pady=4)
        self.chips = ttk.Frame(self)
        self.chips.pack(side="left", fill="x", expand=True)
        self.chips.bind("<Configure>", self._layout)

    def set_items(self, items):
        for button in self.buttons:
            button.destroy()
        self.buttons = []
        for word in items:
            button = tk.Button(self.chips, text=word if len(word) <= 10 else word[:10]+"…",
                command=lambda value=word: self.on_select(value), cursor="hand2", relief="flat",
                bg="#EAF0FB", fg="#334E73", activebackground="#DCE7FA", borderwidth=0,
                font=("Microsoft YaHei UI", 9), padx=9, pady=4)
            button._keyword = word
            button._tooltip = HoverTooltip(button, word)
            self.buttons.append(button)
        self._layout()

    def _layout(self, _event=None):
        width = max(1, self.chips.winfo_width())
        x = y = row_height = 0
        for button in self.buttons:
            requested = min(width, button.winfo_reqwidth())
            height = button.winfo_reqheight()
            if x and x+requested > width:
                x, y = 0, y+row_height+5
                row_height = 0
            button.place(x=x, y=y, width=requested, height=height)
            x += requested+6
            row_height = max(row_height, height)
        self.chips.configure(height=y+row_height if self.buttons else 1)
