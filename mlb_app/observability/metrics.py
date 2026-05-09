from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Iterable

LabelPairs = tuple[tuple[str, str], ...]


def _labels(labels: dict[str, Any] | None = None) -> LabelPairs:
    return tuple(sorted((str(key), str(value)) for key, value in (labels or {}).items()))


@dataclass(frozen=True)
class TimerResult:
    name: str
    elapsed_ms: float
    labels: dict[str, str]


class MetricsRegistry:
    """Tiny in-process metrics registry for Sprint 6 operational visibility.

    This is intentionally boring: counters and rolling latency samples are enough
    to expose request volume, p95/p99 latency, SQLite writes, model load failures,
    and pick-save failures without adding a deployment dependency.
    """

    def __init__(self, *, max_samples_per_series: int = 2048, now: Any | None = None) -> None:
        self.max_samples_per_series = max(32, int(max_samples_per_series))
        self._now = now or time.perf_counter
        self._lock = threading.RLock()
        self._counters: dict[tuple[str, LabelPairs], float] = defaultdict(float)
        self._histograms: dict[tuple[str, LabelPairs], deque[float]] = defaultdict(lambda: deque(maxlen=self.max_samples_per_series))

    def increment(self, name: str, value: float = 1.0, *, labels: dict[str, Any] | None = None) -> None:
        key = (str(name), _labels(labels))
        with self._lock:
            self._counters[key] += float(value)

    def observe(self, name: str, value: float, *, labels: dict[str, Any] | None = None) -> None:
        key = (str(name), _labels(labels))
        with self._lock:
            self._histograms[key].append(float(value))

    def timer(self, name: str, *, labels: dict[str, Any] | None = None) -> "MetricsTimer":
        return MetricsTimer(self, name, dict(labels or {}), now=self._now)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            counters = [
                {"name": name, "labels": dict(labels), "value": value}
                for (name, labels), value in sorted(self._counters.items(), key=lambda item: (item[0][0], item[0][1]))
            ]
            histograms = [
                _histogram_snapshot(name, labels, values)
                for (name, labels), values in sorted(self._histograms.items(), key=lambda item: (item[0][0], item[0][1]))
            ]
        return {"status": "ok", "counters": counters, "histograms": histograms}

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._histograms.clear()


class MetricsTimer:
    def __init__(self, registry: MetricsRegistry, name: str, labels: dict[str, str], *, now: Any) -> None:
        self.registry = registry
        self.name = name
        self.labels = labels
        self._now = now
        self._started_at = float(now())

    def stop(self, *, extra_labels: dict[str, Any] | None = None) -> TimerResult:
        labels = dict(self.labels)
        labels.update({str(key): str(value) for key, value in (extra_labels or {}).items()})
        elapsed_ms = round((float(self._now()) - self._started_at) * 1000.0, 3)
        self.registry.observe(self.name, elapsed_ms, labels=labels)
        return TimerResult(name=self.name, elapsed_ms=elapsed_ms, labels=labels)

    def __enter__(self) -> "MetricsTimer":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.stop(extra_labels={"outcome": "error" if exc_type else "ok"})


def _histogram_snapshot(name: str, labels: LabelPairs, values: Iterable[float]) -> dict[str, Any]:
    series = sorted(float(value) for value in values)
    count = len(series)
    return {
        "name": name,
        "labels": dict(labels),
        "count": count,
        "min": round(series[0], 3) if series else None,
        "max": round(series[-1], 3) if series else None,
        "avg": round(sum(series) / count, 3) if series else None,
        "p50": _percentile(series, 0.50),
        "p95": _percentile(series, 0.95),
        "p99": _percentile(series, 0.99),
    }


def _percentile(series: list[float], percentile: float) -> float | None:
    if not series:
        return None
    index = min(len(series) - 1, max(0, int(round((len(series) - 1) * percentile))))
    return round(series[index], 3)


def default_registry() -> MetricsRegistry:
    return DEFAULT_METRICS


DEFAULT_METRICS = MetricsRegistry()
