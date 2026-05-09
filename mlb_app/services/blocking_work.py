from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

import anyio

from mlb_app.http import ApiError

T = TypeVar("T")


class BlockingWorkLimiter:
    """Bounded bridge for sync service work called from native FastAPI routes.

    The app still has sync repositories/builders during the migration. This
    limiter keeps that blocking work off the event loop while preventing burst
    traffic from saturating the process-wide worker pool indefinitely.
    """

    def __init__(self, *, max_concurrent: int = 24, timeout_seconds: float = 5.0) -> None:
        self.max_concurrent = max(1, int(max_concurrent))
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self._semaphore = anyio.Semaphore(self.max_concurrent)

    async def run(
        self,
        fn: Callable[..., T],
        *args: Any,
        timeout_seconds: float | None = None,
        route_name: str = "blocking_work",
        **kwargs: Any,
    ) -> T:
        timeout = max(0.1, float(timeout_seconds if timeout_seconds is not None else self.timeout_seconds))
        try:
            async with self._semaphore:
                with anyio.fail_after(timeout):
                    return await anyio.to_thread.run_sync(lambda: fn(*args, **kwargs))
        except TimeoutError as exc:
            raise ApiError(
                503,
                f"{route_name} exceeded the configured blocking-work timeout ({timeout:.2f}s).",
                code="blocking_work_timeout",
            ) from exc

    def status(self) -> dict[str, Any]:
        stats = getattr(self._semaphore, "statistics", lambda: None)()
        borrowed_tokens = getattr(stats, "borrowed_tokens", None)
        tasks_waiting = getattr(stats, "tasks_waiting", None)
        return {
            "maxConcurrent": self.max_concurrent,
            "timeoutSeconds": self.timeout_seconds,
            "borrowedTokens": borrowed_tokens,
            "tasksWaiting": tasks_waiting,
        }
