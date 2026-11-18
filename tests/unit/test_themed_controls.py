"""Behavior of the real settings forms after adopting themed controls."""
import os
import sys
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from pathlib import Path
from unittest.mock import patch

from ccz_randomizer import app
from ccz_randomizer.preferences import load_concurrency, load_loop_random
from ccz_randomizer.rules.result_image_editor import show_result_image_members
from ccz_randomizer.ui.theme import setup_theme
from ccz_randomizer.ui.inputs import TextEntry
from ccz_randomizer.ui.searchable_combo import SelectionCombobox


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class ThemedControlsTests(unittest.TestCase):
    def test_runtime_plain_number_entry_and_checkbox_keyboard_persist_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            def exercise(root):
                state = sys._getframe(1).f_locals
                try:
                    root.update()
                    entry = state["concurrency_entry"]
                    self.assertIsInstance(entry, TextEntry)
                    self.assertEqual("TEntry", entry.winfo_class())
                    entry.delete(0, "end")
                    entry.insert(0, "12")
                    entry.event_generate("<FocusOut>")
                    self.assertEqual(12, load_concurrency(base))
                    # Arrow keys and wheel scrolling must not step a number.
                    entry.event_generate("<<Increment>>")
                    entry.event_generate("<<Decrement>>")
                    entry.event_generate("<MouseWheel>", delta=120)
                    self.assertEqual("12", entry.get())
                    entry.delete(0, "end")
                    entry.insert(0, "3")
                    entry.focus_force()
                    root.update()
                    entry.event_generate("<Return>")
                    self.assertEqual(3, load_concurrency(base))
                    self.assertFalse(any(w.winfo_class() in ("Entry", "Spinbox", "TSpinbox") for w in descendants(root)))
                    check = state["loop_check"]
                    self.assertIsInstance(check, ttk.Checkbutton)
                    before = state["loop_var"].get()
                    check.focus_force()
                    root.update()
                    check.event_generate("<KeyPress-space>")
                    check.event_generate("<KeyRelease-space>")
                    self.assertNotEqual(before, state["loop_var"].get())
                    self.assertEqual(bool(state["loop_var"].get()), load_loop_random(base))
                finally:
                    for child in list(root.winfo_children()):
                        child.destroy()
                    for timer in root.tk.call("after", "info"):
                        root.after_cancel(timer)
                    root.destroy()
            with patch.dict(os.environ), \
                 patch.object(tk.Tk, "mainloop", exercise), \
                 patch.object(app, "app_dir", return_value=base), \
                 patch.object(app, "skill_score_catalog", return_value={}), \
                 patch("ccz_randomizer.profile_session.startup_profile_check"), \
                 patch.object(app.threading.Thread, "start"):
                app.gui_main()

    def test_image_mode_controls_disable_selection_and_retain_custom_choices(self):
        root = tk.Tk()
        self.addCleanup(root.destroy)
        confirmed = []
        show_result_image_members(root, {"mode": "selected", "members": ["曹操"]},
                                  ["曹操", "夏侯惇", "夏侯渊"], confirmed.append)
        root.update()
        dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
        def checks():
            return {w.cget("text"): w for w in descendants(dialog) if isinstance(w, ttk.Checkbutton)}
        initial = checks()["夏侯惇"]
        self.assertTrue(initial.instate(("disabled",)))
        initial.invoke()
        self.assertFalse(bool(root.getvar(initial.cget("variable"))))
        modes = {w.cget("text"): w for w in descendants(dialog) if isinstance(w, ttk.Radiobutton)}
        modes["单独选择人物"].invoke()
        root.update()
        self.assertFalse(checks()["夏侯惇"].instate(("disabled",)))
        checks()["夏侯惇"].invoke()
        modes["跟随评分人物"].invoke()
        modes["单独选择人物"].invoke()
        next(w for w in descendants(dialog) if isinstance(w, ttk.Button) and w.cget("text") == "确认").invoke()
        self.assertEqual([{"mode": "custom", "members": ["曹操", "夏侯惇"]}], confirmed)

    def test_inputs_share_height_and_disabled_selection_cannot_change_value(self):
        root = tk.Tk()
        self.addCleanup(root.destroy)
        setup_theme(root)
        widgets = [TextEntry(root), SelectionCombobox(root, values=("一", "二"), state="readonly")]
        for widget in widgets:
            widget.pack()
        root.update_idletasks()
        # Native Windows entry and combobox borders can differ by a few pixels.
        self.assertLessEqual(max(w.winfo_reqheight() for w in widgets) - min(w.winfo_reqheight() for w in widgets), 3)
        value = tk.BooleanVar(root, False)
        check = ttk.Checkbutton(root, text="禁用选项", variable=value, state="disabled")
        check.invoke()
        self.assertFalse(value.get())
