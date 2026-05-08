from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import settings
from .http import RequestContext, json_response
from .middleware import AccessLogEvent, log_access, monotonic_ms
from .routes.data_health import data_health, data_health_dashboard, grading_health
from .routes.edge_board import edge_board
from .routes.health import app_status, prop_ml_status
from .routes.model_cards import model_card, model_cards
from .routes.my_picks import (
    bankroll_settings,
    create_pick,
    exposure_summary,
    my_picks,
    update_bankroll_settings,
    update_pick,
)
from .routes.playerboard import playerboard, playerboard_health
from .routes.prop_detail import prop_detail
from .routes.workflows import workflow_health
from .routing import Router


def build_router() -> Router:
    router = Router()
    router.add("GET", "/api/app/status", app_status)
    router.add("GET", "/api/playerboard/health", playerboard_health)
    router.add("GET", "/api/playerboard", playerboard)
    router.add("GET", "/api/edge-board", edge_board)
    router.add("GET", "/api/prop-detail", prop_detail)
    router.add("GET", "/api/data-health", data_health)
    router.add("GET", "/api/data-health/dashboard", data_health_dashboard)
    router.add("GET", "/api/grading/health", grading_health)
    router.add("GET", "/api/workflows/health", workflow_health)
    router.add("GET", "/api/prop-ml/status", prop_ml_status)
    router.add("GET", "/api/model-cards", model_cards)
    router.add("GET", "/api/model-card", model_card)
    router.add("GET", "/api/my-picks", my_picks)
    router.add("POST", "/api/my-picks", create_pick, mutation=True, mutation_owner="bettor_state", mutation_risk="medium", mutation_kind="pick_write")
    router.add("POST", "/api/my-picks/update", update_pick, mutation=True, mutation_owner="bettor_state", mutation_risk="medium", mutation_kind="pick_write")
    router.add("GET", "/api/bankroll/settings", bankroll_settings)
    router.add("POST", "/api/bankroll/settings", update_bankroll_settings, mutation=True, mutation_owner="risk_controls", mutation_risk="high", mutation_kind="bankroll_write")
    router.add("GET", "/api/exposure/summary", exposure_summary)
    return router


def resolve_static_target(public_dir: Path, request_path: str) -> Path | None:
    """Resolve a static asset path and reject traversal/symlink escapes.

    This helper exists so the local development server and WSGI adapter share
    one path-safety rule. A symlink inside public/ that points outside public/
    resolves outside the root and is therefore rejected.
    """

    public_root = public_dir.resolve()
    relative = "index.html" if request_path in {"", "/"} else request_path.lstrip("/")
    target = (public_root / relative).resolve()

    if not target.is_relative_to(public_root):
        return None
    return target


class AppRequestHandler(BaseHTTPRequestHandler):
    router = build_router()
    public_dir = settings.public_dir

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        context = RequestContext.from_handler(self)
        if self.router.dispatch(context):
            return
        if context.path.startswith("/api/"):
            json_response(self, {"status": "error", "code": "not_found", "error": "Not found"}, HTTPStatus.NOT_FOUND)
            self._log_unmatched(context, int(HTTPStatus.NOT_FOUND), route="unmatched_api")
            return
        self.serve_static(context.path, context)

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        context = RequestContext.from_handler(self, parse_body=True)
        if self.router.dispatch(context):
            return
        json_response(self, {"status": "error", "code": "not_found", "error": "Not found"}, HTTPStatus.NOT_FOUND)
        self._log_unmatched(context, int(HTTPStatus.NOT_FOUND), route="unmatched_api")

    def serve_static(self, request_path: str, context: RequestContext) -> None:
        target = resolve_static_target(self.public_dir, request_path)
        if target is None:
            self.send_error(HTTPStatus.FORBIDDEN)
            self._log_unmatched(context, int(HTTPStatus.FORBIDDEN), route="static")
            return
        if not target.exists() or target.is_dir():
            self.send_error(HTTPStatus.NOT_FOUND)
            self._log_unmatched(context, int(HTTPStatus.NOT_FOUND), route="static")
            return
        content_type = "text/html; charset=utf-8" if target.suffix == ".html" else "application/octet-stream"
        if target.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif target.suffix == ".js":
            content_type = "application/javascript; charset=utf-8"
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        if context.request_id:
            self.send_header("X-Request-Id", context.request_id)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self._log_unmatched(context, int(HTTPStatus.OK), route="static")

    def _log_unmatched(self, context: RequestContext, status: int, *, route: str) -> None:
        log_access(
            AccessLogEvent(
                request_id=context.request_id,
                method=context.method,
                path=context.path,
                status=status,
                elapsed_ms=monotonic_ms(context.started_at or getattr(context.handler, "request_started_at", 0.0)),
                client_ip=context.client_ip,
                route=route,
            )
        )


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), AppRequestHandler)
    print(f"Serving modular MLB app on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the modular MLB app server")
    parser.add_argument("port", nargs="?", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    run(args.host, args.port)
