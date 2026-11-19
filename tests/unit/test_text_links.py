import tkinter as tk
import unittest
import weakref
import gc

from ccz_randomizer.ui.text_links import TextLinks


class TextLinkTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.text = tk.Text(self.root, width=40, height=5)
        self.text.pack()
        self.links = TextLinks(self.text)
        self.root.update()

    def tearDown(self):
        self.root.destroy()

    def click_first_link(self):
        self.root.update()
        x, y, width, height = self.text.bbox("1.0")
        self.text.event_generate("<Motion>", x=x + width // 2, y=y + height // 2)
        self.text.event_generate("<Button-1>", x=x + width // 2, y=y + height // 2)
        self.root.update()

    def test_260_rounds_and_repeated_refresh_keep_callbacks_bounded(self):
        # Production console: 15 slots per round, detail and score links.
        commands = tuple(self.text._tclCommands)
        clicked = []
        for refresh in range(3):
            self.text.configure(state="normal")
            self.links.clear()
            self.text.delete("1.0", "end")
            for round_number in range(1, 261):
                for slot in range(1, 16):
                    for kind in ("detail", "score"):
                        tag = f"{round_number}-{slot}-{kind}"
                        self.text.insert("end", "明细", tag)
                        self.links.add(tag, lambda _, value=(refresh, round_number, slot, kind): clicked.append(value))
                        self.text.insert("end", "\n")
            self.text.configure(state="disabled")
            self.assertEqual(commands, tuple(self.text._tclCommands))
            self.text.see("1.0")
            self.click_first_link()
            self.assertEqual((refresh, 1, 1, "detail"), clicked[-1])
        self.links.clear()
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.assertEqual({"sel", TextLinks.TAG}, set(self.text.tag_names()))

    def test_trim_releases_removed_actions_and_keeps_remaining_link(self):
        class Detail:
            pass
        detail = Detail()
        reference = weakref.ref(detail)
        self.text.insert("end", "旧明细\n", "old")
        self.links.add("old", lambda _, value=detail: value)
        clicked = []
        self.text.insert("end", "新明细\n", "new")
        self.links.add("new", lambda _: clicked.append("new"))
        del detail
        self.text.delete("1.0", "2.0")
        self.links.prune()
        gc.collect()
        self.assertIsNone(reference())
        self.assertNotIn("old", self.text.tag_names())
        self.click_first_link()
        self.assertEqual(["new"], clicked)
