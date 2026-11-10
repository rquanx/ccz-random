"""Execute release failure paths against a temporary project, never a real game."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.name == "nt", "Windows release script")
class ReleaseFailureTests(unittest.TestCase):
    def test_invalid_target_failed_build_and_wrong_artifact_never_overwrite_game_tool(self):
        for scenario in ("invalid-target", "failed-build", "wrong-artifact"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                for name in ("tools/windows/build_release.ps1", "tools/release_support.py"):
                    target = root / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(ROOT / name, target)
                python = root / ".venv-win10-py314/Scripts/python.exe"
                python.parent.mkdir(parents=True)
                shutil.copy2(sys.executable, python)
                shutil.copy2(Path(sys.prefix) / "pyvenv.cfg", python.parent.parent / "pyvenv.cfg")
                (root / "VERSION").write_text("1.0.0", encoding="utf-8")
                spec = root / "packaging/test.spec"
                spec.parent.mkdir()
                spec.write_text("# Test build contract; the local PyInstaller fixture handles output.", encoding="utf-8")
                installer = root / "PyInstaller"
                installer.mkdir()
                (installer / "__init__.py").write_text("", encoding="utf-8")
                (installer / "__main__.py").write_text(
                    "from pathlib import Path\nPath('builder-ran').touch()\n"
                    + ("raise SystemExit(7)\n" if scenario == "failed-build" else
                       "Path('dist/wrong.exe').write_bytes(b'wrong new artifact')\n"), encoding="utf-8")
                profile = root / "resources/data/profiles/ccz-v2.20-1104-night"
                profile.mkdir(parents=True)
                (profile / "manifest.json").write_text(json.dumps({"gameVersion": "fixture",
                    "files": {"fingerprints": "fingerprints.json"}}), encoding="utf-8")
                (profile / "fingerprints.json").write_text(json.dumps({"fixture": {
                    "Ekd5.exe": hashlib.sha256(b"expected game").hexdigest()}}), encoding="utf-8")
                game = root / "game"
                game.mkdir()
                (game / "Ekd5.exe").write_bytes(b"wrong game" if scenario == "invalid-target" else b"expected game")
                protected = game / "tool.exe"
                protected.write_bytes(b"previous published tool")
                (root / "dist").mkdir()
                stale = root / "dist/tool.exe"
                stale.write_bytes(b"stale build that must not be released")
                environment = dict(os.environ, PYTHONPATH=str(root))
                completed = subprocess.run([
                    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(root / "tools/windows/build_release.ps1"), "-GameDir", str(game),
                    "-SpecPath", str(spec), "-OutputName", "tool.exe",
                ], cwd=root, env=environment, capture_output=True, timeout=30)
                self.assertNotEqual(0, completed.returncode)
                self.assertEqual(b"previous published tool", protected.read_bytes())
                self.assertFalse((game / "tool-1.0.0.exe").exists())
                if scenario == "invalid-target":
                    self.assertFalse((root / "builder-ran").exists())
                    self.assertEqual(b"stale build that must not be released", stale.read_bytes())
                else:
                    self.assertTrue((root / "builder-ran").exists(), completed.stderr.decode(errors="replace"))
                    self.assertFalse(stale.exists())
