import unittest

from ccz_randomizer.equipment_labels import merge_equipment_frequencies


class EquipmentFrequencyMergeTests(unittest.TestCase):
    def test_mp_defense_values_merge_without_changing_input_or_other_flat_effects(self):
        rows = [('MP防御+10', 2), ('MP防御 + 20', 3), ('MP防御', 1),
                ('MP上限+10', 4), ('MP上限+20', 5), ('远距攻击-菱形3格', 1)]
        original = list(rows)
        self.assertEqual({'MP防御': 6, 'MP上限+10': 4, 'MP上限+20': 5, '远距攻击-菱形3格': 1},
                         dict(merge_equipment_frequencies(rows)))
        self.assertEqual(original, rows)

    def test_percentage_variants_sum_counts_and_leave_input_intact(self):
        rows = [('骑马克制20%', 3), ('骑马克制25%', 2),
                ('节约MP-10%', 4), ('节约MP-20%', 1)]
        original = list(rows)
        self.assertEqual([('节约MP', 5), ('骑马克制', 5)], merge_equipment_frequencies(rows))
        self.assertEqual(original, rows)

    def test_range_identifiers_strategies_and_non_percentage_values_stay_separate(self):
        rows = [('远程攻击3', 1), ('远程攻击16', 2), ('远距攻击3', 3), ('远距攻击16', 4),
                ('攻击追加-火阵', 1), ('攻击追加-龙卷', 2), ('MP上限+10', 1), ('MP上限+20', 1)]
        self.assertEqual(dict(rows), dict(merge_equipment_frequencies(rows)))
