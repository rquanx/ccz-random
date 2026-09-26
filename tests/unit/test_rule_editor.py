import tempfile
import tkinter as tk
import unittest
import json
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace
from unittest.mock import patch

from fast_randomizer import (
    JOB_MAP,
    TEAM_MEMBERS,
    activate_rule_profile,
    format_user_log,
)
from rule_config import build_rule_export, default_rule_config, load_rule_config
from rule_editor import ScoreGrid, show_rule_editor


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
            self.assertLess(len(descendants(grid)), 8)
            x1, y1, x2, y2, _index = grid.hit_boxes[0]
            grid._start_edit(
                SimpleNamespace(
                    x=(x1 + x2) // 2,
                    y=(y1 + y2) // 2,
                )
            )
            self.assertIsNotNone(grid.editor)
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
            grid.commit_pending()
            visible_text = {
                grid.canvas.itemcget(item, "text")
                for item in grid.canvas.find_all()
                if grid.canvas.type(item) == "text"
            }
            self.assertIn("特殊 · 基础分", visible_text)
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

    def test_job_type_dialog_edits_profile_override(self):
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
                    buttons["设置兵种所属类型"].invoke()
                    root.update()
                    dialog = next(
                        child
                        for child in editor.winfo_children()
                        if isinstance(child, tk.Toplevel)
                    )
                    combos = [
                        widget
                        for widget in descendants(dialog)
                        if isinstance(widget, ttk.Combobox)
                    ]
                    self.assertEqual(len(JOB_MAP), len(combos))
                    self.assertEqual("readonly", str(combos[0].cget("state")))
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
