"""Real handbook fixtures carried through profile packaging and activation."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from dataclasses import replace

from ccz_randomizer.effect_dictionary import load_effect_dictionary
from ccz_randomizer.profile_context import ProfileContext
from ccz_randomizer.profiles import load_profile, validate_profile, install_profile_package, profile_storage_root
from tools.build_profile_package import build_package


class EffectDictionaryPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / 'source'
        shutil.copytree(load_profile().root, self.source)
        self.data_path = self.source / 'effect_dictionary.json'
        self.data = json.loads(self.data_path.read_text('utf-8'))

    def write_data(self, data):
        self.data_path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    def test_only_data_update_changes_text_merges_and_names_after_activation(self):
        initial = build_package(self.source, self.base / 'initial.zip')
        appdir = self.base / 'app'
        install_profile_package(initial, appdir)
        self.data['equipment']['72']['description'] += '\n手册更新测试'
        self.data['mergeRules']['nameOverrides']['equipment:72'] = '名称更新测试'
        del self.data['mergeRules']['equivalences']['57']
        self.write_data(self.data)
        manifest_path = self.source / 'manifest.json'
        manifest = json.loads(manifest_path.read_text('utf-8'))
        manifest['catalogVersion'] += 1
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        archive = build_package(self.source, self.base / 'update.zip')
        with zipfile.ZipFile(archive) as package:
            self.assertIn('effect_dictionary.json', package.namelist())
        install_profile_package(archive, appdir)
        # The real activation path publishes the entire snapshot. Keep its legacy
        # bindings in a child process so unrelated tests retain their own profile.
        code = '''
import sys
from pathlib import Path
from dataclasses import replace
from ccz_randomizer.effect_dictionary import load_effect_dictionary
from ccz_randomizer.profile_context import current_context
from ccz_randomizer.profile_activation import activate_installed_profile
old = current_context()
before = load_effect_dictionary(old)
assert not before.search('名称更新测试')
activate_installed_profile(Path(sys.argv[1]))
after = load_effect_dictionary()
entry, = after.search('名称更新测试')
assert '手册更新测试' in entry.description
assert entry.source_keys == ('equipment:72', 'skill:111')
assert 'skill:46' in {entry.key for entry in after.entries}
assert 'skill:46' not in {entry.key for entry in before.entries}
assert not load_effect_dictionary(old).search('名称更新测试')
'''
        child = subprocess.run([sys.executable, '-c', code, str(appdir)],
                               capture_output=True, text=True, encoding='utf-8', timeout=40)
        self.assertEqual(0, child.returncode, child.stderr)

    def test_optional_handbook_preserves_old_package_and_exact_catalog_fallback(self):
        path = self.source / 'manifest.json'
        manifest = json.loads(path.read_text('utf-8'))
        del manifest['files']['effectDictionary']
        del manifest['sha256']['effect_dictionary.json']
        path.write_text(json.dumps(manifest), encoding='utf-8')
        archive = build_package(self.source, self.base / 'old.zip')
        installed = install_profile_package(archive, self.base / 'app')
        self.assertIsNone(installed.effect_dictionary)
        context = ProfileContext.from_profile(installed)
        self.assertEqual(302, len(load_effect_dictionary(context).entries))
        skills = copy.deepcopy(installed.skills)
        skills['runtimeCatalog'][24]['name'] = '另一套资料'
        self.assertFalse(load_effect_dictionary(replace(context, skills=skills)).entries)

    def test_changed_catalog_never_silently_uses_wrong_handbook(self):
        context = ProfileContext.from_profile(validate_profile(self.source))
        self.assertFalse(load_effect_dictionary(replace(context, game_version='different')).entries)

    def test_checksum_tampering_rejects_handbook(self):
        self.data['equipment']['72']['description'] += 'changed'
        self.write_data(self.data)
        with self.assertRaisesRegex(ValueError, '校验失败'):
            validate_profile(self.source)

    def test_invalid_data_never_replaces_active_package(self):
        appdir = self.base / 'app'
        install_profile_package(build_package(self.source, self.base / 'good.zip'), appdir)
        active = profile_storage_root(appdir) / 'active.json'
        previous = active.read_bytes()
        bad_values = []
        for change in ('identity', 'description', 'merge', 'override'):
            data = copy.deepcopy(self.data)
            if change == 'identity':
                data['profileId'] = 'other'
            elif change == 'description':
                data['equipment']['72']['description'] = 5
            elif change == 'merge':
                data['mergeRules']['equivalences']['72'] = [9999]
            else:
                data['mergeRules']['nameOverrides']['equipment:9999'] = 'invalid'
            bad_values.append((change, data))
        for label, data in bad_values:
            with self.subTest(label=label):
                self.write_data(data)
                path = self.source / 'manifest.json'
                manifest = json.loads(path.read_text('utf-8'))
                manifest['sha256'][self.data_path.name] = hashlib.sha256(self.data_path.read_bytes()).hexdigest()
                path.write_text(json.dumps(manifest), encoding='utf-8')
                bad = self.base / 'invalid.zip'
                with zipfile.ZipFile(bad, 'w') as package:
                    for file in self.source.iterdir():
                        if file.is_file():
                            package.write(file, file.name)
                with self.assertRaisesRegex(ValueError, '特效手册'):
                    install_profile_package(bad, appdir)
                self.assertEqual(previous, active.read_bytes())
