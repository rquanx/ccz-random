from __future__ import annotations

import ctypes
import json
import struct
import sys
import time
from pathlib import Path

from tools.project_paths import JOB_DATA_DIR
from tools.research.experiment_reroll import EXTRACTED_ROOT, read_region
from runtime_loader import install


SAMPLES_PATH = JOB_DATA_DIR / "job_samples.json"
MAP_PATH = JOB_DATA_DIR / "job_id_map.json"
EXPECTED_IDS = set(range(0, 61, 3)) | set(range(61, 80))


def install_foreground_patch() -> None:
    from window.BaseWindow import BaseWindow

    def set_foreground(self) -> None:
        ctypes.windll.user32.ShowWindow(self.hwnd, 9)
        ctypes.windll.user32.SetForegroundWindow(self.hwnd)
        time.sleep(0.12)

    BaseWindow.setForeground = set_foreground


def seed_map() -> dict[int, dict[str, object]]:
    result: dict[int, dict[str, object]] = {}
    for sample in json.loads(SAMPLES_PATH.read_text(encoding="utf-8")):
        for index in (0, 1):
            result[int(sample["values"][index])] = sample["jobs"][index]
    if MAP_PATH.exists():
        for key, value in json.loads(MAP_PATH.read_text(encoding="utf-8")).items():
            result[int(key)] = value
    return result


def write_map(mapping: dict[int, dict[str, object]]) -> None:
    MAP_PATH.write_text(
        json.dumps(
            {str(key): value for key, value in sorted(mapping.items())},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main(pid: int, max_rounds: int) -> None:
    install(EXTRACTED_ROOT)
    install_foreground_patch()
    import task.CczReRandTask as module

    task = module.CczReRandTask(0)
    task.savePos = 1
    task.is2_08 = False
    mapping = seed_map()

    for round_no in range(1, max_rounds + 1):
        unknown = EXPECTED_IDS - mapping.keys()
        if not unknown:
            break

        task.closePeopleWindow()
        time.sleep(0.5)
        task.loadR0Sv()
        time.sleep(0.6)
        task.startRand()
        time.sleep(0.4)
        values = struct.unpack("<169I", read_region(pid, 0x2F40, 169 * 4))
        ids = (values[0], values[1])
        missing_indices = [index for index, job_id in enumerate(ids) if job_id not in mapping]

        if missing_indices:
            task.openPeople()
            time.sleep(0.5)
            task.initPeopleWind()
            mats = task.peopleWind.getJobMatList(2)
            for index in missing_indices:
                job = module.CczUtils.getCczJobWithMat(mats[index])
                if job is not None:
                    mapping[ids[index]] = {
                        "name": job.name,
                        "score": job.score,
                        "type": getattr(job.type, "name", str(job.type)),
                    }
            write_map(mapping)

        print(
            f"round={round_no} ids={ids} mapped={len(mapping)}/{len(EXPECTED_IDS)} "
            f"remaining={sorted(EXPECTED_IDS - mapping.keys())}",
            flush=True,
        )

    task.closePeopleWindow()
    write_map(mapping)


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 100)
