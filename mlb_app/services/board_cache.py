from __future__ import annotations

import copy
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Hashable, Iterable

from mlb_app.observability.metrics import MetricsRegistry

DependencyPath = str | Path
BoardBuilder = Callable[[], dict[str, Any]]


@dataclass(frozen=True)
class FileSignature:
    """Stable source-file fingerprint used for mtime-aware invalidation."""

    path: str
    exists: bool
    mtime_ns: int | None
    size: int | None

    @classmethod
    def from_path(cls, path: DependencyPath) -> "FileSignature":
        target = Path(path).resolve()
        try:
            stat = target.stat()
        except OSError:
            return cls(path=str(target), exists=False, mtime_ns=None, size=None)
        return cls(path=str(target), exists=True, mtime_ns=stat.st_mtime_ns, size=stat.st_size)


@dataclass
class BoardCacheEntry:
    payload: dict[str, Any]
    created_at: float
    ttl_seconds: float
    signatures: tuple[FileSignature, ...]
    hits: int = 0
    last_hit_at: float | None = None

    def age_seconds(self, now: float | None = None) -> float:
        return max(0.0, (now if now is not None else time.monotonic()) - self.created_at)

    def ttl_remaining_seconds(self, now: float | None = None) -> float:
        return max(0.0, self.ttl_seconds - self.age_seconds(now))


@dataclass(frozen=True)
class BoardCacheBuildResult:
    """Result returned by get_or_build so services can expose cache truthfully."""

    payload: dict[str, Any]
    hit: bool
    reason: str
    key: Hashable
    age_seconds: float
    ttl_remaining_seconds: float
    signatures: tuple[FileSignature, ...] = field(default_factory=tuple)


class BoardCache:
    """Thread-safe, TTL and mtime-aware cache for hot EdgeBoard payloads.

    The cache is intentionally process-local. Under Gunicorn each worker owns its
    own cache, which is fine for low-latency read paths because the dependency
    signatures make worker-local entries self-invalidating when pipeline files
    are updated on disk.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float = 30.0,
        max_keys: int = 256,
        now: Callable[[], float] | None = None,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self.ttl_seconds = float(ttl_seconds)
        self.max_keys = max(1, int(max_keys))
        self._now = now or time.monotonic
        self._metrics = metrics
        self._lock = threading.RLock()
        self._key_locks: dict[Hashable, threading.RLock] = {}
        self._entries: dict[Hashable, BoardCacheEntry] = {}
        self._hits = 0
        self._misses = 0
        self._sets = 0
        self._builds = 0
        self._invalidations = 0
        self._evictions = 0
        with self._lock:
            self._emit_cache_size_metrics_locked()

    def get(self, key: Hashable, *, dependency_paths: Iterable[DependencyPath] = ()) -> BoardCacheBuildResult | None:
        """Return a cached payload if TTL and dependency signatures are still valid."""

        signatures = self._signatures(dependency_paths)
        now = self._now()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                self._increment_metric("board_cache_misses_total")
                self._emit_cache_size_metrics_locked()
                return None
            if entry.age_seconds(now) > entry.ttl_seconds:
                self._entries.pop(key, None)
                self._key_locks.pop(key, None)
                self._misses += 1
                self._invalidations += 1
                self._increment_metric("board_cache_misses_total")
                self._emit_cache_size_metrics_locked()
                return None
            if entry.signatures != signatures:
                self._entries.pop(key, None)
                self._key_locks.pop(key, None)
                self._misses += 1
                self._invalidations += 1
                self._increment_metric("board_cache_misses_total")
                self._emit_cache_size_metrics_locked()
                return None
            entry.hits += 1
            entry.last_hit_at = now
            self._hits += 1
            self._increment_metric("board_cache_hits_total")
            self._emit_cache_size_metrics_locked()
            return BoardCacheBuildResult(
                payload=copy.deepcopy(entry.payload),
                hit=True,
                reason="hit",
                key=key,
                age_seconds=entry.age_seconds(now),
                ttl_remaining_seconds=entry.ttl_remaining_seconds(now),
                signatures=entry.signatures,
            )

    def set(
        self,
        key: Hashable,
        payload: dict[str, Any],
        *,
        dependency_paths: Iterable[DependencyPath] = (),
        ttl_seconds: float | None = None,
    ) -> BoardCacheBuildResult:
        """Store a payload with the current source-file signatures."""

        signatures = self._signatures(dependency_paths)
        ttl = float(self.ttl_seconds if ttl_seconds is None else ttl_seconds)
        now = self._now()
        entry = BoardCacheEntry(
            payload=copy.deepcopy(payload),
            created_at=now,
            ttl_seconds=ttl,
            signatures=signatures,
        )
        with self._lock:
            self._entries[key] = entry
            self._sets += 1
            self._evict_overflow_locked()
            self._emit_cache_size_metrics_locked()
        return BoardCacheBuildResult(
            payload=copy.deepcopy(payload),
            hit=False,
            reason="miss_build",
            key=key,
            age_seconds=0.0,
            ttl_remaining_seconds=ttl,
            signatures=signatures,
        )

    def get_or_build(
        self,
        key: Hashable,
        builder: BoardBuilder,
        *,
        dependency_paths: Iterable[DependencyPath] = (),
        ttl_seconds: float | None = None,
    ) -> BoardCacheBuildResult:
        """Return a valid cached payload or build/store exactly once per key."""

        dependency_paths = tuple(dependency_paths)
        cached = self.get(key, dependency_paths=dependency_paths)
        if cached is not None:
            return cached

        key_lock = self._key_lock_for(key)
        with key_lock:
            # Another request may have built the same key while this request was
            # waiting on the per-key lock. Re-check before doing expensive work.
            cached = self.get(key, dependency_paths=dependency_paths)
            if cached is not None:
                return cached
            payload = builder()
            if not isinstance(payload, dict):
                raise TypeError("BoardCache builder must return a dict payload")
            with self._lock:
                self._builds += 1
            return self.set(key, payload, dependency_paths=dependency_paths, ttl_seconds=ttl_seconds)

    def invalidate(self, key: Hashable | None = None) -> None:
        """Clear one cache key, or the whole cache when key is omitted."""

        with self._lock:
            if key is None:
                removed = len(self._entries)
                self._entries.clear()
                self._key_locks.clear()
            else:
                removed = 1 if key in self._entries else 0
                self._entries.pop(key, None)
                self._key_locks.pop(key, None)
            self._invalidations += removed
            self._emit_cache_size_metrics_locked()

    def status(self) -> dict[str, Any]:
        """Return dev/debug-safe cache state without embedding full payloads."""

        now = self._now()
        with self._lock:
            entries = []
            for key, entry in self._entries.items():
                entries.append(
                    {
                        "key": repr(key),
                        "ageSeconds": round(entry.age_seconds(now), 3),
                        "ttlRemainingSeconds": round(entry.ttl_remaining_seconds(now), 3),
                        "hitCount": entry.hits,
                        "lastHitAgeSeconds": None
                        if entry.last_hit_at is None
                        else round(max(0.0, now - entry.last_hit_at), 3),
                        "dependencyCount": len(entry.signatures),
                        "dependencies": [
                            {
                                "path": signature.path,
                                "exists": signature.exists,
                                "mtimeNs": signature.mtime_ns,
                                "size": signature.size,
                            }
                            for signature in entry.signatures
                        ],
                    }
                )
            return {
                "ttlSeconds": self.ttl_seconds,
                "maxKeys": self.max_keys,
                "entryCount": len(self._entries),
                "keyLockCount": len(self._key_locks),
                "hits": self._hits,
                "misses": self._misses,
                "sets": self._sets,
                "builds": self._builds,
                "invalidations": self._invalidations,
                "evictions": self._evictions,
                "entries": entries,
            }

    def _key_lock_for(self, key: Hashable) -> threading.RLock:
        with self._lock:
            lock = self._key_locks.get(key)
            if lock is None:
                lock = threading.RLock()
                self._key_locks[key] = lock
            return lock

    def _evict_overflow_locked(self) -> None:
        while len(self._entries) > self.max_keys:
            victim_key = min(
                self._entries,
                key=lambda key: (
                    self._entries[key].last_hit_at or self._entries[key].created_at,
                    self._entries[key].created_at,
                ),
            )
            self._entries.pop(victim_key, None)
            self._key_locks.pop(victim_key, None)
            self._evictions += 1
            self._increment_metric("board_cache_evictions_total")

    def _emit_cache_size_metrics_locked(self) -> None:
        if self._metrics is None:
            return
        self._metrics.set("board_cache_entries", len(self._entries))
        self._metrics.set("board_cache_key_locks", len(self._key_locks))

    def _increment_metric(self, name: str, value: float = 1.0) -> None:
        if self._metrics is None:
            return
        self._metrics.increment(name, value)

    @staticmethod
    def _signatures(paths: Iterable[DependencyPath]) -> tuple[FileSignature, ...]:
        return tuple(FileSignature.from_path(path) for path in sorted({str(Path(path).resolve()) for path in paths}))
