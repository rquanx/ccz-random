"""At most ten compact keyword buttons, wrapped to the available width."""
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageDraw, ImageTk
from ccz_randomizer.ui.tooltip import HoverTooltip


def delete_icon(master, color="#8492A6"):
    """Rasterize the small Lucide x icon at the current Tk display scale."""
    size = max(12, round(9 * float(master.tk.call("tk", "scaling"))))
    scale = size * 4 / 24
    image = Image.new("RGBA", (size * 4, size * 4))
    draw = ImageDraw.Draw(image)
    stroke = max(1, round(2 * scale))
    for line in ((18, 6, 6, 18), (6, 6, 18, 18)):
        points = tuple(round(n * scale) for n in line)
        draw.line(points, fill=color, width=stroke)
        radius = stroke / 2
        for x, y in (points[:2], points[2:]):
            draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=color)
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
        self._delete_hover_icon = delete_icon(self, "#334E73") if on_remove else None
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
            group = tk.Frame(self.chips, bg="#EAF0FB")
            self.groups.append(group)
            button = tk.Button(group, text=word if len(word) <= 10 else word[:10]+"…",
                command=lambda value=word: self.on_select(value), cursor="hand2", relief="flat",
                bg="#EAF0FB", fg="#334E73", activebackground="#DCE7FA", borderwidth=0,
                font=("Microsoft YaHei UI", 9), padx=9, pady=4)
            button._keyword = word
            button._tooltip = HoverTooltip(button, word)
            self.buttons.append(button)
            close_space = self._delete_icon.width() + 6 if self.on_remove else 0
            button.pack(side="left", padx=(0, close_space))
            if self.on_remove:
                delete = tk.Button(group, image=self._delete_icon,
                    command=lambda value=word: self.on_remove(value),
                    relief="flat", borderwidth=0, highlightthickness=0, takefocus=True,
                    cursor="hand2", bg="#EAF0FB", activebackground="#DCE7FA", padx=2, pady=2)
                delete.place(relx=1, x=-1, y=1, anchor="ne")
                delete.bind("<Enter>", lambda _event, control=delete:
                            control.configure(image=self._delete_hover_icon, bg="#DCE7FA"))
                delete.bind("<Leave>", lambda _event, control=delete:
                            control.configure(image=self._delete_icon, bg="#EAF0FB"))
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
