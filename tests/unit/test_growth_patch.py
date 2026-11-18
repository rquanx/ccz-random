"""Real packaged binaries and temporary game folders; never start the game."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZIP_STORED

from ccz_randomizer import growth_patch as service
from ccz_randomizer.ui.growth_patch import package_path


class GrowthPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = package_path()
        with ZipFile(cls.package) as archive:
            cls.patched = archive.read('Ekd5.exe')
            cls.dll = archive.read('CCZFX.DLL')
        # Reconstruct the confirmed original from the verified five-byte import
        # change; both hashes come from the real runtime investigation.
        original = bytearray(cls.patched)
        assert original[0x6b58:0x6b62] == b'CCZFX.DLL\0'
        original[0x6b58:0x6b62] = b'PSAPI.DLL\0'
        cls.original = bytes(original)
        assert hashlib.sha256(cls.original).hexdigest() == service.ORIGINAL_SHA256

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.exe = self.folder / 'Ekd5.exe'
        self.exe.write_bytes(self.original)
        self.backup = service.backup_path(self.exe)

    def test_install_then_restore_exact_original_and_preserve_save(self):
        save = self.folder / 'SV014.E5S'
        save.write_bytes(b'untouched save sentinel')
        service.install_patch(self.exe, self.package)
        self.assertEqual(self.exe.read_bytes(), self.patched)
        self.assertEqual(self.backup.read_bytes(), self.original)
        self.assertEqual((self.folder / 'CCZFX.DLL').read_bytes(), self.dll)
        service.restore_patch(self.exe)
        self.assertEqual(self.exe.read_bytes(), self.original)
        self.assertFalse(self.backup.exists())
        self.assertEqual(save.read_bytes(), b'untouched save sentinel')
        self.assertFalse(list(self.folder.glob('.peach-*')))

    def test_repeat_install_preserves_original_backup(self):
        service.install_patch(self.exe, self.package)
        with self.assertRaisesRegex(ValueError, '已经'):
            service.install_patch(self.exe, self.package)
        self.assertEqual(self.backup.read_bytes(), self.original)

    def test_other_game_build_can_install_and_restore_exact_backup(self):
        other_build = self.original + b'other distribution marker'
        self.exe.write_bytes(other_build)
        service.install_patch(self.exe, self.package)
        self.assertEqual(self.exe.read_bytes(), self.patched)
        self.assertEqual(self.backup.read_bytes(), other_build)
        service.restore_patch(self.exe)
        self.assertEqual(self.exe.read_bytes(), other_build)
        self.assertFalse(self.backup.exists())

    def test_existing_backup_is_not_overwritten(self):
        self.backup.write_bytes(b'important backup')
        with self.assertRaisesRegex(ValueError, '已有备份'):
            service.install_patch(self.exe, self.package)
        self.assertEqual(self.backup.read_bytes(), b'important backup')
        self.assertEqual(self.exe.read_bytes(), self.original)

    def test_other_dll_is_not_overwritten(self):
        dll = self.folder / 'CCZFX.DLL'
        dll.write_bytes(b'other dll')
        with self.assertRaisesRegex(ValueError, '其他 CCZFX'):
            service.install_patch(self.exe, self.package)
        self.assertEqual(dll.read_bytes(), b'other dll')
        self.assertFalse(self.backup.exists())

    def test_invalid_payload_leaves_game_unchanged(self):
        invalid = self.folder / 'bad.zip'
        with ZipFile(invalid, 'w', ZIP_STORED) as archive:
            archive.writestr('Ekd5.exe', b'corrupt')
            archive.writestr('CCZFX.DLL', self.dll)
        with self.assertRaisesRegex(ValueError, '校验失败'):
            service.install_patch(self.exe, invalid)
        self.assertEqual(self.exe.read_bytes(), self.original)
        self.assertFalse(self.backup.exists())

    def test_copy_failure_rolls_back_renamed_exe_and_new_dll(self):
        real_replace = service.os.replace
        def fail_exe(source, destination):
            if Path(destination) == self.exe and Path(source) != self.backup:
                raise PermissionError('simulated copy failure')
            return real_replace(source, destination)
        with patch.object(service.os, 'replace', side_effect=fail_exe):
            with self.assertRaises(PermissionError):
                service.install_patch(self.exe, self.package)
        self.assertEqual(self.exe.read_bytes(), self.original)
        self.assertFalse(self.backup.exists())
        self.assertFalse((self.folder / 'CCZFX.DLL').exists())
        self.assertFalse(list(self.folder.glob('.peach-*')))

    def test_restore_missing_backup_reports_no_exe(self):
        with self.assertRaisesRegex(ValueError, '没有可以还原的 EXE'):
            service.restore_patch(self.exe)

    def test_restore_recovers_missing_current_exe(self):
        self.exe.rename(self.backup)
        service.restore_patch(self.exe)
        self.assertEqual(self.exe.read_bytes(), self.original)

    def test_restore_does_not_require_known_backup_fingerprint(self):
        other_build = self.original + b'backup from another distribution'
        self.backup.write_bytes(other_build)
        service.restore_patch(self.exe)
        self.assertEqual(self.exe.read_bytes(), other_build)

    def test_restore_replaces_later_modification_with_users_backup(self):
        service.install_patch(self.exe, self.package)
        self.exe.write_bytes(b'later modification')
        service.restore_patch(self.exe)
        self.assertEqual(self.exe.read_bytes(), self.original)
        self.assertFalse(self.backup.exists())

    def test_frozen_resource_path(self):
        with patch('sys.frozen', True, create=True), patch('sys._MEIPASS', str(self.folder), create=True):
            self.assertEqual(package_path(), self.folder / 'resources/patches/growth-fix.zip')
