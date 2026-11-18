"""Exercise ttk bindings with the shared arrowless scrollbar layout."""
import tkinter as tk
from tkinter import ttk
import unittest

from ccz_randomizer.ui.theme import setup_theme
from ccz_randomizer.ui.scrolled_text import ScrolledText


class ScrollbarTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        setup_theme(self.root)
        self.root.geometry('420x300')

    def test_vertical_and_horizontal_thumb_drag_and_track_click(self):
        canvas = tk.Canvas(self.root, scrollregion=(0, 0, 2000, 2000))
        vertical = ttk.Scrollbar(self.root, orient='vertical', command=canvas.yview)
        horizontal = ttk.Scrollbar(self.root, orient='horizontal', command=canvas.xview)
        vertical.pack(side='right', fill='y')
        horizontal.pack(side='bottom', fill='x')
        canvas.pack(fill='both', expand=True)
        canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.root.update()
        for scrollbar, view in ((vertical, canvas.yview), (horizontal, canvas.xview)):
            is_vertical = str(scrollbar.cget('orient')) == 'vertical'
            def point(position):
                return (scrollbar.winfo_width() // 2, position) if is_vertical else (position, scrollbar.winfo_height() // 2)
            length = scrollbar.winfo_height() if is_vertical else scrollbar.winfo_width()
            thumb = [p for p in range(length) if scrollbar.identify(*point(p)).endswith('thumb')]
            self.assertTrue(thumb)
            start = (thumb[0] + thumb[-1]) // 2
            x, y = point(start)
            scrollbar.event_generate('<ButtonPress-1>', x=x, y=y)
            x, y = point(start + length // 3)
            scrollbar.event_generate('<B1-Motion>', x=x, y=y)
            scrollbar.event_generate('<ButtonRelease-1>', x=x, y=y)
            self.root.update()
            self.assertGreater(view()[0], .1)
            before = view()[0]
            x, y = point(length - 4)
            scrollbar.event_generate('<ButtonPress-1>', x=x, y=y)
            scrollbar.event_generate('<ButtonRelease-1>', x=x, y=y)
            self.root.update()
            self.assertGreater(view()[0], before)

    def test_theme_reuse_keeps_images_alive_and_full_range_is_valid(self):
        images = self.root._ccz_scrollbar_images
        setup_theme(self.root)
        self.assertIs(images, self.root._ccz_scrollbar_images)
        bar = ttk.Scrollbar(self.root)
        bar.pack(fill='y')
        bar.set(0, 1)
        self.root.update()
        self.assertEqual((0., 1.), bar.get())
        bar.state(['disabled'])
        self.root.update()
        self.assertTrue(bar.instate(['disabled']))
        self.assertTrue(all(self.root.tk.call('image', 'type', str(image)) == 'photo' for image in images))

    def test_scrolled_text_retains_geometry_text_editing_and_scroll_link(self):
        text = ScrolledText(self.root, width=20, height=5)
        text.pack(fill='both', expand=True)
        text.insert('1.0', '\n'.join(str(i) for i in range(100)))
        self.root.update()
        self.assertIsInstance(text.vbar, ttk.Scrollbar)
        self.assertEqual('0', text.get('1.0', '1.end'))
        text.yview_moveto(1)
        self.root.update()
        self.assertAlmostEqual(1, text.vbar.get()[1])
        self.assertGreater(text.vbar.get()[0], .5)
        text.configure(state='disabled')
        self.assertEqual('disabled', text.cget('state'))
