"""Content readiness includes deferred work, not merely a mapped window."""
import tkinter as tk
from tkinter import ttk
import unittest

from ccz_randomizer.diagnostics.ui_benchmark import Measurements
from ccz_randomizer.ui.history_loading import render_in_batches
from ccz_randomizer.ui.render_state import content_ready, track_render


class RenderStateTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('500x350')
        self.root.update()
        self.addCleanup(self.root.destroy)

    def test_mapped_window_with_delayed_content_cannot_pass_the_latency_budget(self):
        dialog = tk.Toplevel(self.root)
        label = ttk.Label(dialog, text='正在读取')
        label.pack()
        track_render(label, lambda: label.cget('text') == '内容已显示')
        run = Measurements(self.root)
        self.root.update()
        self.assertFalse(content_ready(self.root))
        def open_content():
            dialog.after(350, lambda: label.configure(text='内容已显示'))
        run.measure('delayed-content', open_content, lambda: dialog.winfo_ismapped())
        self.assertEqual('内容已显示', label.cget('text'))
        self.assertGreaterEqual(run.samples[0]['ready_ms'], 350)
        self.assertFalse(run.samples[0]['within_300ms'])

    def test_unfinished_batches_are_tracked_and_destroy_discards_the_pending_job(self):
        dialog = tk.Toplevel(self.root)
        rendered = []
        render_in_batches(dialog, ['曹操', '夏侯惇', '夏侯渊'],
                          lambda i, name: rendered.append(name), batch_size=1, delay_ms=10)
        self.root.update_idletasks()
        self.assertFalse(content_ready(self.root))
        self.assertTrue(dialog._ccz_render_jobs)
        dialog.destroy()
        self.root.update()
        self.assertFalse(dialog._ccz_render_jobs)
        self.assertTrue(content_ready(self.root))

    def test_hidden_pages_do_not_delay_the_visible_page_and_closed_widgets_are_released(self):
        book = ttk.Notebook(self.root)
        book.pack()
        first, second = ttk.Frame(book), ttk.Frame(book)
        book.add(first, text='当前页')
        book.add(second, text='其他页')
        track_render(second, lambda: False)
        self.root.update()
        self.assertTrue(content_ready(self.root))
        book.select(second)
        self.root.update()
        self.assertFalse(content_ready(self.root))
        second.destroy()
        self.root.update()
        self.assertTrue(content_ready(self.root))
