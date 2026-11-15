"""Real rule defaults and local SQLite observations; no game required."""
from tkinter import ttk
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from ccz_randomizer.rules.config import default_rule_config, validate_rule_config, save_rule_config, load_rule_config
from ccz_randomizer.rules.identity import filtering_fingerprint, changed_profiles, mark_overwritten, new_rule_identity
from ccz_randomizer.statistics import StatisticsRecorder
from ccz_randomizer.statistics_store import StatisticsRepository
from ccz_randomizer.statistics_rules import has_rule_statistics
from ccz_randomizer.rules.editor import show_rule_editor
from ccz_randomizer import app
from ccz_randomizer.ui.inputs import TextEntry
from tests.unit.test_statistics import runner_fixture
from tests.unit.test_rule_editor import descendants, SKILL_CATALOG


def editable_config():
    config = default_rule_config()
    profile = copy.deepcopy(config["profiles"]["默认规则"])
    profile.update(builtin=False, editorMode="advanced")
    profile["threePerson"].update(jobQualificationMode="total", minJobAverage=7.4)
    config["profiles"]["测试规则"] = profile
    config["activeProfile"] = "测试规则"
    return validate_rule_config(config)


class RuleStatisticsIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config = editable_config()
        save_rule_config(self.base, self.config)
        self.repo = StatisticsRepository(self.base)

    def record(self, name=None, profile=None, *, legacy=False):
        name = name or self.config["activeProfile"]
        profile = profile or self.config["profiles"][name]
        recorder = StatisticsRecorder(self.base, run_id="run", rule_name=name, rule=profile, mode="three")
        if legacy:
            recorder.context["rule_json"] = json.dumps(profile)
            recorder.context["revision"] = hashlib.sha256((name + "\n" + json.dumps(profile)).encode()).hexdigest()
        with recorder.attempt(runner_fixture(reject=True), round_number=1, slot=1, attempt=1):
            pass
        recorder.close()
        return recorder.context["revision"]

    def test_statistics_prompt_checks_only_associated_observations_without_creating_database(self):
        changes = [("测试规则", "测试规则")]
        self.assertFalse(has_rule_statistics(self.base, self.config, changes))
        self.assertFalse(self.repo.path.exists())
        self.record("默认规则")
        self.assertFalse(has_rule_statistics(self.base, self.config, changes))
        self.record()
        self.assertTrue(has_rule_statistics(self.base, self.config, changes))
        # Once overwritten, the unassociated old data must not trigger another loss warning.
        mark_overwritten(self.config, changes)
        self.assertFalse(has_rule_statistics(self.base, self.config, changes))
        self.record()
        self.assertTrue(has_rule_statistics(self.base, self.config, changes))

    def test_statistics_snapshot_without_observations_does_not_trigger_warning(self):
        self.record()
        with self.repo.connect() as db:
            db.execute("DELETE FROM attempts")
        self.assertFalse(has_rule_statistics(self.base, self.config, [("测试规则", "测试规则")]))

    def test_renamed_and_legacy_snapshots_still_trigger_association_warning(self):
        profile = copy.deepcopy(self.config["profiles"]["测试规则"])
        profile.pop("statisticsId")
        self.record(profile=profile, legacy=True)
        self.config["profiles"]["新名字"] = self.config["profiles"].pop("测试规则")
        self.config["profiles"]["新名字"]["statisticsAliases"] = ["测试规则"]
        self.assertTrue(has_rule_statistics(self.base, self.config, [("新名字", "新名字")]))

    def test_rename_collection_and_presentation_preserve_filter_and_latest_name(self):
        revision = self.record()
        original = copy.deepcopy(self.config)
        profile = self.config["profiles"].pop("测试规则")
        self.config["profiles"]["新的名称"] = profile
        self.config["activeProfile"] = "新的名称"
        profile["dataCollection"]["recruitment"] = True
        profile["resultImage"]["members"] = ["曹操"]
        save_rule_config(self.base, self.config)
        self.assertEqual([], changed_profiles(original, self.config))
        self.assertEqual(revision, self.record())
        self.assertEqual([(revision, "新的名称")], self.repo.choices()["rules"])
        self.assertEqual(2, self.repo.query(revision=revision)["totals"][0])
        self.assertEqual([("新的名称", 2, 0)], self.repo.query()["comparisons"])

    def test_overwrite_retains_all_observations_but_only_new_filter_is_selectable(self):
        old = self.record()
        self.config["profiles"]["测试规则"]["threePerson"]["minJobAverage"] = 9
        save_rule_config(self.base, self.config)
        self.assertEqual([], self.repo.choices()["rules"])
        self.assertEqual(1, self.repo.query()["totals"][0])
        new = self.record()
        self.assertNotEqual(old, new)
        self.assertEqual([(new, "测试规则")], self.repo.choices()["rules"])
        self.assertEqual(1, self.repo.query(revision=new)["totals"][0])
        self.assertEqual(2, self.repo.query()["totals"][0])
        self.assertEqual([("测试规则", 1, 0)], self.repo.query()["comparisons"])

    def test_legacy_metadata_snapshots_merge_and_survive_rename(self):
        profile = copy.deepcopy(self.config["profiles"]["测试规则"])
        profile.pop("statisticsId")
        self.record(profile=profile, legacy=True)
        profile["dataCollection"]["recruitment"] = True
        self.record(profile=profile, legacy=True)
        self.config["profiles"]["新名字"] = self.config["profiles"].pop("测试规则")
        self.config["profiles"]["新名字"]["statisticsAliases"] = ["测试规则"]
        self.config["activeProfile"] = "新名字"
        save_rule_config(self.base, self.config)
        (revision, name), = self.repo.choices()["rules"]
        self.assertEqual("新名字", name)
        self.assertEqual(2, self.repo.query(revision=revision)["totals"][0])
        self.assertEqual(2, sum(row[1] for row in self.repo.ranking("jobs", revision=revision)["rows"]) // 2)

    def test_new_rule_retains_original_association_and_has_distinct_identity(self):
        original = self.record()
        profile = copy.deepcopy(self.config["profiles"]["测试规则"])
        new_rule_identity(profile)
        profile["threePerson"]["minJobAverage"] = 9
        self.config["profiles"]["新规则"] = profile
        save_rule_config(self.base, self.config)
        new = self.record("新规则", profile)
        self.assertEqual({(original, "测试规则"), (new, "新规则")}, set(self.repo.choices()["rules"]))
        self.assertEqual(1, self.repo.query(revision=original)["totals"][0])

    def test_explicit_default_scores_and_numeric_types_are_equivalent(self):
        profile = self.config["profiles"]["测试规则"]
        other = copy.deepcopy(profile)
        name, score, kind = next(iter(app.JOB_MAP.values()))
        other["jobScoring"]["jobBaseScores"][name] = score
        other["jobScoring"]["jobTypeOverrides"][name] = kind
        other["threePerson"]["minJobAverage"] = float(profile["threePerson"]["minJobAverage"])
        self.assertEqual(filtering_fingerprint(profile), filtering_fingerprint(other))

    def test_reverting_a_previously_overwritten_filter_does_not_reassociate_old_data(self):
        old = self.record()
        before = copy.deepcopy(self.config)
        self.config["profiles"]["测试规则"]["threePerson"]["minJobAverage"] = 9
        mark_overwritten(self.config, changed_profiles(before, self.config))
        save_rule_config(self.base, self.config)
        self.record()
        before = copy.deepcopy(self.config)
        self.config["profiles"]["测试规则"]["threePerson"]["minJobAverage"] = 7.4
        mark_overwritten(self.config, changed_profiles(before, self.config))
        save_rule_config(self.base, self.config)
        new = self.record()
        self.assertNotEqual(old, new)
        self.assertEqual([(new, "测试规则")], self.repo.choices()["rules"])
        self.assertEqual(1, self.repo.query(revision=new)["totals"][0])
        self.assertEqual(3, self.repo.query()["totals"][0])


class RuleChangeEditorTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config = editable_config()
        save_rule_config(self.base, self.config)
        self.saved = []
        with patch("ccz_randomizer.rules.editor.show_centered"):
            show_rule_editor(self.root, self.base, self.config, app.JOB_MAP,
                             app.TEAM_MEMBERS, SKILL_CATALOG, self.saved.append)
        self.editor = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
        self.buttons = {w.cget("text"): w for w in descendants(self.editor) if isinstance(w, ttk.Button)}
        self.root.update()

    def edit_filter(self):
        entry = next(w for w in descendants(self.editor)
                     if isinstance(w, TextEntry) and w.get() == "7.4")
        entry.delete(0, "end")
        entry.insert(0, "8.5")

    def test_save_confirm_cancel_and_new_rule(self):
        self.edit_filter()
        for action in ("cancel", "new"):
            with patch("ccz_randomizer.rules.editor.ask_rule_change", return_value=action) as prompt:
                self.buttons["保存规则"].invoke()
            self.assertEqual(1, prompt.call_count)
            if action == "cancel":
                self.assertFalse(self.saved)
                self.assertTrue(self.editor.winfo_exists())
                self.assertEqual(self.config, load_rule_config(self.base).config)
            else:
                saved, = self.saved
                self.assertEqual(self.config["profiles"]["测试规则"], saved["profiles"]["测试规则"])
                self.assertEqual(8.5, saved["profiles"]["测试规则副本"]["threePerson"]["minJobAverage"])
                self.assertNotEqual(saved["profiles"]["测试规则"]["statisticsId"],
                                    saved["profiles"]["测试规则副本"]["statisticsId"])

    def test_cancel_keeps_editor_open_then_discards_without_writing(self):
        self.edit_filter()
        before = (self.base / "random_rules_v2.json").read_bytes()
        for action in ("cancel", "confirm"):
            with patch("ccz_randomizer.rules.editor.ask_rule_change", return_value=action) as prompt:
                self.buttons["取消"].invoke()
            self.assertTrue(prompt.call_args.kwargs["closing"])
        self.assertFalse(self.editor.winfo_exists())
        self.assertEqual(before, (self.base / "random_rules_v2.json").read_bytes())

    def test_saving_unchanged_rule_does_not_prompt(self):
        with patch("ccz_randomizer.rules.editor.ask_rule_change") as prompt:
            self.buttons["保存规则"].invoke()
        prompt.assert_not_called()
        self.assertEqual(1, len(self.saved))

    def test_overwrite_confirms_and_preserves_identity(self):
        self.edit_filter()
        with patch("ccz_randomizer.rules.editor.ask_rule_change", return_value="confirm") as prompt:
            self.buttons["保存规则"].invoke()
        prompt.assert_called_once()
        self.assertIs(prompt.call_args.kwargs["has_statistics"], False)
        self.assertNotIn("names", prompt.call_args.kwargs)
        self.assertEqual(8.5, self.saved[0]["profiles"]["测试规则"]["threePerson"]["minJobAverage"])
        self.assertEqual(self.config["profiles"]["测试规则"]["statisticsId"],
                         self.saved[0]["profiles"]["测试规则"]["statisticsId"])

    def test_rename_saves_without_filter_warning(self):
        with patch("ccz_randomizer.rules.editor.ask_text", return_value="新名字"):
            self.buttons["重命名"].invoke()
        with patch("ccz_randomizer.rules.editor.ask_rule_change") as prompt:
            self.buttons["保存规则"].invoke()
        prompt.assert_not_called()
        self.assertEqual(self.config["profiles"]["测试规则"]["statisticsId"],
                         self.saved[0]["profiles"]["新名字"]["statisticsId"])

    def test_collection_only_saves_without_rewriting_filter_or_prompting(self):
        check = next(w for w in descendants(self.editor)
                     if isinstance(w, tk.Checkbutton) and w.cget("text") == "采集入队人员信息")
        check.invoke()
        with patch("ccz_randomizer.rules.editor.ask_rule_change") as prompt:
            self.buttons["保存规则"].invoke()
        prompt.assert_not_called()
        saved = self.saved[0]["profiles"]["测试规则"]
        self.assertTrue(saved["dataCollection"]["recruitment"])
        self.assertEqual(filtering_fingerprint(self.config["profiles"]["测试规则"]), filtering_fingerprint(saved))


    def test_closing_after_rename_does_not_show_filter_or_new_rule_warning(self):
        with patch("ccz_randomizer.rules.editor.ask_text", return_value="新名字"):
            self.buttons["重命名"].invoke()
        with patch("ccz_randomizer.rules.editor.ask_rule_change") as filtering, patch(
            "ccz_randomizer.rules.editor.messagebox.askyesno") as generic:
            self.buttons["取消"].invoke()
        filtering.assert_not_called()
        generic.assert_not_called()
        self.assertFalse(self.editor.winfo_exists())

    def test_close_can_save_changes_as_new_rule(self):
        self.edit_filter()
        with patch("ccz_randomizer.rules.editor.ask_rule_change", return_value="new") as prompt:
            self.buttons["取消"].invoke()
        self.assertTrue(prompt.call_args.kwargs["closing"])
        self.assertEqual(1, len(self.saved))
        self.assertEqual(self.config["profiles"]["测试规则"], self.saved[0]["profiles"]["测试规则"])
        self.assertIn("测试规则副本", self.saved[0]["profiles"])

    def test_prompt_presents_three_explicit_actions(self):
        from ccz_randomizer.ui.rule_change_prompt import ask_rule_change
        captured = []
        def dismiss():
            dialog = next(w for w in self.editor.winfo_children() if isinstance(w, tk.Toplevel))
            buttons = {w.cget("text"): w for w in descendants(dialog) if isinstance(w, ttk.Button)}
            captured.extend(buttons)
            buttons["取消"].invoke()
        self.root.after(10, dismiss)
        with patch("ccz_randomizer.ui.rule_change_prompt.show_centered"):
            self.assertEqual("cancel", ask_rule_change(self.editor))
        self.assertEqual({"确认覆盖", "取消", "保存为新规则"}, set(captured))

    def test_save_and_close_prompts_report_existing_statistics(self):
        recorder = StatisticsRecorder(self.base, run_id="prompt", rule_name="测试规则",
                                      rule=self.config["profiles"]["测试规则"], mode="three")
        with recorder.attempt(runner_fixture(reject=True), round_number=1, slot=1, attempt=1):
            pass
        recorder.close()
        self.edit_filter()
        for button in ("保存规则", "取消"):
            with patch("ccz_randomizer.rules.editor.ask_rule_change", return_value="cancel") as prompt:
                self.buttons[button].invoke()
            self.assertIs(prompt.call_args.kwargs["has_statistics"], True)

    def test_prompt_omits_names_and_statistics_when_no_observations_exist(self):
        from ccz_randomizer.ui.rule_change_prompt import ask_rule_change
        for closing in (False, True):
            for has_statistics in (False, True):
                with self.subTest(closing=closing, has_statistics=has_statistics):
                    captured = []
                    def dismiss():
                        dialog = next(w for w in self.editor.winfo_children() if isinstance(w, tk.Toplevel))
                        captured.extend(str(w.cget("text")) for w in descendants(dialog) if isinstance(w, tk.Label))
                        next(w for w in descendants(dialog) if isinstance(w, ttk.Button) and w.cget("text") == "取消").invoke()
                    self.root.after(10, dismiss)
                    with patch("ccz_randomizer.ui.rule_change_prompt.show_centered"):
                        self.assertEqual(ask_rule_change(self.editor, closing=closing, has_statistics=has_statistics), "cancel")
                    text = "\n".join(captured)
                    self.assertNotIn("测试规则", text)
                    self.assertEqual("统计" in text, has_statistics)
                    if has_statistics and not closing:
                        self.assertIn("旧数据仍保留在全部统计中", text)


    def test_statistics_options_refresh_latest_name_and_preserve_selection(self):
        import time
        from ccz_randomizer.ui.statistics import show_statistics_window
        from ccz_randomizer.ui.searchable_combo import SelectionCombobox
        recorder = StatisticsRecorder(self.base, run_id="run", rule_name="测试规则",
            rule=self.config["profiles"]["测试规则"], mode="three")
        with recorder.attempt(runner_fixture(reject=True), round_number=1, slot=1, attempt=1):
            pass
        recorder.close()
        with patch("ccz_randomizer.ui.statistics.show_centered"):
            window = show_statistics_window(self.root, self.base)
        combo = next(w for w in descendants(window) if isinstance(w, SelectionCombobox) and w.get() == "全部规则")
        def wait_for(predicate):
            deadline = time.monotonic() + 3
            while not predicate() and time.monotonic() < deadline:
                self.root.update()
                time.sleep(.005)
            self.assertTrue(predicate())
        wait_for(lambda: "测试规则" in combo.cget("values"))
        self.assertEqual(("全部规则", "测试规则"), tuple(combo.cget("values")))
        combo.set("测试规则")
        self.config["profiles"]["新名称"] = self.config["profiles"].pop("测试规则")
        self.config["activeProfile"] = "新名称"
        save_rule_config(self.base, self.config)
        self.root.event_generate("<<RulesUpdated>>", when="tail")
        wait_for(lambda: combo.get() == "新名称")
        self.assertEqual(("全部规则", "新名称"), tuple(combo.cget("values")))
        window.destroy()
        self.root.update()
