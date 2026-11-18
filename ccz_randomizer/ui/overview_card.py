"""Read-only round results drawn without one native window per paragraph."""
from ccz_randomizer.ui.text_block import TextBlock, shared_font


def result_card(parent, snapshot):
    from ccz_randomizer.ui.history import COLORS, FONT, _score, _metrics, _skill_names
    from ccz_randomizer.history_members import history_members
    from ccz_randomizer.history import SUMMARY_MEMBER_LIMIT
    from ccz_randomizer.ui.history import SPECIAL_COLORS
    card = TextBlock(parent, background=COLORS['surface'], width=360, padding=10)
    card.configure(highlightthickness=1, highlightbackground=COLORS['border'])
    normal = shared_font(card, FONT, 8)
    bold = shared_font(card, FONT, 9, 'bold')
    job, skill = _metrics(snapshot)
    blocks = [(f"存档 {snapshot.get('slot', '-')} · 第 {snapshot.get('acceptedAttempt', '-')} 次尝试",
               bold, '#FFFFFF', 12),
              (f"兵种 {_score(job.get('average'))}    特技 {_score(skill.get('skillScore'))}",
               bold, COLORS['blue'], 12)]
    members = history_members(snapshot)
    for member in members[:SUMMARY_MEMBER_LIMIT]:
        blocks.extend(((f"{member.get('name', '未知')} · {member.get('job', '未知兵种')}  {_score(member.get('jobScore'))}",
                        bold, COLORS['red'], 3),
                       ('个人  '+_skill_names(member.get('personalSkills') or [])+'\n兵种  '+
                        _skill_names(member.get('jobSkills') or []), normal, COLORS['ink'], 9)))
    if len(members) > SUMMARY_MEMBER_LIMIT:
        blocks.append((f'……其余 {len(members)-SUMMARY_MEMBER_LIMIT} 人请查看完整详情', normal, COLORS['muted'], 8))
    equipment = snapshot.get('equipment') or {}
    blocks.append(('宝物特殊组合', bold, COLORS['red'], 5))
    specials = equipment.get('specials') or []
    if not specials:
        blocks.append(('无', normal, COLORS['muted'], 6))
    for index, special in enumerate(specials):
        blocks.append((str(special.get('title', ''))+'\n'+'\n'.join('  '+str(v) for v in special.get('items') or []),
                       normal, SPECIAL_COLORS[index % len(SPECIAL_COLORS)], 8))
    blocks.append(('宝物列表', bold, COLORS['green'], 5))
    for category in equipment.get('categories') or []:
        blocks.append((str(category.get('name', '其他'))+'\n'+'\n'.join(
            f"  {item.get('name', '')}  {item.get('effect', '')}" for item in category.get('items') or []),
            normal, COLORS['ink'], 8))
    card.set(blocks)
    background = card.create_rectangle(0, 0, 10000, 36, fill=COLORS['ink'], outline='')
    card.tag_lower(background)
    return card
