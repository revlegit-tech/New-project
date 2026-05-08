from __future__ import annotations

from dataclasses import dataclass, field

from mlb_app.routing import Router


@dataclass
class FakeContext:
    method: str = "GET"
    path: str = "/api/example"
    query: dict[str, list[str]] = field(default_factory=dict)
    body: dict[str, object] = field(default_factory=dict)
    handler: object = None


class FakeHandler:
    command = "GET"
    path = "/api/example"

    def __init__(self) -> None:
        self.status = None
        self.headers = []
        self.body = b""
        self.wfile = self

    def send_response(self, status: int) -> None:
        self.status = status

    def send_header(self, key: str, value: str) -> None:
        self.headers.append((key, value))

    def end_headers(self) -> None:
        pass

    def write(self, body: bytes) -> None:
        self.body += body


def test_router_dispatches_table_route() -> None:
    router = Router()
    handler = FakeHandler()
    context = FakeContext(handler=handler)

    router.add("GET", "/api/example", lambda ctx: {"status": "ok", "path": ctx.path})

    assert router.dispatch(context) is True
    assert handler.status == 200
    assert b'"status":"ok"' in handler.body


def test_router_returns_false_for_legacy_fallback() -> None:
    router = Router()
    handler = FakeHandler()
    context = FakeContext(path="/api/legacy", handler=handler)

    assert router.dispatch(context) is False
