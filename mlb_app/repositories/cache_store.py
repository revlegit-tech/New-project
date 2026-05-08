from __future__ import annotations

from pathlib import Path
from typing import Any

from .json_store import JsonStore


class CacheStore:
    """Compatibility wrapper around JsonStore.

    CacheStore previously used unlocked direct writes. Keeping this adapter lets
    existing services preserve their call sites while all JSON/cache writes now
    share JsonStore's per-path RLock and atomic temp-file replace behavior.
    """

    def read_json(self, path: str | Path, default: Any = None) -> Any:
        return JsonStore.for_path(path).read_any(default)

    def write_json(self, path: str | Path, payload: Any) -> None:
        JsonStore.for_path(path).write_any(payload)
