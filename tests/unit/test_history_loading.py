from __future__ import annotations

from ccz_randomizer.ui.inputs import TextEntry

import copy
import datetime as dt
from contextlib import closing
import gc
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from ccz_randomizer.history import HistoryRepository
from ccz_randomizer.ui import history
from ccz_randomizer.ui.history_loading import HistoryLoader, render_in_batches


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def displayed(widget, parent):
    # Tests keep their root withdrawn. Check layout membership, rather than
    # whether Windows has mapped the owning root onto the desktop.
    while widget is not parent:
        if not widget.winfo_manager():
            return False
        widget = widget.master
    return True


class HistoryLoadingTests(unittest.TestCase):
    def test_slow_database_initialization_keeps_window_responsive(self):
        entered, release = threading.Event(), threading.Event()
        threads = []
        real_repository = history.HistoryRepository
        def initialize(base):
            threads.append(threading.get_ident())
            entered.set()
            release.wait(3)
            return real_repository(base)
        try:
            with patch.object(history, "HistoryRepository", side_effect=initialize):
                history.show_history_window(self.root, Path(self.temporary.name))
                dialog = self.root._history_window
                self.assertTrue(entered.wait(1))
                beats = []
                self.root.after(0, lambda: beats.append(True))
                self.root.update()
                self.assertEqual([True], beats)
                self.assertNotEqual(threading.get_ident(), threads[0])
                self.assertTrue(dialog.winfo_exists())
                history.show_history_window(self.root, Path(self.temporary.name))
                self.assertEqual([dialog], [w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)])
                release.set()
                self.wait_until(lambda: any("共 0 轮" in text for text in self.labels(dialog)))
        finally:
            release.set()

    def test_database_initialization_error_can_be_retried_by_refresh(self):
        real_repository = history.HistoryRepository
        attempts = []
        def initialize(base):
            attempts.append(base)
            if len(attempts) == 1:
                raise OSError("测试数据库暂不可用")
            return real_repository(base)
        with patch.object(history, "HistoryRepository", side_effect=initialize):
            history.show_history_window(self.root, Path(self.temporary.name))
            dialog = self.root._history_window
            self.wait_until(lambda: any("测试数据库暂不可用" in text for text in self.labels(dialog)))
            self.button(dialog, "刷新").invoke()
            self.wait_until(lambda: any("共 0 轮" in text for text in self.labels(dialog)))
            self.assertEqual(2, len(attempts))

    def test_datetime_picker_uses_plain_entries_and_validates_typed_date(self):
        dialog = self.open_window()
        self.root.update()
        # The two date fields follow the keyword search field in the filters.
        fields = [w for w in descendants(dialog) if isinstance(w, TextEntry)]
        start = fields[1]
        start.event_generate("<Button-1>")
        self.root.update()
        picker = next(w for w in descendants(dialog) if isinstance(w, tk.Toplevel) and w.title() == "选择日期与时间")
        entries = [w for w in descendants(picker) if isinstance(w, TextEntry)]
        self.assertEqual(6, len(entries))
        self.assertFalse(any(isinstance(w, (tk.Spinbox, ttk.Spinbox)) for w in descendants(picker)))
        for entry, text in zip(entries, ("2026", "2", "30", "13", "45", "30")):
            entry.delete(0, "end")
            entry.insert(0, text)
        with patch("ccz_randomizer.ui.messages.showerror") as error:
            self.button(picker, "确认").invoke()
            error.assert_called_once()
        self.assertTrue(picker.winfo_exists())
        self.assertEqual("", start.get())
        entries[1].delete(0, "end")
        entries[1].insert(0, "11")
        entries[2].delete(0, "end")
        entries[2].insert(0, "16")
        self.button(picker, "确认").invoke()
        self.assertEqual("2026-11-16 13:45:30", start.get())
        self.assertFalse(picker.winfo_exists())

    def test_paging_reuses_bounded_round_cards_and_edits_current_round(self):
        from ccz_randomizer.ui.history_rounds import RoundCard
        for number in range(1, 22):
            self.add_round(number, [1])
        dialog = self.open_window()
        def cards():
            return [w for w in descendants(dialog) if isinstance(w, RoundCard)]
        self.wait_until(lambda: len(cards()) == 10 and all(c.winfo_manager() for c in cards()))
        original = {str(w) for c in cards() for w in (c, *descendants(c))}
        first_ids = {r["id"] for r in self.repository.list_rounds(page=1, page_size=10)}
        self.button(dialog, "下一页").invoke()
        self.wait_until(lambda: len(cards()) == 10 and not first_ids.intersection(c.row["id"] for c in cards()))
        self.assertEqual(original, {str(w) for c in cards() for w in (c, *descendants(c))})

        current = cards()[0]
        current_id = current.row["id"]
        current.edit_button.invoke()
        entry = next(w for w in descendants(current) if isinstance(w, TextEntry))
        entry.delete(0, "end")
        entry.insert(0, "翻页后修改当前轮次")
        entry.event_generate("<Return>")
        # Explicit focus is unreliable on a private desktop; an outside click also commits.
        dialog.event_generate("<Button-1>")
        self.wait_until(lambda: self.repository.list_rounds(query="翻页后修改当前轮次"))
        self.assertEqual(current_id, self.repository.list_rounds(query="翻页后修改当前轮次")[0]["id"])
        self.assertFalse(first_ids.intersection(r["id"] for r in self.repository.list_rounds(query="翻页后修改当前轮次")))
        self.wait_until(lambda: str(self.button(dialog, "下一页")["state"]) == "normal")
        self.button(dialog, "下一页").invoke()
        self.wait_until(lambda: len([c for c in cards() if c.winfo_manager()]) == 1)
        self.button(dialog, "上一页").invoke()
        self.wait_until(lambda: len([c for c in cards() if c.winfo_manager()]) == 10)
        self.assertEqual(original, {str(w) for c in cards() for w in (c, *descendants(c))})

    def test_closed_history_reuses_controls_and_reads_new_records_when_reopened(self):
        self.add_round(1, [1])
        dialog = self.open_window()
        self.wait_until(lambda: "存档 1" in self.labels(dialog))
        controls = {str(w) for w in descendants(dialog)}
        dialog.tk.call(dialog.protocol("WM_DELETE_WINDOW"))
        self.assertEqual("withdrawn", dialog.state())
        self.add_round(2, [2])
        history.show_history_window(self.root, self.repository)
        self.assertIs(dialog, self.root._history_window)
        tree = next(w for w in descendants(dialog) if isinstance(w, ttk.Treeview))
        self.wait_until(lambda: len(tree.get_children()) == 2)
        tree.selection_set(tree.get_children()[0])
        self.wait_until(lambda: "存档 2" in self.labels(dialog))
        self.assertNotIn("存档 1", self.labels(dialog))
        self.assertTrue(controls.issubset({str(w) for w in descendants(dialog)}))

    def test_rule_filter_resets_paging_and_all_rules_label_is_not_a_reserved_name(self):
        for number in range(1, 12):
            self.add_round(number, [1])
        self.repository.start_run("all-label", mode="three", loop_random=False, rule_name="全部规则", rule={}, build={})
        rid = self.repository.start_round("all-label", 1)
        snapshot = copy.deepcopy(self.snapshot)
        snapshot.update(slot=2, acceptedAttempt=1)
        self.repository.save_result(rid, snapshot)
        dialog = self.open_window()
        tree = next(w for w in descendants(dialog) if isinstance(w, ttk.Treeview))
        combo = next(w for w in descendants(dialog) if isinstance(w, ttk.Combobox))
        dialog.geometry("1120x680")
        self.wait_until(lambda: len(tree.get_children()) == 10 and str(self.button(dialog, "下一页")["state"]) == "normal")
        reset = self.button(dialog, "重置筛选")
        self.assertLessEqual(reset.winfo_rootx() + reset.winfo_width(), dialog.winfo_rootx() + dialog.winfo_width())
        self.button(dialog, "下一页").invoke()
        self.wait_until(lambda: len(tree.get_children()) == 2)
        combo.current(next(i for i, name in enumerate(combo["values"]) if i > 0 and name == "全部规则"))
        combo.event_generate("<<ComboboxSelected>>")
        self.wait_until(lambda: len(tree.get_children()) == 1 and "存档 2" in self.labels(dialog))
        self.assertEqual("disabled", str(self.button(dialog, "上一页")["state"]))
        self.button(dialog, "重置筛选").invoke()
        self.wait_until(lambda: len(tree.get_children()) == 10 and combo.current() == 0)

    def test_rule_dropdown_filters_refreshes_resets_and_keeps_deleted_rule_names(self):
        self.add_round(1, [1])
        self.repository.start_run("switched", mode="three", loop_random=False, rule_name="已删除的旧规则", rule={}, build={})
        rid = self.repository.start_round("switched", 1)
        snapshot = copy.deepcopy(self.snapshot)
        snapshot.update(slot=2, acceptedAttempt=1)
        self.repository.save_result(rid, snapshot)
        dialog = self.open_window()
        tree = next(w for w in descendants(dialog) if isinstance(w, ttk.Treeview))
        combo = next(w for w in descendants(dialog) if isinstance(w, ttk.Combobox))
        self.wait_until(lambda: len(tree.get_children()) == 2 and len(combo["values"]) == 3)
        combo.current(combo["values"].index("默认规则"))
        combo.event_generate("<<ComboboxSelected>>")
        self.wait_until(lambda: len(tree.get_children()) == 1 and "存档 1" in self.labels(dialog))
        self.assertNotIn("存档 2", self.labels(dialog))
        self.button(dialog, "刷新").invoke()
        self.wait_until(lambda: len(tree.get_children()) == 1 and "存档 1" in self.labels(dialog))
        self.assertEqual("默认规则", combo.get())
        combo.current(combo["values"].index("已删除的旧规则"))
        combo.event_generate("<<ComboboxSelected>>")
        self.wait_until(lambda: len(tree.get_children()) == 1 and "存档 2" in self.labels(dialog))
        self.button(dialog, "重置筛选").invoke()
        self.wait_until(lambda: len(tree.get_children()) == 2 and combo.current() == 0)
        # Refresh discovers newly recorded rules without reopening the window.
        self.repository.start_run("new", mode="three", loop_random=True, rule_name="新规则", rule={}, build={})
        self.repository.save_result(self.repository.start_round("new", 1), snapshot)
        self.button(dialog, "刷新").invoke()
        self.wait_until(lambda: "新规则" in combo["values"] and len(tree.get_children()) == 3)

    def setUp(self):
        self.root = tk.Tk()
        # Native viewports need real dimensions. The test runner maps this root
        # exclusively on its private Windows desktop, never the user's screen.
        self.root.geometry("320x200")
        self.root.update_idletasks()
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = HistoryRepository(Path(self.temporary.name))
        self.repository.start_run("recorded", mode="three", loop_random=True,
                                  rule_name="默认规则", rule={}, build={})
        fixture = Path(__file__).parents[1] / "fixtures/personnel_220_1104/randomized-result.json"
        self.snapshot = json.loads(fixture.read_text(encoding="utf-8"))

    def tearDown(self):
        self.root.destroy()
        self.temporary.cleanup()
        gc.collect()  # Destroy Tk objects on their owning thread before the next reader starts.
        self.assertEqual([], self.errors)

    def wait_until(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.002)
        self.assertTrue(predicate(), "历史窗口未完成预期更新")

    def add_round(self, number, slots):
        rid = self.repository.start_round("recorded", number)
        for slot in slots:
            snapshot = copy.copy(self.snapshot)
            snapshot.update(slot=slot, acceptedAttempt=1)
            self.repository.save_result(rid, snapshot)
        return rid

    def open_window(self):
        history.show_history_window(self.root, self.repository)
        return next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))

    def labels(self, dialog):
        texts = []
        for widget in descendants(dialog):
            if not displayed(widget, dialog):
                continue
            if isinstance(widget, tk.Label):
                texts.append(widget.cget("text"))
            elif isinstance(widget, tk.Canvas):
                texts.extend(widget.itemcget(item, "text") for item in widget.find_all()
                             if widget.type(item) == "text" and widget.itemcget(item, "state") != "hidden")
        return texts

    def test_first_round_reads_once_and_scrolling_exposes_all_fifteen_results(self):
        self.add_round(1, range(1, 16))
        original = self.repository.get_round_summaries
        thread_ids = []
        def read(rid):
            thread_ids.append(threading.get_ident())
            return original(rid)
        with patch.object(self.repository, "get_round_summaries", side_effect=read):
            dialog = self.open_window()
            viewport = dialog._result_viewport
            self.wait_until(lambda: viewport.ready)
            initial = {x for x in self.labels(dialog) if x.startswith("存档 ")}
            self.assertLess(len(initial), 15)
            self.assertIn("存档 1", initial)
            seen = set(initial)
            for fraction in (.25, .5, .75, 1):
                viewport.canvas.yview_moveto(fraction)
                self.root.update()
                self.wait_until(lambda: viewport.ready)
                seen.update(x for x in self.labels(dialog) if x.startswith("存档 "))
            self.assertEqual({f"存档 {i}" for i in range(1, 16)}, seen)
            self.assertIn("存档 15", self.labels(dialog))
            from ccz_randomizer.ui.history_cards import SummaryCard
            self.assertLess(len([w for w in descendants(dialog) if isinstance(w, SummaryCard)]), 15)
            last = next(w for w in descendants(dialog) if isinstance(w, SummaryCard)
                        and w.winfo_manager() and w.snapshot.get("slot") == 15)
            bounds = last.canvas.bbox(last.texts["members"])
            self.assertLessEqual(bounds[3], last.canvas.winfo_height())
            with patch.object(history, "_show_detail") as detail:
                last.detail.invoke()
                self.wait_until(lambda: detail.called)
                self.assertEqual(15, detail.call_args.args[1]["slot"])
            tree = next(w for w in descendants(dialog) if isinstance(w, ttk.Treeview))
            tree.event_generate("<<TreeviewSelect>>")
            self.root.update()
            self.assertEqual(1, len(thread_ids))
            self.assertNotEqual(threading.get_ident(), thread_ids[0])
            query = next(w for w in descendants(dialog) if isinstance(w, TextEntry))
            query.insert(0, "不存在的历史轮次")
            self.button(dialog, "搜索").invoke()
            self.wait_until(lambda: not tree.get_children())
            self.assertEqual((0.0, 1.0), viewport.canvas.yview())

    def test_slow_read_does_not_block_input_and_old_selection_never_replaces_new_one(self):
        older = self.add_round(1, [1])
        latest = self.add_round(2, [2])
        entered, release = threading.Event(), threading.Event()
        original = self.repository.get_round_summaries
        def read(rid):
            if rid == latest:
                entered.set()
                release.wait(5)
            return original(rid)
        try:
            with patch.object(self.repository, "get_round_summaries", side_effect=read):
                dialog = self.open_window()
                self.wait_until(entered.is_set)
                heartbeat = []
                self.root.after(0, lambda: heartbeat.append(True))
                self.root.update()
                self.assertTrue(heartbeat)
                tree = next(w for w in descendants(dialog) if isinstance(w, ttk.Treeview))
                tree.selection_set(tree.get_children()[1])
                self.root.update()
                release.set()
                self.wait_until(lambda: "存档 1" in self.labels(dialog))
                self.assertNotIn("存档 2", self.labels(dialog))
                self.assertEqual([1], [r["slot"] for r in original(older)])
        finally:
            release.set()

    def test_full_data_is_loaded_only_when_detail_or_overview_is_requested(self):
        rid = self.add_round(1, [1, 2])
        expected = self.repository.get_round_results(rid)
        with patch.object(self.repository, "get_round_results", wraps=self.repository.get_round_results) as full_round, \
             patch.object(self.repository, "get_result", wraps=self.repository.get_result) as full_result, \
             patch.object(history, "_show_detail") as detail, \
             patch.object(history, "_show_round_overview") as overview:
            dialog = self.open_window()
            self.wait_until(lambda: "存档 2" in self.labels(dialog))
            self.assertEqual(0, full_round.call_count)
            self.assertEqual(0, full_result.call_count)
            button = next(w for w in descendants(dialog)
                          if isinstance(w, ttk.Button) and w.cget("text") == "查看完整详情")
            button.invoke()
            self.wait_until(lambda: detail.called)
            self.assertEqual(expected[0], detail.call_args.args[1])
            self.assertEqual(1, full_result.call_count)
            self.assertEqual(0, full_round.call_count)
            self.assertEqual(0, full_round.call_count)

    def test_close_during_read_discards_result_and_scheduled_render(self):
        dialog = tk.Toplevel(self.root)
        loader = HistoryLoader(dialog)
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        delivered = []
        def read():
            entered.set()
            release.wait(5)
            finished.set()
            return self.snapshot
        loader.request("results", read, delivered.append, delivered.append)
        render_in_batches(dialog, [self.snapshot] * 15, lambda *args: delivered.append(args))
        self.assertTrue(entered.wait(1))
        dialog.destroy()
        release.set()
        self.assertTrue(finished.wait(1))
        self.root.update()
        self.assertTrue(loader.closed)
        self.assertEqual([], delivered)

    def test_read_failure_can_be_retried(self):
        self.add_round(1, [1])
        original = self.repository.list_rounds
        with patch.object(self.repository, "list_rounds", side_effect=OSError("暂时无法读取")):
            dialog = self.open_window()
            self.wait_until(lambda: any("暂时无法读取" in str(dialog.getvar(w.cget("textvariable")))
                                      for w in descendants(dialog)
                                      if isinstance(w, tk.Label) and w.cget("textvariable")))
        button = next(w for w in descendants(dialog) if isinstance(w, ttk.Button) and w.cget("text") == "刷新")
        button.invoke()
        self.wait_until(lambda: "存档 1" in self.labels(dialog))
        self.assertEqual(1, len(original()))

    def test_batch_render_yields_and_stops_when_superseded(self):
        dialog = tk.Toplevel(self.root)
        rendered, input_events = [], []
        current = True
        def render(index, item):
            rendered.append(item)
            if index == 0:
                dialog.after(0, lambda: input_events.append(len(rendered)))
        render_in_batches(dialog, range(15), render, is_current=lambda: current)
        self.wait_until(lambda: bool(input_events))
        self.assertLess(input_events[0], 15)
        current = False
        before = list(rendered)
        deadline = time.monotonic() + .03
        while time.monotonic() < deadline:
            self.root.update()
            time.sleep(.002)
        self.assertEqual(before, rendered)

    def test_expensive_card_yields_before_the_item_limit(self):
        dialog = tk.Toplevel(self.root)
        rendered, input_events = [], []
        clock = [0.0]
        def render(index, item):
            rendered.append(item)
            clock[0] += .010
            if index == 0:
                dialog.after(0, lambda: input_events.append(len(rendered)))
        with patch("ccz_randomizer.ui.history_loading.time.perf_counter", side_effect=lambda: clock[0]):
            render_in_batches(dialog, range(15), render, batch_size=4)
            self.wait_until(lambda: bool(input_events))
        self.assertEqual(1, input_events[0])
        dialog.destroy()

    def test_full_detail_keeps_all_real_members_without_a_widget_tree_per_member(self):
        from ccz_randomizer.history_members import history_members
        from ccz_randomizer.ui.member_card import MemberCard
        history._show_detail(self.root, self.snapshot)
        dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
        self.assertEqual(f"第 {self.snapshot.get('slot', '-')} 号存档详情", dialog.title())
        members = history_members(self.snapshot)
        self.assertEqual(143, len(members))
        viewport = dialog._member_viewport
        self.wait_until(lambda: viewport.ready)
        texts = set()
        for step in range(101):
            viewport.canvas.yview_moveto(step/100)
            self.root.update()
            self.wait_until(lambda: viewport.ready)
            texts.update(self.labels(dialog))
            for card in (w for w in descendants(dialog) if isinstance(w, MemberCard) and w.winfo_manager()):
                for item in card.find_all():
                    if card.type(item) == 'text':
                        bounds = card.bbox(item)
                        self.assertLessEqual(bounds[3], card.winfo_height())
        for member in members:
            self.assertIn(member["name"], texts)
            self.assertTrue(any(str(member["job"]) in text for text in texts))
            self.assertIn(history._skill_names(member.get("personalSkills") or []), texts)
            self.assertIn(history._skill_names(member.get("jobSkills") or []), texts)
        self.assertLessEqual(len([w for w in descendants(dialog) if isinstance(w, MemberCard)]),
                             viewport.columns*(int(viewport.canvas.winfo_height()/min(
                                 b-a for a,b in zip(viewport.offsets, viewport.offsets[1:])))+3))
        self.assertLess(len(list(descendants(dialog))), 150)

    def button(self, window, text):
        return next(w for w in descendants(window) if isinstance(w, ttk.Button) and w.cget("text") == text and displayed(w, window))

    def submit_metadata(self, dialog, title, note):
        editor = next(w for w in descendants(dialog) if isinstance(w, tk.Toplevel) and w.title() == "命名与备注")
        entry = next(w for w in descendants(editor) if isinstance(w, TextEntry))
        entry.delete(0, "end")
        entry.insert(0, title)
        text = next(w for w in descendants(editor) if isinstance(w, tk.Text))
        text.delete("1.0", "end")
        text.insert("1.0", note)
        self.button(editor, "保存").invoke()

    def test_edit_round_then_find_by_name_and_note(self):
        rid = self.add_round(1, [1])
        dialog = self.open_window()
        self.wait_until(lambda: "存档 1" in self.labels(dialog))
        self.repository.annotate_round(rid, title="曹操开局", note="保留这份")
        self.button(dialog, "刷新").invoke()
        self.wait_until(lambda: self.repository.list_rounds()[0]["title"] == "曹操开局")
        self.assertEqual(1, self.repository.count_rounds(query="保留这份"))
        self.repository.annotate_round(rid, title="最佳轮次", note="第一选择")
        self.button(dialog, "刷新").invoke()
        self.wait_until(lambda: self.repository.list_rounds()[0]["title"] == "最佳轮次")
        self.wait_until(lambda: "存档 1" in self.labels(dialog))
        entry = next(w for w in descendants(dialog) if isinstance(w, TextEntry))
        entry.insert(0, "不存在的名称")
        self.button(dialog, "搜索").invoke()
        tree = next(w for w in descendants(dialog) if isinstance(w, ttk.Treeview))
        self.wait_until(lambda: not tree.get_children())
        entry.delete(0, "end")
        entry.insert(0, "第一选择")
        self.button(dialog, "搜索").invoke()
        self.wait_until(lambda: "存档 1" in self.labels(dialog))
        self.assertEqual(rid, self.repository.list_rounds(query="第一选择")[0]["id"])

    def test_export_button_recovers_copy_after_source_was_removed(self):
        rid = self.repository.start_round("recorded", 1)
        data = (Path(__file__).parents[2] / "resources/legacy/random_save_templates.bin").read_bytes()
        source = Path(self.temporary.name) / "SV001.E5S"
        source.write_bytes(data)
        snapshot = copy.deepcopy(self.snapshot)
        snapshot.update(slot=1, acceptedAttempt=1)
        snapshot["save"] = dict(path=str(source), sha256=hashlib.sha256(data).hexdigest())
        self.repository.save_result(rid, snapshot, save_path=source)
        source.unlink()
        destination = Path(self.temporary.name) / "recovered.E5S"
        dialog = self.open_window()
        self.wait_until(lambda: "存档 1" in self.labels(dialog))
        with patch("tkinter.filedialog.asksaveasfilename", return_value=str(destination)), patch("ccz_randomizer.ui.messages.showinfo"):
            card = next(w for w in descendants(dialog) if hasattr(w, "invoke") and getattr(w, "callbacks", {}).get("export"))
            card.invoke("export")
            self.wait_until(destination.is_file)
            self.assertEqual(data, destination.read_bytes())
            # Drain completion before the patched message box is released.
            deadline = time.monotonic() + .05
            while time.monotonic() < deadline:
                self.root.update()
                time.sleep(.002)

    def test_confirmed_metadata_write_finishes_even_if_history_window_closes(self):
        rid = self.add_round(1, [1])
        dialog = tk.Toplevel(self.root)
        loader = HistoryLoader(dialog)
        entered, release, completed = threading.Event(), threading.Event(), threading.Event()
        repo = self.repository
        def blocking_read():
            entered.set()
            release.wait(5)
        def write():
            repo.annotate_round(rid, title="关闭窗口后保留", note="", marked=True)
            completed.set()
        delivered = []
        try:
            loader.request("read", blocking_read, delivered.append, delivered.append)
            self.assertTrue(entered.wait(1))
            loader.request("write", write, delivered.append, delivered.append, durable=True)
            dialog.destroy()
            release.set()
            self.assertTrue(completed.wait(3))
            self.root.update()
            self.assertEqual([], delivered)
            self.assertEqual("关闭窗口后保留", repo.list_rounds()[0]["title"])
        finally:
            release.set()

    def test_date_and_text_filters_show_only_matching_cards_and_reset(self):
        first = self.add_round(1, [1, 2])
        second = self.add_round(2, [3])
        self.repository.annotate_round(first, title="精选", note="这个兵种适合开局")
        with closing(self.repository._connect()) as db, db:
            db.execute("UPDATE rounds SET started_at='2026-11-06T23:59:59+08:00' WHERE id=?", (first,))
            db.execute("UPDATE rounds SET started_at='2026-11-07T00:00:00+08:00' WHERE id=?", (second,))
        dialog = self.open_window()
        self.wait_until(lambda: "存档 3" in self.labels(dialog))
        tree = next(w for w in descendants(dialog) if isinstance(w, ttk.Treeview))
        self.assertNotIn("status", tree["columns"])
        self.assertEqual(("title", "time", "rule"), tree["columns"])
        entries = [w for w in descendants(dialog) if isinstance(w, TextEntry)]
        for entry, value in zip(entries, ("适合开局", "2026-11-06 23:59:59", "2026-11-06 23:59:59")):
            entry.insert(0, value)
        self.button(dialog, "搜索").invoke()
        # A match on the round's note includes every result in that round.
        # Wait for the whole result set instead of observing a partial batch.
        self.wait_until(lambda: "存档 1" in self.labels(dialog) and "存档 2" in self.labels(dialog))
        self.assertNotIn("存档 3", self.labels(dialog))
        self.assertEqual(1, len(tree.get_children()))
        # An invalid draft leaves the currently applied filter and results intact.
        entries[1].delete(0, "end")
        entries[1].insert(0, "2026-11-08")
        with patch("ccz_randomizer.ui.messages.showerror") as error:
            self.button(dialog, "搜索").invoke()
            self.assertTrue(error.called)
        self.assertIn("存档 1", self.labels(dialog))
        self.button(dialog, "重置筛选").invoke()
        self.wait_until(lambda: len(tree.get_children()) == 2)
        self.assertTrue(all(not entry.get() for entry in entries))

    def test_clear_all_confirmation_explicitly_includes_hidden_records(self):
        first = self.add_round(1, [1])
        self.add_round(2, [2])
        self.repository.annotate_round(first, title="选中这轮", note="", marked=False)
        dialog = self.open_window()
        self.wait_until(lambda: "存档 2" in self.labels(dialog))
        entry = next(w for w in descendants(dialog) if isinstance(w, TextEntry))
        entry.insert(0, "选中这轮")
        self.button(dialog, "搜索").invoke()
        self.wait_until(lambda: "存档 1" in self.labels(dialog))
        with patch("ccz_randomizer.ui.messages.askyesno", return_value=False) as confirm:
            self.button(dialog, "清空全部历史").invoke()
            self.assertIn("包括被筛选隐藏的记录", confirm.call_args.args[1])
        self.assertEqual(2, self.repository.count_rounds())

    def test_quick_dates_apply_calendar_days_and_reset_restores_all(self):
        recent = self.add_round(1, [1])
        older = self.add_round(2, [2])
        today = dt.datetime.now().astimezone().date()
        with closing(self.repository._connect()) as db, db:
            for rid, day in ((recent, today), (older, today - dt.timedelta(days=8))):
                db.execute("UPDATE rounds SET started_at=? WHERE id=?", (f"{day}T12:00:00+08:00", rid))
        dialog = self.open_window()
        self.wait_until(lambda: "存档 1" in self.labels(dialog))
        tree = next(w for w in descendants(dialog) if isinstance(w, ttk.Treeview))
        entries = [w for w in descendants(dialog) if isinstance(w, TextEntry)]
        entries[1].insert(0, str(today))
        entries[2].insert(0, str(today))
        self.button(dialog, "搜索").invoke()
        self.wait_until(lambda: len(tree.get_children()) == 1 and "存档 1" in self.labels(dialog))
        self.assertEqual([str(today), str(today)], [entry.get() for entry in entries[1:]])
        self.button(dialog, "重置筛选").invoke()
        self.wait_until(lambda: len(tree.get_children()) == 2)
        self.assertTrue(all(not entry.get() for entry in entries))

    def test_switch_and_refresh_reuse_cards_and_open_current_snapshot(self):
        older = self.add_round(1, [1, 2])
        latest = self.add_round(2, [3, 4])
        self.repository.annotate_round(older, title="旧轮优选", note="备注")
        with patch.object(history, "_show_detail") as detail:
            dialog = self.open_window()
            self.wait_until(lambda: "存档 4" in self.labels(dialog))
            first_controls = {str(w) for w in descendants(dialog)}
            tree = next(w for w in descendants(dialog) if isinstance(w, ttk.Treeview))
            tree.selection_set(tree.get_children()[1])
            self.wait_until(lambda: "存档 2" in self.labels(dialog))
            self.assertEqual(first_controls, {str(w) for w in descendants(dialog)})
            self.assertEqual("旧轮优选", self.repository.list_rounds(page=1, page_size=2)[1]["title"])
            self.button(dialog, "查看完整详情").invoke()
            self.wait_until(lambda: detail.called)

            self.assertEqual(self.repository.get_result(older, 1), detail.call_args.args[1])
            tree.selection_set(tree.get_children()[0])
            self.wait_until(lambda: "存档 4" in self.labels(dialog))
            from ccz_randomizer.ui.history_cards import SummaryCard
            self.assertFalse(any("旧轮优选" in card.view.values() for card in descendants(dialog)
                                 if isinstance(card, SummaryCard) and card.view))
            self.assertNotIn("已标记", self.labels(dialog))
            self.button(dialog, "刷新").invoke()
            self.wait_until(lambda: "存档 4" in self.labels(dialog))
            self.assertEqual(first_controls, {str(w) for w in descendants(dialog)})

    def test_round_picker_allows_only_one_inline_editor(self):
        self.add_round(1, [1])
        self.add_round(2, [2])
        dialog = self.open_window()
        self.wait_until(lambda: "存档 2" in self.labels(dialog))
        buttons = [w for w in descendants(dialog)
                   if isinstance(w, ttk.Button) and w.cget("text") == "编辑"]
        self.assertGreaterEqual(len(buttons), 2)
        buttons[0].invoke()
        self.root.update()
        editors = lambda: [w for w in descendants(dialog)
                           if isinstance(w, TextEntry) and getattr(w.master, "_round_editor", False)]
        self.assertEqual(1, len(editors()))
        buttons[1].invoke()
        self.root.update()
        self.assertLessEqual(len(editors()), 1)

    def test_inline_editor_saves_when_clicking_outside(self):
        rid = self.add_round(1, [1])
        dialog = self.open_window()
        self.wait_until(lambda: "存档 1" in self.labels(dialog))
        button = next(w for w in descendants(dialog)
                      if isinstance(w, ttk.Button) and w.cget("text") == "编辑")
        button.invoke()
        entry = next(w for w in descendants(dialog)
                     if isinstance(w, TextEntry) and getattr(w.master, "_round_editor", False))
        entry.delete(0, "end")
        entry.insert(0, "点击外部保存")
        dialog.event_generate("<Button-1>")
        self.wait_until(lambda: self.repository.list_rounds()[0]["title"] == "点击外部保存")
        self.assertEqual(rid, self.repository.list_rounds()[0]["id"])
        self.wait_until(lambda: "点击外部保存" in self.labels(dialog))

    def test_inline_editor_saves_before_starting_another_round_edit(self):
        rid = self.add_round(1, [1])
        self.add_round(2, [2])
        dialog = self.open_window()
        self.wait_until(lambda: "存档 2" in self.labels(dialog))
        buttons = [w for w in descendants(dialog)
                   if isinstance(w, ttk.Button) and w.cget("text") == "编辑"]
        buttons[0].invoke()
        entry = next(w for w in descendants(dialog)
                     if isinstance(w, TextEntry) and getattr(w.master, "_round_editor", False))
        entry.delete(0, "end")
        entry.insert(0, "先保存")
        buttons[1].invoke()
        self.wait_until(lambda: self.repository.list_rounds(page=1, page_size=1)[0]["title"] == "先保存")
        self.assertNotEqual(rid, self.repository.list_rounds(page=1, page_size=1)[0]["id"])

    def test_inline_editor_saves_when_clicking_another_round_card(self):
        rid = self.add_round(1, [1])
        self.add_round(2, [2])
        dialog = self.open_window()
        self.wait_until(lambda: "存档 2" in self.labels(dialog))
        buttons = [w for w in descendants(dialog)
                   if isinstance(w, ttk.Button) and w.cget("text") == "编辑"]
        buttons[0].invoke()
        entry = next(w for w in descendants(dialog)
                     if isinstance(w, TextEntry) and getattr(w.master, "_round_editor", False))
        entry.delete(0, "end")
        entry.insert(0, "点击轮次保存")
        cards = [w for w in descendants(dialog) if isinstance(w, tk.Frame) and w.cget("highlightthickness") == 1]
        cards[-1].event_generate("<Button-1>")
        self.wait_until(lambda: self.repository.list_rounds(page=1, page_size=1)[0]["title"] == "点击轮次保存")
        self.assertNotEqual(rid, self.repository.list_rounds(page=1, page_size=1)[0]["id"])

    def test_wheel_over_card_buttons_accumulates_small_deltas_without_global_binding(self):
        dialog = tk.Toplevel(self.root)
        holder, canvas, content, _ = history._scrollable_frame(dialog, background="white")
        holder.pack()
        nested = ttk.Button(content, text="卡片按钮")
        nested.pack()
        outside = ttk.Button(dialog, text="其他区域")
        outside.pack()
        self.root.update()
        canvas.configure(scrollregion=(0, 0, 300, 3000))
        canvas.yview_moveto(0)
        for _ in range(3):
            nested.event_generate("<MouseWheel>", delta=-30)
        self.assertEqual(0, canvas.yview()[0])
        nested.event_generate("<MouseWheel>", delta=-30)
        self.assertGreater(canvas.yview()[0], 0)
        before = canvas.yview()
        outside.event_generate("<MouseWheel>", delta=-120)
        self.assertEqual(before, canvas.yview())
        baseline = self.root.bind_all("<MouseWheel>")
        holder.destroy()
        self.assertEqual(baseline, self.root.bind_all("<MouseWheel>"))

    def test_summary_card_content_fits_and_reuse_clears_old_search_and_mark(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["history"] = dict(title="优选存档", note="这里的个人特技适合开局", backed_up=True)
        card = history._render_summary_card(self.root, snapshot, show_detail=lambda _: None,
            edit_metadata=lambda _: None, export_save=lambda _: None, search_query="个人特技")
        card.pack()
        self.root.update_idletasks()
        canvas = card.canvas
        self.assertIn("评分", canvas.itemcget(card.texts["members"], "text"))
        self.assertEqual(history.COLORS["green"], canvas.itemcget(card.backup_dot, "fill"))
        for key, item in card.texts.items():
            bounds = canvas.bbox(item)
            if bounds:
                self.assertGreaterEqual(bounds[0], 0, key)
                self.assertLessEqual(bounds[2], 260, key)
                self.assertLessEqual(bounds[3], int(canvas.cget("height")), key)
        clean = copy.deepcopy(snapshot)
        clean["history"] = dict(title="", note="", backed_up=False)
        controls = {str(w) for w in descendants(card)}
        card.update_content(clean, history._summary_card_view(clean), show_detail=lambda _: None,
                            edit_metadata=lambda _: None, export_save=lambda _: None)
        self.assertEqual(controls, {str(w) for w in descendants(card)})
        self.assertEqual(history.COLORS["muted"], canvas.itemcget(card.backup_dot, "fill"))


if __name__ == "__main__":
    unittest.main()
