from contextlib import closing
import copy
import json
from pathlib import Path
import tempfile
import unittest

from ccz_randomizer.history import HistoryRepository
from ccz_randomizer.history_filters import matching_summaries, parse_time_range


class HistoryTimeRangeTests(unittest.TestCase):
    def test_dates_include_whole_day_and_minutes_include_whole_minute(self):
        self.assertEqual(("2026-11-07T00:00:00", "2026-11-08T00:00:00"),
                         parse_time_range("2026-11-07", "2026-11-07"))
        self.assertEqual(("2026-11-07T12:30:00", "2026-11-07T12:31:00"),
                         parse_time_range("2026-11-07 12:30", "2026-11-07 12:30"))
        self.assertEqual(("2026-11-07T12:30:59", "2026-11-07T12:31:00"),
                         parse_time_range("2026-11-07 12:30:59", "2026-11-07 12:30:59"))

    def test_optional_bounds_leap_day_and_invalid_or_reversed_input(self):
        self.assertEqual((None, None), parse_time_range(" ", ""))
        self.assertEqual((None, "2028-03-01T00:00:00"), parse_time_range("", "2028-02-29"))
        self.assertEqual(("2026-11-07T00:00:00", None), parse_time_range("2026-11-07", ""))
        for start, end in (("2026-02-29", ""), ("2026-11-07 25:00", ""),
                           ("11/07", ""), ("2026-11-07T12:00:00+08:00", ""),
                           ("2026-11-08", "2026-11-07"), ("2026-11-07 12:31", "2026-11-07 12:30")):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                parse_time_range(start, end)


class HistoryFilterRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = HistoryRepository(Path(self.temp.name))
        self.repo.start_run("run", mode="three", loop_random=True, rule_name="默认规则", rule={}, build={})
        self.snapshot = json.loads((Path(__file__).parents[1] / "fixtures/personnel_220_1104/randomized-result.json").read_text(encoding="utf-8"))
        self.snapshot.update(slot=1, acceptedAttempt=1)
        self.ids = []
        # Existing history uses local ISO timestamps with +08:00, at second precision.
        for number, timestamp in enumerate(("2026-11-06T23:59:59", "2026-11-07T00:00:00",
                "2026-11-07T12:30:00", "2026-11-07T12:30:59", "2026-11-07T12:31:00",
                "2026-11-07T23:59:59", "2026-11-08T00:00:00"), 1):
            rid = self.repo.start_round("run", number)
            self.ids.append(rid)
            self.repo.save_result(rid, self.snapshot)
            with closing(self.repo._connect()) as db, db:
                db.execute("UPDATE rounds SET started_at=? WHERE id=?", (timestamp + "+08:00", rid))

    def bounds(self, start, end):
        after, before = parse_time_range(start, end)
        return dict(started_after=after, started_before=before)

    def test_day_range_and_pagination_counts_share_same_boundaries(self):
        filters = self.bounds("2026-11-07", "2026-11-07")
        self.assertEqual(5, self.repo.count_rounds(**filters))
        self.assertEqual(list(reversed(self.ids[1:6])), [r["id"] for r in self.repo.list_rounds(**filters)])
        self.assertEqual(self.ids[1:2], [r["id"] for r in self.repo.list_rounds(page=3, page_size=2, **filters)])

    def test_second_minute_and_open_ended_ranges(self):
        filters = self.bounds("2026-11-07 12:30", "2026-11-07 12:30")
        self.assertEqual([self.ids[3], self.ids[2]], [r["id"] for r in self.repo.list_rounds(**filters)])
        self.assertEqual(1, self.repo.count_rounds(**self.bounds("2026-11-07 12:30:59", "2026-11-07 12:30:59")))
        self.assertEqual(1, self.repo.count_rounds(**self.bounds("", "2026-11-06")))
        self.assertEqual(1, self.repo.count_rounds(**self.bounds("2026-11-08", "")))

    def test_search_and_mark_must_match_same_card_unless_round_matches(self):
        rid = self.ids[3]
        second = copy.deepcopy(self.snapshot)
        second["slot"] = 2
        self.repo.save_result(rid, second)
        self.repo.annotate_round(rid, title="曹操优选", note="搜索命中")
        filters = dict(query="搜索命中", marked_only=False, **self.bounds("2026-11-07", "2026-11-07"))
        rows = self.repo.list_rounds(**filters)
        self.assertEqual([rid], [r["id"] for r in rows])
        visible = matching_summaries(rows[0], self.repo.get_round_summaries(rid), query="搜索命中")
        self.assertEqual([1, 2], [s["slot"] for s in visible])

    def test_partial_round_status_does_not_hide_accepted_results(self):
        for rid, status in zip(self.ids[:3], ("completed", "stopped", "failed")):
            self.repo.finish_round(rid, status)
        self.assertEqual(7, self.repo.count_rounds())
        self.assertTrue(all(row["result_count"] == 1 for row in self.repo.list_rounds()))
