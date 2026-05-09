# Sprint 2 — Playerboard Decoupling

## Goal

Remove the production app dependency on root-level `playerboard.py` and establish a versioned Playerboard contract that all app runtime reads go through.

## Implemented Changes

- Added `mlb_app/contracts/playerboard_schema.py` with:
  - `PLAYERBOARD_SCHEMA_VERSION = "playerboard.v3"`
  - canonical `PLAYERBOARD_FIELDS`
  - required, optional, computed, and deprecated field groups
  - structured `SchemaValidationResult`
  - typed `PlayerboardSchemaError`
  - `validate_playerboard_header(...)`
  - `normalize_playerboard_row(...)`
- Added `mlb_app/contracts/schema_registry.py` with a small registry for current and known legacy Playerboard schemas.
- Added `mlb_app/repositories/playerboard_repository.py` to own Playerboard path resolution, CSV header validation, safe legacy migration, and normalized app-ready reads.
- Extracted the former root-level builder implementation into `mlb_app/services/playerboard_builder.py`.
- Reduced root `playerboard.py` to a seven-line CLI wrapper that delegates to `mlb_app.services.playerboard_builder.main`.
- Updated `PlayerboardService` to depend on the repository/contract/builder modules under `mlb_app`, not root `playerboard.py`.
- Removed root `playerboard.py` imports from app runtime code and operational callers that used builder functions.
- Added schema contract tests in `tests/test_playerboard_contract.py`.

## Verification

```bash
grep -R "from playerboard\|import playerboard" -n mlb_app
python -m pytest -q
```

Expected results:

- No root-level `playerboard.py` imports from `mlb_app`.
- Full pytest suite passes.

## Acceptance Mapping

| Roadmap Ticket | Status |
| --- | --- |
| Create playerboard contract module | Done |
| Create schema registry | Done |
| Create playerboard repository | Done |
| Extract playerboard builder service | Done |
| Reduce root `playerboard.py` to CLI wrapper | Done |
| Add schema contract tests | Done |

## Follow-up Notes

`mlb_app/services/playerboard_builder.py` intentionally preserves legacy builder behavior while moving it behind the `mlb_app` production boundary. A future cleanup pass can split the builder further into smaller collector, odds, normalization, and save modules.
