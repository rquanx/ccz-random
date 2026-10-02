from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from ccz_randomizer.ui.main_web import (
    MainWebSession,
    TkDispatcher,
    _MainServer,
)


class FakeRoot:
    def __init__(self):
        self.callbacks = []

    def after(self, _delay, callback):
        self.callbacks.append(callback)


class MainWebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.assets = Path(self.temp.name)
        (self.assets / "index.html").write_text(
            "<!doctype html><title>主界面</title>",
            encoding="utf-8",
        )
        asset_dir = self.assets / "assets"
        asset_dir.mkdir()
        (asset_dir / "index-test.js").write_text(
            "window.ready=true",
            encoding="utf-8",
        )
        (self.assets / "app-icon.ico").write_bytes(b"icon")
        (self.assets / "source_slot_20_help.png").write_bytes(b"image")
        self.root = FakeRoot()
        self.dispatcher = TkDispatcher(self.root)
        self.dispatcher.start()
        self.session = MainWebSession(
            self.dispatcher,
            bootstrap=lambda: {"version": "V3.2.2"},
            state=lambda: {"running": False},
            action=lambda name, payload: {
                "name": name,
                "value": payload.get("value"),
            },
            save_rules=lambda config: {"saved": config["name"]},
            import_rules=lambda value: {"imported": value["name"]},
            export_rules=lambda: {"name": "测试规则"},
            history=lambda page: {"page": page},
            history_round=lambda round_id: {"id": round_id},
            history_manage=lambda action, payload: {
                "action": action,
                "id": payload.get("id"),
            },
        )
        self.server = _MainServer(self.assets, self.session)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()
        self.base = (
            f"http://127.0.0.1:{self.server.server_port}/"
            f"{self.server.token}"
        )

    def tearDown(self):
        self.dispatcher.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.temp.cleanup()

    def _request(
        self,
        path: str,
        *,
        payload: dict | None = None,
    ) -> tuple[int, bytes, dict[str, str]]:
        request = urllib.request.Request(self.base + path)
        if payload is not None:
            request.data = json.dumps(payload).encode("utf-8")
            request.add_header("Content-Type", "application/json")

        result: dict[str, object] = {}

        def read_response():
            try:
                with urllib.request.urlopen(request, timeout=3) as response:
                    result["status"] = response.status
                    result["body"] = response.read()
                    result["headers"] = dict(response.headers.items())
            except BaseException as exc:
                result["error"] = exc

        worker = threading.Thread(target=read_response)
        worker.start()
        while worker.is_alive():
            callbacks = list(self.root.callbacks)
            self.root.callbacks.clear()
            for callback in callbacks:
                callback()
            worker.join(timeout=0.01)
        if "error" in result:
            raise result["error"]
        return (
            int(result["status"]),
            result["body"],
            result["headers"],
        )

    def test_server_serves_main_assets_and_rejects_bad_token(self):
        status, html, _headers = self._request("/?view=main")
        asset_status, asset, _asset_headers = self._request(
            "/assets/index-test.js"
        )
        icon_status, icon, _icon_headers = self._request("/app-icon.ico")
        help_status, help_image, _help_headers = self._request(
            "/source_slot_20_help.png"
        )

        self.assertEqual(200, status)
        self.assertIn("主界面", html.decode("utf-8"))
        self.assertEqual(200, asset_status)
        self.assertEqual(b"window.ready=true", asset)
        self.assertEqual((200, b"icon"), (icon_status, icon))
        self.assertEqual((200, b"image"), (help_status, help_image))

        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(
                f"http://127.0.0.1:{self.server.server_port}/bad/",
                timeout=3,
            )
        try:
            self.assertEqual(404, raised.exception.code)
        finally:
            raised.exception.close()

    def test_api_routes_dispatch_callbacks_on_owner_loop(self):
        _status, body, _headers = self._request("/api/app/bootstrap")
        bootstrap = json.loads(body.decode("utf-8"))
        _status, body, _headers = self._request(
            "/api/app/action",
            payload={"name": "set-mode", "value": "seven"},
        )
        action = json.loads(body.decode("utf-8"))
        _status, body, _headers = self._request("/api/app/history?page=3")
        history = json.loads(body.decode("utf-8"))

        self.assertEqual("V3.2.2", bootstrap["version"])
        self.assertEqual(
            {"name": "set-mode", "value": "seven"},
            action,
        )
        self.assertEqual(3, history["page"])

    def test_rule_export_is_downloadable_utf8_json(self):
        status, body, headers = self._request("/api/app/rules-export")

        self.assertEqual(200, status)
        self.assertEqual(
            {"name": "测试规则"},
            json.loads(body.decode("utf-8")),
        )
        self.assertIn(
            "attachment;",
            headers["Content-Disposition"],
        )

    def test_dispatcher_propagates_callback_errors(self):
        result: dict[str, BaseException] = {}

        def invoke():
            try:
                self.dispatcher.call(
                    lambda: (_ for _ in ()).throw(ValueError("失败")),
                    timeout=1,
                )
            except BaseException as exc:
                result["error"] = exc

        worker = threading.Thread(target=invoke)
        worker.start()
        while worker.is_alive():
            callbacks = list(self.root.callbacks)
            self.root.callbacks.clear()
            for callback in callbacks:
                callback()
            worker.join(timeout=0.01)

        self.assertIsInstance(result["error"], ValueError)
        self.assertEqual("失败", str(result["error"]))

    def test_tk_host_is_hidden_before_web_window_is_started(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "ccz_randomizer"
            / "app.py"
        ).read_text(encoding="utf-8")
        gui = source.split("def gui_main() -> int:", 1)[1].split(
            "\ndef main() -> int:",
            1,
        )[0]

        self.assertLess(
            gui.index("    root.withdraw()"),
            gui.index("    outer = tk.Frame(root"),
        )
        fallback = gui.split(
            "    main_web_window = show_main_web(",
            1,
        )[1]
        self.assertIn("        root.deiconify()", fallback)

    def test_rule_editor_uses_compact_tabs_and_score_grid_layout(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "web"
            / "statistics"
            / "src"
            / "DesktopApp.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn('<TabsTrigger value="simple">简单模式</TabsTrigger>', source)
        self.assertIn('<TabsTrigger value="threshold">阶段门槛</TabsTrigger>', source)
        self.assertIn('<TabsTrigger value="job-scores">兵种基础分</TabsTrigger>', source)
        self.assertIn('<TabsTrigger value="job-types">兵种类型</TabsTrigger>', source)
        self.assertIn("hide-scrollbar w-full justify-start overflow-x-auto", source)
        self.assertIn('className="grid grid-cols-4 gap-2', source)
        self.assertIn('`${tier} · 基础分`', source)
        self.assertIn(">匹配类型</span>", source)
        self.assertNotIn('<TabsTrigger value="advanced">高级模式</TabsTrigger>', source)
        self.assertNotIn('grid-cols-[180px_1fr]', source)

    def test_rule_editor_is_rendered_inside_the_main_browser_window(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "web"
            / "statistics"
            / "src"
            / "DesktopApp.tsx"
        ).read_text(encoding="utf-8")
        editor = source.split("function RuleEditor(", 1)[1].split(
            "\nexport function HistoryDialog(",
            1,
        )[0]

        self.assertIn('role="dialog"', editor)
        self.assertIn('aria-label="规则设置"', editor)
        self.assertIn("fixed inset-0 z-50 grid place-items-center", editor)
        self.assertNotIn("<Dialog open={open}", editor)

    def test_statistics_is_rendered_inside_the_main_browser_window(self):
        app_source = (
            Path(__file__).resolve().parents[2]
            / "ccz_randomizer"
            / "app.py"
        ).read_text(encoding="utf-8")
        source = (
            Path(__file__).resolve().parents[2]
            / "web"
            / "statistics"
            / "src"
            / "DesktopApp.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn('const [statisticsUrl, setStatisticsUrl] = useState("")', source)
        self.assertIn('title="结果统计"', source)
        self.assertIn("src={statisticsUrl}", source)
        self.assertNotIn('window.open(result.url', source)
        statistics_action = app_source.split(
            '        if name == "statistics":',
            1,
        )[1].split(
            '        if name == "open-file":',
            1,
        )[0]
        self.assertIn("create_statistics_url(", statistics_action)
        self.assertNotIn("open_statistics()", statistics_action)


if __name__ == "__main__":
    unittest.main()
