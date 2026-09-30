from __future__ import annotations

from typing import Callable, Iterable


HEADING_X = 3
SKILL_X = 13


def render_member_text_panel(
    member_name: str,
    job_name: str,
    skills: Iterable[object],
    *,
    font_factory: Callable[..., object],
):
    """Render a compact fallback panel from recognized member text."""
    import cv2
    import numpy as np
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (130, 130), (211, 211, 211))
    draw = ImageDraw.Draw(image)
    font = font_factory(12)
    title_font = font_factory(13)
    skill_items = [
        skill for skill in skills if getattr(skill, "name", skill)
    ]
    categorized = any(
        getattr(skill, "memory_category", "") for skill in skill_items
    )
    if categorized:
        personal_names = [
            str(getattr(skill, "name", skill))
            for skill in skill_items
            if getattr(skill, "memory_category", "") == "personal"
        ]
        job_names = [
            str(getattr(skill, "name", skill))
            for skill in skill_items
            if getattr(skill, "memory_category", "") == "job"
        ]
    else:
        skill_names = [
            str(getattr(skill, "name", skill)) for skill in skill_items
        ]
        personal_names = skill_names[:3]
        job_names = skill_names[3:6]
    lines = [("个人天赋:", title_font, HEADING_X)]
    lines.extend((name, font, SKILL_X) for name in personal_names[:3])
    lines.append(("兵种技能:", title_font, HEADING_X))
    lines.extend((name, font, SKILL_X) for name in job_names[:3])
    y = 3
    for text, line_font, x in lines:
        if y > 94:
            break
        draw.text((x, y), text, font=line_font, fill=(0, 0, 0))
        y += 15
    footer = f"{member_name}-{job_name}"
    footer_width = draw.textlength(footer, font=font)
    draw.text(
        (max(3, 127 - footer_width), 112),
        footer,
        font=font,
        fill=(128, 0, 0),
    )
    return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
