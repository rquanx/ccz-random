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
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
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

    def test_first_round_reads_once_and_all_fifteen_cards_render(self):
        self.add_round(1, range(1, 16))
        original = self.repository.get_round_summaries
        thread_ids = []
        def read(rid):
            thread_ids.append(threading.get_ident())
            return original(rid)
        with patch.object(self.repository, "get_round_summaries", side_effect=read):
            dialog = self.open_window()
            self.wait_until(lambda: len([x for x in self.labels(dialog) if x.startswith("存档 ")]) == 15)
            tree = next(w for w in descendants(dialog) if isinstance(w, ttk.Treeview))
            tree.event_generate("<<TreeviewSelect>>")
            self.root.update()
            self.assertEqual(1, len(thread_ids))
            self.assertNotEqual(threading.get_ident(), thread_ids[0])
            self.assertEqual({f"存档 {i}" for i in range(1, 16)},
                             {x for x in self.labels(dialog) if x.startswith("存档 ")})

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
                          if isinstance(w, tk.Button) and w.cget("text") == "查看完整详情")
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
        button = next(w for w in descendants(dialog) if isinstance(w, tk.Button) and w.cget("text") == "刷新")
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
        members = history_members(self.snapshot)
        self.assertEqual(143, len(members))
        self.wait_until(lambda: len([w for w in descendants(dialog) if isinstance(w, MemberCard)]) == len(members))
        texts = self.labels(dialog)
        for member in members:
            self.assertIn(member["name"], texts)
            self.assertTrue(any(str(member["job"]) in text for text in texts))
            self.assertIn(history._skill_names(member.get("personalSkills") or []), texts)
            self.assertIn(history._skill_names(member.get("jobSkills") or []), texts)
        self.assertLess(len(list(descendants(dialog))), 300)

    def button(self, window, text):
        return next(w for w in descendants(window) if isinstance(w, tk.Button) and w.cget("text") == text and displayed(w, window))

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
        with patch("tkinter.filedialog.asksaveasfilename", return_value=str(destination)), patch("tkinter.messagebox.showinfo"):
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
        with patch("tkinter.messagebox.showerror") as error:
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
        with patch("tkinter.messagebox.askyesno", return_value=False) as confirm:
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
        with patch.object(history, "_render_summary_card", wraps=history._render_summary_card) as create, \
             patch.object(history, "_show_detail") as detail:
            dialog = self.open_window()
            self.wait_until(lambda: "存档 4" in self.labels(dialog))
            first_controls = {str(w) for w in descendants(dialog)}
            tree = next(w for w in descendants(dialog) if isinstance(w, ttk.Treeview))
            tree.selection_set(tree.get_children()[1])
            self.wait_until(lambda: "存档 2" in self.labels(dialog))
            self.assertEqual(2, create.call_count)
            self.assertEqual(first_controls, {str(w) for w in descendants(dialog)})
            self.assertEqual("旧轮优选", self.repository.list_rounds(page=1, page_size=2)[1]["title"])
            self.button(dialog, "查看完整详情").invoke()
            self.wait_until(lambda: detail.called)

            self.assertEqual(self.repository.get_result(older, 1), detail.call_args.args[1])
            tree.selection_set(tree.get_children()[0])
            self.wait_until(lambda: "存档 4" in self.labels(dialog))
            self.assertNotIn("旧轮优选", self.labels(dialog))
            self.assertNotIn("已标记", self.labels(dialog))
            self.button(dialog, "刷新").invoke()
            self.wait_until(lambda: "存档 4" in self.labels(dialog))
            self.assertEqual(2, create.call_count)
            self.assertEqual(first_controls, {str(w) for w in descendants(dialog)})

    def test_round_picker_allows_only_one_inline_editor(self):
        self.add_round(1, [1])
        self.add_round(2, [2])
        dialog = self.open_window()
        self.wait_until(lambda: "存档 2" in self.labels(dialog))
        buttons = [w for w in descendants(dialog)
                   if isinstance(w, tk.Button) and w.cget("text") == "编辑"]
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
                      if isinstance(w, tk.Button) and w.cget("text") == "编辑")
        button.invoke()
        entry = next(w for w in descendants(dialog)
                     if isinstance(w, TextEntry) and getattr(w.master, "_round_editor", False))
        entry.delete(0, "end")
        entry.insert(0, "点击外部保存")
        dialog.event_generate("<Button-1>")
        self.wait_until(lambda: self.repository.list_rounds()[0]["title"] == "点击外部保存")
        self.assertEqual(rid, self.repository.list_rounds()[0]["id"])
        self.wait_until(lambda: any(isinstance(w, tk.Message) and w.cget("text") == "点击外部保存"
                                    for w in descendants(dialog)))

    def test_inline_editor_saves_before_starting_another_round_edit(self):
        rid = self.add_round(1, [1])
        self.add_round(2, [2])
        dialog = self.open_window()
        self.wait_until(lambda: "存档 2" in self.labels(dialog))
        buttons = [w for w in descendants(dialog)
                   if isinstance(w, tk.Button) and w.cget("text") == "编辑"]
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
                   if isinstance(w, tk.Button) and w.cget("text") == "编辑"]
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
        nested = tk.Button(content, text="卡片按钮")
        nested.pack()
        outside = tk.Button(dialog, text="其他区域")
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
