import tkinter as tk
from tkinter import font, ttk
import unittest

from ccz_randomizer.ui.recent_searches import RecentSearchesBar
from ccz_randomizer.ui.theme import setup_theme


class RecentSearchLayoutTests(unittest.TestCase):
    def test_keywords_size_to_text_with_delete_inside_top_right_and_full_value_reuse(self):
        root = tk.Tk()
        self.addCleanup(root.destroy)
        setup_theme(root)
        root.geometry('540x240')
        selected, removed = [], []
        words = ['曹', '夏侯惇', '这是一个超过十个汉字的完整搜索关键词']
        bar = RecentSearchesBar(root, selected.append, removed.append)
        bar.pack(fill='x')
        bar.set_items(words)
        root.update()
        widths = [button.winfo_width() for button in bar.buttons]
        self.assertLess(widths[0], widths[1])
        self.assertLess(widths[1], widths[2])
        label_font = font.Font(root=root, font=ttk.Style(root).lookup('Recent.Keyword.TButton', 'font'))
        self.assertLessEqual(widths[0], label_font.measure('曹') + bar.delete_buttons[0].winfo_width() + 28)
        for button, close in zip(bar.buttons, bar.delete_buttons):
            self.assertGreater(close.winfo_x(), button.winfo_x())
            self.assertLessEqual(close.winfo_x() + close.winfo_width(), button.winfo_width())
            self.assertLessEqual(close.winfo_y() + close.winfo_height(), button.winfo_height())
            self.assertLess(close.winfo_y(), button.winfo_height() / 2)
        bar.delete_buttons[0].invoke()
        self.assertEqual(['曹'], removed)
        self.assertEqual([], selected)
        bar.buttons[-1].invoke()
        self.assertEqual([words[-1]], selected)
        self.assertTrue(bar.buttons[-1].cget('text').endswith('…'))
        root.geometry('280x240')
        root.update()
        for group in bar.groups:
            self.assertLessEqual(group.winfo_x() + group.winfo_width(), bar.chips.winfo_width())
