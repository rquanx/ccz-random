"""Keep progress polling alive when one UI update fails."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def poll_and_reschedule(poll, schedule, report_error) -> None:
    delay = 100
    try:
        delay = poll() or 100
    except Exception as error:
        try:
            report_error(error)
        except Exception:
            # Diagnostic IO failure must not disable the progress display either.
            pass
    finally:
        schedule(delay)


def report_poll_error(base_dir: Path, error: Exception) -> None:
    directory = base_dir / "ccz_fast_logs"
    directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(directory / "gui-progress.log",
                                 maxBytes=1024 * 1024, backupCount=2, encoding="utf-8")
    try:
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        record = logging.LogRecord("ccz.ui", logging.ERROR, __file__, 0,
                                   "Progress refresh failed; polling will continue", (),
                                   (type(error), error, error.__traceback__))
        handler.emit(record)
    finally:
        handler.close()
