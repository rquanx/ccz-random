from __future__ import annotations

import json
import mimetypes
import queue
import secrets
import threading
import urllib.parse
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from ccz_randomizer.ui.statistics_web import _open_browser


@dataclass
class _DispatchTask:
    callback: Callable[[], Any]
    completed: threading.Event
    result: Any = None
    error: BaseException | None = None


class TkDispatcher:
    """Run browser API callbacks on the Tk owner thread."""

    def __init__(self, root: Any):
        self.root = root
        self.tasks: queue.Queue[_DispatchTask] = queue.Queue()
        self.closed = False

    def start(self) -> None:
        self.root.after(20, self._pump)

    def call(self, callback: Callable[[], Any], timeout: float = 30) -> Any:
        if self.closed:
            raise RuntimeError("应用窗口已经关闭")
        task = _DispatchTask(callback, threading.Event())
        self.tasks.put(task)
        if not task.completed.wait(timeout):
            raise TimeoutError("界面操作超时")
        if task.error is not None:
            raise task.error
        return task.result

    def _pump(self) -> None:
        if self.closed:
            return
        for _ in range(100):
            try:
                task = self.tasks.get_nowait()
            except queue.Empty:
                break
            try:
                task.result = task.callback()
            except BaseException as exc:
                task.error = exc
            finally:
                task.completed.set()
        try:
            self.root.after(20, self._pump)
        except Exception:
            self.closed = True

    def close(self) -> None:
        self.closed = True
        while True:
            try:
                task = self.tasks.get_nowait()
            except queue.Empty:
                break
            task.error = RuntimeError("应用窗口已经关闭")
            task.completed.set()


class MainWebSession:
    def __init__(
        self,
        dispatcher: TkDispatcher,
        *,
        bootstrap: Callable[[], dict[str, Any]],
        state: Callable[[], dict[str, Any]],
        action: Callable[[str, dict[str, Any]], dict[str, Any] | None],
        save_rules: Callable[[dict[str, Any]], dict[str, Any]],
        import_rules: Callable[[dict[str, Any]], dict[str, Any]],
        export_rules: Callable[[], dict[str, Any]],
        history: Callable[[int], dict[str, Any]],
        history_round: Callable[[int], dict[str, Any]],
        history_manage: Callable[[str, dict[str, Any]], dict[str, Any]],
    ):
        self.dispatcher = dispatcher
        self._bootstrap = bootstrap
        self._state = state
        self._action = action
        self._save_rules = save_rules
        self._import_rules = import_rules
        self._export_rules = export_rules
        self._history = history
        self._history_round = history_round
        self._history_manage = history_manage

    def bootstrap(self) -> dict[str, Any]:
        return self.dispatcher.call(self._bootstrap)

    def state(self) -> dict[str, Any]:
        return self.dispatcher.call(self._state)

    def action(
        self,
        name: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self.dispatcher.call(
            lambda: self._action(name, payload) or {"ok": True}
        )

    def save_rules(self, config: dict[str, Any]) -> dict[str, Any]:
        return self.dispatcher.call(lambda: self._save_rules(config))

    def import_rules(self, value: dict[str, Any]) -> dict[str, Any]:
        return self.dispatcher.call(lambda: self._import_rules(value))

    def export_rules(self) -> dict[str, Any]:
        return self.dispatcher.call(self._export_rules)

    def history(self, page: int) -> dict[str, Any]:
        return self.dispatcher.call(lambda: self._history(page))

    def history_round(self, round_id: int) -> dict[str, Any]:
        return self.dispatcher.call(lambda: self._history_round(round_id))

    def history_manage(
        self,
        action: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self.dispatcher.call(
            lambda: self._history_manage(action, payload)
        )


class _MainServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, assets: Path, session: MainWebSession):
        super().__init__(("127.0.0.1", 0), _MainHandler)
        self.assets = assets
        self.session = session
        self.token = secrets.token_urlsafe(24)


class _MainHandler(BaseHTTPRequestHandler):
    server: _MainServer

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _route(self) -> tuple[str, dict[str, list[str]]]:
        parsed = urllib.parse.urlsplit(self.path)
        parts = [part for part in parsed.path.split("/") if part]
        if not parts or parts[0] != self.server.token:
            return "", {}
        return "/" + "/".join(parts[1:]), urllib.parse.parse_qs(parsed.query)

    def _send(
        self,
        body: bytes,
        *,
        content_type: str,
        status: HTTPStatus = HTTPStatus.OK,
        filename: str | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if filename:
            encoded = urllib.parse.quote(filename)
            self.send_header(
                "Content-Disposition",
                f"attachment; filename*=UTF-8''{encoded}",
            )
        try:
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass

    def _json(
        self,
        value: Any,
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        self._send(
            json.dumps(
                value,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
            content_type="application/json; charset=utf-8",
            status=status,
        )

    def _payload(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        return value if isinstance(value, dict) else {}

    def _serve_asset(self, relative: str) -> None:
        target = (self.server.assets / relative).resolve()
        assets = self.server.assets.resolve()
        if target != assets and assets not in target.parents:
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        if not target.is_file():
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        content_type = (
            mimetypes.guess_type(target.name)[0]
            or "application/octet-stream"
        )
        if content_type.startswith(("text/", "application/javascript")):
            content_type += "; charset=utf-8"
        self._send(target.read_bytes(), content_type=content_type)

    def do_GET(self) -> None:
        route, query = self._route()
        if not route:
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            if route in {"/", ""}:
                self._serve_asset("index.html")
            elif route.startswith("/assets/"):
                self._serve_asset(route.removeprefix("/"))
            elif route in {"/app-icon.ico", "/source_slot_20_help.png"}:
                self._serve_asset(route.removeprefix("/"))
            elif route == "/api/app/bootstrap":
                self._json(self.server.session.bootstrap())
            elif route == "/api/app/state":
                self._json(self.server.session.state())
            elif route == "/api/app/history":
                page = int((query.get("page") or ["1"])[0])
                self._json(self.server.session.history(page))
            elif route == "/api/app/history-round":
                round_id = int((query.get("id") or ["0"])[0])
                self._json(self.server.session.history_round(round_id))
            elif route == "/api/app/rules-export":
                body = json.dumps(
                    self.server.session.export_rules(),
                    ensure_ascii=False,
                    indent=2,
                ).encode("utf-8")
                self._send(
                    body,
                    content_type="application/json; charset=utf-8",
                    filename="随机规则.json",
                )
            else:
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        route, _query = self._route()
        if not route:
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            payload = self._payload()
            if route == "/api/app/action":
                self._json(
                    self.server.session.action(
                        str(payload.get("name") or ""),
                        payload,
                    )
                )
            elif route == "/api/app/rules-save":
                config = payload.get("config")
                if not isinstance(config, dict):
                    raise ValueError("规则配置格式不正确")
                self._json(self.server.session.save_rules(config))
            elif route == "/api/app/rules-import":
                value = payload.get("value")
                if not isinstance(value, dict):
                    raise ValueError("导入文件格式不正确")
                self._json(self.server.session.import_rules(value))
            elif route == "/api/app/history-manage":
                self._json(
                    self.server.session.history_manage(
                        str(payload.get("action") or ""),
                        payload,
                    )
                )
            else:
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)


@dataclass
class MainWebWindow:
    server: _MainServer
    thread: threading.Thread

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)


def show_main_web(
    root: Any,
    session: MainWebSession,
    *,
    assets: Path,
) -> MainWebWindow | None:
    if not (assets / "index.html").is_file():
        return None
    server = _MainServer(assets, session)
    thread = threading.Thread(
        target=server.serve_forever,
        name="main-web",
        daemon=True,
    )
    thread.start()
    root.update_idletasks()
    width = min(980, max(760, root.winfo_screenwidth() - 120))
    height = min(680, max(520, root.winfo_screenheight() - 100))
    x = max(0, (root.winfo_screenwidth() - width) // 2)
    y = max(0, (root.winfo_screenheight() - height) // 2)
    url = (
        f"http://127.0.0.1:{server.server_port}/{server.token}/"
        "?view=main"
    )
    if not _open_browser(url, (x, y, width, height)):
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        return None
    return MainWebWindow(server, thread)
