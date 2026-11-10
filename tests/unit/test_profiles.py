import tempfile
import unittest
import zipfile
import json
import shutil
import hashlib
import subprocess
import sys
from unittest.mock import patch
from pathlib import Path

from ccz_randomizer.profiles import (
    DEFAULT_PROFILE_ID,
    install_profile_package,
    load_profile,
    profile_package_sha256,
    validate_profile,
    restore_embedded_profile,
)
from ccz_randomizer.profile_compatibility import PROFILE_COMPATIBILITY_ID


class ProfileTests(unittest.TestCase):
    def test_running_roster_and_version_remain_consistent_until_restart(self):
        # The actual previously published package had 17 story + 126 recruits.
        from ccz_randomizer import profiles
        from ccz_randomizer.profile_updates import profile_version_label
        from ccz_randomizer.rule_members import rule_member_indices

        from tests.profile_fixtures import lifecycle_packages
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            old_archive, new_archive = lifecycle_packages(directory)
            appdir = directory / "app"
            install_profile_package(old_archive, appdir)
            with patch.object(profiles, "_default_app_directory", return_value=appdir), \
                 patch.object(profiles, "_PINNED_PROFILE_DIRECTORY", None):
                running = load_profile()
                self.assertEqual(6, running.manifest["catalogVersion"])
                self.assertEqual(143, len(rule_member_indices(running.game_version)))
                self.assertEqual("6", profile_version_label(appdir))
                install_profile_package(new_archive, appdir)
                self.assertEqual(143, len(rule_member_indices(running.game_version)))
                self.assertNotIn("关羽", rule_member_indices(running.game_version))
                self.assertEqual("当前 6；已下载 7，空闲时生效", profile_version_label(appdir))

            code = '''
import sys
from pathlib import Path
from ccz_randomizer import profiles
profiles._default_app_directory = lambda: Path(sys.argv[1])
from ccz_randomizer.rule_members import rule_member_indices
from ccz_randomizer.profile_updates import profile_version_label
current = profiles.load_profile()
assert len(rule_member_indices(current.game_version)) == 144
assert rule_member_indices(current.game_version)["关羽"] == 3
assert profile_version_label(Path(sys.argv[1])) == "7"
'''
            child = subprocess.run([sys.executable, "-c", code, str(appdir)], capture_output=True, text=True)
            self.assertEqual(0, child.returncode, child.stderr)

    def test_latest_profile_is_embedded_and_valid(self):
        profile = load_profile()
        self.assertEqual(DEFAULT_PROFILE_ID, profile.profile_id)
        self.assertEqual("2.20-1104-night", profile.game_version)
        self.assertEqual(126, len(profile.recruitment["people"]))
        self.assertEqual(18, len(profile.fixed_entries["members"]))
        self.assertTrue(profile_package_sha256(profile.root))

    def test_profile_zip_is_installed_after_validation(self):
        source = load_profile()
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "profile.zip"
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
                for path in source.root.rglob("*"):
                    if path.is_file():
                        output.write(path, Path(source.profile_id) / path.relative_to(source.root))
            target = Path(temp) / "app"
            installed = install_profile_package(archive, target)
            self.assertEqual(source.profile_id, installed.profile_id)
            self.assertEqual(installed.profile_id, validate_profile(installed.root).profile_id)
            self.assertEqual(source.profile_id, load_profile(app_directory=target).profile_id)
            restore_embedded_profile(target)
            self.assertEqual(DEFAULT_PROFILE_ID, load_profile(app_directory=target).profile_id)

    def make_archive(self, root, output):
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in root.rglob("*"):
                if file.is_file():
                    archive.write(file, file.relative_to(root))

    def test_new_version_is_activated_without_version_code_changes(self):
        source = load_profile()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "new"
            shutil.copytree(source.root, root)
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            manifest.update(profileId="ccz-profile-next", gameVersion="profile-test-next", fingerprintVersion="profile-test-next")
            fingerprint = root / "fingerprints.json"
            fingerprint.write_text(json.dumps({"profile-test-next": next(iter(source.fingerprints.values()))}), encoding="utf-8")
            manifest["sha256"]["fingerprints.json"] = hashlib.sha256(fingerprint.read_bytes()).hexdigest()
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            archive = Path(temp) / "next.zip"
            self.make_archive(root, archive)
            appdir = Path(temp) / "app"
            install_profile_package(archive, appdir)
            active = load_profile(app_directory=appdir)
            self.assertEqual("profile-test-next", active.game_version)
            from ccz_randomizer import profiles
            with patch.object(profiles, "_default_app_directory", return_value=appdir), patch.object(profiles, "_PINNED_PROFILE_DIRECTORY", None):
                self.assertEqual(active.root.name, profiles.profile_id_for_game_version("profile-test-next"))
                self.assertEqual(126, len(profiles.load_profile(active.root.name).recruitment["people"]))
            # A fresh process is the restart boundary used by the EXE and workers.
            code = '''
import sys, os
from pathlib import Path
from ccz_randomizer import profiles
profiles._default_app_directory = lambda: Path(sys.argv[1])
from ccz_randomizer.game_versions import APP_DEFAULT_GAME_VERSION, normalize_game_version
assert APP_DEFAULT_GAME_VERSION == "profile-test-next"
os.environ["CCZ_GAME_VERSION"] = APP_DEFAULT_GAME_VERSION
assert normalize_game_version(APP_DEFAULT_GAME_VERSION) == APP_DEFAULT_GAME_VERSION
from ccz_randomizer.recruitment_catalog import load_catalog
from ccz_randomizer.fixed_members import fixed_member_indices
from ccz_randomizer.jobs import JOB_MAP
from ccz_randomizer.recruitment import parse_recruits
assert len(load_catalog()) == 126
assert len(fixed_member_indices()) == 18
assert len(JOB_MAP) == 40
assert parse_recruits(dict(schemaVersion=1, gameVersion=APP_DEFAULT_GAME_VERSION, personnel=[])) == ()
from ccz_randomizer import app
from ccz_randomizer.rules.config import default_rule_config, validate_rule_config
validate_rule_config(default_rule_config())
assert app.APP_DEFAULT_GAME_VERSION == APP_DEFAULT_GAME_VERSION
'''
            child = subprocess.run([sys.executable, "-c", code, str(appdir)], capture_output=True, text=True)
            self.assertEqual(0, child.returncode, child.stderr)

    def test_corrupt_package_preserves_previous_activation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "profile"
            shutil.copytree(load_profile().root, root)
            archive = Path(temp) / "profile.zip"
            self.make_archive(root, archive)
            appdir = Path(temp) / "app"
            install_profile_package(archive, appdir)
            previous = load_profile(app_directory=appdir).root
            (root / "jobs.json").write_text('{"jobs": []}', encoding="utf-8")
            self.make_archive(root, archive)
            with self.assertRaises(ValueError):
                install_profile_package(archive, appdir)
            self.assertEqual(previous, load_profile(app_directory=appdir).root)

    def test_unsupported_engine_and_unsafe_profile_id_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "profile"
            shutil.copytree(load_profile().root, root)
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            for changes in ({"engineLayout": "unknown"}, {"profileId": "../other"}):
                (root / "manifest.json").write_text(json.dumps(dict(manifest, **changes)), encoding="utf-8")
                with self.assertRaises(ValueError):
                    validate_profile(root)

    def test_offline_feed_does_not_access_network(self):
        from ccz_randomizer.profile_feed import check_profile_update, save_feed_url
        with tempfile.TemporaryDirectory() as temp, patch("urllib.request.urlopen") as network:
            save_feed_url(Path(temp), "")
            self.assertIsNone(check_profile_update(Path(temp)))
            network.assert_not_called()

    def test_default_feed_checks_embedded_version_without_downloading_package(self):
        from ccz_randomizer.profile_feed import DEFAULT_FEED_URL, check_profile_update, load_feed_url
        profile = load_profile()
        feed = dict(schemaVersion=1, compatibilityId=PROFILE_COMPATIBILITY_ID, profileId=profile.profile_id,
                    catalogVersion=profile.manifest["catalogVersion"],
                    url="https://ccz-fast-profile.oss-cn-guangzhou.aliyuncs.com/ccz-v2.20-1104-night-profile.zip",
                    sha256="36e8cb4cd93018856c1e73cff0dab46e9fd1c2250b7cef02b3777d6cc32c76cf")
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            self.assertEqual(DEFAULT_FEED_URL, load_feed_url(directory))
            with patch("ccz_randomizer.profile_feed.read_https", return_value=json.dumps(feed).encode()) as read:
                self.assertIsNone(check_profile_update(directory))
                read.assert_called_once_with(DEFAULT_FEED_URL, limit=65536)

    def test_custom_feed_and_explicit_opt_out_override_default(self):
        from ccz_randomizer.profile_feed import load_feed_url, save_feed_url
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            save_feed_url(directory, "https://example.invalid/feed.json")
            self.assertEqual("https://example.invalid/feed.json", load_feed_url(directory))
            save_feed_url(directory, "")
            self.assertEqual("", load_feed_url(directory))

    def test_feed_new_revision_and_download_hash(self):
        from ccz_randomizer.profile_feed import check_profile_update, install_feed_update, save_feed_url
        with tempfile.TemporaryDirectory() as temp:
            appdir = Path(temp)
            profile = load_profile()
            save_feed_url(appdir, "https://example.invalid/profile.json")
            feed = dict(schemaVersion=1, compatibilityId=PROFILE_COMPATIBILITY_ID, profileId=profile.profile_id, catalogVersion=profile.manifest["catalogVersion"] + 1, url="https://example.invalid/profile.zip", sha256="0" * 64)
            with patch("ccz_randomizer.profile_feed.read_https", return_value=json.dumps(feed).encode()):
                self.assertEqual(feed, check_profile_update(appdir))
            with patch("ccz_randomizer.profile_feed.read_https", return_value=b"incorrect download"):
                with self.assertRaises(ValueError):
                    install_feed_update(feed, appdir)
            self.assertEqual(profile.profile_id, load_profile(app_directory=appdir).profile_id)

    def test_profile_zip_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "bad.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("../manifest.json", "{}")
            with self.assertRaises(ValueError):
                install_profile_package(archive, Path(temp) / "app")


if __name__ == "__main__":
    unittest.main()
