"""Reused personnel dialogs must discard drafts and apply current callbacks."""
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

from ccz_randomizer.rule_members import RULE_MEMBER_NAMES
from ccz_randomizer.ui.member_pages import MemberPages
from ccz_randomizer.ui.member_picker import show_member_picker


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class MemberPickerTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('980x680')
        self.root.update()
        self.addCleanup(self.root.destroy)

    def picker(self, selected, callback, names=RULE_MEMBER_NAMES, **options):
        dialog = show_member_picker(self.root, names, selected, callback,
            cache_key='test', title='选择人物', description='所选人物同时参与兵种和特技判断', **options)
        self.root.update()
        return dialog

    def button(self, dialog, text):
        return next(w for w in descendants(dialog) if isinstance(w, ttk.Button) and w.cget('text') == text)

    def test_cancelled_draft_search_and_page_reset_and_new_callback_is_used(self):
        original, current = Mock(), Mock()
        dialog = self.picker([RULE_MEMBER_NAMES[0]], original)
        checks = [w for w in descendants(dialog) if isinstance(w, ttk.Checkbutton)]
        pages = next(w for w in descendants(dialog) if isinstance(w, MemberPages))
        checks[0].invoke()
        pages.move(1)
        checks[0].invoke()
        pages.query.set(RULE_MEMBER_NAMES[-1])
        self.root.update()
        self.button(dialog, '取消').invoke()
        self.assertFalse(dialog.winfo_ismapped())
        self.assertIsNone(self.root.grab_current())
        reopened = self.picker([RULE_MEMBER_NAMES[1]], current)
        self.assertIs(dialog, reopened)
        self.assertEqual(checks, [w for w in descendants(dialog) if isinstance(w, ttk.Checkbutton)])
        self.assertEqual('', pages.query.get())
        self.assertEqual(0, pages.page)
        self.button(dialog, '确认').invoke()
        original.assert_not_called()
        current.assert_called_once_with('custom', [RULE_MEMBER_NAMES[1]])

    def test_follow_mode_and_empty_choice_guard_survive_reopening(self):
        apply = Mock()
        dialog = self.picker([RULE_MEMBER_NAMES[0]], apply, follow_mode='selected')
        checks = [w for w in descendants(dialog) if isinstance(w, ttk.Checkbutton)]
        self.assertTrue(checks[0].instate(('disabled',)))
        self.button(dialog, '清空选择').invoke()
        with patch('ccz_randomizer.ui.member_picker.messages.showwarning') as warning:
            self.button(dialog, '确认').invoke()
            warning.assert_called_once()
        apply.assert_not_called()
        self.assertTrue(dialog.winfo_ismapped())
        checks[0].invoke()
        self.button(dialog, '确认').invoke()
        apply.assert_called_once_with('custom', [RULE_MEMBER_NAMES[0]])
        reopened = self.picker([RULE_MEMBER_NAMES[1]], Mock(), follow_mode='selected')
        self.assertIs(dialog, reopened)
        self.assertTrue(checks[0].instate(('disabled',)))

    def test_catalog_change_rebuilds_and_close_restores_parent_modal_ownership(self):
        self.root.grab_set()
        dialog = self.picker([RULE_MEMBER_NAMES[0]], Mock())
        self.button(dialog, '取消').invoke()
        self.assertIs(self.root, self.root.grab_current())
        replacement = self.picker([RULE_MEMBER_NAMES[-1]], Mock(), names=RULE_MEMBER_NAMES[-3:])
        self.assertFalse(dialog.winfo_exists())
        self.assertIsNot(dialog, replacement)
        self.button(replacement, '取消').invoke()
        self.assertIs(self.root, self.root.grab_current())
