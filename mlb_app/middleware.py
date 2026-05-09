from __future__ import annotations

import json
import re
import logging
import time
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from typing import Any, Mapping

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,64}$")


def new_request_id() -> str:
    """Return a compact request id suitable for headers and logs."""

    return uuid.uuid4().hex[:16]


def normalize_request_id(value: object | None) -> str:
    """Accept a safe inbound request id, otherwise generate one.

    We allow upstream proxies/tests to pass an id for correlation, but reject
    newline/control characters and overlong values so the id remains safe for
    response headers and one-line JSON logs.
    """

    if isinstance(value, str):
        candidate = value.strip()
        if _REQUEST_ID_RE.fullmatch(candidate):
            return candidate
    return new_request_id()


def monotonic_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000.0, 3)


def direct_client_ip_from_handler(handler: BaseHTTPRequestHandler) -> str:
    client_address = getattr(handler, "client_address", None)
    if isinstance(client_address, tuple) and client_address:
        return str(client_address[0])
    return "unknown"


def direct_client_ip_from_environ(environ: Mapping[str, Any]) -> str:
    return str(environ.get("REMOTE_ADDR") or "unknown")


def attach_request_metadata(
    carrier: object,
    *,
    request_id: str | None = None,
    client_ip: str | None = None,
    started_at: float | None = None,
) -> tuple[str, str, float]:
    """Attach observability metadata to a handler/adapter-like object.

    The existing route stack writes responses through a tiny handler adapter.
    Attaching metadata to that adapter lets json_response() add headers without
    changing every route signature.
    """

    rid = normalize_request_id(request_id or getattr(carrier, "request_id", None))
    ip = client_ip or getattr(carrier, "client_ip", None) or "unknown"
    start = started_at if started_at is not None else getattr(carrier, "request_started_at", None)
    if not isinstance(start, (float, int)):
        start = time.perf_counter()
    for name, value in (("request_id", rid), ("client_ip", str(ip)), ("request_started_at", float(start))):
        try:
            setattr(carrier, name, value)
        except AttributeError:
            # Some callers only need normalized values and pass an immutable
            # placeholder. Handler/adapter carriers still receive attributes.
            pass
    return rid, str(ip), float(start)


@dataclass(frozen=True)
class AccessLogEvent:
    request_id: str
    method: str
    path: str
    status: int
    elapsed_ms: float
    client_ip: str
    route: str
    cache_hit: bool | None = None
    mutation: bool = False
    rate_limited: bool = False
    auth_mode: str | None = None
    direct_client_ip: str | None = None
    effective_client_ip: str | None = None

    def as_json(self) -> str:
        payload: dict[str, Any] = {
            "event": "http_request",
            "requestId": self.request_id,
            "method": self.method,
            "path": self.path,
            "status": self.status,
            "elapsed_ms": self.elapsed_ms,
            "client_ip": self.client_ip,
            "route": self.route,
        }
        if self.cache_hit is not None:
            payload["cache_hit"] = self.cache_hit
        if self.mutation:
            payload["mutation"] = True
        if self.rate_limited:
            payload["rate_limited"] = True
        if self.auth_mode:
            payload["auth_mode"] = self.auth_mode
        if self.direct_client_ip:
            payload["directClientIp"] = self.direct_client_ip
        if self.effective_client_ip:
            payload["effectiveClientIp"] = self.effective_client_ip
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def log_access(event: AccessLogEvent) -> None:
    """Write one structured access line through stdlib logging."""

    from mlb_app.observability.logging import configure_json_logging

    configure_json_logging()
    logging.getLogger("mlb_app.access").info(event.as_json())
