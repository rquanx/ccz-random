import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ccz_randomizer.history import HistoryRepository
from ccz_randomizer.ui.recruitment import show_recruit_window, special_talent_names
from ccz_randomizer.ui.job_talents import load_job_talents

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/personnel_22"


def wait_until(root, predicate):
    import time
    deadline = time.monotonic() + 3
    while not predicate() and time.monotonic() < deadline:
        root.update()
        time.sleep(.002)
    if not predicate():
        raise AssertionError("人员卡片未在限定时间内完成绘制")


def saved_snapshot():
    return {"schemaVersion": 1, "gameVersion": "2.2", "phase": "randomized",
        "slot": 1, "acceptedAttempt": 1, "mode": "three",
        "personnel": json.loads((FIXTURES / "randomized-personnel.json").read_text(encoding="utf-8")),
        "fixedPersonnel": json.loads((FIXTURES / "randomized-fixed-personnel.json").read_text(encoding="utf-8"))}


class RecruitmentHistoryTests(unittest.TestCase):
    def test_reopen_preserves_result_bound_candidates_and_talents(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = HistoryRepository(Path(directory))
            repository.start_run("recruit-test", mode="three", loop_random=False,
                rule_name="test", rule={}, build={})
            round_id = repository.start_round("recruit-test", 1)
            snapshot = saved_snapshot()
            repository.save_result(round_id, snapshot)
            reopened = HistoryRepository(Path(directory))
            self.assertEqual([snapshot], reopened.get_round_results(round_id))


class JobTalentsTests(unittest.TestCase):
    def test_all_22_jobs_have_valid_talent_catalog(self):
        jobs = load_job_talents(saved_snapshot())
        self.assertEqual(40, len(jobs))
        self.assertEqual({0, 79}, {job["jobId"] for job in jobs} & {0, 79})
        self.assertTrue(all(job["talents"] is None for job in jobs))



class RecruitmentWindowTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.history_path = Path(folder.name)/"searches.json"
        patcher = patch("ccz_randomizer.ui.recruitment.default_search_history_path", return_value=self.history_path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_special_talent_names_follow_rule_threshold_and_aliases(self):
        rule = {"sevenPerson": {
            "specialSkillWeight": 5,
            "skillBaseScores": {"弱点攻击 移动": 5, "普通特技": 4},
        }}
        names = special_talent_names(rule)
        self.assertIn("弱点攻击", names)
        self.assertNotIn("普通特技", names)
        self.assertNotIn("弱点攻击", special_talent_names({"sevenPerson": {
            "specialSkillWeight": 5, "skillBaseScores": {"弱点攻击 移动": 9, "弱点攻击": 0}}}))
        self.assertIn("特效模仿", special_talent_names({"sevenPerson": {
            "specialSkillWeight": 2, "skillBaseScores": {}}}))

    def test_special_talent_is_rendered_red(self):
        import tkinter as tk
        from ccz_randomizer.ui.recruitment import show_recruit_window
        root = tk.Tk()
        self.addCleanup(root.destroy)
        snapshot = saved_snapshot()
        snapshot["personnel"][0]["personalTalents"] = ["特殊特技", "普通特技"]
        rule = {"sevenPerson": {"specialSkillWeight": 5,
                                "skillBaseScores": {"特殊特技": 5, "普通特技": 1}}}
        show_recruit_window(root, snapshot=snapshot, rule=rule)
        root.update()
        dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        canvas = next(w for w in descendants(dialog) if isinstance(w, tk.Canvas))
        wait_until(root, lambda: any(canvas.itemcget(item, "text") == "特殊特技"
                   for item in canvas.find_all() if canvas.type(item) == "text"))
        fills = {canvas.itemcget(item, "text"): canvas.itemcget(item, "fill")
                 for item in canvas.find_all() if canvas.type(item) == "text"}
        self.assertEqual("#B42318", fills["特殊特技"])
        self.assertNotEqual("#B42318", fills["普通特技"])

    def test_unchanged_canvas_size_keeps_existing_cards(self):
        import tkinter as tk
        root = tk.Tk()
        self.addCleanup(root.destroy)
        show_recruit_window(root, snapshot=saved_snapshot())
        root.update()
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        canvas = next(w for w in descendants(root) if isinstance(w, tk.Canvas))
        ready = tk.BooleanVar(root)
        root.after(180, lambda: ready.set(True))
        root.wait_variable(ready)
        cards = canvas.find_all()
        canvas.event_generate("<Configure>", width=canvas.winfo_width(), height=canvas.winfo_height())
        ready.set(False)
        root.after(180, lambda: ready.set(True))
        root.wait_variable(ready)
        self.assertTrue(cards)
        self.assertEqual(cards, canvas.find_all())

    def test_special_only_filters_people_and_combines_search_stage_and_live_rules(self):
        import tkinter as tk
        from tkinter import ttk
        from ccz_randomizer.runtime.skill_memory import normalize_skill_name
        from ccz_randomizer.ui.searchable_combo import SearchableCombobox

        root = tk.Tk()
        self.addCleanup(root.destroy)
        snapshot = saved_snapshot()
        snapshot["personnel"] = snapshot["personnel"][:3]
        snapshot["fixedPersonnel"] = [next(row for row in snapshot["fixedPersonnel"]
            if row["stage"] != snapshot["personnel"][0]["stage"])]
        rows = snapshot["personnel"] + snapshot["fixedPersonnel"]
        # Keep the captured names, stages and talent arrays; change only rule scores.
        scores = {normalize_skill_name(talent): 0 for row in rows
                  for talent in row["jobTalents"] + row["personalTalents"]}
        scores[normalize_skill_name(rows[0]["jobTalents"][0])] = 5
        scores[normalize_skill_name(rows[2]["personalTalents"][0])] = 5
        scores[normalize_skill_name(rows[3]["personalTalents"][0])] = 5
        selected = [{"sevenPerson": {"specialSkillWeight": 5, "skillBaseScores": scores}}]
        root._current_rule_profile = lambda: selected[0]
        show_recruit_window(root, snapshot=snapshot)
        root.update()
        dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))

        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)

        widgets = list(descendants(dialog))
        canvas = next(w for w in widgets if isinstance(w, tk.Canvas))
        checkbox = next(w for w in widgets if isinstance(w, ttk.Checkbutton)
                        and w.cget("text") == "只看特殊技能")
        entry = next(w for w in widgets if isinstance(w, ttk.Entry)
                     and not isinstance(w, ttk.Combobox))
        stage = next(w for w in widgets if isinstance(w, SearchableCombobox))

        def settle():
            ready = tk.BooleanVar(root)
            root.after(180, lambda: ready.set(True))
            root.wait_variable(ready)

        def visible_names():
            texts = [canvas.itemcget(item, "text") for item in canvas.find_all()
                     if canvas.type(item) == "text"]
            return {row["name"] for row in rows
                    if any(text.startswith(row["name"] + " · ") for text in texts)}

        self.assertEqual({row["name"] for row in rows}, visible_names())
        checkbox.invoke(); settle()
        expected = {row["name"] for row in rows if any(
            scores[normalize_skill_name(talent)] >= 5
            for talent in row["jobTalents"] + row["personalTalents"])}
        self.assertEqual(expected, visible_names())
        self.assertNotIn(rows[1]["name"], visible_names())
        entry.insert(0, rows[2]["name"]); settle()
        self.assertEqual({rows[2]["name"]}, visible_names())
        stage.set(rows[3]["stage"].removeprefix("共通 · ")); settle()
        self.assertEqual(set(), visible_names())
        stage.set("全部关卡")
        entry.delete(0, "end")
        selected[0]["sevenPerson"]["specialSkillWeight"] = 6
        root.event_generate("<<RulesUpdated>>"); settle()
        self.assertEqual(set(), visible_names())
        selected[0]["sevenPerson"]["specialSkillWeight"] = 5
        root.event_generate("<<RulesUpdated>>"); settle()
        self.assertEqual(expected, visible_names())
        checkbox.invoke(); settle()
        self.assertEqual({row["name"] for row in rows}, visible_names())

    def test_open_personnel_recolors_when_current_rule_changes_and_unsubscribes(self):
        import tkinter as tk
        root = tk.Tk()
        self.addCleanup(root.destroy)
        snapshot = saved_snapshot()
        snapshot["personnel"][0]["personalTalents"] = ["唯我独尊", "固定增伤"]
        snapshot["personnel"][0]["jobTalents"] = ["弱点攻击"]
        selected = [{"sevenPerson": {"specialSkillWeight": 5, "skillBaseScores": {
            "唯我独尊": 5, "弱点攻击-移动": 5, "固定增伤": 1}}}]
        root._current_rule_profile = lambda: selected[0]
        show_recruit_window(root, snapshot=snapshot)
        root.update()
        dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        canvas = next(w for w in descendants(dialog) if isinstance(w, tk.Canvas))
        def fills(text):
            return [canvas.itemcget(item, "fill") for item in canvas.find_all()
                    if canvas.type(item) == "text" and canvas.itemcget(item, "text") == text]
        import time
        deadline = time.monotonic() + 3
        while not fills("唯我独尊") and time.monotonic() < deadline:
            root.update()
            time.sleep(.005)
        self.assertTrue(fills("唯我独尊"))
        self.assertTrue(all(color == "#B42318" for color in fills("唯我独尊") + fills("弱点攻击")))
        self.assertTrue(all(color != "#B42318" for color in fills("固定增伤")))
        selected[0] = {"sevenPerson": {"specialSkillWeight": 6, "skillBaseScores": {
            "唯我独尊": 5, "弱点攻击": 5, "固定增伤": 1}}}
        root.event_generate("<<RulesUpdated>>")
        ready = tk.BooleanVar(root)
        root.after(180, lambda: ready.set(True))
        root.wait_variable(ready)
        self.assertTrue(all(color != "#B42318" for color in fills("唯我独尊") + fills("弱点攻击")))
        dialog.destroy()
        self.assertFalse(root._ccz_window_events.callbacks["<<RulesUpdated>>"])

    def test_recent_keywords_commit_reuse_wrap_and_reopen(self):
        import tkinter as tk
        from tkinter import ttk
        from ccz_randomizer.ui.recent_searches import RecentSearchesBar
        from ccz_randomizer.search_history import SearchHistory
        root = tk.Tk()
        self.addCleanup(root.destroy)
        root.update()
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        show_recruit_window(root, snapshot=saved_snapshot())
        root.update()
        dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
        dialog.geometry("820x560")
        entry = next(w for w in descendants(dialog) if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox))
        entry.insert(0, "曹仁")
        root.update()
        self.assertFalse(self.history_path.exists())
        entry.focus_force()
        entry.event_generate("<Return>")
        root.update()
        bar = next(w for w in descendants(dialog) if isinstance(w, RecentSearchesBar))
        self.assertEqual(["曹仁"], [button._keyword for button in bar.buttons])
        words = ("曹操", "夏侯惇", "夏侯渊", "曹洪", "荀彧", "郭嘉", "程昱", "于禁", "典韦", "许褚")
        for word in words:
            entry.delete(0, "end"); entry.insert(0, word)
            entry.event_generate("<Return>")
        root.update()
        self.assertEqual(10, len(bar.buttons))
        self.assertTrue(all(button.winfo_x()+button.winfo_width() <= bar.chips.winfo_width() for button in bar.buttons))
        next(button for button in bar.buttons if button._keyword == "曹操").invoke()
        root.update()
        self.assertEqual("曹操", entry.get())
        self.assertEqual("曹操", bar.buttons[0]._keyword)
        entry.delete(0, "end"); entry.insert(0, "郭嘉")
        dialog.tk.call(dialog.protocol("WM_DELETE_WINDOW"))
        self.assertEqual("郭嘉", SearchHistory(self.history_path).items[0])
        show_recruit_window(root, snapshot=saved_snapshot())
        root.update()
        reopened = next(w for w in descendants(root) if isinstance(w, RecentSearchesBar))
        self.assertEqual("郭嘉", reopened.buttons[0]._keyword)
        reopened_dialog = reopened.winfo_toplevel()
        entry = next(w for w in descendants(reopened_dialog) if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox))
        entry.insert(0, "荀彧")
        reopened_dialog.destroy()
        self.assertEqual("荀彧", SearchHistory(self.history_path).items[0])

    def test_idle_search_automatically_records_and_merges_without_enter_or_blur(self):
        import tkinter as tk
        from tkinter import ttk
        from ccz_randomizer.search_history import SearchHistory
        root = tk.Tk()
        self.addCleanup(root.destroy)
        errors = []
        root.report_callback_exception = lambda *args: errors.append(args)
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        def settle():
            ready = tk.BooleanVar()
            root.after(90, lambda: ready.set(True))
            root.wait_variable(ready)
        with patch("ccz_randomizer.ui.recruitment.SEARCH_HISTORY_IDLE_MS", 50):
            show_recruit_window(root, snapshot=saved_snapshot())
            root.update()
            dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
            entry = next(w for w in descendants(dialog) if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox))
            entry.focus_force()
            entry.insert(0, "曹")
            settle()
            self.assertEqual(["曹"], SearchHistory(self.history_path).items)
            self.assertIs(entry, root.focus_get())
            entry.insert("end", "仁")
            settle()
            self.assertEqual(["曹仁"], SearchHistory(self.history_path).items)
            self.assertIs(entry, root.focus_get())
            entry.delete(0, "end"); entry.insert(0, "不存在的关键词")
            settle()
            self.assertEqual(["曹仁"], SearchHistory(self.history_path).items)
            entry.delete(0, "end")
            settle()
            self.assertEqual(["曹仁"], SearchHistory(self.history_path).items)
            entry.insert(0, "郭嘉")
            dialog.destroy()
            settle()
            self.assertEqual(["郭嘉", "曹仁"], SearchHistory(self.history_path).items)
            self.assertEqual([], errors)

    def test_stage_popup_search_selection_escape_and_outside_click(self):
        import tkinter as tk
        from ccz_randomizer.ui.searchable_combo import SearchableCombobox
        root = tk.Tk()
        self.addCleanup(root.destroy)
        errors = []
        root.report_callback_exception = lambda *args: errors.append(args)
        root.update()
        show_recruit_window(root, snapshot=saved_snapshot())
        root.update()
        dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
        dialog.grab_set()
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        combo = next(w for w in descendants(dialog) if isinstance(w, SearchableCombobox))
        combo.open_popup(); root.update()
        combo.search_entry.insert(0, "颍川")
        root.update()
        self.assertEqual("全部关卡", combo.get())
        self.assertEqual(("颍川之战",), combo.listbox.get(0, "end"))
        combo.search_entry.focus_force()
        combo.search_entry.event_generate("<Return>"); root.update()
        self.assertEqual("颍川之战", combo.get())
        self.assertIsNone(combo.popup)
        self.assertIs(dialog, root.grab_current())
        combo.open_popup(); root.update()
        combo.search_entry.insert(0, "不存在的关卡"); root.update()
        self.assertEqual(0, combo.listbox.size())
        self.assertTrue(combo.empty.winfo_manager())
        combo.search_entry.focus_force()
        combo.search_entry.event_generate("<Escape>"); root.update()
        self.assertIsNone(combo.popup)
        self.assertEqual("颍川之战", combo.get())
        combo.open_popup(); root.update()
        canvas = next(w for w in descendants(dialog) if isinstance(w, tk.Canvas))
        canvas.event_generate("<ButtonPress-1>", x=10, y=10); root.update()
        self.assertIsNone(combo.popup)
        self.assertIs(dialog, root.grab_current())
        combo.open_popup(); root.update()
        dialog.destroy(); root.update()
        self.assertEqual([], errors)

    def test_1104_choices_are_appended_to_card_titles(self):
        import tkinter as tk
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        root.withdraw()
        self.addCleanup(root.destroy)
        dialog = tk.Toplevel(root)
        dialog.withdraw()
        snapshot = json.loads((FIXTURES.parent / "personnel_220_1104/randomized-result.json").read_text(encoding="utf-8"))
        with patch("ccz_randomizer.ui.recruitment.centered_toplevel", return_value=dialog):
            show_recruit_window(root, snapshot=snapshot)
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        canvas = next(w for w in descendants(dialog) if isinstance(w, tk.Canvas))
        # The complete catalog now renders in input-friendly batches.
        import time
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            root.update()
            if all(any(name in canvas.itemcget(item, "text") for item in canvas.find_all()
                       if canvas.type(item) == "text") for name in ("曹休", "曹纯")):
                break
            time.sleep(.002)
        texts = [canvas.itemcget(item, "text") for item in canvas.find_all() if canvas.type(item) == "text"]
        self.assertIn("曹休 · 轻炮车/弓骑兵", texts)
        self.assertIn("曹纯 · 道士/虎豹骑", texts)
        self.assertFalse(any("随机结果" in text or "入队时兵种选项" in text for text in texts))
        self.assertIn("兵种天赋", texts)
        self.assertIn("人物天赋", texts)

    def test_all_people_cards_filter_and_stage_grouping(self):
        import tkinter as tk
        from tkinter import ttk
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        root.deiconify()
        self.addCleanup(root.destroy)
        show_recruit_window(root, snapshot=saved_snapshot())
        root.update()

        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)

        widgets = list(descendants(root))
        self.assertGreaterEqual(sum(1 for w in widgets if isinstance(w, tk.Canvas)), 1)
        canvas = next(w for w in widgets if isinstance(w, tk.Canvas))
        def texts():
            return [canvas.itemcget(item, "text") for item in canvas.find_all() if canvas.type(item) == "text"]
        wait_until(root, lambda: any(text.startswith("曹仁 · ") for text in texts()))
        self.assertTrue(any(text.startswith("曹仁 · ") for text in texts()))
        self.assertEqual(["只看特殊技能"],
                         [w.cget("text") for w in widgets if isinstance(w, ttk.Checkbutton)])
        dialog = next(w for w in widgets if isinstance(w, tk.Toplevel))
        self.assertEqual(dialog.title(), "入队人员")
        dialog.geometry("820x560")
        root.update()
        root.after(500, root.quit); root.mainloop()
        from ccz_randomizer.ui.searchable_combo import SearchableCombobox
        stage_combo = next(w for w in widgets if isinstance(w, SearchableCombobox))
        special_filter = next(w for w in widgets if isinstance(w, ttk.Checkbutton))
        self.assertTrue(special_filter.winfo_ismapped())
        self.assertGreaterEqual(special_filter.winfo_rootx(),
                                stage_combo.winfo_rootx() + stage_combo.winfo_width())
        self.assertLess(abs((special_filter.winfo_rooty() + special_filter.winfo_height() / 2)
                            - (stage_combo.winfo_rooty() + stage_combo.winfo_height() / 2)), 2)
        self.assertLessEqual(special_filter.winfo_rootx() + special_filter.winfo_reqwidth(),
                             dialog.winfo_rootx() + dialog.winfo_width() - 20)
        rectangles = [canvas.coords(item) for item in canvas.find_all()
                      if canvas.type(item) == "rectangle"]
        self.assertTrue(rectangles)
        self.assertTrue(all(bounds[2] <= canvas.winfo_width() for bounds in rectangles))
        for top in {bounds[1] for bounds in rectangles}:
            self.assertEqual(len({bounds[3] for bounds in rectangles if bounds[1] == top}), 1)
        from ccz_randomizer.recruitment import parse_recruits
        snapshot = saved_snapshot()
        by_id = {row.record_index: row for row in parse_recruits(dict(snapshot, personnel=snapshot["personnel"] + snapshot["fixedPersonnel"]))}
        for item in canvas.find_all():
            if canvas.type(item) != "rectangle":
                continue
            tag = canvas.gettags(item)[0]
            row = by_id[int(tag.split(":")[1])]
            text_items = [i for i in canvas.find_withtag(tag) if canvas.type(i) == "text"]
            cost = next(i for i in text_items if canvas.itemcget(i, "text") == ("固定" if row.entry_kind == "fixed" else f"{row.cost}次"))
            title = next(i for i in text_items if canvas.itemcget(i, "text").startswith(row.name + " · "))
            self.assertLess(canvas.bbox(title)[2], canvas.bbox(cost)[0])
        # Cards wrap within the viewport, without horizontal scrolling.
        self.assertEqual(canvas.xview(), (0.0, 1.0))
        self.assertFalse(any(text.startswith("共通 · ") for text in texts()))
        self.assertIn("兵种天赋", texts())
        self.assertIn("人物天赋", texts())
        search = next(w for w in descendants(root) if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox))
        search.insert(0, "曹仁")
        root.after(150, root.quit); root.mainloop()
        self.assertEqual(1, sum(text.startswith("曹仁 · ") for text in texts()))
        search.delete(0, "end")
        stage = next(w for w in descendants(root) if isinstance(w, ttk.Combobox))
        stage.set("颍川之战")
        root.update()
        root.after(500, root.quit); root.mainloop()
        self.assertIn("颍川之战", texts())
        self.assertIn("固定入队 · 战前（随机预览）", texts())
        self.assertIn("可招募 · 战后", texts())
        fixed_bottoms, recruit_tops = [], []
        for item in canvas.find_all():
            if canvas.type(item) != "rectangle":
                continue
            index = int(canvas.gettags(item)[0].split(":")[1])
            bounds = canvas.coords(item)
            if by_id[index].entry_kind == "fixed":
                fixed_bottoms.append(bounds[3])
            else:
                recruit_tops.append(bounds[1])
        self.assertEqual(len(fixed_bottoms), 3)
        self.assertGreater(min(recruit_tops), max(fixed_bottoms))

