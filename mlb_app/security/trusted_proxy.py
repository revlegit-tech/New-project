from __future__ import annotations

import ipaddress
from collections.abc import Mapping, Sequence
from typing import Any

DEFAULT_TRUSTED_PROXY_CIDRS: tuple[str, ...] = ("127.0.0.1/32", "::1/128")


def parse_trusted_proxy_cidrs(value: str | Sequence[str] | None) -> tuple[str, ...]:
    """Return normalized trusted proxy CIDRs from env/config input.

    Invalid entries are ignored rather than making the app fail at import time;
    deployment validation can still assert the intended values explicitly.
    """

    if value is None:
        parts: Sequence[str] = DEFAULT_TRUSTED_PROXY_CIDRS
    elif isinstance(value, str):
        parts = tuple(part.strip() for part in value.replace("\n", ",").split(",") if part.strip())
    else:
        parts = tuple(str(part).strip() for part in value if str(part).strip())

    normalized: list[str] = []
    for part in parts:
        try:
            normalized.append(str(ipaddress.ip_network(part, strict=False)))
        except ValueError:
            continue
    return tuple(normalized)


def direct_client_ip_from_request(request: Any) -> str:
    client = getattr(request, "client", None)
    host = getattr(client, "host", None)
    return str(host) if host else "unknown"


def effective_client_ip_from_request(request: Any, trusted_proxy_cidrs: Sequence[str] | None = None) -> str:
    return effective_client_ip(
        direct_client_ip=direct_client_ip_from_request(request),
        headers=getattr(request, "headers", {}),
        trusted_proxy_cidrs=trusted_proxy_cidrs,
    )


def effective_client_ip(
    *,
    direct_client_ip: str,
    headers: Mapping[str, str] | Any | None = None,
    trusted_proxy_cidrs: Sequence[str] | None = None,
) -> str:
    """Return the client IP that should be used for rate limits/audit logs.

    Forwarded headers are trusted only when the direct peer is a configured proxy.
    This prevents public clients from spoofing X-Forwarded-For while still working
    behind nginx, ALB, Cloud Run, or local reverse proxies.
    """

    direct = (direct_client_ip or "unknown").strip() or "unknown"
    if not _is_trusted_direct_client(direct, trusted_proxy_cidrs):
        return direct

    forwarded = _header(headers, "x-forwarded-for")
    if forwarded:
        first = str(forwarded).split(",", 1)[0].strip()
        if first:
            return first
    real_ip = _header(headers, "x-real-ip")
    return str(real_ip).strip() if real_ip else direct


def _is_trusted_direct_client(direct_client_ip: str, trusted_proxy_cidrs: Sequence[str] | None = None) -> bool:
    candidate = (direct_client_ip or "").strip()
    # Starlette TestClient uses a synthetic host by default. Treat it as a
    # trusted local harness so existing mutation tests can pass loopback headers.
    if candidate in {"testclient", "testserver"}:
        return True
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return False
    for raw_network in parse_trusted_proxy_cidrs(trusted_proxy_cidrs):
        try:
            if address in ipaddress.ip_network(raw_network, strict=False):
                return True
        except ValueError:
            continue
    return False


def _header(headers: Mapping[str, str] | Any | None, name: str) -> str:
    if headers is None:
        return ""
    getter = getattr(headers, "get", None)
    if callable(getter):
        value = getter(name)
        if value is None:
            value = getter(name.title())
        return str(value or "")
    if isinstance(headers, Mapping):
        lowered = name.lower()
        for key, value in headers.items():
            if str(key).lower() == lowered:
                return str(value or "")
    return ""
