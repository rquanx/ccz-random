"""A single drawing surface per member instead of a tree of native widgets."""
from __future__ import annotations

import tkinter as tk
from collections import OrderedDict
from ccz_randomizer.ui.text_block import shared_font


class MemberCard(tk.Canvas):
    @staticmethod
    def row_heights(parent, members, columns, width, *, font, score, skill_names):
        probe = None
        item = None
        heights = []
        fonts = {(size, weight): shared_font(parent, font, size, weight)
                 for size, weight in ((8, 'normal'), (8, 'bold'), (10, 'bold'))}
        root = parent._root()
        cache = getattr(root, '_ccz_member_measurements', None)
        if cache is None:
            cache = root._ccz_member_measurements = OrderedDict()
        font_key = tuple((key, tuple(value.actual().items())) for key, value in fonts.items())
        scale = parent.tk.call('tk', 'scaling')
        def box(text, size, weight, wrap=0):
            nonlocal probe, item
            key = (text, size, weight, wrap, font_key, scale)
            if key in cache:
                cache.move_to_end(key)
            else:
                if probe is None:
                    probe = tk.Canvas(parent)
                    item = probe.create_text(0, 0, anchor='nw')
                probe.itemconfigure(item, text=text, font=fonts[size, weight], width=wrap)
                bounds = probe.bbox(item)
                cache[key] = (bounds[2]-bounds[0], bounds[3]-bounds[1])
                if len(cache) > 4096:
                    cache.popitem(last=False)
            return cache[key]
        try:
            for member in members:
                job_width, job_height = box(f"{member.get('job') or '未知兵种'}  {score(member.get('jobScore'))}", 8, 'bold')
                _, name_height = box(str(member.get('name') or '未知'), 10, 'bold', max(35, width-job_width-31))
                y = max(7+name_height, 9+job_height)+7
                for key in ('personalSkills', 'jobSkills'):
                    _, text_height = box(skill_names(member.get(key) or []), 8, 'normal', max(1, width-58))
                    y += max(box('个人', 8, 'bold')[1], text_height)+5
                heights.append(y+9)
            return [max(heights[start:start+columns]) for start in range(0, len(heights), columns)]
        finally:
            if probe is not None:
                probe.destroy()

    def __init__(self, parent, member, *, colors, font, score, skill_names):
        super().__init__(parent, width=268, height=110, bg=colors["surface_alt"],
                         highlightbackground=colors["border"], highlightthickness=1)
        self.member = member
        self.colors = colors
        self.font = font
        self.fonts = {(size, weight): shared_font(self, font, size, weight)
                      for size, weight in ((8, 'normal'), (8, 'bold'), (10, 'bold'))}
        self.score = score
        self.skill_names = skill_names
        self._width = None
        self._content = None
        self._items = None
        self.bind("<Configure>", lambda event: self._draw(event.width))

    def _draw(self, width):
        if self._width == width:
            return
        self._width = width
        member, colors = self.member, self.colors
        content = (f"{member.get('job') or '未知兵种'}  {self.score(member.get('jobScore'))}",
                   str(member.get('name') or '未知'),
                   *(self.skill_names(member.get(key) or []) for key in ('personalSkills', 'jobSkills')))
        if self._items is None:
            background = self.create_rectangle(0, 0, 0, 0, fill=colors['red_soft'], outline='')
            job = self.create_text(0, 0, anchor='ne', font=self.fonts[8, 'bold'], fill=colors['red'])
            name = self.create_text(9, 7, anchor='nw', font=self.fonts[10, 'bold'], fill=colors['ink'])
            rows = []
            for label, color in (('个人', colors['blue']), ('兵种', colors['purple'])):
                heading = self.create_text(9, 0, anchor='nw', text=label, font=self.fonts[8, 'bold'], fill=color)
                text = self.create_text(47, 0, anchor='nw', font=self.fonts[8, 'normal'], fill=colors['ink'])
                rows.append((heading, text))
            self._items = background, job, name, rows
        background, job, name, rows = self._items
        if content != self._content:
            for item, value in zip((job, name, *(text for _, text in rows)), content):
                self.itemconfigure(item, text=value)
            self._content = content
        self.coords(job, width-12, 9)
        bounds = self.bbox(job)
        self.coords(background, bounds[0]-5, bounds[1]-1, bounds[2]+5, bounds[3]+1)
        self.itemconfigure(name, width=max(35, bounds[0]-19))
        y = max(self.bbox(name)[3], bounds[3]) + 7
        for heading, text in rows:
            self.coords(heading, 9, y)
            self.coords(text, 47, y)
            self.itemconfigure(text, width=max(1, width-58))
            y = max(self.bbox(heading)[3], self.bbox(text)[3]) + 5
        if int(self.cget('height')) != y+3:
            self.configure(height=y+3)
