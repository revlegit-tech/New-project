from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int = 0
    remaining: int = 0


class TokenBucketRateLimiter:
    """Small in-process token bucket suitable for a single ASGI worker.

    Gunicorn workers each keep their own local buckets. For multi-node global
    limits, swap this implementation for Redis while preserving the same API.
    """

    def __init__(self, *, max_buckets: int = 8192, now: Any | None = None) -> None:
        self.max_buckets = max(64, int(max_buckets))
        self._now = now or time.monotonic
        self._lock = threading.RLock()
        # key -> (tokens, last_updated_at, last_used_at)
        self._buckets: dict[str, tuple[float, float, float]] = {}

    def allow(
        self,
        key: str,
        *,
        capacity: int,
        window_seconds: float = 60.0,
        refill_per_second: float | None = None,
    ) -> RateLimitDecision:
        capacity = max(1, int(capacity))
        window_seconds = max(1.0, float(window_seconds))
        refill_rate = float(refill_per_second) if refill_per_second is not None else capacity / window_seconds
        refill_rate = max(1.0 / window_seconds, refill_rate)
        current = float(self._now())
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                tokens, updated_at = float(capacity), current
            else:
                tokens, updated_at, _last_used_at = bucket
            elapsed = max(0.0, current - updated_at)
            tokens = min(float(capacity), tokens + elapsed * refill_rate)
            if tokens >= 1.0:
                tokens -= 1.0
                self._buckets[key] = (tokens, current, current)
                self._evict_overflow_locked()
                return RateLimitDecision(True, retry_after=0, remaining=max(0, int(tokens)))
            retry_after = max(1, int((1.0 - tokens) / refill_rate))
            self._buckets[key] = (tokens, current, current)
            self._evict_overflow_locked()
            return RateLimitDecision(False, retry_after=retry_after, remaining=0)

    def _evict_overflow_locked(self) -> None:
        while len(self._buckets) > self.max_buckets:
            victim = min(self._buckets, key=lambda item: self._buckets[item][2])
            self._buckets.pop(victim, None)

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {"bucketCount": len(self._buckets), "maxBuckets": self.max_buckets}
