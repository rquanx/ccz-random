"""Validate declarative handbook data supplied by a game profile."""
import re


def validate_effect_dictionary(data, manifest):
    def fail():
        raise ValueError("特效手册数据格式无效")

    def text(value, *, empty=False):
        if not isinstance(value, str) or len(value) > 20000 or (not empty and not value.strip()):
            fail()

    if (data.get('schemaVersion') != 1
            or data.get('profileId') != manifest['profileId']
            or data.get('gameVersion') != manifest['gameVersion']
            or not isinstance(data.get('catalogHash'), str)
            or not re.fullmatch('[0-9a-f]{64}', data['catalogHash'])):
        fail()
    skills, equipment = data.get('skills'), data.get('equipment')
    if not isinstance(skills, list) or not isinstance(equipment, dict):
        fail()
    ids = set()
    for row in skills:
        if not isinstance(row, dict) or type(row.get('id')) is not int or not 0 <= row['id'] <= 65535 or row['id'] in ids:
            fail()
        ids.add(row['id'])
        for key in ('name', 'baseName', 'description'):
            text(row.get(key), empty=key == 'description')
    for code, row in equipment.items():
        if not isinstance(code, str) or not re.fullmatch(r'\d{1,5}', code) or not isinstance(row, dict):
            fail()
        text(row.get('name'))
        text(row.get('description'))
    rules = data.get('mergeRules')
    if not isinstance(rules, dict) or set(rules) != {'equivalences', 'nameOverrides'}:
        fail()
    equivalences, overrides = rules['equivalences'], rules['nameOverrides']
    if not isinstance(equivalences, dict) or not isinstance(overrides, dict):
        fail()
    merged = set()
    for code, members in equivalences.items():
        if code not in equipment or not isinstance(members, list) or not members:
            fail()
        for member in members:
            if type(member) is not int or member not in ids or member in merged:
                fail()
            merged.add(member)
    keys = {f'skill:{i}' for i in ids} | {f'equipment:{code}' for code in equipment}
    for key, name in overrides.items():
        if key not in keys:
            fail()
        text(name)
