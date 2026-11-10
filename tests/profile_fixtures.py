"""Current protocol with real pre-Guan-Yu roster, for snapshot lifecycle tests."""
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from ccz_randomizer.profiles import load_profile
from tools.build_profile_package import build_package


def lifecycle_packages(directory):
    directory = Path(directory)
    with tempfile.TemporaryDirectory() as temp:
        source = Path(temp) / "profile"
        shutil.copytree(load_profile().root, source)
        manifest_path = source / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        revision = manifest["catalogVersion"] + 1
        manifest["catalogVersion"] = revision + 1
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        new = build_package(source, directory / "new.zip")
        # The roster change is taken from the actually published old package.
        old_zip = Path(__file__).parent / "fixtures/profiles/ccz-v2.20-1104-night-r2.zip"
        with zipfile.ZipFile(old_zip) as archive:
            fixed_name = next(name for name in archive.namelist() if name.endswith("fixed_entries.json"))
            (source / "fixed_entries.json").write_bytes(archive.read(fixed_name))
        manifest["catalogVersion"] = revision
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        old = build_package(source, directory / "old.zip")
    return old, new
