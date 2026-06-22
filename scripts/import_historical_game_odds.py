from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlb_app.config import Settings
from mlb_app.repositories.historical_game_odds_repository import HistoricalGameOddsRepository
from mlb_app.repositories.warehouse_db import WarehouseDatabase
from mlb_app.services.historical_game_odds_import_service import HistoricalGameOddsImportService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import historical MLB game odds into the optional warehouse DB.")
    parser.add_argument("--root", default=str(ROOT), help="Project root. Defaults to this repository.")
    parser.add_argument("--data-dir", default="", help="Data directory. Defaults to <root>/data or MLB_DATA_DIR.")
    parser.add_argument("--database-url", default="", help="Override DATABASE_URL for this import.")
    parser.add_argument("--source-file", default="", help="Source JSON. Defaults to data/external/mlb_odds_dataset.json.")
    parser.add_argument("--export-csv", action="store_true", help="Also write CSV/debug snapshots under data/warehouse/historical_game_odds.")
    parser.add_argument("--skip-init", action="store_true", help="Do not run warehouse migrations before importing.")
    args = parser.parse_args(argv)

    settings = Settings.from_env(Path(args.root).resolve())
    if args.data_dir:
        settings = replace(settings, data_dir=Path(args.data_dir).resolve())
    if args.database_url:
        settings = replace(settings, database_url=args.database_url, db_enabled=True)
    elif settings.database_url and not settings.db_enabled:
        settings = replace(settings, db_enabled=True)

    if not settings.db_enabled or not settings.database_url:
        print("ERROR: historical game odds import requires DB_ENABLED=1 and DATABASE_URL, or --database-url.", file=sys.stderr)
        return 2

    db = WarehouseDatabase.from_settings(settings)
    repository = HistoricalGameOddsRepository(db, settings=settings)
    service = HistoricalGameOddsImportService(repository, settings=settings)
    result = service.import_file(
        source_file=args.source_file or None,
        export_csv=args.export_csv,
        initialize_schema=not args.skip_init,
    )
    payload = result.to_payload()
    print(f"Import status: {payload['importStatus']}")
    print(f"Import id: {payload['importId']}")
    print(f"Games imported: {payload['gamesImported']}")
    print(f"Line rows imported: {payload['lineRowsImported']}")
    print(f"Feature rows written: {payload['featureRowsWritten']}")
    print(f"Grade rows written: {payload['gradeRowsWritten']}")
    for warning in payload["warnings"]:
        print(f"WARNING: {warning}", file=sys.stderr)
    for error in payload["errors"]:
        print(f"ERROR: {error}", file=sys.stderr)
    return 0 if result.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
