from __future__ import annotations

import os
from pathlib import Path

from mlb_app.repositories.csv_store import CsvStore


def _write(path: Path, text: str, *, mtime_ns: int) -> None:
    path.write_text(text, encoding="utf-8")
    os.utime(path, ns=(mtime_ns, mtime_ns))


def test_csv_store_reuses_rows_within_ttl_and_protects_cache_from_mutation(tmp_path: Path) -> None:
    now = [100.0]
    path = tmp_path / "board.csv"
    _write(path, "player,edge\nA,4.2\n", mtime_ns=1_000_000_000)
    CsvStore.invalidate()
    store = CsvStore(now=lambda: now[0])

    first = store.read_rows_cached(path, max_age_seconds=60)
    first[0]["player"] = "MUTATED"
    second = store.read_rows_cached(path, max_age_seconds=60)

    assert second == [{"player": "A", "edge": "4.2"}]
    assert CsvStore.status()["hits"] >= 1


def test_csv_store_invalidates_when_mtime_or_size_changes(tmp_path: Path) -> None:
    now = [100.0]
    path = tmp_path / "board.csv"
    _write(path, "player,edge\nA,4.2\n", mtime_ns=1_000_000_000)
    CsvStore.invalidate()
    store = CsvStore(now=lambda: now[0])

    assert store.read_rows_cached(path, max_age_seconds=60)[0]["edge"] == "4.2"

    _write(path, "player,edge\nA,8.4\n", mtime_ns=2_000_000_000)
    assert store.read_rows_cached(path, max_age_seconds=60)[0]["edge"] == "8.4"


def test_csv_store_invalidates_when_ttl_expires_even_if_signature_unchanged(tmp_path: Path) -> None:
    now = [100.0]
    path = tmp_path / "board.csv"
    _write(path, "player,edge\nA,4.2\n", mtime_ns=1_000_000_000)
    CsvStore.invalidate()
    store = CsvStore(now=lambda: now[0])

    assert store.read_rows_cached(path, max_age_seconds=5)[0]["edge"] == "4.2"

    # Keep the same size and mtime signature to prove TTL can still force a refresh.
    _write(path, "player,edge\nA,9.9\n", mtime_ns=1_000_000_000)
    now[0] = 106.0
    assert store.read_rows_cached(path, max_age_seconds=5)[0]["edge"] == "9.9"


def test_csv_store_count_rows_uses_cached_reader(tmp_path: Path) -> None:
    path = tmp_path / "rows.csv"
    _write(path, "id\n1\n2\n3\n", mtime_ns=1_000_000_000)
    CsvStore.invalidate()
    store = CsvStore()

    assert store.count_rows(path) == 3
    assert store.count_rows(path) == 3
    assert CsvStore.status()["hits"] >= 1


def test_csv_store_write_rows_is_atomic_and_invalidates_cache(tmp_path: Path) -> None:
    path = tmp_path / "rows.csv"
    _write(path, "id,value\n1,old\n", mtime_ns=1_000_000_000)
    CsvStore.invalidate()
    store = CsvStore()

    assert store.read_rows_cached(path)[0]["value"] == "old"

    store.write_rows(path, [{"id": "1", "value": "new"}], ["id", "value"])

    assert store.read_rows_cached(path)[0]["value"] == "new"
    assert not list(tmp_path.glob(".*.tmp"))
