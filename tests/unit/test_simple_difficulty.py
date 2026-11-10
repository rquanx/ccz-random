import copy
import tempfile
import unittest
from pathlib import Path

from ccz_randomizer.rules.config import (
    active_profile, apply_simple_settings, default_rule_config,
    evaluate_job_rules, evaluate_skill_rules, validate_rule_config,
    save_rule_config, load_rule_config,
)
from ccz_randomizer.ui.result_details import format_result_detail


class SimpleDifficultyTests(unittest.TestCase):
    def test_editor_applies_level_and_marks_manual_threshold_custom(self):
        import tkinter as tk
        from tkinter import ttk
        from unittest.mock import patch
        from ccz_randomizer.rules.editor import show_rule_editor
        from tests.unit.test_rule_editor import descendants, JOB_MAP, TEAM_MEMBERS, SKILL_CATALOG

        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        config = default_rule_config()
        config['profiles']['测试规则'] = copy.deepcopy(active_profile(config))
        config['profiles']['测试规则']['builtin'] = False
        config['activeProfile'] = '测试规则'
        saved = []
        with tempfile.TemporaryDirectory() as directory, patch('ccz_randomizer.rules.editor.show_toast'):
            show_rule_editor(root, Path(directory), config, JOB_MAP, TEAM_MEMBERS, SKILL_CATALOG, saved.append)
            root.update()
            editor = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
            preset = next(w for w in descendants(editor) if isinstance(w, ttk.Combobox)
                          and tuple(w.cget('values')) == ('无要求', '宽松', '标准', '严格', '自定义'))
            preset.set('严格')
            preset.event_generate('<<ComboboxSelected>>')
            root.update()
            gate_combos = [w for w in descendants(editor) if isinstance(w, ttk.Combobox)
                           and '无要求' in w.cget('values') and '指定人数达标' in w.cget('values')]
            self.assertEqual(['指定人数达标'] * 2, [w.get() for w in gate_combos])
            gate_combos[0].set('平均分达标')
            root.update()
            self.assertEqual('自定义', preset.get())
            next(w for w in descendants(editor) if isinstance(w, tk.Button) and w.cget('text') == '保存规则').invoke()
            root.update()
        profile = active_profile(saved[0])
        self.assertEqual('average', profile['threePerson']['jobQualificationMode'])
        self.assertEqual('count', profile['skillQualification']['mode'])
        self.assertEqual('自定义', profile['simpleSettings']['difficulty'])

    def evaluate(self, config, job_scores, skill_scores):
        profile = active_profile(config)
        names = profile['threePerson']['qualifiedMembers']
        jobs = [dict(name=f'兵种{i}', score=score, type='WARRIOR')
                for i, score in enumerate(job_scores)]
        members = [dict(name=name, primaryType='NONE', secondaryType='NONE') for name in names]
        skills = {name: [f'特技{i}'] for i, name in enumerate(names)}
        profile['jobScoring']['affinityEnabled'] = False
        profile['sevenPerson']['skillBaseScores'] = {
            f'特技{i}': score for i, score in enumerate(skill_scores)
        }
        job = evaluate_job_rules(config, 'three', jobs, members)
        skill = evaluate_skill_rules(config, 0, skills, set(), set(), set(),
                                     qualification=profile['skillQualification'])
        return job, skill

    def test_default_has_no_score_gates_even_for_negative_scores(self):
        config = validate_rule_config(default_rule_config())
        job, skill = self.evaluate(config, [-10, -10, -10], [0, 0, 0])
        self.assertTrue(job.qualified)
        self.assertTrue(skill.qualified)
        detail = format_result_detail(dict(
            job=dict(qualified=True, metrics=job.metrics, members=[]),
            skill=dict(qualified=True, metrics=skill.metrics, members=[])))
        self.assertTrue(all('无要求' in s['explanation'] for s in detail['sections']))

    def test_levels_use_average_or_each_person_as_documented(self):
        for level, jobs, skills, expected in (
            ('宽松', [7.1]*3, [0]*3, (True, True)),
            ('宽松', [7.0]*3, [100]*3, (False, True)),
            ('标准', [7.0, 7.6, 7.6], [1, 2, 2], (True, True)),
            ('标准', [8]*3, [1]*3, (True, False)),
            ('严格', [7.6, 10, 10], [2]*3, (False, True)),
            ('严格', [8]*3, [1, 10, 10], (True, False)),
            ('严格', [8]*3, [2]*3, (True, True)),
        ):
            with self.subTest(level=level, jobs=jobs, skills=skills):
                config = default_rule_config()
                profile = active_profile(config)
                profile['simpleSettings']['difficulty'] = level
                apply_simple_settings(profile)
                results = self.evaluate(validate_rule_config(config), jobs, skills)
                self.assertEqual(expected, tuple(r.qualified for r in results))
                if level == '宽松' and expected[0]:
                    detail = format_result_detail({'job': dict(
                        qualified=True, metrics=results[0].metrics, members=[])})
                    self.assertIn('已达标', detail['sections'][0]['explanation'])

    def test_preset_preserves_people_affinity_scores_and_image(self):
        profile = active_profile(default_rule_config())
        profile['threePerson']['qualifiedMembers'] = ['曹操']
        before = copy.deepcopy(profile)
        profile['simpleSettings']['difficulty'] = '严格'
        apply_simple_settings(profile)
        self.assertEqual(1, profile['threePerson']['minQualifiedCount'])
        self.assertEqual(1, profile['skillQualification']['requiredCount'])
        self.assertEqual(['曹操'], profile['threePerson']['qualifiedMembers'])
        for key in ('jobScoring', 'memberAffinity', 'resultImage', 'sevenPerson', 'dataCollection'):
            self.assertEqual(before[key], profile[key])

    def test_existing_rule_keeps_its_active_thresholds_after_load(self):
        config = default_rule_config()
        profile = active_profile(config)
        profile['simpleSettings'].pop('difficulty')
        profile['threePerson'].update(jobQualificationMode='average', minJobAverage=8.25)
        profile['skillQualification'].update(mode='total', threshold=9)
        with tempfile.TemporaryDirectory() as temporary:
            save_rule_config(Path(temporary), config)
            restored = active_profile(load_rule_config(Path(temporary)).config)
        self.assertEqual('自定义', restored['simpleSettings']['difficulty'])
        apply_simple_settings(restored)
        self.assertEqual(profile['threePerson'], restored['threePerson'])
        self.assertEqual(profile['skillQualification'], restored['skillQualification'])
