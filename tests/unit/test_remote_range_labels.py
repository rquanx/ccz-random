"""Complete remote ranges from the read-only native table, including ID 14."""
import copy
import json
from pathlib import Path
import unittest

from ccz_randomizer import app
from ccz_randomizer.equipment_labels import (
    equipment_display, equipment_label_resolver, merge_equipment_frequencies,
)
from ccz_randomizer.ui.equipment import EquipmentSearch


FIXTURE = Path(__file__).resolve().parents[1] / 'fixtures/remote_ranges_1104.json'


class RemoteRangeLabelTests(unittest.TestCase):
    def test_every_native_range_keeps_id_and_mapped_name(self):
        fixture = json.loads(FIXTURE.read_text('utf-8'))
        self.assertEqual(list(range(38)), [r['parameter'] for r in fixture['entries']])
        self.assertTrue(fixture['boundsBytes'].startswith('3c25'))
        resolve = equipment_label_resolver()
        for row in fixture['entries']:
            code, name = row['parameter'], row['name']
            expected = f'远距攻击{code}({name})'
            with self.subTest(code=code):
                self.assertEqual(expected, app.decode_equipment_effect(0x32, code))
                for old in (f'远距攻击{code}', f'远程攻击 {code}', f'远距攻击-{name}', expected):
                    self.assertEqual(expected, resolve(old))
        self.assertEqual('远距攻击255', resolve('远距攻击255'))

    def test_14_and_15_names_describe_the_recorded_outer_edges(self):
        entries = {r['parameter']: r for r in json.loads(FIXTURE.read_text('utf-8'))['entries']}
        for code, half_width in ((14, 1), (15, 2)):
            row = entries[code]
            points = set()
            for x, y in row['pairs']:
                points.update((sx*x, sy*y) for sx in (-1, 1) for sy in (-1, 1))
                if y == 0:
                    points.update((0, sign*x) for sign in (-1, 1))
            expected = {(x, y) for x in range(-3, 4) for y in range(-3, 4)
                        if max(abs(x), abs(y)) == 3 and min(abs(x), abs(y)) <= half_width}
            self.assertEqual(expected, points)
            self.assertEqual(12 if code == 14 else 20, len(points))

    def test_old_equipment_snapshots_resolve_and_search_without_mutation(self):
        equipment = {'specials': [], 'categories': [{'name': '剑', 'items': [
            {'name': '倚天剑', 'effect': '远距攻击14'},
            {'name': '雌雄双剑', 'effect': '远距攻击-大没羽'}]}]}
        original = copy.deepcopy(equipment)
        displayed = equipment_display(equipment)
        self.assertEqual('远距攻击14(3格外框·窄边)', displayed['categories'][0]['items'][0]['effect'])
        self.assertEqual('远距攻击12(大没羽)', displayed['categories'][0]['items'][1]['effect'])
        for query in ('远距攻击14', '窄边', '14 窄边'):
            self.assertEqual([displayed['categories'][0]['items'][0]],
                EquipmentSearch(equipment).search(query)['categories'][0]['items'])
        self.assertEqual(original, equipment)

    def test_frequency_merge_keeps_different_range_ids_separate(self):
        rows = [('远距攻击14(3格外框·窄边)', 3), ('远距攻击15(3格外框·去角)', 2)]
        self.assertEqual(dict(rows), dict(merge_equipment_frequencies(rows)))
