"""Variable-width result panels using the actual scored party."""
from __future__ import annotations


def report_members(runner):
    settings = getattr(runner, "_result_image_settings", {})
    if settings.get("mode") == "custom":
        snapshots = (getattr(runner, "_personnel_snapshot", None) or []) + (getattr(runner, "_fixed_personnel_snapshot", None) or [])
        by_name = {row["name"]: row for row in snapshots}
        missing = [name for name in settings["members"] if name not in by_name]
        if missing:
            raise ValueError("结果图缺少本次人物数据：" + "、".join(missing))
        return [dict(name=name, job=by_name[name].get("job", ""),
                     personal=list(by_name[name].get("personalTalents", [])),
                     jobSkills=list(by_name[name].get("jobTalents", [])))
                for name in settings["members"]]
    scored = getattr(runner, "_scored_members", None)
    members = scored if scored is not None else getattr(runner, "_team_members", ())
    job_rows = {row["name"]: row for row in
                (getattr(runner, "_job_evaluation_detail", None) or {}).get("members", [])}
    result = []
    for member in members:
        skills = list(getattr(member, "skillList", ()))
        categorized = any(getattr(skill, "memory_category", "") for skill in skills)
        def names(category):
            selected = [skill for skill in skills if getattr(skill, "memory_category", "") == category] if categorized else (skills if category == "personal" else [])
            return [str(getattr(skill, "name", skill)) for skill in selected]
        result.append(dict(name=member.name,
            job=job_rows.get(member.name, {}).get("job") or getattr(getattr(member, "job", None), "name", ""),
            personal=names("personal"), jobSkills=names("job")))
    return result


def pack_member_columns(blocks, available_height):
    columns = [[]]
    used = 0
    for block in blocks:
        if columns[-1] and used + block[2] > available_height:
            columns.append([])
            used = 0
        columns[-1].append(block)
        used += block[2]
    return columns


def render_result_image(runner, equip_info, save_slot: int, *, result_font):
    from PIL import Image, ImageDraw
    width, height = 740, 1028
    left_width, special_width = 132, 202
    equipment_width = width - left_width - special_width
    body_font = result_font(12)
    heading_font = result_font(13)
    # Keep all body text on the same font object and size. Smaller separately
    # rasterized fonts made the left roster and skill list visibly thinner and
    # harder to read than the equipment columns.
    small_font = body_font
    member_font = body_font
    roster_font = body_font
    roster_job_font = body_font
    line_height = 20
    # The personnel area is self-describing: each block starts with the
    # person's name and job.  Keep only a small top inset instead of reserving
    # a repeated "人物信息" heading for every column.
    member_content_top = 4
    member_content_bottom = 20

    probe = Image.new("RGB", (1, 1))
    probe_draw = ImageDraw.Draw(probe)

    def wrap_text(text: str, font, max_width: int) -> list[str]:
        text = str(text)
        if not text:
            return [""]
        lines = []
        current = ""
        for character in text:
            candidate = current + character
            if (
                current
                and probe_draw.textlength(candidate, font=font) > max_width
            ):
                lines.append(current)
                current = character
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines

    def special_item_texts(item) -> list[str]:
        if isinstance(item, str):
            return [item]
        if isinstance(item, (list, tuple)):
            if (
                len(item) == 2
                and isinstance(item[0], str)
                and isinstance(item[1], str)
            ):
                return [f"{item[0]}: {item[1]}"]
            if (
                len(item) == 2
                and isinstance(item[0], str)
                and isinstance(item[1], (list, tuple, set))
            ):
                result = [f"{item[0]}:"]
                for child in item[1]:
                    result.extend(special_item_texts(child))
                return result
            result = []
            for child in item:
                result.extend(special_item_texts(child))
            return result
        return [str(item)]

    special_palette = (
        (0, 0, 255),
        (255, 0, 0),
        (128, 0, 128),
        (0, 128, 0),
        (255, 0, 255),
        (0, 128, 128),
        (0, 128, 255),
        (149, 80, 30),
        (255, 0, 0),
    )
    special_blocks = []
    special_line_count = 0
    for index, (title, items) in enumerate(
        getattr(runner, "_equip_specials", ())
    ):
        block = [
            (
                line,
                heading_font,
                special_palette[index % len(special_palette)],
            )
            for line in wrap_text(
                f"{title}:", heading_font, special_width - 8
            )
        ]
        for item in items:
            for item_text in special_item_texts(item):
                for line in wrap_text(
                    item_text,
                    body_font,
                    special_width - 8,
                ):
                    block.append(
                        (
                            line,
                            body_font,
                            special_palette[index % len(special_palette)],
                        )
                    )
        block.append(("", body_font, (0, 0, 0)))
        special_blocks.append(block)
        special_line_count += len(block)

    category_blocks = []
    for items, type_name in equip_info or ():
        block = [
            (line, heading_font)
            for line in wrap_text(
                f"{type_name}:", heading_font, equipment_width // 2 - 6
            )
        ]
        for equip_name, skill_name in items:
            block.extend(
                (line, body_font)
                for line in wrap_text(
                    f"{equip_name}: {skill_name}",
                    body_font,
                    equipment_width // 2 - 6,
                )
            )
        block.append(("", body_font))
        category_blocks.append(block)

    equipment_columns = [[], []]
    equipment_lengths = [0, 0]
    for block in sorted(category_blocks, key=len, reverse=True):
        column = 0 if equipment_lengths[0] <= equipment_lengths[1] else 1
        equipment_columns[column].append(block)
        equipment_lengths[column] += len(block)

    # Measure complete text first: no talent truncation or fixed-person limit.
    blocks = []
    for member in report_members(runner):
        lines = [(line, 0, (128, 0, 0)) for line in wrap_text(
            f"{member['name']} · {member['job']}", heading_font, left_width - 10)]
        for title, skills in (("个人天赋:", member['personal']), ("兵种天赋:", member['jobSkills'])):
            lines.append((title, 0, (0, 0, 0)))
            for skill in skills:
                lines.extend((line, 10, (0, 0, 0)) for line in wrap_text(skill, body_font, left_width - 20))
        blocks.append((member['name'], lines, max(130, len(lines) * 16 + 14)))
    member_overhead = member_content_top + member_content_bottom
    height = max(height, 24 + special_line_count * line_height,
                 24 + max(equipment_lengths, default=0) * line_height,
                 max((block[2] + member_overhead for block in blocks), default=0))
    member_columns = pack_member_columns(blocks, height - member_overhead)
    member_column_width = left_width
    left_width *= max(1, len(member_columns))
    width = left_width + special_width + equipment_width

    image = Image.new("RGB", (width, height), (232, 228, 222))
    draw = ImageDraw.Draw(image)

    def draw_crisp(position, text, font, fill) -> None:
        # Render the glyph mask without subpixel anti-aliasing. This keeps the
        # small Chinese text readable after the 5x3 result image is viewed
        # scaled down.
        x, y = position
        bbox = tuple(int(value) for value in draw.textbbox((0, 0), text, font=font))
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        if width <= 0 or height <= 0:
            return
        mask = Image.new("1", (width, height), 0)
        ImageDraw.Draw(mask).text(
            (-bbox[0], -bbox[1]), text, font=font, fill=1
        )
        ink = Image.new("RGB", mask.size, fill)
        image.paste(
            ink,
            (round(x + bbox[0]), round(y + bbox[1])),
            mask,
        )

    # The old tool used the exact primary colors below.  Keeping them exact
    # matters because the result grid is also used as a visual report.
    red = (255, 0, 0)
    blue = (0, 0, 255)
    # A flat neutral background keeps the small bitmap-style text crisp.
    draw.rectangle((2, 2, left_width - 1, height - 2), fill=(211, 211, 211))
    draw.rectangle((1, 1, width - 2, height - 2), outline=red, width=3)
    draw.line((left_width, 0, left_width, height), fill=blue, width=2)
    draw.line(
        (left_width + special_width, 0, left_width + special_width, height),
        fill=blue,
        width=2,
    )
    equipment_mid = left_width + special_width + (equipment_width - 1) // 2
    draw.line(
        (equipment_mid, 0, equipment_mid, height),
        fill=blue,
        width=2,
    )

    for column, blocks in enumerate(member_columns):
        x = column * member_column_width
        if column:
            draw.line((x, 0, x, height), fill=blue, width=2)
        top = member_content_top
        for _name, lines, block_height in blocks:
            draw.line((x + 2, top, x + member_column_width - 1, top), fill=(255, 255, 255), width=2)
            y = top + 5
            for text, indent, color in lines:
                draw_crisp((x + 5 + indent, y), text, font=body_font, fill=color)
                y += 16
            top += block_height

    special_y = 2
    for block in special_blocks:
        for text, font, color in block:
            draw_crisp(
                (left_width + 2, special_y),
                text,
                font=font,
                fill=color,
            )
            special_y += line_height

    equipment_column_width = equipment_width // 2
    for column_index, blocks in enumerate(equipment_columns):
        x = left_width + special_width + column_index * equipment_column_width
        y = 2
        for block in blocks:
            for text, font in block:
                draw_crisp(
                    (x + 2, y),
                    text,
                    font=font,
                    fill=(0, 0, 0),
                )
                y += line_height

    draw_crisp(
        (4, height - 19),
        f"save{save_slot}",
        font=heading_font,
        fill=red,
    )

    return image
