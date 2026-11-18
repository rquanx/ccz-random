"""Channel coexistence and package-only display changes, using real profiles."""
import copy
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from ccz_randomizer import profiles
from ccz_randomizer.display_rules import render_skill, render_equipment, normalize_name
from ccz_randomizer.profile_feed import DEFAULT_FEED_URL, load_feed_url, save_feed_url
from tools.build_profile_package import build_package


class ProfileChannelTests(unittest.TestCase):
    def setUp(self):
        error_state = patch.object(profiles, "PROFILE_LOAD_ERROR", "")
        error_state.start()
        self.addCleanup(error_state.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.source = self.directory / "source"
        self.embedded = profiles.load_profile(profiles.DEFAULT_PROFILE_ID)
        shutil.copytree(self.embedded.root, self.source)

    def package(self, revision=None, edit=None):
        if revision is None:
            revision = self.embedded.manifest['catalogVersion'] + 1
        manifest = json.loads((self.source / "manifest.json").read_text(encoding="utf-8"))
        manifest["catalogVersion"] = revision
        if manifest['profileId'] != self.embedded.profile_id:
            # This identity fixture has no independently verified handbook.
            name = manifest['files'].pop('effectDictionary', None)
            manifest['sha256'].pop(name, None)
        (self.source / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        if edit:
            data = json.loads((self.source / "skills.json").read_text(encoding="utf-8"))
            edit(data)
            (self.source / "skills.json").write_text(json.dumps(data), encoding="utf-8")
        return build_package(self.source, self.directory / f"r{revision}.zip")

    def old_installation(self):
        # Recreate the old EXE's shared directory without invoking the new installer.
        root = self.directory / "ccz_fast_data/profiles"
        old = Path(__file__).parents[1] / "fixtures/profiles/ccz-v2.20-1104-night-r3.zip"
        with zipfile.ZipFile(old) as archive:
            archive.extractall(root / "old-v1")
        marker = root / "active.json"
        marker.write_text(json.dumps({"profileId": "old-v1"}), encoding="utf-8")
        return root, {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}

    def test_old_and_new_packages_coexist_and_restore_preserves_all_old_files(self):
        root, before = self.old_installation()
        self.assertEqual(self.embedded.root, profiles.load_profile(app_directory=self.directory).root)
        new = profiles.install_profile_package(self.package(), self.directory)
        self.assertEqual(new.root, profiles.load_profile(app_directory=self.directory).root)
        self.assertIn("ccz-fast-v2", new.root.parts)
        profiles.restore_embedded_profile(self.directory)
        self.assertEqual(self.embedded.root, profiles.load_profile(app_directory=self.directory).root)
        self.assertEqual(before, {p: (root / p).read_bytes() for p in before})

    def test_real_v1_package_is_rejected_without_touching_current_activation(self):
        installed = profiles.install_profile_package(self.package(), self.directory)
        marker = profiles.profile_storage_root(self.directory) / "active.json"
        before = marker.read_bytes()
        old = Path(__file__).parents[1] / "fixtures/profiles/ccz-v2.20-1104-night-r3.zip"
        with self.assertRaisesRegex(ValueError, "不兼容"):
            profiles.install_profile_package(old, self.directory)
        self.assertEqual(before, marker.read_bytes())
        self.assertEqual(installed.root, profiles.load_profile(app_directory=self.directory).root)

    def test_old_external_revision_does_not_hide_newer_embedded_but_worker_keeps_pin(self):
        old = profiles.install_profile_package(self.package(4), self.directory)
        self.assertEqual(self.embedded.root, profiles.load_profile(app_directory=self.directory).root)
        with patch.object(profiles, "_default_app_directory", return_value=self.directory), \
             patch.object(profiles, "_PINNED_PROFILE_DIRECTORY", None), \
             patch.dict("os.environ", {"CCZ_PROFILE_DIRECTORY": old.root.name}):
            self.assertEqual(4, profiles.load_profile().manifest["catalogVersion"])

    def test_corrupt_marker_and_wrong_group_fall_back_to_embedded(self):
        installed = profiles.install_profile_package(self.package(), self.directory)
        marker = profiles.profile_storage_root(self.directory) / "active.json"
        marker.write_text("broken", encoding="utf-8")
        self.assertEqual(self.embedded.root, profiles.load_profile(app_directory=self.directory).root)
        manifest_path = installed.root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update(toolCompatibility=["ccz-fast-v1"], catalogVersion=9999)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        marker.write_text(json.dumps({"profileId": installed.root.name}), encoding="utf-8")
        profiles._load_immutable_profile.cache_clear()
        self.assertEqual(self.embedded.root, profiles.load_profile(app_directory=self.directory).root)

    def test_legacy_source_is_not_inherited_but_opt_out_is_preserved(self):
        legacy = self.directory / "ccz_fast_data/profile_update.json"
        legacy.parent.mkdir()
        for url in ("https://custom.invalid/feed.json", DEFAULT_FEED_URL.replace("v2", "v1")):
            legacy.write_text(json.dumps({"feedUrl": url}), encoding="utf-8")
            self.assertEqual(DEFAULT_FEED_URL, load_feed_url(self.directory))
        legacy.write_text('{"feedUrl":""}', encoding="utf-8")
        self.assertEqual("", load_feed_url(self.directory))
        save_feed_url(self.directory, "https://new.invalid/feed.json")
        self.assertEqual("https://new.invalid/feed.json", load_feed_url(self.directory))
        self.assertEqual('{"feedUrl":""}', legacy.read_text(encoding="utf-8"))

    def test_maximum_length_profile_id_can_be_installed_and_reloaded(self):
        path = self.source / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["profileId"] = "a" * 80
        path.write_text(json.dumps(manifest), encoding="utf-8")
        installed = profiles.install_profile_package(self.package(), self.directory)
        self.assertEqual("a" * 80, profiles.load_profile(app_directory=self.directory).profile_id)
        self.assertLessEqual(len(installed.root.name), 80)

    def test_display_behavior_changes_by_package_data_alone(self):
        def edit(data):
            rules = data["displayRules"]
            rules["formats"]["8"].update(maximum=6, template="{base}：{target}")
            rules["formats"]["9"]["count"] = 6
            rules["aliases"]["弱点攻击移动"] = "数据包别名"
            equipment = rules["equipment"]
            equipment["effects"]["112"].update(base="新版效果")
            equipment["EQUIPMENT_NAMES"][0] = "数据包宝物"
            # Keep name references consistent when renaming a treasure.
            equipment["EQUIPMENT_CATEGORY_BY_NAME"]["数据包宝物"] = equipment["EQUIPMENT_CATEGORY_BY_NAME"].pop("雌雄双剑")
            for _, names in equipment["EQUIPMENT_SETS"]:
                names[:] = ["数据包宝物" if name == "雌雄双剑" else name for name in names]
        installed = profiles.install_profile_package(self.package(edit=edit), self.directory)
        rules, tables = installed.skills["displayRules"], installed.skills["nameFormatting"]
        self.assertEqual("弱点攻击：移动", render_skill(rules, tables, "弱点攻击", 8, 6))
        self.assertEqual("测试 移", render_skill(rules, tables, "测试", 9, 32))
        self.assertEqual("新版效果：移动", render_equipment(rules, tables, 0x70, 6))
        self.assertEqual("数据包别名", normalize_name(rules, "弱点攻击-移动"))
        self.assertEqual("数据包宝物", rules["equipment"]["EQUIPMENT_NAMES"][0])

    def test_invalid_rules_are_rejected_before_any_activation_change(self):
        profiles.install_profile_package(self.package(), self.directory)
        marker = profiles.profile_storage_root(self.directory) / "active.json"
        before = marker.read_bytes()
        original = json.loads((self.source / "skills.json").read_text(encoding="utf-8"))
        edits = [lambda d: d["displayRules"]["formats"]["8"].update(maximum=999),
                 lambda d: d["displayRules"]["formats"]["6"].update(radix=0),
                 lambda d: d["displayRules"]["formats"]["6"].update(sourceFallback=9),
                 lambda d: d["displayRules"]["formats"]["1"].update(template="{base.__class__}"),
                 lambda d: d["displayRules"]["formats"]["1"].update(op="python"),
                 lambda d: d["displayRules"]["equipment"]["effects"]["112"].update(format=222),
                 lambda d: d["displayRules"]["equipment"]["recordGroups"][0].update(parameterOffset=99)]
        for edit in edits:
            with self.subTest(edit=edit):
                data = copy.deepcopy(original)
                edit(data)
                (self.source / "skills.json").write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(ValueError):
                    build_package(self.source, self.directory / "bad.zip")
                self.assertEqual(before, marker.read_bytes())
