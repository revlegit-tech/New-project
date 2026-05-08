"""Thread-safe repository for canonical game-context files.

Game context is stored separately from player prop markets and can be joined onto
Playerboard rows for hot-path reads. The repository is mtime-aware and uses
atomic writes so a daily pipeline cannot expose partial CSV/JSON files.
"""
from __future__ import annotations

import csv
import json
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


class GameContextRepository:
    def __init__(self, root: Path | str = Path("data/warehouse/game_context")) -> None:
        self.root = Path(root)
        self._lock = threading.RLock()
        self._csv_cache: Dict[Path, Tuple[float, List[Dict[str, str]]]] = {}
        self._json_cache: Dict[Path, Tuple[float, Any]] = {}

    def context_csv_path(self, date: str) -> Path:
        return self.root / f"game_context_{date}.csv"

    def markets_csv_path(self, date: str) -> Path:
        return self.root / f"game_context_markets_{date}.csv"

    def game_lines_json_path(self, date: str) -> Path:
        return self.root / f"game_lines_{date}.json"

    def read_csv_rows(self, path: Path) -> List[Dict[str, str]]:
        with self._lock:
            if not path.exists():
                return []
            mtime = path.stat().st_mtime
            cached = self._csv_cache.get(path)
            if cached and cached[0] == mtime:
                return [dict(r) for r in cached[1]]
            with path.open("r", encoding="utf-8-sig", newline="") as fh:
                rows = [dict(r) for r in csv.DictReader(fh)]
            self._csv_cache[path] = (mtime, rows)
            return [dict(r) for r in rows]

    def write_csv_rows(self, path: Path, fieldnames: Sequence[str], rows: Sequence[Dict[str, Any]]) -> None:
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=str(path.parent), delete=False, suffix=".tmp") as tmp:
                writer = csv.DictWriter(tmp, fieldnames=list(fieldnames), extrasaction="ignore")
                writer.writeheader()
                for row in rows:
                    writer.writerow({field: row.get(field, "") for field in fieldnames})
                tmp_path = Path(tmp.name)
            tmp_path.replace(path)
            self._csv_cache.pop(path, None)

    def read_json(self, path: Path) -> Optional[Any]:
        with self._lock:
            if not path.exists():
                return None
            mtime = path.stat().st_mtime
            cached = self._json_cache.get(path)
            if cached and cached[0] == mtime:
                return cached[1]
            payload = json.loads(path.read_text(encoding="utf-8"))
            self._json_cache[path] = (mtime, payload)
            return payload

    def write_json(self, path: Path, payload: Any) -> None:
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False, suffix=".tmp") as tmp:
                json.dump(payload, tmp, indent=2, sort_keys=True)
                tmp.write("\n")
                tmp_path = Path(tmp.name)
            tmp_path.replace(path)
            self._json_cache.pop(path, None)
