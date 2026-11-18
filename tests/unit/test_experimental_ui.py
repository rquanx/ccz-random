"""Verify hover reminders without extra labels or changes to entry actions."""
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import ttk
import unittest

from ccz_randomizer.ui.support_menu import show_support_menu
from ccz_randomizer.rules.config import default_rule_config, validate_rule_config, save_rule_config, load_rule_config


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class ExperimentalUiTests(unittest.TestCase):
    def test_support_hover_keeps_descriptions_and_actions_without_badges(self):
        root = tk.Tk()
        self.addCleanup(root.destroy)
        root.update()
        invoked = []
        keys = ('guide', 'effects', 'onboarding', 'diagnostics', 'sound', 'logs',
                'growth_patch', 'audio_patch', 'update', 'cleanup')
        actions = {key: lambda parent, key=key: invoked.append(key) for key in keys}
        dialog = show_support_menu(root, actions, 'test')
        root.update()
        buttons = {w.cget('text'): w for w in descendants(dialog) if isinstance(w, ttk.Button)}
        for name, key, description in (
            ('新手引导', 'onboarding', '高亮'),
            ('吃桃补丁', 'growth_patch', '高编号人物'),
            ('音效卡顿补丁', 'audio_patch', '释放策略卡顿'),
        ):
            button = buttons[name]
            self.assertFalse(hasattr(button, '_experimental_badge'))
            self.assertIn(description, button._tooltip.text)
            self.assertIn('尚未充分测试', button._tooltip.text)
            button._tooltip._show()
            root.update_idletasks()
            button._tooltip.hide()
            button.invoke()
            self.assertEqual(key, invoked[-1])
        self.assertFalse(hasattr(buttons['特效手册'], '_experimental_badge'))
        labels = [w.cget('text') for w in descendants(dialog) if isinstance(w, tk.Label)]
        self.assertFalse({'实验', 'test'} & set(labels))

    def test_old_collection_options_roundtrip_without_migration(self):
        for options in (None, {'recruitment': True, 'jobTalents': False},
                        {'recruitment': False, 'jobTalents': True, 'allRandomPersonnel': True}):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as directory:
                config = default_rule_config()
                profile = config['profiles']['默认规则']
                if options is None:
                    profile.pop('dataCollection')
                else:
                    profile['dataCollection'] = options.copy()
                normalized = validate_rule_config(config)
                expected = {'recruitment': False, 'jobTalents': False, 'allRandomPersonnel': False}
                expected.update(options or {})
                self.assertEqual(expected, normalized['profiles']['默认规则']['dataCollection'])
                save_rule_config(Path(directory), normalized)
                loaded = load_rule_config(Path(directory))
                self.assertEqual(expected, loaded.config['profiles']['默认规则']['dataCollection'])
