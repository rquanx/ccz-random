from __future__ import annotations

import datetime as dt
import json
import mimetypes
import secrets
import shutil
import subprocess
import threading
import urllib.parse
import webbrowser
from dataclasses import replace
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ccz_randomizer.catalogs import (
    job_catalog_rows,
    skill_catalog_rows,
    treasure_property_catalog_rows,
)
from ccz_randomizer.statistics import StatisticsFilters, StatisticsRepository


_SERVER_LOCK = threading.Lock()
_SERVER: "_StatisticsServer | None" = None


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _include_zero_rows(
    rows: list[dict[str, Any]],
    universe: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    existing = {
        (
            str(row.get("rule_snapshot_hash") or ""),
            str(row.get("value") or ""),
        ): dict(row)
        for row in rows
    }
    result = list(existing.values())
    for template in universe:
        key = (
            str(template.get("rule_snapshot_hash") or ""),
            str(template.get("value") or ""),
        )
        if key not in existing:
            result.append(
                {
                    **template,
                    "count": 0,
                    "attempt_count": 0,
                    "save_count": 0,
                    "member_count": 0,
                    "ratio": 0.0,
                }
            )
    result.sort(key=lambda row: (-int(row.get("count") or 0), str(row.get("label") or "")))
    return result


def _local_day_bound(value: str | None) -> str | None:
    if not value:
        return None
    return (
        dt.datetime.combine(dt.date.fromisoformat(value), dt.time.min)
        .astimezone()
        .isoformat(timespec="seconds")
    )


class StatisticsWebSession:
    def __init__(
        self,
        repository: StatisticsRepository,
        *,
        current_run_id: str | None,
        current_rule_hash: str | None,
    ):
        self.repository = repository
        self.current_run_id = current_run_id
        self.current_rule_hash = current_rule_hash

    def bootstrap(self) -> dict[str, Any]:
        rules = self.repository.list_rule_options()
        name_counts: dict[str, int] = {}
        rule_options = [{"value": "", "label": "全部规则"}]
        for item in rules:
            name = str(item.get("rule_name") or "未命名规则")
            name_counts[name] = name_counts.get(name, 0) + 1
            suffix = name_counts[name]
            label = name if suffix == 1 else f"{name}（历史版本 {suffix}）"
            rule_options.append(
                {
                    "value": str(item.get("rule_snapshot_hash") or ""),
                    "label": label,
                }
            )
        return {
            "rules": rule_options,
            "members": self.repository.list_member_options(),
            "runs": self.repository.list_run_options(page_size=100),
        }

    def filters(self, source: dict[str, Any]) -> StatisticsFilters:
        content = str(source.get("content") or "all")
        metric = "attempts" if content == "other" else "completed"
        status = {
            "accepted": "accepted",
            "rejected": "rejected",
        }.get(content)
        status_group = "other" if content == "other" else None
        rule_hash = str(source.get("rule") or "")
        return StatisticsFilters(
            scope="history",
            metric=metric,
            mode=str(source.get("mode") or "all"),
            rule_mode="selected" if rule_hash else "all_summary",
            rule_hashes=(rule_hash,) if rule_hash else (),
            current_rule_hash=self.current_rule_hash,
            status=status,
            status_group=status_group,
            started_after=_local_day_bound(source.get("after")),
            started_before=_local_day_bound(source.get("before")),
        )

    def overview(self, source: dict[str, Any]) -> dict[str, Any]:
        filters = self.filters(source)
        category_filters = replace(filters, status=None, status_group=None)
        accepted = int(
            self.repository.get_summary(
                replace(
                    category_filters,
                    metric="completed",
                    status="accepted",
                )
            ).get("attempt_count", 0)
        )
        rejected = int(
            self.repository.get_summary(
                replace(
                    category_filters,
                    metric="completed",
                    status="rejected",
                )
            ).get("attempt_count", 0)
        )
        other = int(
            self.repository.get_summary(
                replace(
                    category_filters,
                    metric="attempts",
                    status_group="other",
                )
            ).get("attempt_count", 0)
        )
        summary = self.repository.get_summary(filters)
        recognition = self.repository.get_recognition_summary(filters)
        validation = self.repository.validate_statistics(filters)
        return {
            "summary": summary,
            "counts": {
                "all": accepted + rejected,
                "accepted": accepted,
                "rejected": rejected,
                "other": other,
            },
            "trend": self.repository.get_trend(filters),
            "recognition": recognition,
            "validation": {
                "valid": validation.valid,
                "issues": list(validation.issues),
            },
        }

    def details(self, source: dict[str, Any]) -> dict[str, Any]:
        filters = self.filters(source)
        page = max(1, int(source.get("page") or 1))
        page_size = 50
        total = self.repository.count_detail_rows(filters)
        rows = self.repository.get_detail_rows(
            filters,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        return {
            "rows": rows,
            "total": total,
            "page": page,
            "pageSize": page_size,
            "pageCount": max(1, (total + page_size - 1) // page_size),
        }

    def distribution(
        self,
        source: dict[str, Any],
    ) -> dict[str, Any]:
        filters = self.filters(source)
        kind = str(source.get("kind") or "jobs")
        member_id = str(source.get("memberId") or "")
        target_id = str(source.get("targetId") or "")
        section = str(source.get("section") or "all")
        if section not in {"all", "member", "target"}:
            raise ValueError(f"未知分布区域：{section}")
        members = (
            self.repository.list_member_options()
            if section == "all"
            else []
        )

        if kind == "jobs":
            rows = (
                _include_zero_rows(
                    self.repository.get_job_distribution(filters),
                    list(job_catalog_rows()),
                )
                if section == "all"
                else []
            )
            member_rows = (
                self.repository.get_job_distribution(
                    replace(filters, member_id=member_id)
                )
                if member_id and section in {"all", "member"}
                else []
            )
            target_rows = (
                self.repository.get_members_for_job(filters, target_id)
                if target_id and section in {"all", "target"}
                else []
            )
        elif kind in {"personal", "job"}:
            rows = (
                _include_zero_rows(
                    self.repository.get_skill_distribution(
                        filters,
                        scope=kind,
                    ),
                    list(skill_catalog_rows()),
                )
                if section == "all"
                else []
            )
            member_rows = (
                self.repository.get_skill_distribution(
                    replace(filters, member_id=member_id),
                    scope=kind,
                )
                if member_id and section in {"all", "member"}
                else []
            )
            target_rows = (
                self.repository.get_members_for_skill(
                    filters,
                    scope=kind,
                    skill_id=target_id,
                )
                if target_id and section in {"all", "target"}
                else []
            )
        elif kind == "treasure":
            rows = (
                _include_zero_rows(
                    self.repository.get_treasure_property_distribution(
                        filters
                    ),
                    list(treasure_property_catalog_rows()),
                )
                if section == "all"
                else []
            )
            treasure_rows = (
                self.repository.get_treasure_distribution(filters)
                if section == "all"
                else []
            )
            member_rows = (
                self.repository.get_properties_for_treasure(
                    filters,
                    member_id,
                )
                if member_id and section in {"all", "member"}
                else []
            )
            target_rows = (
                self.repository.get_treasures_for_property(
                    filters,
                    target_id,
                )
                if target_id and section in {"all", "target"}
                else []
            )
            members = [
                {
                    "member_id": str(row.get("value") or ""),
                    "member_name": str(row.get("label") or "未知宝物"),
                }
                for row in treasure_rows
            ]
        else:
            raise ValueError(f"未知分布类型：{kind}")

        targets = [
            {
                "value": str(row.get("value") or ""),
                "label": str(row.get("label") or "未知"),
            }
            for row in rows
            if str(row.get("label") or "") != "无"
        ]
        return {
            "rows": rows,
            "memberRows": member_rows,
            "targetRows": target_rows,
            "members": members,
            "targets": targets,
        }


class _StatisticsServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, assets: Path):
        super().__init__(("127.0.0.1", 0), _StatisticsHandler)
        self.assets = assets
        self.token = secrets.token_urlsafe(24)
        self.sessions: dict[str, StatisticsWebSession] = {}

    def add_session(self, session: StatisticsWebSession) -> str:
        session_id = secrets.token_urlsafe(16)
        self.sessions[session_id] = session
        return session_id


class _StatisticsHandler(BaseHTTPRequestHandler):
    server: _StatisticsServer

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _route(self) -> tuple[StatisticsWebSession | None, str, dict[str, list[str]]]:
        parsed = urllib.parse.urlsplit(self.path)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2 or parts[0] != self.server.token:
            return None, "", {}
        session = self.server.sessions.get(parts[1])
        route = "/" + "/".join(parts[2:])
        return session, route, urllib.parse.parse_qs(parsed.query)

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

    def _json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send(
            _json_bytes(value),
            content_type="application/json; charset=utf-8",
            status=status,
        )

    def _payload(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        return value if isinstance(value, dict) else {}

    def do_GET(self) -> None:
        session, route, query = self._route()
        if session is None:
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            if route in {"", "/"}:
                self._serve_asset("index.html")
            elif route.startswith("/assets/"):
                self._serve_asset(route.removeprefix("/"))
            elif route == "/api/bootstrap":
                self._json(session.bootstrap())
            elif route == "/api/export":
                self._export(session, query)
            else:
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        session, route, _query = self._route()
        if session is None:
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            payload = self._payload()
            if route == "/api/overview":
                self._json(session.overview(payload))
            elif route == "/api/details":
                self._json(session.details(payload))
            elif route == "/api/distribution":
                self._json(session.distribution(payload))
            elif route == "/api/manage":
                self._manage(session, payload)
            else:
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _serve_asset(self, relative: str) -> None:
        target = (self.server.assets / relative).resolve()
        if self.server.assets.resolve() not in target.parents and target != self.server.assets.resolve():
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        if not target.is_file():
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith(("text/", "application/javascript")):
            content_type += "; charset=utf-8"
        self._send(target.read_bytes(), content_type=content_type)

    def _export(
        self,
        session: StatisticsWebSession,
        query: dict[str, list[str]],
    ) -> None:
        format_name = (query.get("format") or ["json"])[0]
        raw_filters = (query.get("filters") or ["{}"])[0]
        filters_source = json.loads(raw_filters)
        filters = session.filters(filters_source)
        suffix = ".csv" if format_name == "csv" else ".json"
        target = Path(session.repository.path).with_name(
            f".statistics-export-{secrets.token_hex(6)}{suffix}"
        )
        try:
            session.repository.export_statistics(filters, format_name, target)
            content_type = (
                "text/csv; charset=utf-8"
                if format_name == "csv"
                else "application/json; charset=utf-8"
            )
            self._send(
                target.read_bytes(),
                content_type=content_type,
                filename=f"曹操传随机统计{suffix}",
            )
        finally:
            target.unlink(missing_ok=True)

    def _manage(
        self,
        session: StatisticsWebSession,
        payload: dict[str, Any],
    ) -> None:
        action = str(payload.get("action") or "")
        if action == "rebuild":
            session.repository.rebuild_statistics()
        elif action == "clear":
            session.repository.clear_statistics()
        elif action == "delete":
            run_id = str(payload.get("runId") or "")
            if not run_id:
                raise ValueError("缺少运行记录")
            session.repository.delete_run(run_id)
        else:
            raise ValueError("未知数据管理操作")
        self._json({"ok": True, "bootstrap": session.bootstrap()})


def _assets_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "resources" / "statistics_web"


def _server() -> _StatisticsServer:
    global _SERVER
    with _SERVER_LOCK:
        if _SERVER is None:
            assets = _assets_dir()
            if not (assets / "index.html").is_file():
                raise FileNotFoundError("统计页面资源缺失")
            _SERVER = _StatisticsServer(assets)
            threading.Thread(
                target=_SERVER.serve_forever,
                name="statistics-web",
                daemon=True,
            ).start()
        return _SERVER


def _edge_path() -> Path | None:
    direct = shutil.which("msedge")
    candidates = [
        Path(direct) if direct else None,
        Path.home()
        / "AppData/Local/Microsoft/Edge/Application/msedge.exe",
        Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
        Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
    ]
    return next(
        (candidate for candidate in candidates if candidate and candidate.is_file()),
        None,
    )


def _open_browser(url: str, geometry: tuple[int, int, int, int] | None) -> bool:
    edge = _edge_path()
    if edge is None:
        return bool(webbrowser.open_new(url))
    command = [str(edge), f"--app={url}", "--no-first-run"]
    if geometry:
        x, y, width, height = geometry
        command.extend(
            [
                f"--window-position={max(0, x)},{max(0, y)}",
                f"--window-size={width},{height}",
            ]
        )
    subprocess.Popen(command)
    return True


def create_statistics_url(
    repository: StatisticsRepository,
    *,
    current_run_id: str | None = None,
    current_rule_hash: str | None = None,
) -> str:
    server = _server()
    session_id = server.add_session(
        StatisticsWebSession(
            repository,
            current_run_id=current_run_id,
            current_rule_hash=current_rule_hash,
        )
    )
    return (
        f"http://127.0.0.1:{server.server_port}/"
        f"{server.token}/{session_id}/"
    )


def show_statistics_web(
    parent: Any,
    repository: StatisticsRepository,
    *,
    current_run_id: str | None = None,
    current_rule_hash: str | None = None,
) -> bool:
    geometry = None
    try:
        parent.update_idletasks()
        width = min(1440, max(1100, parent.winfo_screenwidth() - 120))
        height = min(920, max(720, parent.winfo_screenheight() - 120))
        x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
        geometry = (x, y, width, height)
    except Exception:
        pass
    url = create_statistics_url(
        repository,
        current_run_id=current_run_id,
        current_rule_hash=current_rule_hash,
    )
    return _open_browser(url, geometry)
