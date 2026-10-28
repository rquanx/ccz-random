import json
from pathlib import Path
import unittest

from ccz_randomizer.recruitment import parse_recruits, filter_recruits
from ccz_randomizer.recruitment_catalog import load_catalog, attach_recruitment
from ccz_randomizer.workflow.recruitment import enable_recruitment, recruitment_enabled
from tools.research.recruitment_catalog import extract_stage_recruits

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/personnel_22"


class RecruitmentCatalogTests(unittest.TestCase):
    def test_real_script_assignments_match_all_catalog_stages(self):
        extracted = extract_stage_recruits((FIXTURES / "r99-stage-assignments.bin").read_bytes())
        actual = {stage["stageId"]: stage["recordIndices"] for stage in extracted}
        expected = {}
        catalog = load_catalog()
        for person in catalog:
            for stage in person["stages"]:
                expected.setdefault(stage["stageId"], []).append(person["recordIndex"])
        self.assertEqual(42, len(actual))
        self.assertEqual(116, len(catalog))
        self.assertEqual(126, sum(map(len, actual.values())))
        self.assertEqual({k: sorted(v) for k, v in actual.items()},
                         {k: sorted(v) for k, v in expected.items()})
        self.assertEqual([146, 147, 5], actual[0])
        self.assertEqual({205, 206, 207, 208, 209},
                         {p["recordIndex"] for p in catalog if p["fixedConfiguration"]})

    def test_real_title_record_can_be_bound_to_verified_stage_without_inventing_talents(self):
        title = json.loads((FIXTURES / "title.json").read_text(encoding="utf-8"))
        person = next(p for p in load_catalog() if p["recordIndex"] == 5)
        merged = attach_recruitment(title["personnel"], (person,))
        rows = parse_recruits(dict(title, personnel=merged))
        self.assertEqual("曹仁", rows[0].name)
        self.assertEqual(rows, filter_recruits(rows, stage="共通 · 颍川之战"))
        self.assertEqual((), filter_recruits(rows, stage="共通 · 虎牢关之战"))
        self.assertEqual(title["personnel"][5]["jobTalents"], merged[0]["jobTalents"])
        with self.assertRaises(ValueError):
            attach_recruitment(title["personnel"], (dict(person, name="错误人物"),))

    def test_truncated_real_script_fails_closed(self):
        data = (FIXTURES / "r99-stage-assignments.bin").read_bytes()
        with self.assertRaises(ValueError):
            extract_stage_recruits(data[:-3])


class RecruitmentChoiceTests(unittest.TestCase):
    def setUp(self):
        self.before = (FIXTURES / "recruitment-before.bin").read_bytes()
        self.after = (FIXTURES / "recruitment-after.bin").read_bytes()

    def test_first_choice_stops_only_after_real_enabled_marker(self):
        self.assertFalse(recruitment_enabled(self.before))
        self.assertTrue(recruitment_enabled(self.after))
        states = iter([self.before, self.before, self.after])
        actions = []
        enable_recruitment(read_state=lambda: next(states), start_dialogue=lambda: actions.append("npc"),
            advance_first_choice=lambda: actions.append("first"), check_stop=lambda: None)
        self.assertEqual(["npc", "first"], actions)

    def test_unconfirmed_choice_never_silently_succeeds(self):
        actions = []
        with self.assertRaises(RuntimeError):
            enable_recruitment(read_state=lambda: self.before, start_dialogue=lambda: None,
                advance_first_choice=lambda: actions.append(1), check_stop=lambda: None, max_steps=3)
        self.assertEqual(3, len(actions))

    def test_already_enabled_and_cancelled_do_not_click(self):
        def no_click():
            self.fail("不应继续点击")
        enable_recruitment(read_state=lambda: self.after, start_dialogue=no_click,
            advance_first_choice=no_click, check_stop=lambda: None)
        def stop():
            raise InterruptedError()
        with self.assertRaises(InterruptedError):
            enable_recruitment(read_state=lambda: self.before, start_dialogue=no_click,
                advance_first_choice=no_click, check_stop=stop)
