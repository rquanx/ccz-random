import copy
import json
import tempfile
import unittest
from pathlib import Path

from ccz_randomizer.rules.config import (
    default_rule_config, merge_rule_export, build_rule_export,
    save_rule_config, load_rule_config, evaluate_job_rules,
)
from ccz_randomizer.rules.legacy_import import LegacyModeRequired, read_legacy_mode

FIXTURES = Path(__file__).parents[1] / "fixtures" / "rules_210"


class LegacyRuleImportTests(unittest.TestCase):
    def payload(self, name="export.json"):
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    def test_stable_exports_and_full_config_follow_saved_runtime_mode(self):
        for filename in ("export.json", "full-config.json"):
            for mode, names, threshold, count in (
                ("three", ["曹操"], 8.1, 1),
                ("seven", ["曹仁", "曹洪"], 7.3, 2),
            ):
                with self.subTest(filename=filename, mode=mode):
                    payload = self.payload(filename)
                    before = copy.deepcopy(payload)
                    config, imported = merge_rule_export(default_rule_config(), payload, legacy_mode=mode)
                    profile = config["profiles"][imported[0]]
                    self.assertCountEqual(names, profile["threePerson"]["qualifiedMembers"])
                    self.assertEqual(threshold, profile["threePerson"]["minJobAverage"])
                    self.assertEqual(count, profile["threePerson"]["minQualifiedCount"])
                    self.assertEqual("count", profile["threePerson"]["jobQualificationMode"])
                    self.assertEqual("advanced", profile["editorMode"])
                    self.assertEqual(dict(mode="total", threshold=9, requiredCount=1), profile["skillQualification"])
                    self.assertEqual(8.5, profile["jobScoring"]["jobBaseScores"]["群雄"])
                    self.assertEqual("MASTER", profile["jobScoring"]["jobTypeOverrides"]["群雄"])
                    self.assertEqual(6, profile["sevenPerson"]["skillBaseScores"]["先手攻击"])
                    self.assertEqual("NONE", profile["sevenPerson"]["skillTypeOverrides"]["先手攻击"])
                    self.assertFalse(profile["sevenPerson"]["highJobAutoPass"])
                    self.assertFalse(profile["jobScoring"]["extraMasterPenaltyEnabled"])
                    self.assertEqual(before, payload)
                    config["activeProfile"] = imported[0]
                    result = evaluate_job_rules(config, "three",
                        [dict(name="群雄", score=8, type="ALL_ROUNDER") for _ in names],
                        [dict(name=name, primaryType="NONE", secondaryType="NONE") for name in names])
                    self.assertTrue(result.qualified)

    def test_unknown_mode_does_not_silently_choose_or_mutate_existing_rules(self):
        config = default_rule_config()
        before = copy.deepcopy(config)
        with self.assertRaises(LegacyModeRequired):
            merge_rule_export(config, self.payload())
        self.assertEqual(before, config)

    def test_companion_settings_require_explicit_valid_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            rule_path = Path(directory) / "export.json"
            settings = rule_path.with_name("randomizer_settings.json")
            self.assertIsNone(read_legacy_mode(rule_path))
            for value in ("{}", "[]", "{broken", '{"randomMode":"invalid"}'):
                settings.write_text(value, encoding="utf-8")
                self.assertIsNone(read_legacy_mode(rule_path))
            settings.write_text('{"version":1,"randomMode":"seven"}', encoding="utf-8-sig")
            self.assertEqual("seven", read_legacy_mode(rule_path))

    def test_save_export_and_reimport_preserve_migration_without_mode(self):
        config, names = merge_rule_export(default_rule_config(), self.payload(), legacy_mode="seven")
        with tempfile.TemporaryDirectory() as directory:
            save_rule_config(Path(directory), config)
            loaded = load_rule_config(Path(directory)).config
        exported = build_rule_export(loaded, names)
        merged, added = merge_rule_export(loaded, exported)
        self.assertEqual("旧版自定义(1)", added[0])
        self.assertEqual(loaded["profiles"][names[0]], merged["profiles"][added[0]])

    def test_v1_skill_threshold_is_migrated_instead_of_reset_to_default(self):
        payload = dict(version=1, activeProfile="旧规则", profiles={"旧规则": {
            "threePerson": {"minJobAverage": 8.1},
            "sevenPerson": {"minJobAverage": 7.2, "lowMinEffectiveSkills": 11}}})
        config, names = merge_rule_export(default_rule_config(), payload, legacy_mode="seven")
        profile = config["profiles"][names[0]]
        self.assertEqual(11, profile["skillQualification"]["threshold"])
        self.assertEqual(7.2, profile["threePerson"]["minJobAverage"])

    def test_editor_import_uses_companion_mode_without_prompt(self):
        import tkinter as tk
        from unittest.mock import patch
        from ccz_randomizer.rules.editor import show_rule_editor
        from tests.unit.test_rule_editor import JOB_MAP, TEAM_MEMBERS, SKILL_CATALOG, descendants
        root = tk.Tk()
        self.addCleanup(root.destroy)
        saved = []
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as destination:
            path = Path(source) / "export.json"
            path.write_text(json.dumps(self.payload(), ensure_ascii=False), encoding="utf-8")
            path.with_name("randomizer_settings.json").write_text('{"randomMode":"seven"}', encoding="utf-8")
            with patch("ccz_randomizer.rules.editor.filedialog.askopenfilename", return_value=str(path)), \
                 patch("ccz_randomizer.rules.editor.messagebox.askyesnocancel") as ask, \
                 patch("ccz_randomizer.rules.editor.messagebox.showinfo") as info, \
                 patch("ccz_randomizer.rules.editor.messagebox.showerror") as error:
                show_rule_editor(root, Path(destination), default_rule_config(), JOB_MAP,
                                 TEAM_MEMBERS, SKILL_CATALOG, saved.append)
                root.update()
                next(w for w in descendants(root) if isinstance(w, tk.Button) and w.cget("text") == "导入规则").invoke()
                root.update()
                ask.assert_not_called()
                error.assert_not_called()
                self.assertIn("旧版规则已自动迁移", info.call_args.args[1])
                profile = saved[-1]["profiles"]["旧版自定义"]
                self.assertEqual("seven", profile["legacyImport"]["mode"])
                self.assertEqual(7.3, profile["threePerson"]["minJobAverage"])
                self.assertEqual(json.loads(path.read_text(encoding="utf-8")), self.payload())
