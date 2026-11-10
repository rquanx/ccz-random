"""Full copies for integration tests; no hard links back into a player's game."""
from contextlib import contextmanager
from pathlib import Path
import shutil
import tempfile

from ccz_randomizer.runtime.game_sandbox import EXCLUDED_NAMES


@contextmanager
def isolated_game_copy(source: Path):
    source = source.resolve()
    if not (source / "Ekd5.exe").is_file():
        raise FileNotFoundError(source / "Ekd5.exe")
    with tempfile.TemporaryDirectory(prefix="ccz-t-") as temporary:
        target = Path(temporary) / "game"
        shutil.copytree(source, target, ignore=shutil.ignore_patterns(*EXCLUDED_NAMES, "*.log"))
        yield target
