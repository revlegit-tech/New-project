from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from mlb_app.repositories.cache_store import CacheStore
from mlb_app.repositories.json_store import JsonStore


def test_cache_store_uses_json_store_atomic_write_path(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    cache = CacheStore()

    cache.write_json(path, {"status": "ok", "rows": [1, 2, 3]})

    assert cache.read_json(path) == {"status": "ok", "rows": [1, 2, 3]}
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "ok"
    assert not list(tmp_path.glob("tmp*"))


def test_json_store_concurrent_writes_never_leave_partial_json(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    cache = CacheStore()

    def write_one(index: int) -> None:
        cache.write_json(path, {"index": index, "payload": [index] * 25})
        loaded = cache.read_json(path)
        assert isinstance(loaded, dict)
        assert "index" in loaded

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(write_one, range(50)))

    final_payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(final_payload, dict)
    assert "index" in final_payload


def test_json_store_strict_read_errors_surface_corruption(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setenv("MLB_DEV_MODE", "1")

    with pytest.raises(ValueError, match="Failed to read JSON store"):
        JsonStore(path).read()


def test_json_store_non_strict_corruption_returns_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.delenv("MLB_DEV_MODE", raising=False)
    monkeypatch.delenv("MLB_STRICT_JSON_READS", raising=False)

    assert JsonStore(path, default={"safe": True}).read() == {"safe": True}
