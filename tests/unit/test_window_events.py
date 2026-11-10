import tkinter as tk
from tkinter import ttk
import unittest

from ccz_randomizer.ui.theme import setup_theme
from ccz_randomizer.ui.window_events import bind_window_event


class WindowEventTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)

    def test_child_events_do_not_reach_window_only_callbacks_and_bindings_are_cleaned(self):
        dialog = tk.Toplevel(self.root)
        delivered = []
        remove = bind_window_event(dialog, "<Destroy>", lambda event: delivered.append(event.widget))
        binder = dialog._ccz_window_events
        children = [tk.Frame(dialog) for _ in range(30)]
        for child in children:
            child.destroy()
        self.assertEqual([], delivered)
        cancelled = []
        cancel = bind_window_event(dialog, "<Destroy>", cancelled.append)
        cancel()
        dialog.destroy()
        self.assertEqual([dialog], delivered)
        self.assertEqual([], cancelled)
        self.assertEqual("", self.root.bind_class(binder.tag, "<Destroy>"))
        self.assertEqual({}, binder.callbacks)
        remove()  # Removing an expired subscription remains safe.

    def test_opening_another_dialog_does_not_reapply_global_theme_to_existing_tree(self):
        setup_theme(self.root)
        tree = ttk.Treeview(self.root)
        tree.pack()
        style = ttk.Style(self.root)
        style.configure("Treeview", rowheight=40)
        self.root.update()
        events = []
        tree.bind("<<ThemeChanged>>", events.append)
        dialog = tk.Toplevel(self.root)
        setup_theme(dialog)
        button = tk.Button(dialog, text="继承字体")
        button.pack()
        self.root.update()
        self.assertEqual([], events)
        self.assertEqual(40, style.lookup("Treeview", "rowheight"))
        self.assertIn("Microsoft YaHei UI", button.cget("font"))
