from __future__ import annotations

import copy
import csv
import os
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable


@dataclass(frozen=True)
class CsvFileSignature:
    """Stable file identity used for mtime-aware CSV cache invalidation."""

    path: str
    exists: bool
    mtime_ns: int | None = None
    size: int | None = None

    @classmethod
    def from_path(cls, path: str | Path) -> "CsvFileSignature":
        target = Path(path).resolve()
        try:
            stat = target.stat()
        except OSError:
            return cls(path=str(target), exists=False)
        return cls(path=str(target), exists=True, mtime_ns=stat.st_mtime_ns, size=stat.st_size)


@dataclass
class _CsvCacheEntry:
    rows: list[dict[str, str]]
    signature: CsvFileSignature
    loaded_at: float
    max_age_seconds: float
    hits: int = 0
    last_hit_at: float | None = None

    def age_seconds(self, now: float) -> float:
        return max(0.0, now - self.loaded_at)

    def ttl_remaining_seconds(self, now: float) -> float:
        return max(0.0, self.max_age_seconds - self.age_seconds(now))


class CsvStore:
    """CSV repository with process-local, mtime-aware read caching.

    CSV files are the platform's operational database until a real database is
    introduced. This store therefore treats read caching and safe writes as
    production concerns:

    * cache keys are resolved paths;
    * cache entries are invalidated by TTL or (mtime_ns, size) changes;
    * cache state is protected by a class-level RLock;
    * callers receive deep copies so row mutation cannot corrupt hot cache data;
    * writes go through a temp file plus atomic os.replace().
    """

    _cache: dict[str, _CsvCacheEntry] = {}
    _lock = threading.RLock()
    _hits = 0
    _misses = 0
    _invalidations = 0
    _writes = 0

    def __init__(self, *, now: Callable[[], float] | None = None) -> None:
        self._now = now or time.monotonic

    def read_rows(self, path: str | Path) -> list[dict[str, str]]:
        """Compatibility wrapper.

        Existing services can keep calling read_rows() and still benefit from
        the default mtime-aware cache. Newer hot paths may call read_rows_cached()
        directly to make the TTL explicit.
        """

        return self.read_rows_cached(path)

    def read_rows_uncached(self, path: str | Path) -> list[dict[str, str]]:
        """Read directly from disk without consulting or updating the cache."""

        return self._read_rows_from_disk(Path(path).resolve())

    def read_rows_cached(self, path: str | Path, max_age_seconds: float = 60.0) -> list[dict[str, str]]:
        target = Path(path).resolve()
        key = str(target)
        signature = CsvFileSignature.from_path(target)
        now = self._now()

        with self._lock:
            entry = self._cache.get(key)
            if entry is not None:
                stale_by_ttl = entry.age_seconds(now) > entry.max_age_seconds
                stale_by_mtime = entry.signature != signature
                stale_by_policy = float(max_age_seconds) != entry.max_age_seconds
                if not stale_by_ttl and not stale_by_mtime and not stale_by_policy:
                    entry.hits += 1
                    entry.last_hit_at = now
                    type(self)._hits += 1
                    return copy.deepcopy(entry.rows)
                self._cache.pop(key, None)
                type(self)._invalidations += 1

        rows = self._read_rows_from_disk(target)
        entry = _CsvCacheEntry(
            rows=copy.deepcopy(rows),
            signature=signature,
            loaded_at=now,
            max_age_seconds=float(max_age_seconds),
        )
        with self._lock:
            self._cache[key] = entry
            type(self)._misses += 1
        return copy.deepcopy(rows)

    def count_rows(self, path: str | Path, *, max_age_seconds: float = 60.0) -> int:
        return len(self.read_rows_cached(path, max_age_seconds=max_age_seconds))

    def write_rows(self, path: str | Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
        target = Path(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow({field: row.get(field, "") for field in fieldnames})
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, target)
        except Exception:
            try:
                tmp_path.unlink(missing_ok=True)
            finally:
                raise

        with self._lock:
            self._cache.pop(str(target), None)
            type(self)._writes += 1
            type(self)._invalidations += 1

    @classmethod
    def invalidate(cls, path: str | Path | None = None) -> None:
        with cls._lock:
            if path is None:
                removed = len(cls._cache)
                cls._cache.clear()
            else:
                removed = 1 if str(Path(path).resolve()) in cls._cache else 0
                cls._cache.pop(str(Path(path).resolve()), None)
            cls._invalidations += removed

    @classmethod
    def status(cls) -> dict[str, Any]:
        now = time.monotonic()
        with cls._lock:
            entries = []
            for key, entry in cls._cache.items():
                entries.append(
                    {
                        "path": key,
                        "rows": len(entry.rows),
                        "exists": entry.signature.exists,
                        "mtimeNs": entry.signature.mtime_ns,
                        "size": entry.signature.size,
                        "ageSeconds": round(entry.age_seconds(now), 3),
                        "ttlRemainingSeconds": round(entry.ttl_remaining_seconds(now), 3),
                        "hits": entry.hits,
                    }
                )
            return {
                "entries": entries,
                "entryCount": len(entries),
                "hits": cls._hits,
                "misses": cls._misses,
                "invalidations": cls._invalidations,
                "writes": cls._writes,
            }

    @staticmethod
    def _read_rows_from_disk(path: Path) -> list[dict[str, str]]:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
