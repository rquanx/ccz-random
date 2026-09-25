from __future__ import annotations

import os
import time
from pathlib import Path

import fast_randomizer as fast
from trace_original_flow import read_absolute


GAME = Path(
    r"E:\game\ccz\曹操传加强版V2.10.4c"
    r"\曹操传加强版V2.10.4c\Ekd5.exe"
)


def main() -> None:
    os.environ["CCZ_USE_ISOLATED_DESKTOP"] = "1"
    with fast.HiddenGameSession(GAME) as game:
        print(f"before={fast.read_job_ids(game.pid)}")
        process = fast.native_open_load_dialog(game.pid)
        time.sleep(1)
        for command in (["loadui", "1", "0"],):
            try:
                fast.run_native_control(game.pid, command)
                print(f"{command}: ok")
            except Exception as exc:
                print(f"{command}: {exc}")
            time.sleep(2)
        print(
            [
                (h, fast.window_class(h), fast.window_text(h))
                for h in fast.process_windows(game.pid, visible_only=False)
            ]
        )
        print(f"jobs={fast.read_job_ids(game.pid)}")
        print(
            {
                hex(address): read_absolute(game.pid, address, size).hex()
                for address, size in (
                    (0x00492FBC, 4),
                    (0x00496F48, 4),
                    (0x00498058, 4),
                    (0x0049CEE0, 4),
                    (0x00500FFF, 1),
                    (0x004AB020, 1),
                    (0x0048B4C8, 4),
                )
            }
        )
        process.kill()
        process.wait()


if __name__ == "__main__":
    main()
