import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch

from fast_randomizer import JOB_MAP, TEAM_MEMBERS
from rule_config import default_rule_config, load_rule_config
from rule_editor import show_rule_editor


SKILL_CATALOG = (
    ("普通特技", 0.0, "其他"),
    ("优质特技", 1.0, "优质"),
    ("强力特技", 2.0, "强力"),
    ("特殊特技", 5.0, "特殊"),
)


def descendants(widget):
    result = []
    for child in widget.winfo_children():
        result.append(child)
        result.extend(descendants(child))
    return result


class RuleEditorTests(unittest.TestCase):
    def test_copy_select_and_save_profile(self):
        root = tk.Tk()
        root.withdraw()
        saved = []
        try:
            with tempfile.TemporaryDirectory() as directory:
                with (
                    patch("rule_editor.messagebox.showinfo"),
                    patch("rule_editor.messagebox.showerror") as show_error,
                ):
                    show_rule_editor(
                        root,
                        Path(directory),
                        default_rule_config(),
                        JOB_MAP,
                        TEAM_MEMBERS,
                        SKILL_CATALOG,
                        saved.append,
                    )
                    root.update()
                    editor = next(
                        child
                        for child in root.winfo_children()
                        if isinstance(child, tk.Toplevel)
                    )
                    buttons = {
                        widget.cget("text"): widget
                        for widget in descendants(editor)
                        if isinstance(widget, tk.Button)
                    }
                    buttons["新建副本"].invoke()
                    root.update()
                    buttons["规则说明"].invoke()
                    root.update()
                    help_dialog = next(
                        child
                        for child in descendants(root)
                        if isinstance(child, tk.Toplevel)
                        and child != editor
                    )
                    help_books = [
                        widget
                        for widget in descendants(help_dialog)
                        if isinstance(widget, ttk.Notebook)
                    ]
                    self.assertEqual(1, len(help_books))
                    self.assertEqual(6, len(help_books[0].tabs()))
                    help_dialog.destroy()
                    buttons["设为当前规则"].invoke()
                    buttons["保存规则"].invoke()
                    root.update()

                self.assertFalse(show_error.called)
                self.assertEqual(1, len(saved))
                loaded = load_rule_config(Path(directory))
                self.assertEqual(2, len(loaded.config["profiles"]))
                self.assertNotEqual(
                    "默认规则", loaded.config["activeProfile"]
                )
                profile = loaded.config["profiles"][
                    loaded.config["activeProfile"]
                ]
                self.assertEqual(
                    {}, profile["sevenPerson"]["skillBaseScores"]
                )
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
