from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlb_app.config import Settings
from mlb_app.container import AppContainer
from mlb_app.repositories.player_metric_repository import PLAYER_METRIC_DATASETS
from mlb_app.repositories.statcast_repository import STATCAST_DATASETS


def main(argv: list[str] | None = None) -> int:
    datasets = sorted(set(STATCAST_DATASETS) | set(PLAYER_METRIC_DATASETS))
    parser = argparse.ArgumentParser(description="Import local Statcast/Savant daily CSV rows into the feature warehouse.")
    parser.add_argument("--dataset", choices=datasets, default="statcast_pitches")
    parser.add_argument("--source-file", required=True, help="Local CSV source file. No network calls are made.")
    parser.add_argument("--date", default="", help="Feature date in YYYY-MM-DD format.")
    parser.add_argument("--data-dir", default="", help="Override data directory.")
    parser.add_argument("--database-url", default="", help="Override DATABASE_URL and enable DB mode.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and count rows without writing.")
    parser.add_argument("--replace-csv", action="store_true", help="Replace fallback CSV for this dataset/date.")
    parser.add_argument("--skip-init", action="store_true", help="Do not run warehouse DB migrations before writing.")
    args = parser.parse_args(argv)

    settings = Settings.from_env(ROOT)
    if args.data_dir:
        settings = replace(settings, data_dir=Path(args.data_dir).resolve())
    if args.database_url:
        settings = replace(settings, database_url=args.database_url, db_enabled=True)
    elif settings.database_url and not settings.db_enabled:
        settings = replace(settings, db_enabled=True)

    container = AppContainer(settings=settings)
    if settings.db_enabled and settings.database_url and not args.dry_run and not args.skip_init:
        container.warehouse_db.initialize()

    rows = _read_csv(Path(args.source_file))
    if args.dry_run:
        print(json.dumps({"status": "ok", "dataset": args.dataset, "dry_run": True, "row_count": len(rows)}, indent=2))
        return 0

    result = container.statcast_ingestion_service.ingest_rows(
        args.dataset,
        rows,
        date_label=args.date,
        source_path=args.source_file,
        replace_csv=args.replace_csv,
    )
    print(json.dumps({"status": "ok", **result.__dict__}, indent=2))
    return 0


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    import csv

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


if __name__ == "__main__":
    raise SystemExit(main())
