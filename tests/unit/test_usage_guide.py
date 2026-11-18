import tkinter as tk
from tkinter import ttk
import unittest

from ccz_randomizer.ui.usage_guide import MODULES, QUICK_START, show_usage_guide


class UsageGuideTests(unittest.TestCase):
    def test_closing_help_restores_the_support_menu_modal_grab(self):
        root = tk.Tk()
        self.addCleanup(root.destroy)
        menu = tk.Toplevel(root)
        menu.grab_set()
        show_usage_guide(menu)
        root.update()
        dialog = next(w for w in menu.winfo_children() if isinstance(w, tk.Toplevel))
        self.assertIs(dialog, root.grab_current())
        next(w for w in dialog.winfo_children()[0].winfo_children()
             if isinstance(w, ttk.Button)).invoke()
        self.assertIs(menu, root.grab_current())

    def test_pages_load_when_selected_and_keep_their_content(self):
        root = tk.Tk()
        self.addCleanup(root.destroy)
        show_usage_guide(root)
        root.update()
        dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
        notebook = next(w for w in dialog.winfo_children()[0].winfo_children() if isinstance(w, ttk.Notebook))
        pages = [root.nametowidget(name) for name in notebook.tabs()]
        self.assertEqual(1, sum(isinstance(w, tk.Text) for page in pages for w in page.winfo_children()))
        for index, content in enumerate([QUICK_START, *(content for _, content in MODULES)]):
            notebook.select(index)
            root.update()
            texts = [w for w in pages[index].winfo_children() if isinstance(w, tk.Text)]
            self.assertEqual(1, len(texts))
            self.assertEqual(content, texts[0].get("1.0", "end-1c"))
            self.assertEqual("disabled", texts[0].cget("state"))
        notebook.select(0)
        root.update()
        self.assertEqual(1, sum(isinstance(w, tk.Text) for w in pages[0].winfo_children()))
