"""Supersampled chart shapes, with hit regions independent of raster pixels."""
from dataclasses import dataclass
import math

from PIL import Image, ImageDraw


@dataclass(frozen=True)
class HitRegion:
    bounds: tuple
    kind: str = "rectangle"
    start: float = 0
    extent: float = 360
    inner_ratio: float = 0

    def contains(self, x, y):
        left, top, right, bottom = self.bounds
        if not left <= x <= right or not top <= y <= bottom:
            return False
        if self.kind == "rectangle":
            return True
        rx, ry = (right-left)/2, (bottom-top)/2
        if rx <= 0 or ry <= 0:
            return False
        dx, dy = (x-(left+right)/2)/rx, ((top+bottom)/2-y)/ry
        distance = dx*dx + dy*dy
        if not self.inner_ratio**2 <= distance <= 1:
            return False
        if self.kind == "oval":
            return True
        angle = math.degrees(math.atan2(dy, dx)) % 360
        return self.extent >= 360 or (angle-self.start) % 360 <= self.extent


class ChartGraphics:
    def __init__(self, width, height, *, scale=3):
        self.size, self.scale = (width, height), scale
        self.commands = []

    def _shape(self, kind, bounds, options, layer=1):
        self.commands.append((layer, kind, bounds, options))

    def arc(self, *bounds, start, extent, fill, outline="white", width=2):
        self._shape("arc", bounds, dict(start=start, extent=extent, fill=fill,
                                       outline=outline, width=width))
        return HitRegion(bounds, "arc", start, extent, .72)

    def oval(self, *bounds, fill, outline="", layer=2):
        self._shape("oval", bounds, dict(fill=fill, outline=outline), layer)
        return HitRegion(bounds, "oval")

    def rectangle(self, *bounds, fill, outline=""):
        if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
            return HitRegion(bounds)
        self._shape("rectangle", bounds, dict(fill=fill, outline=outline))
        return HitRegion(bounds)

    def line(self, *coords, fill, width=1, dash=None, layer=0):
        self._shape("line", coords, dict(fill=fill, width=width, dash=dash), layer)

    def render(self):
        scale = self.scale
        image = Image.new("RGB", (self.size[0]*scale, self.size[1]*scale), "white")
        draw = ImageDraw.Draw(image)
        for _, kind, coords, options in sorted(self.commands, key=lambda item: item[0]):
            points = tuple(round(value*scale) for value in coords)
            fill, outline = options["fill"], options.get("outline") or None
            if kind == "arc":
                if options["extent"] >= 359.999:
                    draw.ellipse(points, fill=fill, outline=outline, width=options["width"]*scale)
                else:
                    draw.pieslice(points, start=-options["start"]-options["extent"],
                                  end=-options["start"], fill=fill, outline=outline,
                                  width=options["width"]*scale)
            elif kind == "oval":
                draw.ellipse(points, fill=fill, outline=outline, width=scale)
            elif kind == "rectangle":
                radius = min(3*scale, (points[3]-points[1])/2, (points[2]-points[0])/2)
                draw.rounded_rectangle(points, radius=radius, fill=fill, outline=outline)
            elif options["dash"]:
                # Grid lines are horizontal and keep a consistent quiet rhythm.
                step, gap = (value*scale for value in options["dash"])
                for x in range(points[0], points[2], step+gap):
                    draw.line((x, points[1], min(x+step, points[2]), points[3]),
                              fill=fill, width=max(1, round(options["width"]*scale)))
            else:
                draw.line(points, fill=fill, width=max(1, round(options["width"]*scale)), joint="curve")
        return image.resize(self.size, Image.Resampling.LANCZOS)
