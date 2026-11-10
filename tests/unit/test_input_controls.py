"""Real Tk interactions for shared controls, with no game dependency."""
import gc
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace

from ccz_randomizer.search_history import SearchHistory
from ccz_randomizer.ui.inputs import SearchEntry, TextEntry
from ccz_randomizer.ui.search_memory import SearchMemory
from ccz_randomizer.ui.searchable_combo import SelectionCombobox
from ccz_randomizer.rules.editor import ScoreGrid


class InputControlTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry("640x480+30+30")
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.addCleanup(self.root.destroy)

    def settle(self, delay=0):
        self.root.update()
        if delay:
            ready = tk.BooleanVar(self.root)
            self.root.after(delay, lambda: ready.set(True))
            self.root.wait_variable(ready)
        self.root.update()

    def test_search_escape_clears_query_before_window_shortcut(self):
        variable = tk.StringVar(value="曹仁")
        entry = SearchEntry(self.root, textvariable=variable)
        entry.pack()
        escaped = []
        self.root.bind("<Escape>", lambda _event: escaped.append(True))
        self.settle()
        entry.focus_force()
        entry.event_generate("<Control-a>")
        self.assertEqual("曹仁", entry.selection_get())
        entry.event_generate("<Escape>")
        self.assertEqual("", variable.get())
        self.assertEqual([], escaped)
        entry.event_generate("<Escape>")
        self.assertEqual([True], escaped)

    def test_editing_preserves_text_on_escape_and_owns_variable(self):
        entry = TextEntry(self.root, textvariable=tk.StringVar(value="名称和数字 123"))
        entry.pack()
        gc.collect()
        self.settle()
        self.assertEqual("名称和数字 123", entry.get())
        entry.configure(textvariable=tk.StringVar(value="修改后"))
        gc.collect()
        entry.focus_force()
        entry.event_generate("<Escape>")
        self.assertEqual("修改后", entry.get())

    def combo(self, **kwargs):
        combo = SelectionCombobox(self.root, **kwargs)
        combo.pack()
        self.settle()
        return combo

    def test_small_menu_keeps_native_picker_and_wheel_does_not_edit(self):
        combo = self.combo(values=("无", "武将型", "文官型"))
        combo.set("武将型")
        self.assertIsNone(combo.open_popup())
        self.assertIsNone(combo.popup)
        combo.event_generate("<MouseWheel>", delta=120)
        self.assertEqual("武将型", combo.get())
        # Open and select through the native Tk list, not our search popup.
        self.root.tk.call("ttk::combobox::Post", str(combo))
        popup = self.root.tk.call("ttk::combobox::PopdownWindow", str(combo))
        listing = str(popup)+".f.l"
        self.root.tk.call(listing, "selection", "clear", 0, "end")
        self.root.tk.call(listing, "selection", "set", 2)
        self.root.tk.call("ttk::combobox::LBSelected", listing)
        self.settle()
        self.assertEqual("文官型", combo.get())

    def test_long_menu_search_cancel_tab_and_commit_restore_modal_grab(self):
        values = tuple(f"规则 {i}" for i in range(12))
        combo = self.combo(values=values)
        combo.set(values[0])
        next_entry = TextEntry(self.root)
        next_entry.pack()
        self.root.grab_set()
        self.settle()
        combo.open_popup()
        self.settle()
        combo.search_entry.insert(0, "规则 11")
        self.assertEqual(("规则 11",), combo.listbox.get(0, "end"))
        self.assertEqual(values[0], combo.get())
        combo.search_entry.focus_force()
        combo.search_entry.event_generate("<Escape>")
        self.settle()
        self.assertIsNone(combo.popup)
        self.assertEqual(values[0], combo.get())
        self.assertEqual(self.root, self.root.grab_current())
        combo.open_popup()
        self.settle()
        combo.search_entry.focus_force()
        combo.search_entry.event_generate("<Tab>")
        self.settle()
        self.assertEqual(next_entry, self.root.focus_get())
        self.assertEqual(values[0], combo.get())
        observed = []
        combo.bind("<<ComboboxSelected>>", lambda _event: observed.append(
            (combo.get(), combo.popup, self.root.grab_current())))
        combo.open_popup()
        self.settle()
        combo.search_entry.insert(0, "规则 11")
        combo.search_entry.focus_force()
        combo.search_entry.event_generate("<Return>")
        self.settle()
        self.assertEqual([("规则 11", None, self.root)], observed)
        self.assertEqual([], self.errors)

    def test_disabled_and_changed_options_cannot_leave_stale_popup(self):
        combo = self.combo(values=tuple(map(str, range(15))), state="disabled")
        combo.set("5")
        combo.open_popup()
        self.assertIsNone(combo.popup)
        combo.configure(state="readonly")
        combo.open_popup()
        self.settle()
        combo.configure(values=("A", "B"))
        self.assertIsNone(combo.popup)
        self.assertEqual("5", combo.get())
        combo.open_popup()
        self.assertIsNone(combo.popup)
        combo.configure(values=tuple(map(str, range(20))))
        combo.open_popup()
        self.settle()
        combo.configure(state="disabled")
        self.assertIsNone(combo.popup)
        self.assertEqual([], self.errors)

    def test_empty_results_and_blank_list_area_do_not_select(self):
        combo = self.combo(values=tuple(map(str, range(15))))
        combo.set("0")
        combo.open_popup()
        self.settle()
        combo.search_entry.insert(0, "14")
        self.settle()
        combo.listbox.event_generate("<ButtonRelease-1>", x=5, y=150)
        self.assertEqual("0", combo.get())
        self.assertIsNotNone(combo.popup)
        combo.search_entry.delete(0, "end")
        combo.search_entry.insert(0, "不存在")
        combo.search_entry.focus_force()
        combo.search_entry.event_generate("<Return>")
        self.assertEqual("0", combo.get())
        self.assertIsNotNone(combo.popup)
        combo.destroy()
        self.settle()
        self.assertEqual([], self.errors)

    def test_history_is_optional_scoped_and_disposed_with_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            query = tk.StringVar()
            entry = SearchEntry(self.root, textvariable=query)
            entry.pack()
            body = tk.Frame(self.root)
            body.pack()
            path = Path(directory)/"searches.json"
            memory = SearchMemory(entry, query, path, has_matches=lambda word: word in ("曹", "曹仁"),
                                  parent=self.root, before=body, idle_ms=20)
            query.set("曹")
            self.settle(40)
            query.set("曹仁")
            self.settle(40)
            self.assertEqual(["曹仁"], SearchHistory(path).items)
            self.assertEqual(["曹仁"], [button._keyword for button in memory.bar.buttons])
            query.set("无结果")
            entry.destroy()
            query.set("曹")  # A surviving variable must not retain a dead widget callback.
            self.settle(40)
            self.assertEqual(["曹仁"], SearchHistory(path).items)
            self.assertEqual([], self.errors)

    def test_inline_card_controls_fit_and_close_without_destroy_errors(self):
        score = tk.StringVar(value="8.5")
        kind = tk.StringVar(value="ALL_ROUNDER")
        grid = ScoreGrid(self.root, [("轻步兵", score, "")], type_variables={"轻步兵": kind})
        grid.pack(fill="both", expand=True)
        self.settle()
        for boxes in (grid.hit_boxes, grid.type_hit_boxes):
            x1, y1, x2, y2, _ = boxes[0]
            grid._start_edit(SimpleNamespace(x=(x1+x2)//2, y=(y1+y2)//2))
            self.settle()
            self.assertLessEqual(grid.editor.winfo_reqheight(), grid.editor.winfo_height())
            grid.commit_pending()
        x1, y1, x2, y2, _ = grid.hit_boxes[0]
        grid._start_edit(SimpleNamespace(x=(x1+x2)//2, y=(y1+y2)//2))
        self.settle()
        grid.destroy()
        self.settle()
        self.assertEqual("8.5", score.get())
        self.assertEqual([], self.errors)
