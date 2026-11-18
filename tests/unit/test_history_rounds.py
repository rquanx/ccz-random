import tkinter as tk
import unittest

from ccz_randomizer.ui.history import COLORS, FONT
from ccz_randomizer.ui.history_rounds import RoundCard
from ccz_randomizer.ui.theme import setup_theme
from tests.unit.test_recruitment_ui import wait_until


class RoundCardLayoutTests(unittest.TestCase):
    def test_metadata_stays_together_and_edit_centers_for_short_and_wrapped_text(self):
        root = tk.Tk()
        self.addCleanup(root.destroy)
        setup_theme(root)
        root.geometry('460x400')
        edits = []
        card = RoundCard(root, colors=COLORS, font=FONT,
            display_title=lambda value: value or '未命名', display_time=lambda _: '2026-11-15 13:29',
            select=lambda _: None, edit=lambda row, *_: edits.append(row['id']))
        card.pack(fill='x')
        for width, rule in ((460, '默认规则副本'), (280, '一个较长的规则名字' * 4)):
            root.geometry(f'{width}x400')
            card.update_content(dict(id=width, title='', started_at=0, rule_name=rule))
            root.update()
            wait_until(root, lambda: abs(card.edit_button.winfo_y() + card.edit_button.winfo_height() / 2
                                        - card.head.winfo_height() / 2) <= 1)
            canvas = card._round_name_label
            self.assertEqual('未命名', canvas.itemcget(card.title_item, 'text'))
            self.assertEqual(f'2026-11-15 13:29 · {rule}', canvas.itemcget(card.time_item, 'text'))
            self.assertEqual(0, canvas.coords(card.time_item)[0])
            self.assertGreater(canvas.bbox(card.time_item)[1], canvas.bbox(card.title_item)[3])
            self.assertLessEqual(canvas.bbox(card.time_item)[2], canvas.winfo_width() + 2)
            self.assertLessEqual(canvas.bbox(card.time_item)[3], canvas.winfo_height())
            center = card.edit_button.winfo_y() + card.edit_button.winfo_height() / 2
            self.assertLessEqual(abs(center - card.head.winfo_height() / 2), 1,
                (width, card.head.winfo_height(), card.edit_button.winfo_y(), card.edit_button.winfo_height()))
            card.edit_button.invoke()
        self.assertEqual([460, 280], edits)
