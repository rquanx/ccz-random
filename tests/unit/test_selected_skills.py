import os
from ccz_randomizer.ui.inputs import TextEntry
import json
import unittest
from unittest.mock import patch

from ccz_randomizer import app
from ccz_randomizer.rules.config import default_rule_config, active_profile, validate_rule_config, evaluate_skill_rules
from ccz_randomizer.runtime.skill_memory import read_skill_memory
from ccz_randomizer.runtime.personnel_memory import read_rule_job_ids
from ccz_randomizer.ui.result_details import format_result_detail
from tests.unit.test_personnel_memory import RecordedReader, FIXTURES


class SelectedSkillTests(unittest.TestCase):
    def setUp(self):
        version = patch.dict(os.environ, CCZ_GAME_VERSION="2.2")
        version.start()
        self.addCleanup(version.stop)

    def test_editor_saves_independent_gates_for_shared_selection(self):
        import copy
        import tempfile
        import tkinter as tk
        from tkinter import ttk
        from pathlib import Path
        from ccz_randomizer.rules.editor import show_rule_editor
        from tests.unit.test_rule_editor import descendants, SKILL_CATALOG
        config = default_rule_config()
        config['profiles']['张宝规则'] = copy.deepcopy(active_profile(config))
        config['activeProfile'] = '张宝规则'
        profile = active_profile(config)
        profile.update(builtin=False, editorMode='advanced')
        profile['dataCollection']['allRandomPersonnel'] = True
        profile['threePerson'].update(qualifiedMembers=['张宝'], minQualifiedCount=1, minJobAverage=8)
        root = tk.Tk()
        self.addCleanup(root.destroy)
        saved = []
        with tempfile.TemporaryDirectory() as directory, patch('ccz_randomizer.rules.editor.show_toast'):
            show_rule_editor(root, Path(directory), config, app.JOB_MAP, app.TEAM_MEMBERS, SKILL_CATALOG, saved.append)
            root.update()
            editor = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
            chooser = next(w for w in descendants(editor) if isinstance(w, tk.Button) and w.cget('text') == '选择人物（1/130）')
            label = next(w for w in descendants(editor) if isinstance(w, tk.Label) and w.cget('text') == '人物设置')
            self.assertLessEqual(abs((chooser.winfo_rooty() + chooser.winfo_height() / 2)
                - (label.winfo_rooty() + label.winfo_height() / 2)), 1)
            affinity = next(w for w in descendants(editor) if isinstance(w, tk.Button) and w.cget('text') == '设置人物倾向')
            self.assertEqual(chooser.winfo_rooty(), affinity.winfo_rooty())
            self.assertGreaterEqual(affinity.winfo_rootx(), chooser.winfo_rootx() + chooser.winfo_width())
            chooser.invoke()
            root.update()
            selection = next(w for w in descendants(editor) if isinstance(w, tk.Toplevel) and w.title() == '选择人物')
            checks = [w for w in descendants(selection) if isinstance(w, tk.Checkbutton)]
            self.assertEqual(42, len(checks))
            self.assertEqual(set(range(7)), {int(w.grid_info()['column']) for w in checks})
            self.assertTrue(all(w.winfo_x() + w.winfo_width() <= w.master.winfo_width() for w in checks))
            next(w for w in descendants(selection) if isinstance(w, tk.Button) and w.cget('text') == '取消').invoke()
            root.update()
            mode = next(w for w in descendants(editor) if isinstance(w, ttk.Combobox) and tuple(w.cget('values')) == ('无要求', '指定人数达标', '平均分达标', '总分达标') and int(w.grid_info()['row']) == 2)
            mode.set('平均分达标')
            mode.event_generate('<<ComboboxSelected>>')
            threshold = next(w for w in descendants(editor) if isinstance(w, tk.Label) and w.cget('text') == '特技合格分')
            entry = next(w for w in threshold.master.grid_slaves(row=2, column=1) if isinstance(w, TextEntry))
            entry.delete(0, 'end')
            entry.insert(0, '2.5')
            next(w for w in descendants(editor) if isinstance(w, tk.Button) and w.cget('text') == '保存规则').invoke()
            root.update()
        result = active_profile(saved[0])
        self.assertEqual(['张宝'], result['threePerson']['qualifiedMembers'])
        self.assertEqual(8, result['threePerson']['minJobAverage'])
        self.assertEqual(dict(mode='average', threshold=2.5, requiredCount=1, specialSkillAutoPass=False), result['skillQualification'])

    def test_only_selected_person_is_read_with_planned_job_and_real_talents(self):
        app.install(app.bundle_root())
        import task.CczReRandTask as task_module
        rules = default_rule_config()
        active_profile(rules)['threePerson']['qualifiedMembers'] = ['张宝']
        with patch('ccz_randomizer.runtime.personnel_memory.read_rule_job_ids',
                   side_effect=lambda pid, positions: read_rule_job_ids(pid, positions, reader_factory=RecordedReader)), \
             patch.object(app, 'read_skill_memory', side_effect=lambda pid, positions, **kwargs:
                   read_skill_memory(pid, positions, reader_factory=RecordedReader, **kwargs)):
            members = app.load_selected_rule_members(task_module, 0, rules)
        expected = next(p for p in json.loads((FIXTURES / 'randomized-personnel.json').read_text(encoding='utf-8')) if p['name'] == '张宝')
        self.assertEqual(['张宝'], [m.name for m in members])
        self.assertEqual(expected['personalTalents'] + expected['jobTalents'], [s.name for s in members[0].skillList])
        active_profile(rules)['skillQualification'].update(mode='total', threshold=100)
        result = app.evaluate_task_skill_rules(rules, task_module, members, 20)
        self.assertFalse(result.qualified)
        self.assertEqual('', result.metrics['autoPassReason'])
        self.assertEqual(['张宝'], list(result.metrics['memberSkillScores']))
        view = format_result_detail(dict(mode='three', skill=app.skill_result_detail(result, members)))
        self.assertEqual('特技评分', view['sections'][0]['title'])
        self.assertEqual(1, len(view['sections'][0]['rows']))
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        runner = SimpleNamespace(_result_outcome='accepted', _three_person_mode=True,
            _scored_members=members, _team_members=[SimpleNamespace(name='曹操', skillList=[])],
            _skill_evaluation_detail=app.skill_result_detail(result, members))
        with tempfile.TemporaryDirectory() as directory:
            snapshot = app.build_history_result_snapshot(runner, result_slot=1, accepted_attempt=1,
                round_number=1, equip_info=None, save_path=Path(directory) / 'missing.E5S')
        self.assertEqual(['张宝'], [m['name'] for m in snapshot['members']])
        self.assertEqual(expected['personalTalents'], [s['name'] for s in snapshot['members'][0]['personalSkills']])

    def test_three_independent_modes_and_no_automatic_bypass(self):
        people = json.loads((FIXTURES / 'randomized-personnel.json').read_text(encoding='utf-8'))[:2]
        skills = {p['name']: p['personalTalents'] + p['jobTalents'] for p in people}
        names = {s for values in skills.values() for s in values}
        config = default_rule_config()
        profile = active_profile(config)
        profile['sevenPerson']['skillBaseScores'] = {name: 2 for name in names}
        totals = [len(items) * 2 for items in skills.values()]
        for mode, boundary in [('total', sum(totals)), ('average', sum(totals) / 2), ('count', min(totals))]:
            for threshold, passes in [(boundary, True), (boundary + 0.1, False)]:
                gate = dict(mode=mode, threshold=threshold, requiredCount=2)
                result = evaluate_skill_rules(config, 20, skills, names, set(), names,
                    qualification=gate, effective_skills_by_member=skills)
                self.assertEqual(passes, result.qualified, (mode, threshold))
                self.assertEqual('', result.metrics['autoPassReason'])
        # Equal named skills on different people retain their own type eligibility.
        name = next(iter(names))
        result = evaluate_skill_rules(config, 20, {'张宝': [name], '曹操': [name]}, {name}, set(), set(),
            qualification=dict(mode='total', threshold=2, requiredCount=1),
            effective_skills_by_member={'张宝': [], '曹操': [name]})
        self.assertEqual({'张宝': 0, '曹操': 2}, result.metrics['memberSkillScores'])

    def test_old_selection_and_skill_threshold_are_migrated_without_silent_bypass(self):
        config = default_rule_config()
        profile = active_profile(config)
        del profile['skillQualification']
        profile['threePerson'].update(qualifiedMembers=['张宝'], minQualifiedCount=1)
        profile['sevenPerson']['lowMinSkillScore'] = 3
        migrated = active_profile(validate_rule_config(config))
        self.assertEqual(['张宝'], migrated['threePerson']['qualifiedMembers'])
        self.assertEqual(dict(mode='total', threshold=3, requiredCount=1), migrated['skillQualification'])
