from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable


def _strict_json_reads_enabled() -> bool:
    value = os.environ.get("MLB_STRICT_JSON_READS") or os.environ.get("MLB_DEV_MODE") or ""
    return value.strip().lower() in {"1", "true", "yes", "on"}


class JsonStore:
    """Thread-safe, atomic JSON file store for local app state and caches."""

    _locks: dict[Path, threading.RLock] = {}
    _locks_guard = threading.Lock()

    def __init__(self, path: Path | str, *, default: dict[str, Any] | None = None) -> None:
        self.path = Path(path)
        self.default = default or {}
        with self._locks_guard:
            self._lock = self._locks.setdefault(self.path.resolve(), threading.RLock())

    @classmethod
    def for_path(cls, path: Path | str) -> "JsonStore":
        return cls(path)

    def _handle_read_error(self, error: Exception, default: Any) -> Any:
        if _strict_json_reads_enabled():
            raise ValueError(f"Failed to read JSON store {self.path}: {error}") from error
        return default

    def read_any(self, default: Any = None) -> Any:
        with self._lock:
            if not self.path.exists():
                return default
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                return self._handle_read_error(error, default)

    def read(self) -> dict[str, Any]:
        payload = self.read_any(dict(self.default))
        if isinstance(payload, dict):
            return payload
        if _strict_json_reads_enabled():
            raise ValueError(f"JSON store {self.path} expected object payload, got {type(payload).__name__}")
        return dict(self.default)

    def write_any(self, payload: Any) -> Any:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, delete=False) as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                    temp_path = Path(handle.name)
                os.replace(temp_path, self.path)
            finally:
                if temp_path is not None and temp_path.exists():
                    try:
                        temp_path.unlink()
                    except OSError:
                        pass
            return payload

    def write(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise TypeError("JsonStore.write expects a dictionary")
        self.write_any(payload)
        return payload

    def update(self, mutator: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        with self._lock:
            next_payload = mutator(self.read())
            if not isinstance(next_payload, dict):
                raise TypeError("JsonStore mutator must return a dictionary")
            return self.write(next_payload)
