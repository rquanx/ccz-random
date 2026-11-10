"""Small profile badge shared by the application and isolated UI previews."""
from __future__ import annotations

import math
import tkinter as tk
from dataclasses import dataclass
from functools import lru_cache
from PIL import Image, ImageColor, ImageDraw, ImageTk
from ccz_randomizer.ui.tooltip import HoverTooltip


@dataclass(frozen=True)
class ProfileStatus:
    state: str
    current: int
    target: int | None = None
    detail: str = ""


STATES = {
    "old": ("旧版本", "#d34d55"),
    "updating": ("更新中", "#d49b24"),
    "checking": ("检测中", "#d49b24"),
    "latest": ("最新", "#78ad8b"),
    "local": ("暂无更新", "#78ad8b"),
    "unknown": ("检测失败", "#939ba5"),
    "pending": ("待生效", "#d49b24"),
}

STATUS_TOOLTIPS = {
    "old": "有可用的新数据包，当前仍在使用旧版本。\n自动更新失败时，可在常见问题中手动更新数据。",
    "updating": "数据包更新中，更新完成后在工具空闲时自动生效。",
    "checking": "正在检测数据包更新。",
    "latest": "当前数据包已是最新版本。",
    "local": "暂无可用更新，正在使用本地数据包。",
    "unknown": "检测失败，请检查网络或稍后重试。",
    "pending": "数据包更新完成，停止随机后自动生效。",
}


@lru_cache(maxsize=128)
def render_status_dot(color, background, halo_opacity=0):
    """Supersample symmetric circles rather than Tk's hard-edged small ovals."""
    scale = 8
    image = Image.new("RGB", (16 * scale, 16 * scale), background)
    draw = ImageDraw.Draw(image)
    if halo_opacity:
        base, foreground = ImageColor.getrgb(background), ImageColor.getrgb(color)
        blend = tuple(round(a + (b-a)*halo_opacity) for a, b in zip(base, foreground))
        draw.ellipse((scale, scale, 15*scale-1, 15*scale-1), fill=blend)
    draw.ellipse((4*scale, 4*scale, 12*scale-1, 12*scale-1), fill=color)
    return image.resize((16, 16), Image.Resampling.LANCZOS)


class ProfileStatusBadge(tk.Frame):
    def __init__(self, parent, status: ProfileStatus, **kwargs):
        super().__init__(parent, **kwargs)
        self._timer = None
        self._phase = 0
        self._status = status
        self._frames = {}
        bg = self.cget("bg")
        self.dot = tk.Canvas(self, width=16, height=16, bg=bg, highlightthickness=0)
        self.dot.pack(side="left")
        self._image_item = self.dot.create_image(8, 8)
        self.tooltip = HoverTooltip(self.dot, self._tooltip_text)
        self.bind("<Destroy>", self._destroyed, add="+")
        self.set_status(status)

    def set_status(self, status: ProfileStatus):
        self._stop_animation()
        self._status = status
        _label, color = STATES[status.state]
        self.tooltip.refresh()
        bg = self.winfo_rgb(self.cget("bg"))
        background = "#" + "".join(f"{value//257:02x}" for value in bg)
        key = (color, background, status.state in {"checking", "updating"})
        if key not in self._frames:
            opacities = [.12 + .28 * (1 + math.sin(i * math.tau / 24)) / 2 for i in range(24)] if key[2] else [0]
            self._frames[key] = [ImageTk.PhotoImage(render_status_dot(color, background, opacity), master=self)
                                 for opacity in opacities]
        self._active_frames = self._frames[key]
        self._phase = 0
        self.dot.itemconfigure(self._image_item, image=self._active_frames[0])
        if key[2]:
            self._pulse()

    def _tooltip_text(self):
        text = STATUS_TOOLTIPS[self._status.state]
        if self._status.detail:
            text += "\n" + self._status.detail
        return text

    @property
    def status(self):
        return self._status

    def _pulse(self):
        self._timer = None
        self.dot.itemconfigure(self._image_item, image=self._active_frames[self._phase])
        self._phase = (self._phase + 1) % len(self._active_frames)
        self._timer = self.after(80, self._pulse)

    def _stop_animation(self):
        if self._timer is not None:
            self.after_cancel(self._timer)
            self._timer = None

    def _destroyed(self, event):
        if event.widget is self:
            self._stop_animation()
