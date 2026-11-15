"""Real versioned help fixtures; no live game or guessed combat data."""
from dataclasses import replace
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from ccz_randomizer.effect_dictionary import _plain, load_effect_dictionary
from ccz_randomizer.profile_context import current_context


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class EffectDictionaryTests(unittest.TestCase):
    def setUp(self):
        self.dictionary = load_effect_dictionary()

    def test_help_is_independent_and_covers_current_effect_codes(self):
        self.assertEqual(99, len(self.dictionary.search(category="宝物特效")))
        self.assertEqual(226, len(self.dictionary.search(category="特技说明")))
        self.assertEqual(302, len({item.key for item in self.dictionary.entries}))
        guide = self.dictionary.search("引导攻击", "特技说明")
        self.assertEqual(1, len(guide))
        self.assertIn("击杀一个敌人后", guide[0].description)
        self.assertIn("连续攻击范围内的另一个敌人", guide[0].description)

    def test_equivalent_names_share_one_result_and_preserve_alias_search(self):
        for query in ("削铁如泥", "削铁如泥ALL"):
            entry, = self.dictionary.search(query)
            self.assertEqual("削铁如泥", entry.name)
            self.assertIn("10%～15%", entry.description)
            self.assertEqual(("equipment:72", "skill:111"), entry.source_keys)
        for query in ("反击成双", "策略免疫", "纵横无阻", "吸血攻击"):
            with self.subTest(query=query):
                entry, = [item for item in self.dictionary.search(query) if item.name == query]
                self.assertEqual(2, len(entry.source_keys))
        entry, = self.dictionary.search("节约MP -30%")
        self.assertEqual("equipment:57", entry.key)

    def test_same_name_different_mechanisms_remain_distinct(self):
        for query in ("破甲攻击", "MP防御", "主动连击", "引导攻击", "迅捷之勇"):
            results = [item for item in self.dictionary.search(query) if item.name.startswith(query)]
            self.assertEqual(2, len(results), query)
            self.assertTrue(any("（宝物）" in item.name for item in results))
            self.assertTrue(any("（特技）" in item.name for item in results))
        equipment, skill = self.dictionary.search("破甲攻击")
        self.assertIn("最大HP", equipment.description)
        self.assertIn("固定值", skill.description)

    def test_parameterized_names_and_keywords_find_the_effect(self):
        for query, key in (("一夫当关12%", "equipment:105"), ("节约MP-30%", "equipment:57"),
                           ("能力替换 攻→防", "equipment:124"), ("策略先手-焦热", "equipment:120"),
                           ("穿透攻击-两格", "equipment:51"), ("MP防御+10", "equipment:68")):
            with self.subTest(query=query):
                self.assertIn(key, {item.key for item in self.dictionary.search(query, "宝物特效")})
        self.assertIn("equipment:54", {item.key for item in self.dictionary.search("击杀 连续", "宝物特效")})
        self.assertEqual((), self.dictionary.search("完全不存在的特效"))

    def test_original_item_codes_resolve_composite_effects(self):
        expected = {"回马强反": ("转向90°", "反击伤害不衰减"),
                    "辅士猛击": ("士气", "混乱"),
                    "昭威奋烈": ("再反击一次", "首次受到"),
                    "百战不殆": ("自身等级", "敌人等级"),
                    "辅爆强连": ("爆发力", "连击率"),
                    "怀恨必中": ("必定命中", "被攻击的次数")}
        for query, details in expected.items():
            entry, = self.dictionary.search(query, "宝物特效")
            for detail in details:
                self.assertIn(detail, entry.description)
        entry, = self.dictionary.search("穿越偷袭", "宝物特效")
        self.assertIn("穿越移动", entry.description)
        self.assertIn("偷袭攻击", entry.description)

    def test_equipment_uses_its_own_mechanism_and_parameters(self):
        entry, = self.dictionary.search("破甲攻击25%", "宝物特效")
        self.assertIn("目标最大HP", entry.description)
        self.assertIn("必定命中", entry.description)
        entry, = self.dictionary.search("限制伤害75", "宝物特效")
        self.assertIn("最高为特效值", entry.description)
        self.assertNotIn("70", entry.description)
        entry, = self.dictionary.search("攻击限伤", "特技说明")
        self.assertIn("70", entry.description)

    def test_all_equipment_entries_have_direct_explanations(self):
        self.assertEqual("", self.dictionary.notice)
        for item in self.dictionary.search(category="宝物特效"):
            self.assertTrue(item.description.strip())
            for redundant in ("尚未核实", "说明待核实", "仅供理解", "说明来源", "不能直接套用", "同名特技"):
                self.assertNotIn(redundant, item.description)

    def test_equipment_mimic_is_searchable_with_its_verified_help(self):
        entry, = self.dictionary.search("特效模仿", "宝物特效")
        self.assertEqual("equipment:116", entry.key)
        self.assertIn("周围四格", entry.description)
        self.assertIn("不分敌我", entry.description)
        self.assertIn("部分特效无法模仿", entry.description)

    def test_category_lookup_keeps_its_own_name_and_all_aliases(self):
        for query in ("众矢之的", "众矢之的-攻击", "众矢之的-策略", "众矢之的ALL"):
            entry, = self.dictionary.search(query, "宝物特效")
            self.assertEqual("equipment:111", entry.key)
            self.assertTrue(entry.name.startswith("众矢之的"))
        entry, = self.dictionary.search("穿透攻击-两格", "宝物特效")
        self.assertEqual("equipment:51", entry.key)

    def test_empty_placeholder_and_joke_help_is_not_presented_as_mechanics(self):
        entries = {item.key: item for item in self.dictionary.entries}
        for skill_id in (3, 36, 73, 78, 103, 211):
            self.assertNotIn(f"skill:{skill_id}", entries)
        self.assertFalse(self.dictionary.search("晴天雨天"))

    def test_different_version_or_changed_catalog_never_reuses_old_help(self):
        context = current_context()
        contexts = [replace(context, profile_id="ccz-v2.2"), replace(context, game_version="2.30")]
        skills = _plain(context.skills)
        skills["runtimeCatalog"][24]["name"] = "不同的引导攻击"
        contexts.append(replace(context, skills=skills))
        for other in contexts:
            with self.subTest(version=other.game_version):
                dictionary = load_effect_dictionary(other)
                self.assertFalse(dictionary.entries)
                self.assertIn("暂无配套", dictionary.notice)
        # Unrelated package revision does not invalidate identical effect data.
        self.assertTrue(load_effect_dictionary(replace(context, revision=100)).entries)

    def test_frozen_application_loads_bundled_help(self):
        from ccz_randomizer.effect_dictionary import _read_resource
        root = Path(__file__).resolve().parents[2]
        _read_resource.cache_clear()
        self.addCleanup(_read_resource.cache_clear)
        with patch("sys._MEIPASS", str(root), create=True):
            self.assertEqual(302, len(load_effect_dictionary().entries))


class EffectDictionaryUiTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)

    def test_search_selection_empty_result_and_pending_close(self):
        from ccz_randomizer.ui.effect_dictionary import show_effect_dictionary
        dialog = show_effect_dictionary(self.root)
        table = next(w for w in descendants(dialog) if isinstance(w, ttk.Treeview))
        text = next(w for w in descendants(dialog) if isinstance(w, tk.Text))
        search = next(w for w in descendants(dialog) if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox))
        self.assertEqual(302, len(table.get_children()))
        search.insert(0, "穿越偷袭")
        self.root.after(150, self.root.quit)
        self.root.mainloop()
        self.assertEqual(("equipment:93",), table.get_children())
        self.assertIn("偷袭攻击", text.get("1.0", "end"))
        self.assertEqual("disabled", text.cget("state"))
        self.assertFalse(table.cget("columns"))
        self.assertNotIn("说明来源", text.get("1.0", "end"))
        search.delete(0, "end")
        search.insert(0, "无此特效")
        self.root.after(150, self.root.quit)
        self.root.mainloop()
        self.assertFalse(table.get_children())
        self.assertIn("没有匹配", text.get("1.0", "end"))
        search.delete(0, "end")
        dialog.destroy()
        self.root.after(150, self.root.quit)
        self.root.mainloop()  # Strict runner also checks Tk timer errors after close.

    def test_all_categories_are_visible_without_a_selector(self):
        from ccz_randomizer.ui.effect_dictionary import show_effect_dictionary
        dialog = show_effect_dictionary(self.root)
        self.assertFalse(any(isinstance(w, ttk.Combobox) for w in descendants(dialog)))
        table = next(w for w in descendants(dialog) if isinstance(w, ttk.Treeview))
        keys = table.get_children()
        self.assertEqual(302, len(keys))
        self.assertIn("equipment:93", keys)
        self.assertIn("skill:54", keys)
        dialog.destroy()

    def test_unavailable_help_shows_explanation_without_stale_rows(self):
        from ccz_randomizer.ui.effect_dictionary import show_effect_dictionary
        dictionary = load_effect_dictionary(replace(current_context(), profile_id="ccz-v2.2"))
        with patch("ccz_randomizer.ui.effect_dictionary.load_effect_dictionary", return_value=dictionary):
            dialog = show_effect_dictionary(self.root)
        text = next(w for w in descendants(dialog) if isinstance(w, tk.Text))
        self.assertIn("暂无配套", text.get("1.0", "end"))
        dialog.destroy()

    def test_small_window_keeps_list_details_and_close_button_visible(self):
        from ccz_randomizer.ui.effect_dictionary import show_effect_dictionary
        self.root.deiconify()
        self.root.update()
        dialog = show_effect_dictionary(self.root)
        dialog.geometry("660x440")
        self.root.update()
        table = next(w for w in descendants(dialog) if isinstance(w, ttk.Treeview))
        detail = next(w for w in descendants(dialog) if isinstance(w, tk.Text))
        close = next(w for w in descendants(dialog)
                     if isinstance(w, ttk.Button) and w.cget("text") == "关闭")
        self.assertGreater(table.winfo_width(), 180)
        self.assertGreater(detail.winfo_width(), 180)
        self.assertTrue(close.winfo_ismapped())
        self.assertLessEqual(close.winfo_rooty() + close.winfo_height(),
                             dialog.winfo_rooty() + dialog.winfo_height())
        dialog.destroy()

    def test_equipment_entry_opens_dictionary_without_equipment_snapshot(self):
        from ccz_randomizer.ui.equipment import show_equipment_window
        with tempfile.TemporaryDirectory() as temp, patch(
                "ccz_randomizer.ui.effect_dictionary.show_effect_dictionary") as show:
            show_equipment_window(self.root, snapshot={}, history_path=Path(temp) / "search.json")
            dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
            button = next(w for w in descendants(dialog)
                          if isinstance(w, ttk.Button) and w.cget("text") == "特效手册")
            button.invoke()
            show.assert_called_once_with(dialog)
            dialog.destroy()
