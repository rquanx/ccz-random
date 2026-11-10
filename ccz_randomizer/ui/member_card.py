"""A single drawing surface per member instead of a tree of native widgets."""
from __future__ import annotations

import tkinter as tk


class MemberCard(tk.Canvas):
    def __init__(self, parent, member, *, colors, font, score, skill_names):
        super().__init__(parent, width=268, height=110, bg=colors["surface_alt"],
                         highlightbackground=colors["border"], highlightthickness=1)
        self.member = member
        self.colors = colors
        self.font = font
        self.score = score
        self.skill_names = skill_names
        self._width = None
        self.bind("<Configure>", lambda event: self._draw(event.width))
        self._draw(268)

    def _draw(self, width):
        if self._width == width:
            return
        self._width = width
        self.delete("all")
        member, colors = self.member, self.colors
        job = self.create_text(width-12, 9, anchor="ne",
            text=f"{member.get('job') or '未知兵种'}  {self.score(member.get('jobScore'))}",
            font=(self.font, 8, "bold"), fill=colors["red"])
        bounds = self.bbox(job)
        background = self.create_rectangle(bounds[0]-5, bounds[1]-1, bounds[2]+5, bounds[3]+1,
                                           fill=colors["red_soft"], outline="")
        self.tag_lower(background, job)
        name = self.create_text(9, 7, anchor="nw", text=str(member.get("name") or "未知"),
            font=(self.font, 10, "bold"), fill=colors["ink"], width=max(35, bounds[0]-19))
        y = max(self.bbox(name)[3], bounds[3]) + 7
        for label, key, color in (("个人", "personalSkills", colors["blue"]),
                                  ("兵种", "jobSkills", colors["purple"])):
            heading = self.create_text(9, y, anchor="nw", text=label,
                font=(self.font, 8, "bold"), fill=color)
            text = self.create_text(47, y, anchor="nw", text=self.skill_names(member.get(key) or []),
                font=(self.font, 8), fill=colors["ink"], width=max(1, width-58))
            y = max(self.bbox(heading)[3], self.bbox(text)[3]) + 5
        self.configure(height=y+3)
