"""Replay the real 1104 roll, saved preview, and reloaded process memory."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ccz_randomizer import app
from ccz_randomizer.entry_catalog import attach_fixed_entries
from ccz_randomizer.fixed_members import fixed_member_indices
from ccz_randomizer.recruitment_catalog import load_catalog, attach_recruitment
from ccz_randomizer.rule_members import rule_member_indices, required_data_collection, validate_profile_members
from ccz_randomizer.rules.config import active_profile
from ccz_randomizer.rules.skill_scores import DEFAULT_SCORES, DEFAULT_TYPES
from ccz_randomizer.runtime.personnel_memory import read_personnel, read_rule_job_ids
from ccz_randomizer.runtime.skill_memory import read_skill_memory
from ccz_randomizer.runtime.job_talents import read_job_talents
from ccz_randomizer.ui.result_image import report_members
from tools.diagnostics.smoke_recruitment_22 import diagnostic_rules

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures/personnel_220_1104'
VERSION = '2.20-1104'


class Recorded1104Reader:
    def __init__(self, _pid):
        raw = json.loads((FIXTURES / 'randomized-memory.json').read_text(encoding='utf-8'))
        self.spans = [(int(key.split(':')[0]), bytes.fromhex(value)) for key, value in raw.items()]

    def __enter__(self): return self
    def __exit__(self, *_args): pass

    def read(self, address, size):
        for base, data in self.spans:
            if base <= address and address + size <= base + len(data):
                return data[address-base:address-base+size]
        raise AssertionError(f'未采集范围：{address:x} / {size}')


class Skills1104Tests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, CCZ_GAME_VERSION=VERSION)
        env.start()
        self.addCleanup(env.stop)
        self.result = json.loads((FIXTURES / 'randomized-result.json').read_text(encoding='utf-8'))

    def load_members(self, rules):
        app.skill_score_catalog()
        import task.CczReRandTask as task_module
        with patch('ccz_randomizer.runtime.personnel_memory.read_rule_job_ids',
                   side_effect=lambda pid, positions: read_rule_job_ids(pid, positions, reader_factory=Recorded1104Reader)), \
             patch.object(app, 'read_skill_memory', side_effect=lambda *a, **k: read_skill_memory(*a, **k, reader_factory=Recorded1104Reader)):
            members = app.load_selected_rule_members(task_module, 0, rules)
        return task_module, members

    def test_every_effective_talent_name_and_parameter_matches_editor_catalog(self):
        snapshot = read_skill_memory(0, [0], reader_factory=Recorded1104Reader)
        rows = app.runtime_skill_catalog_rows()
        self.assertEqual(240, len(rows))
        for row in rows:
            skill = snapshot.catalog[row['id']]
            self.assertEqual((row['name'], row['baseName'], row['formatType'], row['parameter']),
                             (skill.display_name, skill.base_name, skill.format_type, skill.parameter))
        editor_rows = app.skill_score_catalog()
        for name, score, category, kind in editor_rows:
            self.assertEqual(DEFAULT_SCORES[name], score, name)
            self.assertEqual(DEFAULT_TYPES[name], 'NONE' if category == '特殊' else kind, name)
        editor = {row[0] for row in editor_rows}
        used = {s for p in self.result['personnel']+self.result['fixedPersonnel']
                for s in p['personalTalents']+p['jobTalents']}
        self.assertFalse(used - editor)

    def test_all_143_jobs_and_talents_replay_saved_preview(self):
        catalog = load_catalog()
        candidates = attach_recruitment(read_personnel(0, [p['recordIndex'] for p in catalog],
            planned=True, fixed_indices=[p['recordIndex'] for p in catalog if p['fixedConfiguration']],
            reader_factory=Recorded1104Reader), catalog)
        fixed = attach_fixed_entries(read_personnel(0, fixed_member_indices().values(), planned=True,
            reader_factory=Recorded1104Reader))
        guanyu = next(p for p in fixed if p['name'] == '关羽')
        self.assertEqual(15, guanyu['jobId'])
        self.assertEqual(['每回合恢复MP 8', '策略绝对命中'], guanyu['personalTalents'])
        # The recorded UI preview predates the catalog fix and omitted Guan Yu.
        fixed = [p for p in fixed if p['recordIndex'] != 3]
        keys = ('name', 'recordIndex', 'jobId', 'jobTalents', 'personalTalents')
        self.assertEqual([{k: p[k] for k in keys} for p in self.result['personnel']+self.result['fixedPersonnel']],
                         [{k: p[k] for k in keys} for p in candidates+fixed])
        self.assertEqual(self.result['jobTalents'], read_job_talents(0, reader_factory=Recorded1104Reader))
        self.assertEqual(40, len(self.result['jobTalents']))

    def test_live_type_matching_and_default_scores_replay_exactly(self):
        rules = diagnostic_rules(VERSION, all_members=True)
        active_profile(rules)['threePerson']['qualifiedMembers'] = [
            name for name in active_profile(rules)['threePerson']['qualifiedMembers'] if name != '关羽']
        task, members = self.load_members(rules)
        evaluation = app.evaluate_task_skill_rules(rules, task, members, 0)
        self.assertEqual(143, len(members))
        expected = self.result['detail']['skill']['metrics']
        self.assertEqual(expected['memberSkillScores'], evaluation.metrics['memberSkillScores'])
        self.assertEqual(expected['skillDetails'], evaluation.metrics['skillDetails'])
        self.assertEqual(expected['skillScore'], evaluation.metrics['skillScore'])

    def test_new_members_obey_nonzero_skill_thresholds_in_all_modes(self):
        selected = ['曹昂', '邓艾', '曹纯', '陈到', '曹仁', '荀攸', '貂蝉']
        rules = diagnostic_rules(VERSION, members=selected)
        task, members = self.load_members(rules)
        profile = active_profile(rules)
        profile['sevenPerson']['skillTypeMatchingEnabled'] = False
        profile['sevenPerson']['skillBaseScores'] = {s.name: 2 for m in members for s in m.skillList}
        totals = [2 * len(m.skillList) for m in members]
        self.assertTrue(all(totals))
        for mode, boundary in [('total', sum(totals)), ('average', sum(totals)/len(totals)), ('count', min(totals))]:
            profile['skillQualification'].update(mode=mode, threshold=boundary, requiredCount=len(selected))
            self.assertTrue(app.evaluate_task_skill_rules(rules, task, members, 0).qualified, mode)
            profile['skillQualification']['threshold'] = boundary + .1
            self.assertFalse(app.evaluate_task_skill_rules(rules, task, members, 0).qualified, mode)

    def test_custom_image_collects_people_even_with_optional_collection_disabled(self):
        names = ['曹昂', '邓艾', '貂蝉']
        rules = diagnostic_rules(VERSION, image_members=names)
        profile = active_profile(rules)
        self.assertFalse(profile['dataCollection']['recruitment'])
        self.assertTrue(required_data_collection(profile)['recruitment'])
        # The saved preference remains off; the current result supplies actual data.
        self.assertFalse(profile['dataCollection']['recruitment'])
        runner = SimpleNamespace(_result_image_settings=profile['resultImage'],
            _personnel_snapshot=self.result['personnel'], _fixed_personnel_snapshot=self.result['fixedPersonnel'])
        rows = report_members(runner)
        self.assertEqual(names, [p['name'] for p in rows])
        for row in rows:
            source = next(p for p in self.result['personnel']+self.result['fixedPersonnel'] if p['name']==row['name'])
            self.assertEqual(source['personalTalents'], row['personal'])
            self.assertEqual(source['jobTalents'], row['jobSkills'])
        with self.assertRaisesRegex(ValueError, '曹昂.*邓艾'):
            validate_profile_members(profile, '2.2')

    def test_diagnostic_defaults_really_exercise_collection_and_skill_gate(self):
        profile = active_profile(diagnostic_rules(VERSION, all_members=True))
        self.assertTrue(profile['dataCollection']['recruitment'])
        self.assertTrue(profile['dataCollection']['jobTalents'])
        self.assertEqual('count', profile['skillQualification']['mode'])
        self.assertEqual(list(rule_member_indices(VERSION)), profile['threePerson']['qualifiedMembers'])
