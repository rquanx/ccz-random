import tkinter as tk
import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from ccz_randomizer.ui.window_position import center_on_parent, centered_toplevel


class WindowPositionTests(unittest.TestCase):
    def test_history_dialog_centers_outer_frame_after_full_layout(self):
        from ccz_randomizer.history import HistoryRepository
        from ccz_randomizer.ui.history import show_history_window
        root = tk.Tk()
        self.addCleanup(root.destroy)
        root.geometry("900x600+400+200")
        root.update()
        with tempfile.TemporaryDirectory() as directory:
            show_history_window(root, HistoryRepository(Path(directory)))
            root.update()
            dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
            expected_x = max(0, min(root.winfo_x() + (root.winfo_width() - dialog.winfo_width()) // 2,
                                   root.winfo_screenwidth() - dialog.winfo_width()))
            expected_y = max(0, min(root.winfo_y() + (root.winfo_height() - dialog.winfo_height()) // 2,
                                   root.winfo_screenheight() - dialog.winfo_height()))
            self.assertEqual((expected_x, expected_y), (dialog.winfo_x(), dialog.winfo_y()))
            self.assertEqual(1, dialog.attributes("-alpha"))

    def test_larger_dialog_centers_on_parent_and_stays_on_desktop(self):
        parent = Mock()
        parent.winfo_toplevel.return_value = parent
        parent.winfo_x.return_value = 500
        parent.winfo_y.return_value = 300
        parent.winfo_width.return_value = 400
        parent.winfo_height.return_value = 300
        window = Mock()
        window.winfo_width.return_value = 800
        window.winfo_height.return_value = 600
        window.winfo_vrootx.return_value = 0
        window.winfo_vrooty.return_value = 0
        window.winfo_vrootwidth.return_value = 1920
        window.winfo_vrootheight.return_value = 1080
        center_on_parent(window, parent)
        window.geometry.assert_called_with("+300+150")
        parent.winfo_x.return_value = 20
        parent.winfo_y.return_value = 20
        center_on_parent(window, parent)
        window.geometry.assert_called_with("+0+0")

    def test_initial_placement_uses_final_size_and_does_not_recenter_on_resize(self):
        root = tk.Tk()
        self.addCleanup(root.destroy)
        root.geometry("500x400+350+250")
        root.update()
        dialog = centered_toplevel(root)
        dialog.geometry("300x200+0+0")
        root.update()
        expected_x = root.winfo_x() + (root.winfo_width() - 300) // 2
        expected_y = root.winfo_y() + (root.winfo_height() - 200) // 2
        self.assertTrue(dialog.geometry().endswith(f"+{expected_x}+{expected_y}"))
        dialog.geometry("320x220+100+100")
        root.update()
        self.assertTrue(dialog.geometry().endswith("+100+100"))

    def test_toplevel_stays_hidden_until_initial_center_is_ready(self):
        root = tk.Tk()
        self.addCleanup(root.destroy)
        root.geometry("500x400+350+250")
        root.update()
        dialog = centered_toplevel(root)
        self.assertEqual(0.0, dialog.attributes("-alpha"))
        dialog.geometry("300x200")
        root.update_idletasks()
        root.update()
        self.assertEqual("normal", dialog.state())
        self.assertEqual(1.0, dialog.attributes("-alpha"))
        expected_x = root.winfo_x() + (root.winfo_width() - 300) // 2
        expected_y = root.winfo_y() + (root.winfo_height() - 200) // 2
        self.assertTrue(dialog.geometry().endswith(f"+{expected_x}+{expected_y}"))

    def test_explicit_show_only_reveals_window_at_final_position(self):
        root = tk.Tk()
        self.addCleanup(root.destroy)
        root.geometry("500x400+350+250")
        root.update()
        dialog = centered_toplevel(root)
        dialog.withdraw()
        dialog.geometry("320x220+0+0")
        root.update_idletasks()
        self.assertEqual(0, dialog.attributes("-alpha"))
        shown_at = []
        original = dialog.attributes

        def record(*args):
            if args == ("-alpha", 1.0):
                shown_at.append(dialog.geometry())
            return original(*args)

        with patch.object(dialog, "attributes", side_effect=record):
            dialog.deiconify()
            root.update()
        x = root.winfo_x() + (root.winfo_width() - 320) // 2
        y = root.winfo_y() + (root.winfo_height() - 220) // 2
        self.assertEqual([f"320x220+{x}+{y}"], shown_at)
