# Phase 21 v2 — Freshness Alias Cleanup

Phase 21 v2 cleans up the daily freshness report.

## Fixes

- Treats `americanOdds` as `american_odds`.
- Treats `bookCount` as `sportsbook_count`.
- Treats `book` as `best_book`.
- Treats camelCase context fields as aliases for snake_case context fields.
- Stops showing the Phase 21 daily report as `optional_missing` before the wrapper has written it.
- Separates canonical game-context coverage from core Playerboard prop coverage.

## Apply

```powershell
cd "C:\Users\RevLe\OneDrive\Documents\New project"

Expand-Archive "$env:USERPROFILE\Downloads\phase21_v2_freshness_alias_cleanup_artifacts.zip" -DestinationPath . -Force

$env:PYTHONPATH = (Get-Location).Path
python .\tools\apply_phase21_v2_freshness_alias_cleanup.py

python -m py_compile tools/phase21_freshness_report.py tools/apply_phase21_v2_freshness_alias_cleanup.py
python -m pytest tests/test_phase21_v2_freshness_alias_cleanup.py -q
```

## QA

```powershell
$Date = "2026-05-07"

python .\tools\phase21_freshness_report.py --date $Date --season 2026 --write
```

The report should show `playerboardCoreCoverage` with non-zero coverage for odds/book fields if the rows contain `americanOdds`, `bookCount`, and `book`.
