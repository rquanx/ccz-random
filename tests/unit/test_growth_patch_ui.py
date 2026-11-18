"""Exercise actual FAQ and asynchronous patch actions on the private test desktop."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from ccz_randomizer.ui.growth_patch import show_growth_patch, package_path
from ccz_randomizer.ui.support_menu import show_support_menu
from ccz_randomizer.growth_patch import backup_path


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class GrowthPatchUiTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.api = SimpleNamespace(app_dir=lambda: self.directory, find_process_ids=lambda _: ())
        self.exe = self.directory / 'Ekd5.exe'
        with ZipFile(package_path()) as archive:
            original = bytearray(archive.read('Ekd5.exe'))
        original[0x6b58:0x6b62] = b'PSAPI.DLL\0'
        self.original = bytes(original)
        self.exe.write_bytes(self.original)

    def buttons(self, dialog):
        return {w.cget('text'): w for w in descendants(dialog) if isinstance(w, ttk.Button)}

    def wait(self, predicate):
        deadline = time.monotonic() + 10
        while not predicate() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        self.assertTrue(predicate())

    def test_faq_tooltip_install_restore_and_cancel(self):
        opened = []
        actions = {key: lambda _: None for key in ('guide', 'effects', 'diagnostics', 'sound', 'logs', 'update', 'cleanup')}
        actions['growth_patch'] = lambda parent: opened.append(show_growth_patch(parent, self.api))
        faq = show_support_menu(self.root, actions, 'test')
        entry = self.buttons(faq)['吃桃补丁']
        self.assertIn('支持高编号人物吃桃', entry._tooltip.text)
        entry.invoke()
        dialog = opened[0]
        labels = '\n'.join(str(w.cget('text')) for w in descendants(dialog) if isinstance(w, ttk.Label))
        self.assertIn('尚未充分测试', labels)
        self.assertIn('是否适用于当前游戏请自行判断', labels)
        self.assertNotIn('仅支持已验证', labels)
        self.assertIn('Ekd5.exe', labels)
        self.assertIn('自动将原 EXE 重命名', labels)
        buttons = self.buttons(dialog)
        self.assertEqual(set(buttons), {'使用补丁', '还原', '取消'})
        with patch('ccz_randomizer.ui.growth_patch.messages.showinfo') as info:
            buttons['使用补丁'].invoke()
            self.wait(lambda: info.call_count == 1)
            self.assertEqual(backup_path(self.exe).read_bytes(), self.original)
            buttons['还原'].invoke()
            self.wait(lambda: info.call_count == 2)
        self.assertEqual(self.exe.read_bytes(), self.original)
        with patch('ccz_randomizer.ui.growth_patch.messages.showerror') as error:
            buttons['还原'].invoke()
            self.wait(lambda: error.called)
            self.assertIn('没有可以还原的 EXE', error.call_args.args[1])
        buttons['取消'].invoke()
        self.assertFalse(dialog.winfo_exists())
        self.assertEqual(faq.grab_current(), faq)

    def test_running_randomizer_prevents_install(self):
        dialog = show_growth_patch(self.root, self.api, is_running=lambda: True)
        with patch('ccz_randomizer.ui.growth_patch.messages.showwarning') as warning:
            self.buttons(dialog)['使用补丁'].invoke()
        self.assertTrue(warning.called)
        self.assertFalse(backup_path(self.exe).exists())

    def test_running_game_prevents_install(self):
        self.api.find_process_ids = lambda _: (123,)
        dialog = show_growth_patch(self.root, self.api)
        with patch('ccz_randomizer.ui.growth_patch.messages.showerror') as error:
            self.buttons(dialog)['使用补丁'].invoke()
            self.wait(lambda: error.called)
            self.assertIn('先关闭游戏', error.call_args.args[1])
        self.assertFalse(backup_path(self.exe).exists())
