from __future__ import annotations

import ipaddress
import os
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Mapping

ACTION_HEADER = "X-Baseball-Prop-Action"
TOKEN_HEADERS = ("X-MLB-App-Token", "X-API-Token", "Authorization")
CSRF_HEADER = "X-CSRF-Token"
DEFAULT_MUTATION_LIMIT = 10
DEFAULT_MUTATION_WINDOW_SECONDS = 60.0


class MutationSecurityError(Exception):
    """Safe mutation-boundary error rendered by Router.dispatch()."""

    def __init__(self, status: int | HTTPStatus, message: str, *, code: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.status = int(status)
        self.message = message
        self.code = code
        self.retry_after = retry_after


@dataclass(frozen=True)
class MutationEndpointSpec:
    """Security metadata for a state-changing endpoint."""

    owner: str
    risk: str
    kind: str = "product_mutation"
    enabled: bool = True


@dataclass(frozen=True)
class MutationSecurityConfig:
    runtime_mode: str
    action_header: str = ACTION_HEADER
    token_headers: tuple[str, ...] = TOKEN_HEADERS
    csrf_header: str = CSRF_HEADER
    max_requests: int = DEFAULT_MUTATION_LIMIT
    window_seconds: float = DEFAULT_MUTATION_WINDOW_SECONDS
    require_csrf: bool = False
    configured_tokens: frozenset[str] = frozenset()
    configured_csrf_token: str = ""

    @property
    def token_required(self) -> bool:
        return self.runtime_mode in {"shared", "staging", "production"}

    @property
    def localhost_required(self) -> bool:
        return self.runtime_mode in {"local", "development", "test"}


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _runtime_mode_from_env(environ: Mapping[str, str] | None = None) -> str:
    source = environ or os.environ
    raw = (source.get("MLB_ENV") or source.get("MLB_APP_ENV") or source.get("APP_ENV") or "").strip().lower()
    if _truthy(source.get("MLB_DEV_MODE")):
        return "local"
    if raw in {"local", "development", "dev", "test"}:
        return "local"
    if raw in {"shared", "staging", "stage", "preview"}:
        return "staging"
    if raw in {"production", "prod"}:
        return "production"
    # Safe for developer machines: action header + loopback are still required.
    return "local"


def _split_tokens(value: str | None) -> set[str]:
    if not value:
        return set()
    return {part.strip() for part in value.replace("\n", ",").split(",") if part.strip()}


def mutation_security_config(environ: Mapping[str, str] | None = None) -> MutationSecurityConfig:
    source = environ or os.environ
    tokens: set[str] = set()
    for key in ("MLB_MUTATION_TOKEN", "MLB_API_TOKEN", "MLB_ADMIN_TOKEN"):
        tokens.update(_split_tokens(source.get(key)))
    try:
        max_requests = max(1, int(source.get("MLB_MUTATION_RATE_LIMIT", str(DEFAULT_MUTATION_LIMIT))))
    except ValueError:
        max_requests = DEFAULT_MUTATION_LIMIT
    try:
        window_seconds = max(1.0, float(source.get("MLB_MUTATION_RATE_WINDOW_SECONDS", str(DEFAULT_MUTATION_WINDOW_SECONDS))))
    except ValueError:
        window_seconds = DEFAULT_MUTATION_WINDOW_SECONDS
    csrf_token = (source.get("MLB_CSRF_TOKEN") or "").strip()
    return MutationSecurityConfig(
        runtime_mode=_runtime_mode_from_env(source),
        max_requests=max_requests,
        window_seconds=window_seconds,
        require_csrf=_truthy(source.get("MLB_REQUIRE_CSRF")) or bool(csrf_token),
        configured_tokens=frozenset(tokens),
        configured_csrf_token=csrf_token,
    )


class TokenBucketRateLimiter:
    """Process-local token bucket for mutation endpoints."""

    def __init__(self, *, capacity: int = DEFAULT_MUTATION_LIMIT, window_seconds: float = DEFAULT_MUTATION_WINDOW_SECONDS) -> None:
        self.capacity = max(1, int(capacity))
        self.window_seconds = max(1.0, float(window_seconds))
        self.refill_rate = self.capacity / self.window_seconds
        self._lock = threading.RLock()
        self._buckets: dict[str, tuple[float, float]] = {}

    def allow(self, key: str, *, now: float | None = None) -> tuple[bool, int]:
        current = time.monotonic() if now is None else now
        with self._lock:
            tokens, updated_at = self._buckets.get(key, (float(self.capacity), current))
            elapsed = max(0.0, current - updated_at)
            tokens = min(float(self.capacity), tokens + elapsed * self.refill_rate)
            if tokens >= 1.0:
                self._buckets[key] = (tokens - 1.0, current)
                return True, 0
            retry_after = max(1, int((1.0 - tokens) / self.refill_rate))
            self._buckets[key] = (tokens, current)
            return False, retry_after

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {"capacity": self.capacity, "windowSeconds": self.window_seconds, "bucketCount": len(self._buckets)}


mutation_rate_limiter = TokenBucketRateLimiter()


def header_value(headers: Any, name: str) -> str | None:
    if headers is None:
        return None
    getter = getattr(headers, "get", None)
    if callable(getter):
        value = getter(name)
        if value is not None:
            return str(value)
        items = getattr(headers, "items", None)
        if callable(items):
            for key, candidate in items():
                if str(key).lower() == name.lower():
                    return str(candidate)
    return None


def _extract_token(headers: Any, config: MutationSecurityConfig) -> str:
    for name in config.token_headers:
        value = header_value(headers, name)
        if not value:
            continue
        value = value.strip()
        if name.lower() == "authorization" and value.lower().startswith("bearer "):
            return value[7:].strip()
        if name.lower() != "authorization":
            return value
    return ""


def _is_loopback_client(client_ip: str) -> bool:
    candidate = (client_ip or "").strip()
    if candidate in {"localhost", "::1", "127.0.0.1"}:
        return True
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return False


def enforce_mutation_security(
    *,
    context: Any,
    spec: MutationEndpointSpec | None,
    config: MutationSecurityConfig | None = None,
    limiter: TokenBucketRateLimiter | None = None,
) -> None:
    if spec is None:
        return
    if not spec.enabled:
        raise MutationSecurityError(HTTPStatus.NOT_FOUND, "Workflow is not exposed by this runtime", code="workflow_quarantined")

    cfg = config or mutation_security_config()
    headers = getattr(getattr(context, "handler", None), "headers", None)
    if header_value(headers, cfg.action_header) != "1":
        raise MutationSecurityError(HTTPStatus.FORBIDDEN, f"Mutating actions require {cfg.action_header}: 1", code="action_header_required")

    if cfg.localhost_required and not _is_loopback_client(getattr(context, "client_ip", "unknown")):
        raise MutationSecurityError(HTTPStatus.FORBIDDEN, "Local mutation mode only accepts loopback clients", code="localhost_required")

    if cfg.token_required:
        if not cfg.configured_tokens:
            raise MutationSecurityError(HTTPStatus.SERVICE_UNAVAILABLE, "Mutation token is not configured for this runtime", code="mutation_token_not_configured")
        if _extract_token(headers, cfg) not in cfg.configured_tokens:
            raise MutationSecurityError(HTTPStatus.UNAUTHORIZED, "Valid mutation token required", code="mutation_token_required")

    if cfg.runtime_mode == "production" and cfg.require_csrf:
        csrf_value = header_value(headers, cfg.csrf_header) or ""
        if cfg.configured_csrf_token and csrf_value != cfg.configured_csrf_token:
            raise MutationSecurityError(HTTPStatus.FORBIDDEN, "Valid CSRF token required", code="csrf_token_required")
        if not cfg.configured_csrf_token and not csrf_value:
            raise MutationSecurityError(HTTPStatus.FORBIDDEN, "CSRF token required", code="csrf_token_required")

    global mutation_rate_limiter
    active_limiter = limiter or mutation_rate_limiter
    if limiter is None and (active_limiter.capacity != cfg.max_requests or active_limiter.window_seconds != cfg.window_seconds):
        active_limiter = TokenBucketRateLimiter(capacity=cfg.max_requests, window_seconds=cfg.window_seconds)
        mutation_rate_limiter = active_limiter
    route_name = getattr(context, "route_name", "mutation") or "mutation"
    key = f"{getattr(context, 'client_ip', 'unknown')}:{route_name}"
    allowed, retry_after = active_limiter.allow(key)
    if not allowed:
        raise MutationSecurityError(HTTPStatus.TOO_MANY_REQUESTS, "Mutation rate limit exceeded", code="rate_limited", retry_after=retry_after)
