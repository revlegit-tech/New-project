# Sprint 3 — Transactional User State

Sprint 3 moves app-owned mutable user state from JSON files into SQLite WAL.
The public `/api/my-picks`, `/api/bankroll/settings`, and exposure payload shapes remain compatible with the Sprint 2 UI, but the source of truth is now `Settings.state_db_path`.

## Runtime database

`mlb_app.repositories.db.SQLiteDatabase` opens short-lived SQLite connections and applies these pragmas on every connection:

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;
```

The default path is:

```text
data/mlb_app_state.sqlite3
```

Override it with:

```bash
MLB_APP_DB_PATH=/absolute/path/to/mlb_app_state.sqlite3
```

## Migrations

Migrations live in `mlb_app/repositories/migrations/`:

- `0001_initial.sql` creates `bankroll_settings`.
- `0002_picks.sql` creates transactional `picks` with normalized query/audit columns and metadata JSON for current API compatibility.
- `0003_prediction_events.sql` creates append-only prediction audit storage.

Migration application is idempotent and tracked in `schema_migrations`.

## Repositories

- `BankrollRepository` owns `bankroll_settings`.
- `PicksRepository` owns `picks` and preserves the existing pick API contract through `metadata_json`.
- `PredictionEventsRepository` owns append-only `prediction_events`.

Services now use repositories instead of `JsonStore` for user state.

## Legacy JSON migration

`BankrollService` and `PicksService` automatically import existing JSON once when the corresponding SQLite table has no state.
After import, JSON is not read as source of truth.

Operators can run the explicit migration CLI first:

```bash
python tools/ops/migrate_user_state_to_sqlite.py --dry-run
python tools/ops/migrate_user_state_to_sqlite.py
```

## Tests

Sprint 3 coverage includes:

- WAL and migration verification.
- Bankroll repository round-trip.
- Pick create/update persistence.
- One-time JSON import with SQLite source-of-truth behavior.
- Concurrent pick writes.
- Prediction event append/list behavior.
