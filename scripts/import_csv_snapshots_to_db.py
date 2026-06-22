from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlb_app.config import Settings
from mlb_app.repositories.collector_run_repository import CollectorRunRepository
from mlb_app.repositories.edge_board_snapshot_repository import EdgeBoardSnapshotRepository
from mlb_app.repositories.playerboard_snapshot_repository import PlayerboardSnapshotRepository
from mlb_app.repositories.prop_repository import PropRepository
from mlb_app.repositories.warehouse_db import WarehouseDatabase
from mlb_app.repositories.warehouse_utils import clean, date_from_row, first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import RevLegit CSV/JSON snapshots into the optional warehouse DB.")
    parser.add_argument("--root", default=str(ROOT), help="Project root. Defaults to this repository.")
    parser.add_argument("--data-dir", default="", help="Data directory. Defaults to <root>/data or MLB_DATA_DIR.")
    parser.add_argument("--database-url", default="", help="Override DATABASE_URL for this import.")
    parser.add_argument("--season", type=int, default=0, help="Season to import. Defaults to settings current season.")
    parser.add_argument("--date", default="", help="Optional YYYY-MM-DD date filter.")
    parser.add_argument("--dry-run", action="store_true", help="Scan and print counts without writing to the DB.")
    parser.add_argument("--skip-init", action="store_true", help="Do not run warehouse migrations before importing.")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    settings = Settings.from_env(root)
    if args.data_dir:
        settings = replace(settings, data_dir=Path(args.data_dir).resolve())
    if args.database_url:
        settings = replace(settings, database_url=args.database_url, db_enabled=True)
    elif settings.database_url and not settings.db_enabled:
        settings = replace(settings, db_enabled=True)
    season = int(args.season or settings.current_season)
    data_dir = settings.data_dir

    db = WarehouseDatabase.from_settings(settings)
    repos = _Repositories(db) if not args.dry_run else None
    if args.dry_run:
        print("DRY RUN - no database writes will be performed.")
    else:
        if not db.configured:
            print("ERROR: DB import requires DB_ENABLED=1 and DATABASE_URL, or --database-url.", file=sys.stderr)
            return 2
        if not args.skip_init:
            db.initialize()

    totals: dict[str, int] = defaultdict(int)
    totals.update(_import_manifests(data_dir, repos=repos, date_filter=args.date))
    totals.update(_import_playerboards(data_dir, repos=repos, season=season, date_filter=args.date))
    totals.update(_import_edge_boards(data_dir, repos=repos, season=season, date_filter=args.date))
    totals.update(_import_odds_snapshots(data_dir, repos=repos, date_filter=args.date))

    print("Import row counts:")
    for key in sorted(totals):
        print(f"  {key}: {totals[key]}")
    return 0


class _Repositories:
    def __init__(self, db: WarehouseDatabase) -> None:
        self.collector_runs = CollectorRunRepository(db)
        self.playerboards = PlayerboardSnapshotRepository(db)
        self.edge_boards = EdgeBoardSnapshotRepository(db)
        self.props = PropRepository(db)


def _import_manifests(data_dir: Path, *, repos: _Repositories | None, date_filter: str) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    manifest_root = data_dir / "health"
    paths: list[Path] = []
    latest = manifest_root / "latest_collector_manifest.json"
    if latest.exists():
        paths.append(latest)
    collector_dir = manifest_root / "collector_manifests"
    if collector_dir.exists():
        paths.extend(sorted(collector_dir.glob("*.json")))
    else:
        print(f"Skipped missing folder: {_display_path(collector_dir)}")
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        payload = _read_json(path)
        if not isinstance(payload, dict):
            continue
        if date_filter and clean(payload.get("date")) != date_filter:
            continue
        counts["collector_manifests"] += 1
        if repos is not None:
            repos.collector_runs.upsert_manifest(payload, manifest_path=_display_path(path, data_dir=data_dir))
    return counts


def _import_playerboards(
    data_dir: Path,
    *,
    repos: _Repositories | None,
    season: int,
    date_filter: str,
) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    root = data_dir / "playerboard"
    if not root.exists():
        print(f"Skipped missing folder: {_display_path(root)}")
        return counts
    for path in sorted(root.glob("playerboard_*.csv")):
        file_season = _season_from_path(path) or season
        rows = _read_csv(path)
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        fallback_date = _date_from_path(path)
        fallback_snapshot = _file_snapshot_at(path)
        for row in rows:
            date_label = date_from_row(row, fallback_date)
            if date_filter and date_label != date_filter:
                continue
            snapshot_at = clean(first(row, "snapshotAt", "snapshot_at")) or fallback_snapshot
            grouped[(date_label, snapshot_at)].append(row)
        for (date_label, snapshot_at), group in grouped.items():
            counts["playerboard_rows"] += len(group)
            counts["playerboard_snapshots"] += 1
            if repos is not None:
                repos.playerboards.upsert_snapshot(
                    season=file_season,
                    date_label=date_label,
                    rows=group,
                    snapshot_at=snapshot_at,
                    source_path=_display_path(path, data_dir=data_dir),
                )
    return counts


def _import_edge_boards(
    data_dir: Path,
    *,
    repos: _Repositories | None,
    season: int,
    date_filter: str,
) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    root = data_dir / "edge_board"
    if not root.exists():
        print(f"Skipped missing folder: {_display_path(root)}")
        return counts
    for path in sorted([*root.glob("*.csv"), *root.glob("*.json")]):
        rows, payload = _edge_rows(path)
        date_label = clean(payload.get("date")) or _date_from_path(path)
        if date_filter and date_label != date_filter:
            continue
        file_season = int(payload.get("season") or _season_from_path(path) or season)
        snapshot_at = clean(first(payload, "snapshotAt", "generatedAt", "generated_at")) or _file_snapshot_at(path)
        counts["edge_board_rows"] += len(rows)
        counts["edge_board_snapshots"] += 1
        if repos is not None:
            repos.edge_boards.upsert_snapshot(
                season=file_season,
                date_label=date_label,
                rows=rows,
                snapshot_at=snapshot_at,
                source_path=_display_path(path, data_dir=data_dir),
            )
    return counts


def _import_odds_snapshots(data_dir: Path, *, repos: _Repositories | None, date_filter: str) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    odds_root = data_dir / "odds"
    if odds_root.exists():
        for path in sorted(odds_root.glob("*.csv")):
            rows = _filter_rows_by_date(_read_csv(path), date_filter=date_filter, fallback_date=_date_from_path(path))
            counts["prop_rows"] += len(rows)
            if repos is not None:
                repos.props.upsert_props(rows, source_path=_display_path(path, data_dir=data_dir))
    else:
        print(f"Skipped missing folder: {_display_path(odds_root)}")

    snapshot_roots = [
        data_dir / "warehouse" / "odds_snapshots",
        data_dir / "cache" / "odds_movement",
    ]
    for root in snapshot_roots:
        if not root.exists():
            print(f"Skipped missing folder: {_display_path(root)}")
            continue
        patterns = ("*.csv",) if root.name == "odds_snapshots" else ("prop_snapshots_*.csv",)
        for path in _matching(root, patterns):
            rows = _filter_rows_by_date(_read_csv(path), date_filter=date_filter, fallback_date=_date_from_path(path))
            snapshot_at = _file_snapshot_at(path)
            counts["odds_snapshot_rows"] += len(rows)
            counts["odds_snapshot_files"] += 1
            if repos is not None:
                repos.props.upsert_odds_snapshots(
                    rows,
                    snapshot_at=snapshot_at,
                    source_path=_display_path(path, data_dir=data_dir),
                )
    return counts


def _read_csv(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except OSError:
        return []


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _edge_rows(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        rows = _read_csv(path)
        return rows, {"date": _date_from_path(path), "rowCount": len(rows)}
    payload = _read_json(path)
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)], {"date": _date_from_path(path)}
    if isinstance(payload, dict):
        rows = payload.get("rows")
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else [], payload
    return [], {"date": _date_from_path(path)}


def _filter_rows_by_date(rows: Iterable[Mapping[str, Any]], *, date_filter: str, fallback_date: str) -> list[dict[str, Any]]:
    result = []
    for raw in rows:
        row = dict(raw)
        date_label = date_from_row(row, fallback_date)
        if date_label:
            row.setdefault("date", date_label)
        if date_filter and date_label != date_filter:
            continue
        result.append(row)
    return result


def _matching(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    files: dict[Path, None] = {}
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file():
                files[path] = None
    return sorted(files)


def _date_from_path(path: Path) -> str:
    match = re.search(r"(20\d{2}-\d{2}-\d{2})", path.name)
    return match.group(1) if match else ""


def _season_from_path(path: Path) -> int:
    match = re.search(r"(20\d{2})", path.name)
    return int(match.group(1)) if match else 0


def _file_snapshot_at(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except OSError:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _display_path(path: Path, *, data_dir: Path | None = None) -> str:
    if data_dir is not None:
        try:
            return str(Path("data") / path.resolve().relative_to(data_dir.resolve())).replace("\\", "/")
        except (OSError, ValueError):
            pass
    try:
        return str(path.resolve().relative_to(ROOT)).replace("\\", "/")
    except (OSError, ValueError):
        return str(path).replace("\\", "/")


if __name__ == "__main__":
    raise SystemExit(main())
