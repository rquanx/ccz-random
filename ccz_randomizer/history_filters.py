"""Local wall-clock bounds and matching rules for the history browser."""
from __future__ import annotations

import datetime as dt
import re


def parse_time_range(start: str, end: str) -> tuple[str | None, str | None]:
    """Return inclusive start/exclusive end; a date includes its whole day."""
    def parse(text, is_end):
        text = text.strip()
        if not text:
            return None
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?", text):
            raise ValueError("请输入日期 YYYY-MM-DD 或时间 YYYY-MM-DD HH:MM[:SS]")
        try:
            value = dt.datetime.fromisoformat(text)
            if is_end:
                value += (dt.timedelta(days=1) if len(text) == 10 else
                          dt.timedelta(minutes=1) if len(text) == 16 else dt.timedelta(seconds=1))
        except (ValueError, OverflowError) as error:
            raise ValueError("日期或时间无效，请检查输入") from error
        return value.isoformat(timespec="seconds")

    after, before = parse(start, False), parse(end, True)
    if after and before and after >= before:
        raise ValueError("开始时间不能晚于结束时间")
    return after, before


def round_text_matches(row, query):
    text = " ".join(str(row.get(key) or "") for key in ("title", "note"))
    needle = query.strip().lower()
    return not needle or needle in text.lower() or needle in str(row.get("rule_name") or "").lower()


def matching_summaries(row, snapshots, *, query="", marked_only=False):
    round_matches = round_text_matches(row, query)
    visible = []
    for snapshot in snapshots:
        metadata = snapshot.get("history") or {}
        text = " ".join(str(metadata.get(key) or "") for key in ("title", "note"))
        if (round_matches or query.strip().lower() in text.lower()) and (
            not marked_only or row.get("marked") or metadata.get("marked")
        ):
            visible.append(snapshot)
    return visible
