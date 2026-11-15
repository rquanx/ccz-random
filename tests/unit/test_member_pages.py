import tkinter as tk
from tkinter import ttk
import unittest

from ccz_randomizer.ui.member_pages import MemberPages
from ccz_randomizer.rule_members import RULE_MEMBER_NAMES
from ccz_randomizer.rules.editor import show_member_affinity_editor


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class MemberPagesTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)

    def test_selection_survives_search_and_page_changes(self):
        selected = {name: tk.BooleanVar(self.root) for name in RULE_MEMBER_NAMES}
        def render(body, names):
            for row, name in enumerate(names):
                tk.Checkbutton(body, text=name, variable=selected[name]).grid(row=row, column=0)
        pages = MemberPages(self.root, RULE_MEMBER_NAMES, render)
        pages.pack()
        pages.body.winfo_children()[0].invoke()
        self.assertTrue(selected[RULE_MEMBER_NAMES[0]].get())
        pages.move(1)
        self.assertLessEqual(len(pages.body.winfo_children()), 24)
        pages.query.set(RULE_MEMBER_NAMES[-1])
        self.root.update()
        pages.body.winfo_children()[0].invoke()
        pages.query.set('')
        self.root.update()
        self.assertTrue(selected[RULE_MEMBER_NAMES[0]].get())
        self.assertTrue(selected[RULE_MEMBER_NAMES[-1]].get())
        pages.query.set('无此人')
        self.root.update()
        self.assertEqual('没有符合条件的人物。', pages.body.winfo_children()[0].cget('text'))
        pages.query.set('')
        pages.destroy()
        self.root.update()

    def test_affinity_edits_on_different_pages_are_all_applied(self):
        applied = []
        show_member_affinity_editor(self.root, RULE_MEMBER_NAMES,
            {name: ('NONE', 'NONE') for name in RULE_MEMBER_NAMES}, True, applied.append)
        self.root.update()
        dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
        combos = [w for w in descendants(dialog) if isinstance(w, ttk.Combobox) and w.winfo_manager()]
        self.assertEqual(20, len(combos))
        combos[0].set('文官型')
        pages = next(w for w in descendants(dialog) if isinstance(w, MemberPages))
        pages.move(1)
        self.root.update()
        combos = [w for w in descendants(dialog) if isinstance(w, ttk.Combobox) and w.winfo_manager()]
        self.assertEqual('无', combos[0].get())
        combos[0].set('武将型')
        pages.move(-1)
        self.root.update()
        self.assertEqual('文官型', combos[0].get())
        pages.query.set(RULE_MEMBER_NAMES[-1])
        self.root.update()
        combos = [w for w in descendants(dialog) if isinstance(w, ttk.Combobox) and w.winfo_manager()]
        self.assertEqual(2, len(combos))
        combos[0].set('文官型')
        pages.query.set('无此人')
        self.root.update()
        next(w for w in descendants(dialog) if isinstance(w, ttk.Button) and w.cget('text') == '确认').invoke()
        self.assertEqual(130, len(applied[0]))
        self.assertEqual(('MASTER', 'NONE'), applied[0][RULE_MEMBER_NAMES[0]])
        self.assertEqual(('MASTER', 'NONE'), applied[0][RULE_MEMBER_NAMES[-1]])
        self.assertEqual(('WARRIOR', 'NONE'), applied[0][RULE_MEMBER_NAMES[10]])
