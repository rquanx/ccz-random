import subprocess
import sys
import tempfile
import tkinter as tk
import unittest
import textwrap
from pathlib import Path
from unittest.mock import patch

from ccz_randomizer.profile_session import ProfileUpdateSession
from ccz_randomizer.ui.profile_status import ProfileStatus, ProfileStatusBadge
from ccz_randomizer.profiles import load_profile
from tools.build_profile_package import build_package


class ProfileActivationTests(unittest.TestCase):
    def test_failed_check_passes_error_detail_to_badge_state(self):
        from unittest.mock import Mock
        from tests.unit.test_profile_updates import immediate_background
        states = []
        errors = []
        session = ProfileUpdateSession(Mock(), Path("unused"), is_idle=lambda: True,
            display=states.append, notify=lambda text: None, log_error=errors.append)
        error = OSError("连接超时")
        with patch("ccz_randomizer.profile_updates.background_call", side_effect=immediate_background), \
             patch("ccz_randomizer.profile_updates.check_profile_update", side_effect=error):
            session.start()
        self.assertEqual(["checking", "unknown"], [status.state for status in states])
        self.assertEqual("连接超时", states[-1].detail)
        self.assertEqual([error], errors)

    def test_dot_is_symmetric_and_has_antialiased_edges(self):
        from PIL import Image, ImageChops, ImageOps, ImageColor
        from ccz_randomizer.ui.profile_status import render_status_dot, STATES
        color, background = STATES["latest"][1], "#f0f0f0"
        image = render_status_dot(color, background)
        self.assertIsNone(ImageChops.difference(image, ImageOps.mirror(image)).getbbox())
        self.assertIsNone(ImageChops.difference(image, ImageOps.flip(image)).getbbox())
        # Separable resampling can round transposed edge channels one level apart.
        diagonal_error = ImageChops.difference(image, image.transpose(Image.Transpose.TRANSPOSE))
        self.assertLessEqual(max(upper for lower, upper in diagonal_error.getextrema()), 1)
        self.assertTrue(set(image.getdata()) - {ImageColor.getrgb(color), ImageColor.getrgb(background)})

    def test_activation_refreshes_job_skill_memory_and_editor_snapshots(self):
        code = '''
import copy, gc, hashlib, json, os, shutil, tempfile, tkinter as tk
from pathlib import Path
from ccz_randomizer import profiles
from tools.build_profile_package import build_package
with tempfile.TemporaryDirectory() as temp:
    directory = Path(temp)
    original = profiles.load_profile()
    source = directory / 'source'
    shutil.copytree(original.root, source)
    initial = build_package(source, directory / 'initial.zip')
    appdir = directory / 'app'
    profiles.install_profile_package(initial, appdir)
    profiles._default_app_directory = lambda: appdir
    profiles._PINNED_PROFILE_DIRECTORY = None
    os.environ['CCZ_GAME_VERSION'] = profiles.load_profile().game_version
    from ccz_randomizer import app
    from ccz_randomizer.rules import config, editor, skill_defaults, skill_scores
    from ccz_randomizer.runtime import personnel_memory
    from ccz_randomizer.profile_activation import activate_installed_profile
    from tests.unit.test_rule_editor import descendants
    app.runtime_skill_catalog_rows()
    app.skill_score_catalog()
    root = tk.Tk(); root.withdraw()
    rules = config.default_rule_config()
    rules['profiles']['QA'] = copy.deepcopy(config.active_profile(rules))
    rules['activeProfile'] = 'QA'
    config.active_profile(rules).update(builtin=False, editorMode='advanced')
    editor.show_rule_editor(root, appdir, rules, app.JOB_MAP, app.TEAM_MEMBERS, skill_defaults.SKILL_DEFAULTS, lambda value: None)
    root.update()
    window = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
    check = next(w for w in descendants(window) if isinstance(w, tk.Checkbutton) and w.cget('text') == '出现特殊特技时直接合格')
    check.invoke()  # Unsaved edits must survive the data refresh.
    manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
    manifest['catalogVersion'] += 1
    jobs = json.loads((source / 'jobs.json').read_text(encoding='utf-8'))
    job_id = jobs['jobs'][0]['id']
    jobs['jobs'][0]['score'] = 3.25
    skills = json.loads((source / 'skills.json').read_text(encoding='utf-8'))
    next(row for row in skills['defaults'] if row[0] == '特效模仿')[1] = 6
    skills['displayRules']['formats']['8']['maximum'] = 6
    skills['displayRules']['equipment']['effects']['41']['template'] = '热更新宝物效果'
    skills['displayRules']['aliases']['旧别名'] = '新别名'
    layout = json.loads((source / 'memory_layout.json').read_text(encoding='utf-8'))
    old_address = personnel_memory.PLANNED_JOB_ARRAY_ADDRESS
    layout['plannedJobArrayAddress'] = hex(old_address + 4)
    for name, data in [('jobs.json', jobs), ('skills.json', skills), ('memory_layout.json', layout)]:
        (source / name).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        manifest['sha256'][name] = hashlib.sha256((source / name).read_bytes()).hexdigest()
    (source / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    archive = build_package(source, directory / 'new.zip')
    profiles.install_profile_package(archive, appdir)
    activate_installed_profile(appdir)
    assert app.JOB_MAP[job_id][1] == 3.25
    from ccz_randomizer.runtime.skill_memory import format_profile_skill_name, normalize_skill_name
    assert format_profile_skill_name('弱点攻击', 8, 6) == '弱点攻击 移动'
    assert normalize_skill_name('旧别名') == '新别名'
    assert app.decode_equipment_effect(41, 0) == '热更新宝物效果'
    assert skill_scores.DEFAULT_SCORES['特效模仿'] == 6
    assert next(row for row in app.skill_score_catalog() if row[0] == '特效模仿')[1] == 6
    assert personnel_memory.PLANNED_JOB_ARRAY_ADDRESS == old_address + 4
    assert app.JOB_OFFSET == old_address + 4 - app.MEMORY_BASE
    window.event_generate('<<ProfileUpdated>>', when='tail')
    root.update()
    replacement = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
    assert replacement is not window
    check = next(w for w in descendants(replacement) if isinstance(w, tk.Checkbutton) and w.cget('text') == '出现特殊特技时直接合格')
    assert root.getvar(check.cget('variable')) == 1
    replacement.destroy()
    del check, replacement, window
    gc.collect()  # Tcl is still alive while widget/Variable cycles are released.
    root.destroy()
    gc.collect()
'''
        # Dispose Tcl/PhotoImage cycles while Python and Tcl are still fully alive.
        # Module-level widgets otherwise survive until interpreter shutdown.
        code = "import gc\ndef exercise():\n" + textwrap.indent(code, "    ") + "\nexercise()\ngc.collect()\n"
        child = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[2],
                               capture_output=True, text=True, timeout=30)
        self.assertEqual(0, child.returncode, child.stderr)

    def test_roster_update_waits_for_idle_and_keeps_worker_snapshot(self):
        from tests.profile_fixtures import lifecycle_packages
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            old, new = lifecycle_packages(directory)
            code = '''
import os, sys
from pathlib import Path
from ccz_randomizer import profiles
directory = Path(sys.argv[1])
profiles._default_app_directory = lambda: directory
profiles.install_profile_package(Path(sys.argv[2]), directory)
os.environ['CCZ_GAME_VERSION'] = profiles.load_profile().game_version
from ccz_randomizer.rule_members import rule_member_indices
from ccz_randomizer.recruitment_catalog import load_catalog
from ccz_randomizer import app
from ccz_randomizer.profile_session import ProfileUpdateSession
from ccz_randomizer.profile_updates import profile_version_label
assert len(rule_member_indices()) == 143
assert len(load_catalog()) == 126
app.skill_score_catalog()
new = profiles.install_profile_package(Path(sys.argv[3]), directory)
class Parent:
    callbacks = []
    def winfo_exists(self): return True
    def after(self, delay, action): self.callbacks.append(action); return len(self.callbacks)
    def after_cancel(self, timer): pass
busy = [True]
states, notices = [], []
parent = Parent()
session = ProfileUpdateSession(parent, directory, is_idle=lambda: not busy[0], display=states.append, notify=notices.append)
session.downloaded(new)
assert states[-1].state == 'pending'
assert states[-1].current == 6 and states[-1].target == 7
assert len(rule_member_indices()) == 143
# A worker is pinned to the old immutable directory even though active.json changed.
old_root = session.current.root.name
worker_code = 'from ccz_randomizer.profiles import load_profile; assert load_profile().manifest["catalogVersion"] == 6'
worker_env = dict(os.environ, CCZ_PROFILE_DIRECTORY=old_root)
worker_code = 'from pathlib import Path; from ccz_randomizer import profiles; profiles._default_app_directory=lambda:Path(' + repr(str(directory)) + '); ' + worker_code
import subprocess
child = subprocess.run([sys.executable, '-c', worker_code], env=worker_env, capture_output=True, text=True)
assert child.returncode == 0, child.stderr
busy[0] = False
parent.callbacks.pop()()
assert len(rule_member_indices()) == 144
assert rule_member_indices()['关羽'] == 3
assert states[-1].state == 'latest' and states[-1].current == 7
assert profiles.load_profile().manifest['catalogVersion'] == 7
assert profile_version_label(directory) == '7'
assert len(load_catalog()) == 126
assert app.skill_score_catalog()
assert not notices
'''
            child = subprocess.run([sys.executable, "-c", code, str(directory / "app"), str(old), str(new)],
                capture_output=True, text=True)
            self.assertEqual(0, child.returncode, child.stderr)

    def test_session_checks_only_once(self):
        with patch("ccz_randomizer.profile_session.startup_profile_check") as check:
            session = ProfileUpdateSession(None, Path("unused"), is_idle=lambda: True,
                display=lambda value: None, notify=lambda value: None)
            session.start()
            session.start()
            self.assertEqual(1, check.call_count)

    def test_badge_animation_stops_after_transition_and_destroy(self):
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        badge = ProfileStatusBadge(root, ProfileStatus("updating", 2, 3))
        timer = badge._timer
        def rendered_frame():
            return root.tk.call(badge.dot.itemcget(badge._image_item, "image"), "data", "-format", "png")
        first = rendered_frame()
        ready = tk.BooleanVar()
        root.after(180, lambda: ready.set(True))
        root.wait_variable(ready)
        self.assertNotEqual(first, rendered_frame())
        badge.set_status(ProfileStatus("latest", 3))
        self.assertIsNone(badge._timer)
        self.assertFalse(any(isinstance(w, tk.Label) for w in badge.winfo_children()))
        self.assertNotIn(timer, root.tk.call("after", "info"))
        badge.set_status(ProfileStatus("old", 2, 3))
        self.assertEqual((211, 77, 85), root.tk.call(badge.dot.itemcget(badge._image_item, "image"), "get", 8, 8))
        badge.set_status(ProfileStatus("updating", 2, 3))
        timer = badge._timer
        badge.destroy()
        self.assertNotIn(timer, root.tk.call("after", "info"))

    def test_status_hover_explains_each_state_and_cleans_up(self):
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        badge = ProfileStatusBadge(root, ProfileStatus("updating", 2, 3))
        badge.tooltip.delay = 0
        badge.pack()
        root.deiconify()
        root.update()
        badge.dot.event_generate("<Enter>")
        root.update()
        self.assertIn("数据包更新中", badge.tooltip.label.cget("text"))
        self.assertIsNone(root.grab_current())
        for state, message in (("pending", "停止随机后自动生效"), ("latest", "最新版本"),
                               ("old", "旧版本"), ("unknown", "检测失败"),
                               ("checking", "正在检测"), ("local", "暂无可用更新")):
            badge.set_status(ProfileStatus(state, 2, 3))
            self.assertIn(message, badge.tooltip.label.cget("text"))
        badge.set_status(ProfileStatus("unknown", 2, detail="连接超时"))
        self.assertIn("连接超时", badge.tooltip.label.cget("text"))
        badge.dot.event_generate("<Leave>")
        self.assertIsNone(badge.tooltip.popup)
        badge.tooltip.delay = 300
        badge.dot.event_generate("<Enter>")
        timer = badge.tooltip.timer
        badge.destroy()
        self.assertNotIn(timer, root.tk.call("after", "info"))
