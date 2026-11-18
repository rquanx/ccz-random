"""Reusable round cards with one text surface and a native edit button."""
import tkinter as tk
from tkinter import ttk


class RoundCard(tk.Frame):
    def __init__(self, parent, *, colors, font, display_title, display_time, select, edit):
        super().__init__(parent, bg=colors["surface"], padx=10, pady=8,
                         highlightthickness=1, highlightbackground=colors["border"])
        self.row = {}
        self.colors = colors
        self.display_title, self.display_time = display_title, display_time
        self._selected = None
        self._values = None
        self._width = None
        self.head = tk.Frame(self, bg=colors["surface"])
        self.head.pack(fill="x")
        self._round_name_label = tk.Canvas(self.head, width=250, height=60,
            highlightthickness=0, bg=colors["surface"])
        self._round_name_label.pack(side="left", fill="x", expand=True)
        self.edit_button = ttk.Button(self.head, text="编辑", width=-1,
            command=lambda: edit(self.row, self.head, self._round_name_label, self.edit_button))
        self.edit_button.pack(side="right", anchor="center", padx=(12, 0), before=self._round_name_label)
        canvas = self._round_name_label
        self.title_item = canvas.create_text(0, 0, anchor="nw", font=(font, 11, "bold"), fill=colors["ink"])
        self.time_item = canvas.create_text(0, 0, anchor="nw", font=(font, 8), fill=colors["muted"])
        canvas.bind("<Configure>", lambda _event: self._layout())
        self._backgrounds = (self, self.head, canvas)
        for widget in self._backgrounds:
            widget.bind("<Button-1>", lambda _event: select(self.row))

    def _layout(self, width=None):
        canvas = self._round_name_label
        width = max(80, canvas.winfo_width() if width is None else width)
        if width <= 80:
            width = 250
        if width == self._width:
            return
        self._width = width
        canvas.itemconfigure(self.title_item, width=width)
        canvas.itemconfigure(self.time_item, width=width)
        title = canvas.bbox(self.title_item)
        top = (title[3] if title else 20) + 5
        canvas.coords(self.time_item, 0, top)
        bounds = canvas.bbox("all")
        canvas.configure(height=max(40, bounds[3] + 2 if bounds else 60))

    def update_content(self, row):
        # Callbacks read the current row so recycled cards never edit an old round.
        self.row = row
        values = (self.display_title(row.get("title")), self.display_time(row["started_at"]), row["rule_name"])
        if values != self._values:
            metadata = ' · '.join(str(value) for value in values[1:] if value)
            for item, text in zip((self.title_item, self.time_item), (values[0], metadata)):
                self._round_name_label.itemconfigure(item, text=text)
            self._values = values
            self._width = None
            self._layout()

    def set_selected(self, selected):
        if self._selected == selected:
            return
        self._selected = selected
        color = self.colors["blue_soft"] if selected else self.colors["surface"]
        for widget in self._backgrounds:
            widget.configure(bg=color)
