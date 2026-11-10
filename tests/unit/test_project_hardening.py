"""Local-only publication, snapshot and Tk lifetime regression tests."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch

import numpy as np

from ccz_randomizer.profiles import load_profile, validate_profile, install_profile_package, profile_storage_root
from ccz_randomizer.ui.tasks import WindowTasks
from tests.profile_fixtures import lifecycle_packages

ROOT = Path(__file__).resolve().parents[2]


def packaging_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "packaging" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PublicationTests(unittest.TestCase):
    def test_simultaneous_same_and_different_revision_installations(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            old, new = lifecycle_packages(directory)
            appdir = directory / "app"
            code = '''
import sys, time
from pathlib import Path
from ccz_randomizer.profiles import install_profile_package
gate = Path(sys.argv[3])
while not gate.exists(): time.sleep(.01)
install_profile_package(Path(sys.argv[1]), Path(sys.argv[2]))
'''
            gate = directory / "go"
            children = [subprocess.Popen([sys.executable, "-c", code, str(archive), str(appdir), str(gate)],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE) for archive in (old, new, new)]
            try:
                gate.touch()
                for child in children:
                    _, errors = child.communicate(timeout=20)
                    self.assertEqual(0, child.returncode, errors.decode(errors="replace"))
                active = load_profile(app_directory=appdir)
                self.assertIn(active.manifest["catalogVersion"], (6, 7))
                root = profile_storage_root(appdir)
                installed = [path for path in root.iterdir() if path.is_dir() and not path.name.startswith(".")]
                self.assertEqual(2, len(installed))
                for path in installed:
                    validate_profile(path)
                self.assertFalse(list(root.glob(".staging-*")))
            finally:
                for child in children:
                    if child.poll() is None:
                        child.kill()
                        child.wait()

    def test_process_dying_before_activation_keeps_previous_and_releases_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            old, new = lifecycle_packages(directory)
            appdir = directory / "app"
            previous = install_profile_package(old, appdir)
            marker = directory / "publishing"
            code = '''
import sys, time
from pathlib import Path
from ccz_randomizer.profiles import install_profile_package
original = Path.replace
def replace(self, destination):
    if self.name.startswith('.active-'):
        Path(sys.argv[3]).touch()
        time.sleep(30)
    return original(self, destination)
Path.replace = replace
install_profile_package(Path(sys.argv[1]), Path(sys.argv[2]))
'''
            child = subprocess.Popen([sys.executable, "-c", code, str(new), str(appdir), str(marker)])
            try:
                deadline = time.monotonic() + 10
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(marker.exists())
            finally:
                child.kill()
                child.wait(timeout=5)
            self.assertEqual(previous.root, load_profile(app_directory=appdir).root)
            current = install_profile_package(new, appdir)
            self.assertEqual(7, current.manifest["catalogVersion"])
            self.assertEqual(current.root, load_profile(app_directory=appdir).root)

    def test_snapshot_is_deeply_immutable_and_retained_after_publication(self):
        from ccz_randomizer import profile_context as contexts
        previous = contexts.current_context()
        snapshot = contexts.ProfileContext.from_profile(load_profile())
        with self.assertRaises(TypeError):
            snapshot.skills["displayRules"]["aliases"]["x"] = "y"
        with self.assertRaises(TypeError):
            snapshot.jobs["jobs"][0]["score"] = -1
        try:
            contexts.publish_context(snapshot)
            self.assertIs(snapshot, contexts.current_context())
            self.assertIsNot(previous, snapshot)
            self.assertTrue(previous.skills["defaults"])
        finally:
            contexts.publish_context(previous)

    def test_activation_failure_rolls_back_compatibility_bindings_and_context(self):
        from ccz_randomizer import app, jobs, profiles
        from ccz_randomizer.profile_context import current_context
        from ccz_randomizer.profile_activation import activate_installed_profile
        previous = current_context()
        job_map = dict(jobs.JOB_MAP)
        pin = profiles._PINNED_PROFILE_DIRECTORY
        with tempfile.TemporaryDirectory() as temp:
            old, new = lifecycle_packages(Path(temp))
            install_profile_package(new, Path(temp) / "app")
            with patch.object(app, "apply_equipment_profile", side_effect=RuntimeError("publication failed")):
                with self.assertRaisesRegex(RuntimeError, "publication failed"):
                    activate_installed_profile(Path(temp) / "app")
        self.assertEqual(job_map, jobs.JOB_MAP)
        self.assertEqual(pin, profiles._PINNED_PROFILE_DIRECTORY)
        self.assertIs(previous, current_context())


class BuildProvenanceTests(unittest.TestCase):
    def test_external_runtime_change_changes_build_id_even_with_fixed_clock(self):
        metadata = packaging_module("build_metadata")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "VERSION").write_text("test")
            first_path = metadata.write_build_info(root, runtime_files={"module.pyc": "first"})
            first = json.loads(first_path.read_text(encoding="utf-8"))
            second = json.loads(metadata.write_build_info(root,
                runtime_files={"module.pyc": "second"}).read_text(encoding="utf-8"))
            self.assertNotEqual(first["buildId"], second["buildId"])
            self.assertEqual(first["sourceHash"], second["sourceHash"])

    def test_resource_and_spec_changes_change_source_hash(self):
        metadata = packaging_module("build_metadata")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "resources/data").mkdir(parents=True)
            (root / "packaging").mkdir()
            resource = root / "resources/data/catalog.json"
            resource.write_text('{"revision":1}')
            before = metadata._source_hash(root)
            resource.write_text('{"revision":2}')
            after = metadata._source_hash(root)
            self.assertNotEqual(before, after)
            (root / "packaging/app.spec").write_text("new spec")
            self.assertNotEqual(after, metadata._source_hash(root))

    def test_runtime_location_is_explicit_and_missing_files_fail_early(self):
        runtime = packaging_module("runtime_dependencies")
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"CCZ_RUNTIME_ROOT": "runtime"}):
            root = Path(temp)
            with self.assertRaisesRegex(ValueError, "Missing:"):
                runtime.runtime_root(root)
            modules = root / "runtime/PYZ.pyz_extracted"
            modules.mkdir(parents=True)
            for name in runtime.RUNTIME_PACKAGES:
                (modules / (name + ".pyc")).write_bytes(b"fixture")
            self.assertEqual((root / "runtime").resolve(), runtime.runtime_root(root))

    def test_game_target_requires_matching_fingerprints(self):
        from tools.release_support import validate_game_directory
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "manifest.json").write_text(json.dumps({"gameVersion": "test",
                "files": {"fingerprints": "fingerprints.json"}}))
            executable = root / "Ekd5.exe"
            executable.write_bytes(b"expected game bytes")
            (root / "fingerprints.json").write_text(json.dumps({"test": {
                "Ekd5.exe": hashlib.sha256(executable.read_bytes()).hexdigest()}}))
            validate_game_directory(root, root)
            executable.write_bytes(b"wrong game bytes")
            with self.assertRaisesRegex(ValueError, "Ekd5.exe"):
                validate_game_directory(root, root)


class WindowTaskTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.errors = []
        self.root.report_callback_exception = lambda *error: self.errors.append(error)

    def wait(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.002)
        self.assertTrue(predicate())

    def test_worker_progress_and_result_are_delivered_on_ui_thread(self):
        tasks = WindowTasks(self.root, serial=False)
        ui_thread = threading.get_ident()
        delivered = []
        writer = tasks.channel("progress", lambda value: delivered.append((value, threading.get_ident())))
        def action():
            self.assertNotEqual(ui_thread, threading.get_ident())
            writer("progress")
            return "done"
        tasks.request("test", action, lambda value: delivered.append((value, threading.get_ident())), self.fail)
        self.wait(lambda: len(delivered) == 2)
        self.assertEqual([("progress", ui_thread), ("done", ui_thread)], delivered)
        tasks.close()

    def test_close_cancels_and_discards_late_progress_results_and_errors(self):
        for fail in (False, True):
            dialog = tk.Toplevel(self.root)
            canceled = threading.Event()
            started, release, finished = threading.Event(), threading.Event(), threading.Event()
            tasks = WindowTasks(dialog, serial=False)
            delivered = []
            writer = tasks.channel("progress", delivered.append)
            def action():
                started.set()
                release.wait(2)
                writer("late progress")
                finished.set()
                if fail:
                    raise RuntimeError("late error")
                return "late result"
            tasks.request("test", action, delivered.append, delivered.append, cancel_event=canceled)
            self.assertTrue(started.wait(1))
            dialog.destroy()
            self.assertTrue(canceled.is_set())
            release.set()
            self.assertTrue(finished.wait(1))
            self.root.update()
            self.assertEqual([], delivered)
            self.assertTrue(tasks.closed)
        self.assertEqual([], self.errors)

    def test_replaced_request_discards_old_result_and_signals_cancellation(self):
        tasks = WindowTasks(self.root, serial=False)
        cancel, entered, release = threading.Event(), threading.Event(), threading.Event()
        delivered = []
        def old_request():
            entered.set()
            release.wait(2)
            return "old"
        try:
            tasks.request("selection", old_request, delivered.append, delivered.append, cancel_event=cancel)
            self.assertTrue(entered.wait(1))
            tasks.request("selection", lambda: "new", delivered.append, delivered.append)
            self.assertTrue(cancel.is_set())
            release.set()
            self.wait(lambda: delivered)
            self.assertEqual(["new"], delivered)
        finally:
            release.set()
            tasks.close()


class RuntimeAdapterTests(unittest.TestCase):
    def test_capture_works_before_application_media_modules_are_loaded(self):
        from types import SimpleNamespace, ModuleType
        from ccz_randomizer import app

        class BaseWindow:
            hwnd = 123
            def getMat(self, *args):
                raise AssertionError("Valid PrintWindow capture must be retained")

        class Task:
            checkPeopleAtR0 = lambda self: True
            checkCczVersion = lambda self: True
            loadAndConfirm = lambda self: True
            saveAndConfirm = lambda self: True

        modules = {"window": ModuleType("window"),
                   "window.BaseWindow": SimpleNamespace(BaseWindow=BaseWindow),
                   "window.CczWindow": SimpleNamespace(CczPeopleWindow=type("PeopleWindow", (), {}))}
        panel = np.array([[[0, 0, 0], [255, 255, 255]]], dtype=np.uint8)
        with tempfile.TemporaryDirectory() as temp, patch.dict(sys.modules, modules), \
                patch.object(app, "np", None), \
                patch.object(app, "print_window_mat", return_value=panel):
            directory = Path(temp)
            (directory / "SV").mkdir()
            (directory / "SV/SV020.E5S").write_bytes(b"source preserved")
            task = SimpleNamespace(CczReRandTask=Task, KeyboardUtils=SimpleNamespace())
            app.patch_runtime(task, 123, game_executable=directory / "Ekd5.exe")
            np.testing.assert_array_equal(BaseWindow().getMat(), panel)

    def test_adapters_keep_original_methods_and_route_keyboard_to_selected_process(self):
        from types import SimpleNamespace, ModuleType
        from ccz_randomizer import app
        class BaseWindow:
            def getMat(self):
                return "original capture"
        class PeopleWindow:
            pass
        class Task:
            checkPeopleAtR0 = lambda self: True
            checkCczVersion = lambda self: True
            loadAndConfirm = lambda self: True
            saveAndConfirm = lambda self: True
        task = SimpleNamespace(CczReRandTask=Task, KeyboardUtils=SimpleNamespace())
        modules = {"window": ModuleType("window"),
                   "window.BaseWindow": SimpleNamespace(BaseWindow=BaseWindow),
                   "window.CczWindow": SimpleNamespace(CczPeopleWindow=PeopleWindow)}
        original = Task.checkPeopleAtR0
        with tempfile.TemporaryDirectory() as temp, patch.dict(sys.modules, modules), \
                patch.object(app, "post_key_to_game") as post:
            directory = Path(temp)
            (directory / "SV").mkdir()
            # Opaque source bytes: installing adapters must not parse or mutate them.
            source = directory / "SV/SV020.E5S"
            source.write_bytes(b"source preserved")
            app.patch_runtime(task, 123, game_executable=directory / "Ekd5.exe")
            self.assertIs(original, Task._ccz_original_check_r0)
            task.KeyboardUtils.tapKey("ENTER")
            post.assert_called_once_with(123, "ENTER")
            self.assertIsNone(BaseWindow().setForeground())
            self.assertEqual(b"source preserved", source.read_bytes())
            app.patch_runtime(task, 124, game_executable=directory / "Ekd5.exe")
            self.assertIs(original, Task._ccz_original_check_r0)
            task.KeyboardUtils.tapKey("ESC")
            post.assert_called_with(124, "ESC")
            app.patch_inspection_runtime(task, 125, directory)
            self.assertIsNone(BaseWindow().setForeground())
