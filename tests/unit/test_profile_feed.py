"""Exercise release checks and installations using real profile package data."""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import tempfile
import unittest
import copy
import zipfile
from urllib.error import HTTPError
from pathlib import Path
from unittest.mock import patch

from ccz_randomizer.profile_feed import (
    DEFAULT_FEED_URL,
    check_profile_update,
    install_feed_update,
)
from ccz_randomizer.profiles import (
    install_profile_package,
    load_profile,
    profile_storage_root,
)
from ccz_randomizer.profile_compatibility import PROFILE_COMPATIBILITY_ID
from ccz_randomizer.profile_updates import auto_update_profile, startup_profile_check, UPDATE_FAILED_MESSAGE


class ProfileFeedTests(unittest.TestCase):
    def test_startup_toast_requires_a_valid_compatible_new_feed_and_failed_install(self):
        _, feed, _ = self.package(self.embedded.manifest["catalogVersion"] + 1)
        same = dict(feed, catalogVersion=self.embedded.manifest["catalogVersion"])
        older = dict(feed, catalogVersion=self.embedded.manifest["catalogVersion"] - 1)
        incompatible = dict(feed, compatibilityId="ccz-fast-unsupported")
        for label, responses, expected in (
            ("channel-not-published", [HTTPError(DEFAULT_FEED_URL, 404, "Not Found", {}, None)], []),
            ("offline", [OSError("offline")], []),
            ("malformed", [b"not JSON"], []),
            ("incompatible", [json.dumps(incompatible).encode()], []),
            ("same", [json.dumps(same).encode()], []),
            ("older", [json.dumps(older).encode()], []),
            ("new-download-fails", [json.dumps(feed).encode(), OSError("download failed")], [UPDATE_FAILED_MESSAGE]),
            ("new-corrupt-package", [json.dumps(feed).encode(), b"corrupt"], [UPDATE_FAILED_MESSAGE]),
        ):
            with self.subTest(case=label):
                notices = []
                def immediate(parent, action, done, failed):
                    try:
                        result = action()
                    except Exception as exc:
                        failed(exc)
                    else:
                        done(result)
                with patch("ccz_randomizer.profile_updates.background_call", side_effect=immediate), \
                     patch("ccz_randomizer.profile_feed.read_https", side_effect=responses):
                    startup_profile_check(None, self.appdir, notices.append)
                self.assertEqual(expected, notices)
                self.assertFalse((profile_storage_root(self.appdir) / "active.json").exists())

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.appdir = self.root / "app"
        self.embedded = load_profile()

    def package(self, revision, profile_id=None):
        # Derive fixtures from the validated embedded game data. Only the
        # publisher-controlled identity/revision changes in these releases.
        source = self.root / f"source-{revision}-{profile_id or 'same'}"
        shutil.copytree(self.embedded.root, source)
        manifest_path = source / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["catalogVersion"] = revision
        if profile_id:
            manifest["profileId"] = profile_id
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        archive_path = source.with_suffix(".zip")
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in source.rglob("*"):
                if file.is_file():
                    archive.write(file, file.relative_to(source))
        data = archive_path.read_bytes()
        feed = dict(
            schemaVersion=1,
            compatibilityId=PROFILE_COMPATIBILITY_ID,
            profileId=manifest["profileId"],
            catalogVersion=revision,
            url=f"https://ccz-fast-profile.oss-cn-guangzhou.aliyuncs.com/{archive_path.name}",
            sha256=hashlib.sha256(data).hexdigest(),
        )
        return archive_path, feed, data

    def server(self, feed, data):
        requested = []

        def open_url(request, timeout):
            url = request.full_url
            requested.append(url)
            bodies = {DEFAULT_FEED_URL: json.dumps(feed).encode(), feed["url"]: data}
            response = io.BytesIO(bodies[url])
            response.geturl = lambda: url
            return response

        return patch("urllib.request.urlopen", side_effect=open_url), requested

    def test_embedded_version_matches_feed_without_package_download_or_writes(self):
        _, feed, data = self.package(self.embedded.manifest["catalogVersion"])
        server, requests = self.server(feed, data)
        with server:
            self.assertIsNone(check_profile_update(self.appdir))
        self.assertEqual([DEFAULT_FEED_URL], requests)
        self.assertFalse(self.appdir.exists())

    def test_installed_version_matches_feed_even_when_embedded_is_older(self):
        archive, feed, data = self.package(self.embedded.manifest["catalogVersion"] + 1)
        installed = install_profile_package(archive, self.appdir)
        marker = profile_storage_root(self.appdir) / "active.json"
        previous = marker.read_bytes()
        server, requests = self.server(feed, data)
        with server:
            self.assertIsNone(check_profile_update(self.appdir))
        self.assertEqual([DEFAULT_FEED_URL], requests)
        self.assertEqual(previous, marker.read_bytes())
        self.assertEqual(installed.root, load_profile(app_directory=self.appdir).root)

    def test_new_revision_installs_and_next_check_does_not_download_again(self):
        _, feed, data = self.package(self.embedded.manifest["catalogVersion"] + 1)
        server, requests = self.server(feed, data)
        with server:
            update = check_profile_update(self.appdir)
            self.assertEqual(feed, update)
            # The check is read-only; the startup workflow installs its result.
            self.assertFalse(self.appdir.exists())
            installed = install_feed_update(update, self.appdir)
            self.assertEqual(feed["catalogVersion"], installed.manifest["catalogVersion"])
            self.assertEqual(installed.root, load_profile(app_directory=self.appdir).root)
            self.assertIsNone(check_profile_update(self.appdir))
        self.assertEqual([DEFAULT_FEED_URL, feed["url"], DEFAULT_FEED_URL], requests)

    def test_new_profile_id_installs_even_with_same_revision_number(self):
        _, feed, data = self.package(self.embedded.manifest["catalogVersion"], "ccz-feed-test-next")
        server, requests = self.server(feed, data)
        with server:
            update = check_profile_update(self.appdir)
            self.assertEqual(feed, update)
            install_feed_update(update, self.appdir)
            self.assertEqual(feed["profileId"], load_profile(app_directory=self.appdir).profile_id)
            self.assertIsNone(check_profile_update(self.appdir))
        self.assertEqual([DEFAULT_FEED_URL, feed["url"], DEFAULT_FEED_URL], requests)

    def test_older_feed_does_not_downgrade_installed_revision(self):
        archive, _, _ = self.package(self.embedded.manifest["catalogVersion"] + 1)
        installed = install_profile_package(archive, self.appdir)
        _, feed, data = self.package(self.embedded.manifest["catalogVersion"])
        server, requests = self.server(feed, data)
        with server:
            self.assertIsNone(check_profile_update(self.appdir))
        self.assertEqual([DEFAULT_FEED_URL], requests)
        self.assertEqual(installed.root, load_profile(app_directory=self.appdir).root)

    def test_automatic_update_installs_new_revision_once(self):
        _, feed, data = self.package(self.embedded.manifest["catalogVersion"] + 1)
        server, requests = self.server(feed, data)
        with server:
            updated = auto_update_profile(self.appdir)
            self.assertEqual(feed["catalogVersion"], updated.manifest["catalogVersion"])
            self.assertIsNone(auto_update_profile(self.appdir))
        self.assertEqual([DEFAULT_FEED_URL, feed["url"], DEFAULT_FEED_URL], requests)

    def test_failed_automatic_download_preserves_active_package(self):
        archive, _, _ = self.package(self.embedded.manifest["catalogVersion"])
        installed = install_profile_package(archive, self.appdir)
        _, feed, data = self.package(self.embedded.manifest["catalogVersion"] + 1)
        for failure in (OSError("download unavailable"), b"corrupt download"):
            with self.subTest(failure=str(failure)):
                with patch("ccz_randomizer.profile_feed.read_https", side_effect=[json.dumps(feed).encode(), failure]):
                    with self.assertRaises((OSError, ValueError)):
                        auto_update_profile(self.appdir)
                self.assertEqual(installed.root, load_profile(app_directory=self.appdir).root)

    def test_wrong_feed_group_is_rejected_before_download(self):
        _, feed, data = self.package(self.embedded.manifest["catalogVersion"] + 1)
        feed["compatibilityId"] = "ccz-fast-unsupported"
        server, requests = self.server(feed, data)
        with server, self.assertRaisesRegex(ValueError, "不兼容"):
            auto_update_profile(self.appdir)
        self.assertEqual([DEFAULT_FEED_URL], requests)
        self.assertFalse(self.appdir.exists())

    def test_package_group_is_checked_for_auto_and_manual_import(self):
        archive, feed, _ = self.package(self.embedded.manifest["catalogVersion"] + 1)
        source = next(self.root.glob("source-*/manifest.json"))
        manifest = json.loads(source.read_text(encoding="utf-8"))
        for groups in (None, ["ccz-fast-unsupported"]):
            with self.subTest(groups=groups):
                changed = copy.deepcopy(manifest)
                if groups is None:
                    changed.pop("toolCompatibility")
                else:
                    changed["toolCompatibility"] = groups
                source.write_text(json.dumps(changed), encoding="utf-8")
                with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
                    for file in source.parent.iterdir():
                        if file.is_file():
                            z.write(file, file.name)
                data = archive.read_bytes()
                feed["sha256"] = hashlib.sha256(data).hexdigest()
                server, _ = self.server(feed, data)
                with server, self.assertRaises(ValueError):
                    auto_update_profile(self.appdir)
                with self.assertRaises(ValueError):
                    install_profile_package(archive, self.appdir)
                self.assertFalse((profile_storage_root(self.appdir) / "active.json").exists())

    def test_shared_package_accepts_current_group_among_multiple_groups(self):
        archive, _, _ = self.package(self.embedded.manifest["catalogVersion"] + 1)
        manifest_path = next(self.root.glob("source-*/manifest.json"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["toolCompatibility"] = [PROFILE_COMPATIBILITY_ID, "ccz-fast-unsupported"]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for file in manifest_path.parent.iterdir():
                if file.is_file():
                    z.write(file, file.name)
        installed = install_profile_package(archive, self.appdir)
        self.assertEqual(manifest["toolCompatibility"], installed.manifest["toolCompatibility"])

    def test_existing_legacy_source_moves_to_current_group_without_changing_opt_out(self):
        from ccz_randomizer.profile_feed import LEGACY_FEED_URL, load_feed_url, save_feed_url
        save_feed_url(self.appdir, LEGACY_FEED_URL)
        self.assertEqual(DEFAULT_FEED_URL, load_feed_url(self.appdir))
        save_feed_url(self.appdir, "")
        self.assertEqual("", load_feed_url(self.appdir))

    def test_automatic_install_keeps_running_process_pinned_until_restart(self):
        from ccz_randomizer import profiles
        _, feed, data = self.package(self.embedded.manifest["catalogVersion"] + 1)
        server, _ = self.server(feed, data)
        with patch.object(profiles, "_default_app_directory", return_value=self.appdir), \
             patch.object(profiles, "_PINNED_PROFILE_DIRECTORY", None), server:
            running = load_profile()
            auto_update_profile(self.appdir)
            self.assertEqual(running.root, load_profile().root)
            self.assertEqual(feed["catalogVersion"], load_profile(app_directory=self.appdir).manifest["catalogVersion"])


if __name__ == "__main__":
    unittest.main()
