"""At most ten compact keyword buttons, wrapped to the available width."""
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageDraw, ImageTk
from ccz_randomizer.ui.tooltip import HoverTooltip


def delete_icon(master):
    """Rasterize Lucide circle-x geometry at the current Tk display scale."""
    size = max(16, round(12 * float(master.tk.call("tk", "scaling"))))
    scale = size * 4 / 24
    image = Image.new("RGBA", (size * 4, size * 4))
    draw = ImageDraw.Draw(image)
    stroke = max(1, round(2 * scale))
    draw.ellipse(tuple(round(n * scale) for n in (2, 2, 22, 22)),
                 fill="#F4F6FA", outline="#667085", width=stroke)
    for line in ((15, 9, 9, 15), (9, 9, 15, 15)):
        draw.line(tuple(round(n * scale) for n in line), fill="#667085", width=stroke)
    return ImageTk.PhotoImage(image.resize((size, size), Image.Resampling.LANCZOS), master=master)


class RecentSearchesBar(ttk.Frame):
    def __init__(self, parent, on_select, on_remove=None, on_clear=None):
        super().__init__(parent)
        self.on_select = on_select
        self.buttons = []
        self.groups = []
        self.delete_buttons = []
        self.on_remove = on_remove
        self._delete_icon = delete_icon(self) if on_remove else None
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
            button.pack(side="left", padx=(8, 0) if self.on_remove else 0,
                        pady=(8, 0) if self.on_remove else 0)
            if self.on_remove:
                delete = tk.Button(group, image=self._delete_icon,
                    command=lambda value=word: self.on_remove(value),
                    relief="flat", borderwidth=0, highlightthickness=0, takefocus=True,
                    cursor="hand2", bg="#F4F6FA", activebackground="#DCE7FA", padx=1, pady=1)
                delete.place(x=0, y=0)
                delete._tooltip = HoverTooltip(delete, f"删除最近搜索：{word}")
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
