"""Lightweight observations of actual runner invocations, independent of history."""
from __future__ import annotations

from contextlib import contextmanager
import json
import logging
import math
from pathlib import Path
import queue
import threading
import time
import uuid

from ccz_randomizer.statistics_store import StatisticsRepository
from ccz_randomizer.rules.identity import statistics_revision

_log = logging.getLogger(__name__)
_log.addHandler(logging.NullHandler())


def observation(runner, *, saved, interrupted, failed, elapsed):
    """Only copy evaluated stages; never fabricate an unobserved skill sample."""
    job = getattr(runner, "_job_evaluation_detail", None)
    skill = getattr(runner, "_skill_evaluation_detail", None)
    outcome = getattr(runner, "_result_outcome", "")
    status = ("stopped" if interrupted else "error" if failed else
              "saved" if saved else outcome if outcome in
              ("job_failed", "skill_failed", "inspection_abandoned") else "incomplete")
    members = {}
    reasons = []
    for stage, detail in (("job", job), ("skill", skill)):
        if not detail:
            continue
        reasons.extend((stage, str(reason)) for reason in detail.get("reasons", []))
        for member in detail.get("members", []):
            name = str(member["name"])
            row = members.setdefault(name, {"name": name})
            score = member.get("score")
            if isinstance(score, (int, float)) and math.isfinite(score):
                row[stage + "_score"] = float(score)
            if stage == "job":
                row["job"] = str(member.get("job", ""))
            else:
                row["skills"] = sorted(set(map(str, member.get("skills", []))))
    return {
        "id": uuid.uuid4().hex, "at": time.time(), "status": status,
        "saved": bool(saved or getattr(runner, "_result_save_committed", False)),
        "elapsed": max(0, elapsed), "job_checked": bool(job),
        "skill_checked": bool(skill),
        "qualified": bool(job and job.get("qualified") and skill and skill.get("qualified")),
        "members": list(members.values()), "reasons": reasons,
        "equipment": getattr(runner, "_statistics_equipment", None),
    }


class StatisticsRecorder:
    """Bounded nonblocking collection; SQLite work only runs on the writer thread."""
    def __init__(self, base: Path, *, run_id, rule_name, rule, mode, on_error=None):
        rule_json = json.dumps(rule, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.context = dict(run_id=run_id, rule_name=rule_name, rule_json=rule_json,
                            revision=statistics_revision(rule_name, rule), mode=mode)
        self.repository = StatisticsRepository(base)
        self.queue = queue.Queue(maxsize=8192)
        self.closed = threading.Event()
        self.lost = 0
        self.loss_lock = threading.Lock()
        self.on_error = on_error
        self.thread = threading.Thread(target=self._write, name="statistics-writer", daemon=True)
        self.thread.start()

    @contextmanager
    def attempt(self, runner, *, round_number, slot, attempt):
        started = time.perf_counter()
        result = {"saved": False}
        interrupted = failed = False
        try:
            yield result
        except KeyboardInterrupt:
            interrupted = True
            raise
        except BaseException:
            failed = True
            raise
        finally:
            try:
                event = observation(runner, saved=result["saved"], interrupted=interrupted,
                                    failed=failed, elapsed=time.perf_counter() - started)
                event.update(round_number=round_number, slot=slot, attempt=attempt)
                self.queue.put_nowait(event)
            except Exception as error:
                self._lose(1, error)

    def _lose(self, count, error):
        with self.loss_lock:
            first = self.lost == 0
            self.lost += count
        if first:
            if self.on_error is None:
                _log.error("随机统计采集失败，随机及存档流程继续", exc_info=error)
            else:
                try:
                    self.on_error(error)
                except Exception:
                    pass

    def _write(self):
        while not self.closed.is_set() or not self.queue.empty():
            batch = []
            try:
                batch.append(self.queue.get(timeout=0.5))
            except queue.Empty:
                continue
            deadline = time.monotonic() + 0.3
            while len(batch) < 128 and time.monotonic() < deadline:
                try:
                    batch.append(self.queue.get(timeout=0.02))
                except queue.Empty:
                    if self.closed.is_set():
                        break
            try:
                self.repository.append(self.context, batch)
            except Exception as error:
                self._lose(len(batch), error)
        if self.lost:
            try:
                self.repository.record_loss(self.lost)
            except Exception as error:
                if self.on_error is not None:
                    try:
                        self.on_error(error)
                    except Exception:
                        pass
                else:
                    _log.error("无法保存统计缺失计数：%s", self.lost, exc_info=error)

    def close(self):
        self.closed.set()
        self.thread.join()
