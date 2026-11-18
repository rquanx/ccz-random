"""A reusable drawing surface for read-only, wrapped card paragraphs."""
import tkinter as tk
from tkinter.font import Font


def shared_font(widget, family, size, weight='normal'):
    owner = widget._root()
    fonts = getattr(owner, '_ccz_card_fonts', None)
    if fonts is None:
        fonts = owner._ccz_card_fonts = {}
    key = (family, size, weight)
    if key not in fonts:
        fonts[key] = Font(root=owner, family=family, size=size, weight=weight)
    return fonts[key]


class TextBlock(tk.Canvas):
    """Keep text items and fonts alive when the filtered card contents change."""
    def __init__(self, parent, *, background, width, padding=6):
        super().__init__(parent, background=background, highlightthickness=0,
                         width=width, height=1)
        self.padding = padding
        self.items = []
        self.blocks = ()
        self._layout = None
        self.bind('<Configure>', lambda event: self.draw(event.width))

    def set(self, blocks):
        blocks = tuple(blocks)
        if self._layout is not None and blocks == self.blocks:
            return
        self.blocks = blocks
        self.draw(self.winfo_width() if self.winfo_width() > 1 else int(self.cget('width')))

    def draw(self, width):
        layout = (width, self.blocks)
        if layout == self._layout:
            return
        same_blocks = self._layout is not None and self._layout[1] == self.blocks
        self._layout = layout
        y = self.padding
        for index, (text, font, color, gap) in enumerate(self.blocks):
            if index == len(self.items):
                self.items.append(self.create_text(0, 0, anchor='nw'))
            item = self.items[index]
            if same_blocks:
                self.itemconfigure(item, width=max(1, width-2*self.padding))
            else:
                self.itemconfigure(item, text=text or ' ', font=font, fill=color,
                                   width=max(1, width-2*self.padding), state='normal')
            self.coords(item, self.padding, y)
            y = self.bbox(item)[3] + gap
        for item in self.items[len(self.blocks):]:
            self.itemconfigure(item, state='hidden')
        self.configure(height=max(1, y+self.padding))
