"""Reusable round picker cards, bounded by the history page size."""
import tkinter as tk
from tkinter import ttk


class RoundCard(tk.Frame):
    def __init__(self, parent, *, colors, font, display_title, display_time, select, edit):
        super().__init__(parent, bg=colors["surface"], padx=10, pady=8,
                         highlightthickness=1, highlightbackground=colors["border"])
        self.row = {}
        self.colors = colors
        self.display_title = display_title
        self.display_time = display_time
        self._selected = None
        self._values = {}
        self.head = tk.Frame(self, bg=colors["surface"])
        self.head.pack(fill="x")
        self._round_name_label = tk.Message(self.head, width=250, font=(font, 11, "bold"),
            fg=colors["ink"], bg=colors["surface"], anchor="w")
        self._round_name_label.pack(side="left", fill="x", expand=True)
        self.edit_button = ttk.Button(self.head, text="编辑", width=-1,
            command=lambda: edit(self.row, self.head, self._round_name_label, self.edit_button))
        self.edit_button.pack(side="right")
        meta = tk.Frame(self, bg=colors["surface"])
        meta.pack(fill="x", pady=(5, 0))
        self.time_label = tk.Label(meta, font=(font, 8), fg=colors["muted"],
                                   bg=colors["surface"], anchor="w")
        self.time_label.pack(side="left")
        self.rule_label = tk.Label(meta, font=(font, 8), fg=colors["muted"],
                                   bg=colors["surface"], anchor="e")
        self.rule_label.pack(side="right")
        self._backgrounds = (self, self.head, self._round_name_label, meta, self.time_label, self.rule_label)
        for widget in self._backgrounds:
            widget.bind("<Button-1>", lambda _event: select(self.row))

    def update_content(self, row):
        # Callbacks read the current row so recycled cards never edit/export an old round.
        self.row = row
        for widget, text in (
            (self._round_name_label, self.display_title(row.get("title"))),
            (self.time_label, self.display_time(row["started_at"])),
            (self.rule_label, row["rule_name"]),
        ):
            if self._values.get(widget) != text:
                widget.configure(text=text)
                self._values[widget] = text

    def set_selected(self, selected):
        if self._selected == selected:
            return
        self._selected = selected
        color = self.colors["blue_soft"] if selected else self.colors["surface"]
        for widget in self._backgrounds:
            widget.configure(bg=color)
