from __future__ import annotations

from mlb_app.security.rate_limit import TokenBucketRateLimiter


class Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float = 1.0) -> None:
        self.value += seconds


def test_rate_limiter_status_exposes_bucket_cap() -> None:
    limiter = TokenBucketRateLimiter(max_buckets=128)

    assert limiter.status() == {"bucketCount": 0, "maxBuckets": 128}


def test_rate_limiter_evicts_lru_buckets_overflow() -> None:
    clock = Clock()
    limiter = TokenBucketRateLimiter(max_buckets=64, now=clock)

    for index in range(100):
        limiter.allow(f"ip-{index}:GET:/api/app/status", capacity=10)
        clock.advance()

    status = limiter.status()
    assert status["bucketCount"] == 64
    assert status["maxBuckets"] == 64
    assert "ip-0:GET:/api/app/status" not in limiter._buckets
    assert "ip-99:GET:/api/app/status" in limiter._buckets
