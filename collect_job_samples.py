from __future__ import annotations

import ctypes
import json
import struct
import sys
import time
from pathlib import Path

from experiment_reroll import EXTRACTED_ROOT, read_region
from runtime_loader import install


OUTPUT = Path(__file__).resolve().parent / "job_samples.json"


def install_foreground_patch() -> None:
    from window.BaseWindow import BaseWindow

    def set_foreground(self) -> None:
        ctypes.windll.user32.ShowWindow(self.hwnd, 9)
        ctypes.windll.user32.SetForegroundWindow(self.hwnd)
        time.sleep(0.15)

    BaseWindow.setForeground = set_foreground


def recognize_jobs(task, module, count: int) -> list[dict[str, object]]:
    task.initPeopleWind()
    if not task.peopleWind.isInitSuccess():
        raise RuntimeError("people window not found")
    result = []
    for mat in task.peopleWind.getJobMatList(count):
        job = module.CczUtils.getCczJobWithMat(mat)
        if job is None:
            raise RuntimeError("job recognition failed")
        result.append(
            {
                "name": job.name,
                "score": job.score,
                "type": getattr(job.type, "name", str(job.type)),
            }
        )
    return result


def main(pid: int, rounds: int) -> None:
    install(EXTRACTED_ROOT)
    install_foreground_patch()
    import task.CczReRandTask as module

    task = module.CczReRandTask(0)
    task.savePos = 1
    task.is2_08 = False
    samples: list[dict[str, object]] = []
    if OUTPUT.exists():
        samples = json.loads(OUTPUT.read_text(encoding="utf-8"))

    for round_no in range(len(samples) + 1, rounds + 1):
        started = time.perf_counter()
        task.closePeopleWindow()
        time.sleep(0.8)
        task.loadR0Sv()
        time.sleep(1.0)
        task.startRand()
        time.sleep(0.8)
        task.openPeople()
        time.sleep(0.8)
        jobs = recognize_jobs(task, module, 3)
        raw = read_region(pid, 0x2F40, 169 * 4)
        values = list(struct.unpack("<169I", raw))
        sample = {
            "round": round_no,
            "jobs": jobs,
            "values": values,
            "seconds": round(time.perf_counter() - started, 3),
        }
        samples.append(sample)
        OUTPUT.write_text(
            json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "round": round_no,
                    "jobs": jobs,
                    "head": values[:12],
                    "seconds": sample["seconds"],
                },
                ensure_ascii=True,
            ),
            flush=True,
        )

    task.closePeopleWindow()


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 20)
