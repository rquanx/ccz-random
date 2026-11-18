import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from pathlib import Path

from ccz_randomizer.search_history import SearchHistory
from ccz_randomizer.ui.search_memory import SearchMemory


class SearchMemoryTests(unittest.TestCase):
    def test_remove_and_clear_keep_query_and_survive_idle_focus_and_close(self):
        for scope, words in (("recruitment", ("曹操", "夏侯惇")),
                             ("equipment", ("雌雄双剑", "镜铠"))):
            with self.subTest(scope=scope), tempfile.TemporaryDirectory() as temp:
                root = tk.Tk()
                root.withdraw()
                try:
                    path = Path(temp) / f"{scope}.json"
                    history = SearchHistory(path)
                    for word in words:
                        history.remember(word)
                    query = tk.StringVar(root, words[0])
                    entry = ttk.Entry(root, textvariable=query)
                    entry.pack()
                    body = ttk.Frame(root)
                    body.pack()
                    memory = SearchMemory(entry, query, path, has_matches=lambda word: word in words,
                                          parent=root, before=body, idle_ms=1)
                    root.geometry("720x240")
                    root.deiconify()
                    root.update()
                    query.set(words[0])  # Pending automatic recording must be cancelled.
                    index = memory.history.items.index(words[0])
                    delete = memory.bar.delete_buttons[index]
                    self.assertEqual("", delete.cget("text"))
                    self.assertTrue(delete.cget("image"))
                    root.update_idletasks()
                    group = memory.bar.groups[index]
                    label = memory.bar.buttons[index]
                    self.assertGreater(delete.winfo_x(), label.winfo_x())
                    self.assertLess(delete.winfo_x(), label.winfo_x() + label.winfo_width())
                    self.assertLessEqual(delete.winfo_x() + delete.winfo_width(), group.winfo_width())
                    self.assertLess(delete.winfo_y(), label.winfo_height() / 2)
                    self.assertLessEqual(delete.winfo_y() + delete.winfo_height(), label.winfo_height())
                    memory.bar.delete_buttons[index].invoke()
                    root.update()
                    memory.remember()  # Focus-out / close also must not restore it.
                    self.assertEqual(words[0], query.get())
                    self.assertEqual([words[1]], SearchHistory(path).items)
                    query.set(words[1])
                    memory.bar.clear_button.invoke()
                    root.update()
                    memory.remember()
                    entry.destroy()
                    self.assertEqual([], SearchHistory(path).items)
                    self.assertFalse(memory.bar.winfo_manager())
                    self.assertEqual(words[1], query.get())
                finally:
                    root.destroy()

    def test_new_query_can_be_remembered_after_clear(self):
        with tempfile.TemporaryDirectory() as temp:
            root = tk.Tk()
            root.withdraw()
            try:
                query = tk.StringVar(root, "曹操")
                entry = ttk.Entry(root, textvariable=query)
                body = ttk.Frame(root)
                body.pack()
                path = Path(temp) / "searches.json"
                memory = SearchMemory(entry, query, path, has_matches=lambda word: True,
                                      parent=root, before=body)
                memory.clear()
                query.set("夏侯惇")
                memory.remember()
                self.assertEqual(["夏侯惇"], SearchHistory(path).items)
            finally:
                root.destroy()
