# Sprint 13 Database Foundation

Sprint 13 adds an optional warehouse database for historical MLB collector, prop, playerboard, edge-board, report, grade, and audit data. CSV remains the default local source and recovery fallback.

## Runtime Settings

- `DB_ENABLED=0` by default. Set to `1` to attempt DB-first reads.
- `DB_FALLBACK_TO_CSV=1` by default. CSV/current flows remain available if the DB is empty or unavailable.
- `DATABASE_URL=` is optional locally. Use a PostgreSQL URL in production, or a SQLite URL for local import/testing.
- `DATABASE_POOL_SIZE=5` and `DATABASE_ECHO=0` are parsed for production DB clients and diagnostics.

## Migration

Migration SQL lives in:

- `mlb_app/db/migrations/postgresql/0001_sprint13_foundation.sql`
- `mlb_app/db/migrations/sqlite/0001_sprint13_foundation.sql`

The import command runs migrations by default unless `--skip-init` is passed:

```powershell
$env:DB_ENABLED = "1"
$env:DATABASE_URL = "postgresql://user:password@host:5432/revlegit"
python scripts/import_csv_snapshots_to_db.py --data-dir data
```

For a local SQLite dry run or smoke import:

```powershell
python scripts/import_csv_snapshots_to_db.py --data-dir data --dry-run
python scripts/import_csv_snapshots_to_db.py --database-url "sqlite:///C:/tmp/revlegit_warehouse.sqlite3" --data-dir data
```

## Tables

The initial schema creates:

- `collector_runs`
- `data_manifests`
- `players`
- `teams`
- `games`
- `props`
- `odds_snapshots`
- `playerboard_snapshots`
- `edge_board_snapshots`
- `research_reports`
- `model_grades`
- `audit_events`

Core indexes cover date, market, player, latest snapshot lookup, and report lookup. JSON payloads are stored as text for portable imports across SQLite and PostgreSQL.

## Import Coverage

`scripts/import_csv_snapshots_to_db.py` imports:

- collector manifests from `data/health/latest_collector_manifest.json` and `data/health/collector_manifests/*.json`
- playerboard CSV snapshots from `data/playerboard/playerboard_*.csv`
- edge-board CSV/JSON snapshots from `data/edge_board/*`
- props from `data/odds/*.csv`
- odds snapshots from `data/warehouse/odds_snapshots/*.csv` and `data/cache/odds_movement/prop_snapshots_*.csv`

The importer is idempotent, prints row counts, skips missing folders, and never deletes CSV files.
