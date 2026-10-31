"""Compose result panels without shrinking their text or dropping extra columns."""
from __future__ import annotations
import math
import os
from pathlib import Path


def compose_result_panels(panels: dict[int, Path], output: Path) -> None:
    from PIL import Image
    available = {}
    cell_width, cell_height = 740, 1028
    for slot, path in sorted(panels.items()):
        if slot < 1 or not path.is_file():
            continue
        with Image.open(path) as image:
            cell_width = max(cell_width, image.width)
            cell_height = max(cell_height, image.height)
        available[slot] = path
    columns = max(1, min(5, 3700 // cell_width))
    rows = max(1, math.ceil(max(available, default=1) / columns))
    grid = Image.new("RGB", (columns * cell_width, rows * cell_height), (235, 233, 228))
    temporary = output.with_suffix(".tmp.png")
    try:
        for slot, path in available.items():
            with Image.open(path) as source:
                panel = source.convert("RGB")
                try:
                    grid.paste(panel, (((slot - 1) % columns) * cell_width,
                                      ((slot - 1) // columns) * cell_height))
                finally:
                    panel.close()
        output.parent.mkdir(parents=True, exist_ok=True)
        grid.save(temporary, "PNG")
        os.replace(temporary, output)
    finally:
        grid.close()
        temporary.unlink(missing_ok=True)
