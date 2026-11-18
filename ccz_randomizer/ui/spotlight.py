"""Windows spotlight surface and target-aware floating-card placement."""
import tkinter as tk


def place_surface(window, width, height, x, y):
    """The explicit + prefix keeps negative positions absolute in Tk geometry."""
    window.geometry(f'{width}x{height}+{x}+{y}')
    window.deiconify()


def card_position(width, height, card_width, card_height, holes):
    """Prefer a nearby clear side; minimize target overlap in cramped windows."""
    margin, gap = 12, 16
    xmax, ymax = max(margin, width-card_width-margin), max(margin, height-card_height-margin)
    candidates = []
    for left, top, right, bottom in holes:
        candidates.extend(((left, bottom+gap), (left, top-card_height-gap),
                           (right+gap, top), (left-card_width-gap, top)))
    candidates.extend(((xmax, ymax), (margin, ymax), (xmax, margin), (margin, margin)))
    candidates = [(max(margin, min(x, xmax)), max(margin, min(y, ymax))) for x, y in candidates]

    def overlap(point):
        x, y = point
        return sum(max(0, min(x+card_width, r)-max(x, l)) *
                   max(0, min(y+card_height, b)-max(y, t)) for l, t, r, b in holes)
    return min(candidates, key=overlap)


class Spotlight(tk.Toplevel):
    """One translucent owned window; transparent holes reveal actual controls."""
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.withdraw()
        self.overrideredirect(True)
        self.transient(owner)
        self.attributes('-alpha', 0.58)
        self.attributes('-transparentcolor', '#FF00FF')
        self.canvas = tk.Canvas(self, bg='#101828', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.holes = []

    def show(self, holes):
        owner = self.owner
        place_surface(self, owner.winfo_width(), owner.winfo_height(),
                      owner.winfo_rootx(), owner.winfo_rooty())
        self.holes = holes
        self.canvas.delete('all')
        for box in holes:
            self.canvas.create_rectangle(*box, fill='#FF00FF', outline='#60A5FA', width=2)
        self.lift(owner)
