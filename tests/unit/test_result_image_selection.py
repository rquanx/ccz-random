import copy
import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from ccz_randomizer.rules.config import default_rule_config, validate_rule_config, save_rule_config, load_rule_config, build_rule_export, merge_rule_export
from ccz_randomizer.rules.editor import show_rule_editor
from ccz_randomizer.ui.result_image import report_members
from tests.unit.test_result_image_layout import recorded_runner, FIXTURES
from tests.unit.test_rule_editor import JOB_MAP, TEAM_MEMBERS, SKILL_CATALOG, descendants


def custom_config():
    config = default_rule_config()
    profile = copy.deepcopy(config['profiles']['默认规则'])
    profile.update(builtin=False, editorMode='advanced')
    profile['threePerson'].update(qualifiedMembers=['张宝'], minQualifiedCount=1)
    profile['resultImage'] = {'mode':'custom', 'members':['曹操', '典韦']}
    config['profiles']['图片独立'] = profile
    config['activeProfile'] = '图片独立'
    return config


class ResultImageSelectionTests(unittest.TestCase):
    def test_old_rules_follow_scored_people(self):
        config=custom_config()
        del config['profiles']['图片独立']['resultImage']
        normalized=validate_rule_config(config)
        self.assertEqual({'mode':'selected','members':[]}, normalized['profiles']['图片独立']['resultImage'])

    def test_display_choice_roundtrips_without_changing_scoring(self):
        config=custom_config()
        with tempfile.TemporaryDirectory() as folder:
            save_rule_config(Path(folder),config)
            loaded=load_rule_config(Path(folder)).config
        profile=loaded['profiles']['图片独立']
        self.assertEqual(['张宝'],profile['threePerson']['qualifiedMembers'])
        self.assertEqual(['曹操','典韦'],profile['resultImage']['members'])
        exported=build_rule_export(loaded, ['图片独立'])
        imported,names=merge_rule_export(default_rule_config(),exported)
        self.assertEqual(profile['resultImage'],imported['profiles'][names[0]]['resultImage'])

    def test_custom_image_uses_current_unscored_personnel(self):
        runner=recorded_runner(1)
        runner._result_image_settings={'mode':'custom','members':['曹操','典韦']}
        runner._fixed_personnel_snapshot=json.loads((FIXTURES/'randomized-fixed-personnel.json').read_text(encoding='utf-8'))
        for row in runner._fixed_personnel_snapshot:
            row['job']=JOB_MAP[row['jobId']][0]
        rows=report_members(runner)
        self.assertEqual(['曹操','典韦'],[row['name'] for row in rows])
        for row in rows:
            source=next(x for x in runner._fixed_personnel_snapshot if x['name']==row['name'])
            self.assertEqual(source['job'],row['job'])
            self.assertEqual(source['personalTalents'],row['personal'])
        self.assertEqual('张宝',runner._scored_members[0].name)
        runner._result_image_settings['members']=['张宝']
        with self.assertRaisesRegex(ValueError,'张宝'):
            report_members(runner)

    def test_empty_custom_selection_is_rejected(self):
        config=custom_config()
        config['profiles']['图片独立']['resultImage']['members']=[]
        with self.assertRaisesRegex(ValueError,'至少选择'):
            validate_rule_config(config)

    def test_editor_saves_image_selection_independently(self):
        root=tk.Tk();root.withdraw()
        saved=[]
        try:
            with tempfile.TemporaryDirectory() as folder, patch('rule_editor.show_toast'):
                show_rule_editor(root,Path(folder),custom_config(),JOB_MAP,TEAM_MEMBERS,SKILL_CATALOG,saved.append)
                root.update()
                editor=next(w for w in root.winfo_children() if isinstance(w,tk.Toplevel))
                next(w for w in descendants(editor) if isinstance(w,tk.Button) and w.cget('text').startswith('结果图人物')).invoke()
                root.update()
                dialog=next(w for w in descendants(editor) if isinstance(w,tk.Toplevel) and w.title()=='结果图人物')
                next(w for w in descendants(dialog) if isinstance(w,tk.Button) and w.cget('text')=='清空选择').invoke()
                next(w for w in descendants(dialog) if isinstance(w,tk.Checkbutton) and w.cget('text')=='曹操').invoke()
                next(w for w in descendants(dialog) if isinstance(w,tk.Button) and w.cget('text')=='确定').invoke()
                next(w for w in descendants(editor) if isinstance(w,tk.Button) and w.cget('text')=='保存规则').invoke()
                self.assertEqual(1,len(saved))
                profile=load_rule_config(Path(folder)).config['profiles']['图片独立']
                self.assertEqual(['曹操'],profile['resultImage']['members'])
                self.assertEqual(['张宝'],profile['threePerson']['qualifiedMembers'])
        finally:
            for callback in root.tk.call('after','info'):
                root.after_cancel(callback)
            root.destroy()
