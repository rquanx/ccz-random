import tkinter as tk
from tkinter import ttk
import unittest

from ccz_randomizer.ui.dialog_actions import add_dialog_actions
from ccz_randomizer.ui import messages


class DialogActionsTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)

    def test_action_order_and_disabled_primary_preserve_callbacks(self):
        frame = ttk.Frame(self.root)
        frame.pack(fill="x")
        called = []
        buttons = add_dialog_actions(frame, confirm=lambda: called.append("confirm"),
            cancel=lambda: called.append("cancel"),
            alternatives=(("保存为新规则", lambda: called.append("new")),))
        self.root.update()
        self.assertTrue(all(isinstance(w, ttk.Button) for w in frame.winfo_children()))
        self.assertLess(buttons["cancel"].winfo_x(), buttons["保存为新规则"].winfo_x())
        self.assertLess(buttons["保存为新规则"].winfo_x(), buttons["confirm"].winfo_x())
        buttons["confirm"].state(["disabled"])
        buttons["confirm"].invoke()
        self.assertEqual(called, [])
        buttons["confirm"].state(["!disabled"])
        for key in ("cancel", "保存为新规则", "confirm"):
            buttons[key].invoke()
        self.assertEqual(called, ["cancel", "new", "confirm"])

    def choose(self, label, function):
        captured = []
        def invoke():
            dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)
            buttons = [w for w in descendants(dialog) if isinstance(w, ttk.Button)]
            captured.extend(w.cget("text") for w in buttons)
            next(w for w in buttons if w.cget("text") == label).invoke()
        self.root.after(10, invoke)
        result = function("测试确认", "请选择操作", parent=self.root)
        return result, captured

    def test_confirm_and_cancel_have_consistent_labels_and_boolean_results(self):
        for label, expected in (("确认", True), ("取消", False)):
            result, buttons = self.choose(label, messages.askyesno)
            self.assertIs(result, expected)
            self.assertEqual(set(buttons), {"取消", "确认"})

    def test_three_way_choice_keeps_cancel_distinct_from_second_option(self):
        for label, expected in (("三人规则", True), ("七人规则", False), ("取消", None)):
            result, buttons = self.choose(label, messages.askyesnocancel)
            self.assertIs(result, expected)
            self.assertEqual(set(buttons), {"取消", "七人规则", "三人规则"})

    def test_information_dialog_has_only_close_action(self):
        result, buttons = self.choose("关闭", messages.showinfo)
        self.assertEqual(result, "ok")
        self.assertEqual(buttons, ["关闭"])

    def test_long_messages_remain_scrollable_and_close_button_stays_visible(self):
        captured = []
        message = "需要完整显示的诊断详情\n" * 100
        def close():
            dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
            dialog.update_idletasks()
            body = dialog.winfo_children()[1]
            text = next(w for w in body.winfo_children() if isinstance(w, tk.Frame))
            content = next(w for w in text.winfo_children() if isinstance(w, tk.Text))
            button = next(w for w in dialog.winfo_children()[0].winfo_children() if isinstance(w, ttk.Button))
            captured.append((content.get("1.0", "end-1c"), button.winfo_ismapped(),
                             button.winfo_rooty()+button.winfo_height() <= dialog.winfo_rooty()+dialog.winfo_height()))
            button.invoke()
        self.root.after(10, close)
        messages.showerror("操作未完成", message, parent=self.root)
        self.assertEqual(captured, [(message, True, True)])
