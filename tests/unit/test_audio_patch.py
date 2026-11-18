"""Real launcher payload, temporary game files and actual FAQ controls."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from ccz_randomizer.audio_patch import install_launcher, LAUNCHER_NAME
from ccz_randomizer.ui.audio_patch import launcher_resource, show_audio_patch
from ccz_randomizer.ui.support_menu import show_support_menu


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class AudioPatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.exe = self.folder / 'Ekd5.exe'
        self.exe.write_bytes(b'original game sentinel')
        self.target = self.folder / LAUNCHER_NAME

    def test_install_copies_exact_launcher_and_preserves_game_and_growth_patch(self):
        dll = self.folder / 'CCZFX.DLL'
        dll.write_bytes(b'growth patch sentinel')
        self.assertEqual(install_launcher(self.exe, launcher_resource()), self.target)
        self.assertEqual(self.target.read_bytes(), launcher_resource().read_bytes())
        self.assertEqual(self.exe.read_bytes(), b'original game sentinel')
        self.assertEqual(dll.read_bytes(), b'growth patch sentinel')
        self.assertFalse(list(self.folder.glob('.audio-*')))

    def test_repeat_install_is_idempotent(self):
        install_launcher(self.exe, launcher_resource())
        stamp = self.target.stat().st_mtime_ns
        install_launcher(self.exe, launcher_resource())
        self.assertEqual(self.target.stat().st_mtime_ns, stamp)

    def test_other_launcher_is_preserved(self):
        self.target.write_bytes(b'other launcher')
        with self.assertRaisesRegex(ValueError, '已有其他'):
            install_launcher(self.exe, launcher_resource())
        self.assertEqual(self.target.read_bytes(), b'other launcher')

    def test_invalid_payload_does_not_write_launcher(self):
        invalid = self.folder / 'invalid.exe'
        invalid.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, '校验失败'):
            install_launcher(self.exe, invalid)
        self.assertFalse(self.target.exists())

    def test_copy_failure_cleans_temporary_file_and_preserves_game(self):
        with patch.object(Path, 'rename', side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):
                install_launcher(self.exe, launcher_resource())
        self.assertFalse(self.target.exists())
        self.assertFalse(list(self.folder.glob('.audio-*')))
        self.assertEqual(self.exe.read_bytes(), b'original game sentinel')

    def test_missing_game_does_not_install(self):
        self.exe.unlink()
        with self.assertRaisesRegex(ValueError, '没有找到游戏'):
            install_launcher(self.exe, launcher_resource())
        self.assertFalse(self.target.exists())

    def test_frozen_resource_path(self):
        with patch('sys.frozen', True, create=True), patch('sys._MEIPASS', str(self.folder), create=True):
            self.assertEqual(launcher_resource(), self.folder / 'resources/patches' / LAUNCHER_NAME)


class AudioPatchUiTests(unittest.TestCase):
    setUp = AudioPatchTests.setUp

    def test_faq_has_two_patches_and_exact_hover_and_install_dialog(self):
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        api = SimpleNamespace(locate_game_executable=lambda: self.exe)
        opened = []
        actions = {key: lambda _: None for key in ('guide', 'effects', 'diagnostics', 'sound', 'logs', 'update', 'cleanup', 'growth_patch')}
        actions['audio_patch'] = lambda parent: opened.append(show_audio_patch(parent, api))
        faq = show_support_menu(root, actions, 'test')
        buttons = {w.cget('text'): w for w in descendants(faq) if isinstance(w, ttk.Button)}
        self.assertIn('吃桃补丁', buttons)
        self.assertIn('修复部分设备开启音效后在攻击、释放策略卡顿问题', buttons['音效卡顿补丁']._tooltip.text)
        self.assertIn('尚未充分测试', buttons['音效卡顿补丁']._tooltip.text)
        buttons['音效卡顿补丁'].invoke()
        dialog = opened[0]
        labels = '\n'.join(str(w.cget('text')) for w in descendants(dialog) if isinstance(w, ttk.Label))
        self.assertIn('独立 EXE 启动器', labels)
        self.assertIn('需要使用补丁提供的 EXE 启动游戏', labels)
        buttons = {w.cget('text'): w for w in descendants(dialog) if isinstance(w, ttk.Button)}
        self.assertEqual(set(buttons), {'使用补丁', '取消'})
        with patch('ccz_randomizer.ui.audio_patch.messages.showinfo') as info:
            buttons['使用补丁'].invoke()
            deadline = time.monotonic() + 5
            while not info.called and time.monotonic() < deadline:
                root.update()
                time.sleep(.01)
            self.assertTrue(info.called)
            self.assertIn(LAUNCHER_NAME, info.call_args.args[1])
        self.assertEqual(self.target.read_bytes(), launcher_resource().read_bytes())
        self.assertEqual(self.exe.read_bytes(), b'original game sentinel')
        buttons['取消'].invoke()
        self.assertFalse(dialog.winfo_exists())
        self.assertEqual(faq.grab_current(), faq)

    def test_cancel_does_not_install(self):
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        dialog = show_audio_patch(root, SimpleNamespace(locate_game_executable=lambda: self.exe))
        next(w for w in descendants(dialog) if isinstance(w, ttk.Button) and w.cget('text') == '取消').invoke()
        self.assertFalse(self.target.exists())
