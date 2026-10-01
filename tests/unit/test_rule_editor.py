import tempfile
import tkinter as tk
import unittest
import json
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace
from unittest.mock import patch

from fast_randomizer import (
    CURRENT_RUN_RULE_NOTICE,
    JOB_MAP,
    TEAM_MEMBERS,
    activate_rule_profile,
    current_run_rule_save_notice,
    history_rule_environment_json,
    format_user_log,
    serialize_rule_profile,
)
from rule_config import build_rule_export, default_rule_config, load_rule_config
from rule_editor import (
    ADVANCED_HELP_SECTIONS,
    ScoreGrid,
    show_rule_editor,
)


SKILL_CATALOG = (
    ("普通特技", 0.0, "其他", "ALL_ROUNDER"),
    ("优质特技", 1.0, "优质", "WARRIOR"),
    ("强力特技", 2.0, "强力", "MASTER"),
    ("特殊特技", 5.0, "特殊", "ALL_ROUNDER"),
)


def descendants(widget):
    result = []
    for child in widget.winfo_children():
        result.append(child)
        result.extend(descendants(child))
    return result


class RuleEditorTests(unittest.TestCase):
    def test_rule_help_describes_current_skill_type_behavior(self):
        help_text = "\n".join(
            text for _title, text in ADVANCED_HELP_SECTIONS
        )

        self.assertIn("武将当前兵种的类型", help_text)
        self.assertIn("选择“无”表示该特技不限制匹配类型", help_text)
        self.assertIn("单击“基础分”整行可以编辑分数", help_text)

    def test_initial_skill_check_progress_is_visible(self):
        self.assertEqual(
            "正在检查特技条件……",
            format_user_log("初始三人兵种合格，正在检查特技条件"),
        )

    def test_active_profile_can_be_switched_and_persisted(self):
        config = default_rule_config()
        config["profiles"]["测试规则"] = json.loads(
            json.dumps(config["profiles"]["默认规则"], ensure_ascii=False)
        )
        config["profiles"]["测试规则"]["builtin"] = False

        with tempfile.TemporaryDirectory() as directory:
            updated = activate_rule_profile(
                Path(directory),
                config,
                "测试规则",
            )
            loaded = load_rule_config(Path(directory))

        self.assertEqual("测试规则", updated["activeProfile"])
        self.assertEqual("测试规则", loaded.config["activeProfile"])

    def test_rule_reason_is_hidden_from_user_log(self):
        self.assertEqual(
            "",
            format_user_log(
                "规则原因: 兵种综合评价未达到当前规则要求"
            ),
        )

    def test_runtime_recovery_details_are_hidden_from_user_log(self):
        messages = (
            "当前设备不兼容后台快速读档，已自动切换兼容模式",
            "兼容模式：正在刷新后台游戏实例",
            "第 3 号存档已保存，但结果图生成失败；"
            "将继续处理下一个存档",
        )
        for message in messages:
            with self.subTest(message=message):
                self.assertEqual("", format_user_log(message))

    def test_score_grid_uses_one_canvas_and_edits_values(self):
        root = tk.Tk()
        root.withdraw()
        try:
            variable = tk.StringVar(value="2")
            grid = ScoreGrid(
                root,
                [("测试特技", variable, "强力")],
                width=800,
                height=300,
            )
            grid.pack(fill="both", expand=True)
            root.update()
            self.assertLess(len(descendants(grid)), 16)
            x1, y1, x2, y2, _index = grid.hit_boxes[0]
            self.assertGreater(x2 - x1, 100)
            grid._start_edit(
                SimpleNamespace(
                    x=(x1 + x2) // 2,
                    y=(y1 + y2) // 2,
                )
            )
            self.assertIsNotNone(grid.editor)
            editor_x1, _editor_y1, editor_x2, _editor_y2 = (
                grid.canvas.bbox(grid.editor_window)
            )
            self.assertLess(editor_x2 - editor_x1, x2 - x1)
            visible_text = {
                grid.canvas.itemcget(item, "text")
                for item in grid.canvas.find_all()
                if grid.canvas.type(item) == "text"
            }
            self.assertIn("强力 · 基础分", visible_text)
            grid.editor.delete(0, "end")
            grid.editor.insert(0, "3.5")
            grid.commit_pending()
            self.assertEqual("3.5", variable.get())
        finally:
            root.destroy()

    def test_score_grid_filters_items_by_search_text(self):
        root = tk.Tk()
        root.withdraw()
        try:
            grid = ScoreGrid(
                root,
                [
                    ("提升策略命中", tk.StringVar(value="7"), "强力"),
                    ("辅助攻击格挡", tk.StringVar(value="7"), "强力"),
                    ("策略无视天气", tk.StringVar(value="5"), "特殊"),
                ],
                width=800,
                height=300,
            )
            grid.pack(fill="both", expand=True)
            root.update()

            grid.search_var.set("策略 命中")
            root.update()

            visible_text = {
                grid.canvas.itemcget(item, "text")
                for item in grid.canvas.find_all()
                if grid.canvas.type(item) == "text"
            }
            self.assertIn("提升策略命中", visible_text)
            self.assertNotIn("策略无视天气", visible_text)
            self.assertNotIn("辅助攻击格挡", visible_text)
            self.assertEqual("1 项", grid.result_text.get())
            self.assertEqual(1, len(grid.hit_boxes))

            grid.search_var.set("不存在")
            root.update()
            self.assertEqual("0 项", grid.result_text.get())
            self.assertIn(
                "没有匹配的项目",
                {
                    grid.canvas.itemcget(item, "text")
                    for item in grid.canvas.find_all()
                    if grid.canvas.type(item) == "text"
                },
            )
        finally:
            root.destroy()

    def test_score_grid_updates_dynamic_skill_tier_after_edit(self):
        root = tk.Tk()
        root.withdraw()
        try:
            variable = tk.StringVar(value="1")
            grid = ScoreGrid(
                root,
                [("测试特技", variable, "优质")],
                category_resolver=lambda _name, score, _category: (
                    "特殊" if float(score) >= 5 else "优质"
                ),
                width=800,
                height=300,
            )
            grid.pack(fill="both", expand=True)
            root.update()
            x1, y1, x2, y2, _index = grid.hit_boxes[0]
            grid._start_edit(
                SimpleNamespace(
                    x=(x1 + x2) // 2,
                    y=(y1 + y2) // 2,
                )
            )
            grid.editor.delete(0, "end")
            grid.editor.insert(0, "5")
            grid._preview_score()
            visible_text = {
                grid.canvas.itemcget(item, "text")
                for item in grid.canvas.find_all()
                if grid.canvas.type(item) == "text"
            }
            self.assertIn("特殊 · 基础分", visible_text)
            self.assertEqual("1", variable.get())
            grid.commit_pending()
            self.assertEqual("5", variable.get())
        finally:
            root.destroy()

    def test_copy_select_and_save_profile(self):
        root = tk.Tk()
        root.withdraw()
        saved = []
        try:
            with tempfile.TemporaryDirectory() as directory:
                with (
                    patch("rule_editor.messagebox.showinfo") as show_info,
                    patch("rule_editor.messagebox.showerror") as show_error,
                    patch("rule_editor.show_toast") as show_toast,
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
                    self.assertIn("导入规则", buttons)
                    self.assertIn("导出规则", buttons)
                    self.assertIn("选择人员（3/3）", buttons)
                    self.assertIn("选择人员（7/7）", buttons)
                    self.assertIn("设置人物倾向", buttons)
                    self.assertNotIn("设为当前规则", buttons)
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
                    self.assertEqual(7, len(help_books[0].tabs()))
                    self.assertEqual(
                        "先看这里",
                        help_books[0].tab(
                            help_books[0].select(),
                            "text",
                        ),
                    )
                    help_dialog.destroy()
                    buttons["保存规则"].invoke()
                    root.update()

                self.assertFalse(show_error.called)
                self.assertFalse(show_info.called)
                show_toast.assert_called_once_with(root, "规则已保存")
                self.assertEqual(1, len(saved))
                loaded = load_rule_config(Path(directory))
                self.assertEqual(2, len(loaded.config["profiles"]))
                self.assertEqual("默认规则", loaded.config["activeProfile"])
                profile = loaded.config["profiles"][
                    next(
                        name
                        for name in loaded.config["profiles"]
                        if name != "默认规则"
                    )
                ]
                self.assertEqual(
                    {}, profile["sevenPerson"]["skillBaseScores"]
                )
        finally:
            root.destroy()

    def test_unsaved_new_profile_requires_close_confirmation(self):
        root = tk.Tk()
        root.withdraw()
        try:
            with tempfile.TemporaryDirectory() as directory:
                with (
                    patch("rule_editor.messagebox.askyesno") as confirm,
                    patch("rule_editor.messagebox.showerror"),
                ):
                    show_rule_editor(
                        root,
                        Path(directory),
                        default_rule_config(),
                        JOB_MAP,
                        TEAM_MEMBERS,
                        SKILL_CATALOG,
                        lambda _config: None,
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

                    confirm.return_value = False
                    buttons["取消"].invoke()
                    root.update()
                    self.assertTrue(editor.winfo_exists())

                    confirm.return_value = True
                    buttons["取消"].invoke()
                    root.update()
                    self.assertFalse(editor.winfo_exists())
                    self.assertEqual(2, confirm.call_count)
        finally:
            root.destroy()

    def test_saving_while_random_is_running_shows_next_run_notice(self):
        root = tk.Tk()
        root.withdraw()
        try:
            with tempfile.TemporaryDirectory() as directory:
                with (
                    patch("rule_editor.messagebox.showerror") as show_error,
                    patch("rule_editor.show_toast") as show_toast,
                ):
                    show_rule_editor(
                        root,
                        Path(directory),
                        default_rule_config(),
                        JOB_MAP,
                        TEAM_MEMBERS,
                        SKILL_CATALOG,
                        lambda _config: None,
                        save_notice=lambda _config: CURRENT_RUN_RULE_NOTICE,
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
                    buttons["保存规则"].invoke()
                    root.update()

                self.assertFalse(show_error.called)
                show_toast.assert_called_once_with(
                    root,
                    "规则已保存\n"
                    + CURRENT_RUN_RULE_NOTICE,
                    3600,
                )
        finally:
            root.destroy()

    def test_current_run_notice_only_when_running_profile_changes(self):
        config = default_rule_config()
        config["profiles"]["其他规则"] = json.loads(
            json.dumps(config["profiles"]["默认规则"], ensure_ascii=False)
        )
        config["profiles"]["其他规则"]["builtin"] = False
        running_name = "默认规则"
        running_snapshot = serialize_rule_profile(
            config["profiles"][running_name]
        )

        unchanged = json.loads(json.dumps(config, ensure_ascii=False))
        unchanged["profiles"]["其他规则"]["threePerson"][
            "minJobAverage"
        ] = 9
        self.assertIsNone(
            current_run_rule_save_notice(
                unchanged,
                running_name,
                running_snapshot,
            )
        )

        changed = json.loads(json.dumps(config, ensure_ascii=False))
        changed["profiles"][running_name]["threePerson"][
            "minJobAverage"
        ] = 9
        self.assertEqual(
            CURRENT_RUN_RULE_NOTICE,
            current_run_rule_save_notice(
                changed,
                running_name,
                running_snapshot,
            ),
        )

    def test_history_rule_environment_value_remains_json_object(self):
        profile = {
            "id": "rule-a",
            "schemaVersion": "rule-schema-v1",
            "threePerson": {"minJobAverage": 8},
        }

        encoded = history_rule_environment_json(
            serialize_rule_profile(profile)
        )

        self.assertEqual(profile, json.loads(encoded))
        self.assertIsInstance(json.loads(encoded), dict)
        with self.assertRaises(ValueError):
            history_rule_environment_json('"not-an-object"')

    def test_job_type_tab_edits_profile_override(self):
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
                    combos = [
                        widget
                        for widget in descendants(editor)
                        if isinstance(widget, ttk.Combobox)
                        and tuple(widget.cget("values"))
                        == ("全能型", "武将型", "文官型")
                    ]
                    self.assertEqual(len(JOB_MAP), len(combos))
                    self.assertEqual("readonly", str(combos[0].cget("state")))
                    combos[0].set("文官型")
                    combos[0].event_generate("<<ComboboxSelected>>")
                    root.update()
                    buttons["保存规则"].invoke()
                    root.update()

                self.assertFalse(show_error.called)
                self.assertEqual(1, len(saved))
                profile_name = next(
                    name
                    for name in saved[0]["profiles"]
                    if name != "默认规则"
                )
                overrides = saved[0]["profiles"][profile_name][
                    "jobScoring"
                ]["jobTypeOverrides"]
                self.assertEqual("MASTER", overrides["群雄"])
        finally:
            root.destroy()

    def test_member_affinity_is_edited_from_job_scoring_dialog(self):
        root = tk.Tk()
        root.withdraw()
        saved = []
        try:
            with tempfile.TemporaryDirectory() as directory:
                with (
                    patch("rule_editor.messagebox.showerror") as show_error,
                    patch("rule_editor.show_toast"),
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
                    advanced_book = next(
                        widget
                        for widget in descendants(editor)
                        if isinstance(widget, ttk.Notebook)
                        and tuple(
                            widget.tab(tab_id, "text")
                            for tab_id in widget.tabs()
                        )
                        == (
                            "阶段门槛",
                            "兵种评分",
                            "兵种基础分",
                            "特技评分",
                            "特技基础设置",
                            "兵种类型",
                        )
                    )
                    self.assertNotIn(
                        "人物倾向",
                        tuple(
                            advanced_book.tab(tab_id, "text")
                            for tab_id in advanced_book.tabs()
                        ),
                    )
                    buttons = {
                        widget.cget("text"): widget
                        for widget in descendants(editor)
                        if isinstance(widget, tk.Button)
                    }
                    buttons["设置人物倾向"].invoke()
                    root.update()
                    dialog = next(
                        child
                        for child in editor.winfo_children()
                        if isinstance(child, tk.Toplevel)
                        and child.title() == "人物倾向设置"
                    )
                    combos = [
                        widget
                        for widget in descendants(dialog)
                        if isinstance(widget, ttk.Combobox)
                    ]
                    self.assertEqual(len(TEAM_MEMBERS) * 2, len(combos))
                    combos[0].set("文官型")
                    dialog_buttons = {
                        widget.cget("text"): widget
                        for widget in descendants(dialog)
                        if isinstance(widget, tk.Button)
                    }
                    dialog_buttons["确定"].invoke()
                    root.update()
                    buttons["保存规则"].invoke()
                    root.update()

                self.assertFalse(show_error.called)
                profile_name = next(
                    name
                    for name in saved[0]["profiles"]
                    if name != "默认规则"
                )
                self.assertEqual(
                    "MASTER",
                    saved[0]["profiles"][profile_name]["memberAffinity"][
                        "曹操"
                    ]["primaryType"],
                )
        finally:
            root.destroy()

    def test_skill_settings_edit_type_and_matching_switch(self):
        root = tk.Tk()
        root.withdraw()
        saved = []
        try:
            with tempfile.TemporaryDirectory() as directory:
                with (
                    patch("rule_editor.messagebox.showerror") as show_error,
                    patch("rule_editor.show_toast"),
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
                    matching_check = next(
                        widget
                        for widget in descendants(editor)
                        if isinstance(widget, tk.Checkbutton)
                        and widget.cget("text") == "启用特技类型匹配"
                    )
                    matching_check.invoke()
                    skill_grid = next(
                        widget
                        for widget in descendants(editor)
                        if isinstance(widget, ScoreGrid)
                        and widget.type_variables
                    )
                    skill_grid.canvas.configure(width=800, height=300)
                    root.update()
                    x1, y1, x2, y2, _index = (
                        skill_grid.type_hit_boxes[0]
                    )
                    skill_grid._start_edit(
                        SimpleNamespace(
                            x=(x1 + x2) // 2,
                            y=(y1 + y2) // 2,
                        )
                    )
                    self.assertIsInstance(skill_grid.editor, ttk.Combobox)
                    self.assertIn(
                        "无",
                        tuple(skill_grid.editor.cget("values")),
                    )
                    skill_grid.editor.set("无")
                    skill_grid.editor.event_generate(
                        "<<ComboboxSelected>>"
                    )
                    root.update()
                    buttons["保存规则"].invoke()
                    root.update()

                self.assertFalse(show_error.called)
                profile_name = next(
                    name
                    for name in saved[0]["profiles"]
                    if name != "默认规则"
                )
                seven = saved[0]["profiles"][profile_name]["sevenPerson"]
                self.assertFalse(seven["skillTypeMatchingEnabled"])
                self.assertEqual(
                    "NONE",
                    seven["skillTypeOverrides"]["普通特技"],
                )
        finally:
            root.destroy()

    def test_job_count_members_can_be_selected_and_saved(self):
        root = tk.Tk()
        root.withdraw()
        saved = []
        try:
            with tempfile.TemporaryDirectory() as directory:
                with (
                    patch("rule_editor.messagebox.showerror") as show_error,
                    patch("rule_editor.show_toast"),
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
                    mode_notebook = next(
                        widget
                        for widget in descendants(editor)
                        if isinstance(widget, ttk.Notebook)
                        and tuple(
                            widget.tab(tab_id, "text")
                            for tab_id in widget.tabs()
                        )
                        == ("简单模式", "高级模式")
                    )
                    mode_notebook.select(mode_notebook.tabs()[1])
                    mode_combos = [
                        widget
                        for widget in descendants(editor)
                        if isinstance(widget, ttk.Combobox)
                        and tuple(widget.cget("values"))
                        == ("按平均分判断", "按达标人数判断")
                    ]
                    mode_combos[0].set("按达标人数判断")
                    mode_combos[0].event_generate("<<ComboboxSelected>>")
                    root.update()
                    buttons = {
                        widget.cget("text"): widget
                        for widget in descendants(editor)
                        if isinstance(widget, tk.Button)
                    }
                    buttons["选择人员（3/3）"].invoke()
                    root.update()
                    dialog = next(
                        child
                        for child in editor.winfo_children()
                        if isinstance(child, tk.Toplevel)
                    )
                    checks = {
                        widget.cget("text"): widget
                        for widget in descendants(dialog)
                        if isinstance(widget, tk.Checkbutton)
                    }
                    checks["夏侯惇"].invoke()
                    dialog_buttons = {
                        widget.cget("text"): widget
                        for widget in descendants(dialog)
                        if isinstance(widget, tk.Button)
                    }
                    dialog_buttons["确定"].invoke()
                    root.update()
                    buttons = {
                        widget.cget("text"): widget
                        for widget in descendants(editor)
                        if isinstance(widget, tk.Button)
                    }
                    self.assertIn("选择人员（2/3）", buttons)
                    buttons["保存规则"].invoke()
                    root.update()

                self.assertFalse(show_error.called)
                profile_name = next(
                    name
                    for name in saved[0]["profiles"]
                    if name != "默认规则"
                )
                three = saved[0]["profiles"][profile_name]["threePerson"]
                self.assertEqual("count", three["jobQualificationMode"])
                self.assertEqual(
                    ["曹操", "夏侯渊"],
                    three["qualifiedMembers"],
                )
        finally:
            root.destroy()

    def test_import_saves_profiles_immediately(self):
        root = tk.Tk()
        root.withdraw()
        saved = []
        try:
            with tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                import_path = base / "import.json"
                import_path.write_text(
                    json.dumps(
                        build_rule_export(default_rule_config()),
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                with (
                    patch(
                        "rule_editor.filedialog.askopenfilename",
                        return_value=str(import_path),
                    ),
                    patch("rule_editor.messagebox.showinfo"),
                    patch("rule_editor.messagebox.showerror") as show_error,
                ):
                    show_rule_editor(
                        root,
                        base,
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
                    buttons["导入规则"].invoke()
                    root.update()

                self.assertFalse(show_error.called)
                self.assertEqual(1, len(saved))
                loaded = load_rule_config(base)
                self.assertIn("默认规则(1)", loaded.config["profiles"])
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
