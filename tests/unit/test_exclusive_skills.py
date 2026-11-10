import unittest

from ccz_randomizer.rules.skill_defaults import EXCLUSIVE_SKILLS_22


class ExclusiveSkillsTest(unittest.TestCase):
    def test_22_exclusive_talents_are_marked(self):
        self.assertEqual(len(EXCLUSIVE_SKILLS_22), 11)
        self.assertIn("天人之勇", EXCLUSIVE_SKILLS_22)
        self.assertIn("古之恶来", EXCLUSIVE_SKILLS_22)
        self.assertNotIn("万里龙城", EXCLUSIVE_SKILLS_22)
        self.assertNotIn("步步为营", EXCLUSIVE_SKILLS_22)


if __name__ == "__main__":
    unittest.main()
