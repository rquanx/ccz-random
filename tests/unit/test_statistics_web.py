from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ccz_randomizer.ui.statistics_web import (
    _StatisticsHandler,
    StatisticsWebSession,
    _StatisticsServer,
    _assets_dir,
    create_statistics_url,
    _open_browser,
)


class FakeStatisticsRepository:
    def __init__(self, base: Path):
        self.path = base / "history.sqlite3"
        self.calls: list[tuple[str, object]] = []

    def list_rule_options(self):
        return [
            {
                "rule_snapshot_hash": "hash-a",
                "rule_name": "七人高特技",
                "rule_schema_version": 1,
            },
            {
                "rule_snapshot_hash": "hash-b",
                "rule_name": "七人高特技",
                "rule_schema_version": 2,
            },
        ]

    def list_member_options(self):
        return [
            {"member_id": "cao-cao", "member_name": "曹操"},
            {"member_id": "xiahou-dun", "member_name": "夏侯惇"},
        ]

    def list_run_options(self, *, page_size=100):
        return [{"id": "run-1", "rule_name": "七人高特技"}]

    def get_job_distribution(self, filters):
        self.calls.append(("jobs", filters.member_id))
        if filters.member_id:
            return [
                {
                    "value": "job-1",
                    "label": "策士",
                    "count": 2,
                    "ratio": 1.0,
                }
            ]
        return [
            {
                "value": "job-1",
                "label": "策士",
                "count": 2,
                "ratio": 1.0,
            }
        ]

    def get_members_for_job(self, _filters, job_id):
        self.calls.append(("job-members", job_id))
        return [
            {
                "value": "cao-cao",
                "label": "曹操",
                "count": 2,
                "ratio": 1.0,
            }
        ]

    def rebuild_statistics(self):
        self.calls.append(("manage", "rebuild"))

    def clear_statistics(self):
        self.calls.append(("manage", "clear"))

    def delete_run(self, run_id):
        self.calls.append(("manage", run_id))


class StatisticsWebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.repository = FakeStatisticsRepository(self.base)
        self.session = StatisticsWebSession(
            self.repository,
            current_run_id=None,
            current_rule_hash="current-hash",
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_bootstrap_disambiguates_historical_rule_names(self):
        bootstrap = self.session.bootstrap()

        self.assertEqual(
            ["全部规则", "七人高特技", "七人高特技（历史版本 2）"],
            [item["label"] for item in bootstrap["rules"]],
        )

    def test_filters_map_completed_status_rule_and_local_dates(self):
        filters = self.session.filters(
            {
                "content": "accepted",
                "mode": "seven",
                "rule": "hash-a",
                "after": "2026-09-01",
                "before": "2026-10-01",
            }
        )

        self.assertEqual("completed", filters.metric)
        self.assertEqual("accepted", filters.status)
        self.assertEqual("seven", filters.mode)
        self.assertEqual("selected", filters.rule_mode)
        self.assertEqual(("hash-a",), filters.rule_hashes)
        self.assertIn("2026-09-01T00:00:00", filters.started_after)
        self.assertIn("2026-10-01T00:00:00", filters.started_before)

    def test_distribution_only_queries_requested_chart_relations(self):
        result = self.session.distribution(
            {
                "kind": "jobs",
                "content": "all",
                "memberId": "cao-cao",
                "targetId": "job-1",
            }
        )

        self.assertIn(("jobs", None), self.repository.calls)
        self.assertIn(("jobs", "cao-cao"), self.repository.calls)
        self.assertIn(("job-members", "job-1"), self.repository.calls)
        self.assertEqual("策士", result["memberRows"][0]["label"])
        self.assertGreater(len(result["rows"]), 1)
        self.assertTrue(any(row["count"] == 0 for row in result["rows"]))

    def test_distribution_member_section_only_queries_member_chart(self):
        result = self.session.distribution(
            {
                "kind": "jobs",
                "content": "all",
                "memberId": "cao-cao",
                "targetId": "job-1",
                "section": "member",
            }
        )

        self.assertEqual([("jobs", "cao-cao")], self.repository.calls)
        self.assertEqual("策士", result["memberRows"][0]["label"])
        self.assertEqual([], result["rows"])
        self.assertEqual([], result["targetRows"])
        self.assertEqual([], result["members"])

    def test_overview_does_not_load_removed_result_details(self):
        repository = mock.Mock()
        repository.get_summary.return_value = {
            "attempt_count": 2,
            "rule_count": 1,
            "save_count": 1,
        }
        repository.get_recognition_summary.return_value = {
            "known_positions": 3,
            "total_positions": 3,
        }
        repository.validate_statistics.return_value = SimpleNamespace(
            valid=True,
            issues=(),
        )
        repository.get_trend.return_value = []
        session = StatisticsWebSession(
            repository,
            current_run_id=None,
            current_rule_hash=None,
        )

        result = session.overview({"content": "all"})

        self.assertNotIn("details", result)
        repository.count_detail_rows.assert_not_called()
        repository.get_detail_rows.assert_not_called()

    def test_statistics_views_keep_loaded_content_during_navigation_and_refresh(self):
        source = (
            Path(__file__).parents[2]
            / "web"
            / "statistics"
            / "src"
            / "App.tsx"
        ).read_text(encoding="utf-8")

        self.assertNotIn("setData(null)", source)
        self.assertIn('hidden={tab !== "overview"}', source)
        self.assertIn('hidden={tab !== "jobs"}', source)
        self.assertIn('hidden={tab !== "skills"}', source)
        self.assertIn('hidden={tab !== "treasure"}', source)
        self.assertIn('active={tab === "overview"}', source)
        self.assertIn('active={tab === "skills" && skillTab === "personal"}', source)
        self.assertIn("loading && <RefreshIndicator />", source)
        self.assertIn('<main className="mt-4">', source)
        self.assertNotIn('min-h-[1060px]', source)
        self.assertNotIn('min-h-[940px]', source)
        self.assertNotIn('min-h-[760px]', source)

    def test_distribution_charts_hide_scrollbars_without_disabling_scroll(self):
        root = Path(__file__).parents[2] / "web" / "statistics" / "src"
        chart_source = (
            root / "components" / "virtual-bar-chart.tsx"
        ).read_text(encoding="utf-8")
        style_source = (root / "index.css").read_text(encoding="utf-8")

        self.assertIn(
            'className="hide-scrollbar overflow-auto border-t"',
            chart_source,
        )
        self.assertIn(".hide-scrollbar::-webkit-scrollbar", style_source)
        self.assertIn("scrollbar-width: none", style_source)

    def test_page_scrollbar_is_hidden_without_disabling_page_scroll(self):
        style_source = (
            Path(__file__).parents[2]
            / "web"
            / "statistics"
            / "src"
            / "index.css"
        ).read_text(encoding="utf-8")

        html_rule = style_source.split("html {", 1)[1].split("}", 1)[0]
        self.assertIn("overflow-y: auto", html_rule)
        self.assertIn("scrollbar-width: none", html_rule)
        self.assertIn("html::-webkit-scrollbar", style_source)
        self.assertNotIn("overflow-y: hidden", html_rule)

    def test_http_server_serves_assets_and_rejects_missing_token(self):
        server = _StatisticsServer(_assets_dir())
        session_id = server.add_session(self.session)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = (
                f"http://127.0.0.1:{server.server_port}/"
                f"{server.token}/{session_id}"
            )
            with urllib.request.urlopen(base + "/", timeout=3) as response:
                html = response.read().decode("utf-8")
            asset_path = next(
                part.split('"')[0]
                for part in html.split("/assets/")[1:]
                if part.startswith("index-")
            )
            with urllib.request.urlopen(
                base + "/assets/" + asset_path,
                timeout=3,
            ) as response:
                asset = response.read()
            with urllib.request.urlopen(
                base + "/api/bootstrap",
                timeout=3,
            ) as response:
                bootstrap = json.loads(response.read().decode("utf-8"))
            self.assertIn("结果统计", html)
            self.assertTrue(asset)
            self.assertEqual("全部规则", bootstrap["rules"][0]["label"])
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(
                    f"http://127.0.0.1:{server.server_port}/bad/",
                    timeout=3,
                )
            try:
                self.assertEqual(404, raised.exception.code)
            finally:
                raised.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_edge_app_mode_is_used_when_edge_is_available(self):
        with (
            mock.patch(
                "ccz_randomizer.ui.statistics_web._edge_path",
                return_value=Path("C:/Edge/msedge.exe"),
            ),
            mock.patch(
                "ccz_randomizer.ui.statistics_web.subprocess.Popen"
            ) as popen,
        ):
            opened = _open_browser(
                "http://127.0.0.1:1234/token/session/",
                (10, 20, 1280, 840),
            )

        self.assertTrue(opened)
        command = popen.call_args.args[0]
        self.assertIn(
            "--app=http://127.0.0.1:1234/token/session/",
            command,
        )
        self.assertIn("--window-position=10,20", command)
        self.assertIn("--window-size=1280,840", command)

    def test_create_statistics_url_registers_an_embeddable_session(self):
        server = mock.Mock()
        server.server_port = 4321
        server.token = "token"
        server.add_session.return_value = "session"
        with mock.patch(
            "ccz_randomizer.ui.statistics_web._server",
            return_value=server,
        ):
            url = create_statistics_url(
                self.repository,
                current_run_id="run-1",
                current_rule_hash="rule-1",
            )

        self.assertEqual(
            "http://127.0.0.1:4321/token/session/",
            url,
        )
        session = server.add_session.call_args.args[0]
        self.assertEqual("run-1", session.current_run_id)
        self.assertEqual("rule-1", session.current_rule_hash)

    def test_client_disconnect_during_response_is_ignored(self):
        handler = object.__new__(_StatisticsHandler)
        handler.send_response = mock.Mock()
        handler.send_header = mock.Mock()
        handler.end_headers = mock.Mock()
        handler.wfile = mock.Mock()
        handler.wfile.write.side_effect = ConnectionAbortedError()

        handler._send(b"payload", content_type="text/plain")

        handler.wfile.write.assert_called_once_with(b"payload")


if __name__ == "__main__":
    unittest.main()
