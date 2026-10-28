"""Read-only evidence capture. No script patch, save, or randomization is performed."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile

from ccz_randomizer.runtime.personnel_memory import read_personnel


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pid", type=int, help="Read an existing, idle game process")
    source.add_argument("--game-dir", type=Path, help="Read title data in an isolated copy")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--records", type=int, default=1024)
    args = parser.parse_args()
    if not 1 <= args.records <= 1024:
        parser.error("--records must be 1..1024")
    source_hash = ""
    if args.pid:
        rows = read_personnel(args.pid, range(args.records))
        phase = "unverified"
    else:
        from ccz_randomizer import app
        from ccz_randomizer.runtime.game_sandbox import create_game_sandbox
        # The session's native controller is unnecessary for read-only capture.
        from unittest.mock import patch
        source_hash = hashlib.sha256((args.game_dir / "Ekd5.exe").read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory(prefix="ccz-personnel-") as temporary:
            sandbox = create_game_sandbox(args.game_dir, root=Path(temporary))
            with patch.object(app, "start_persistent_native_controller"), patch.object(app, "stop_persistent_native_controller"):
                with app.HiddenGameSession(sandbox / "Ekd5.exe", announce=False) as game:
                    rows = read_personnel(game.pid, range(args.records))
        phase = "title"
    payload = {"schemaVersion": 1, "gameVersion": "2.2", "phase": phase,
        "capturedAt": dt.datetime.now().astimezone().isoformat(),
        "executableSha256": source_hash, "personnel": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已读取 {len(rows)} 条人物记录：{args.output}")


if __name__ == "__main__":
    main()
