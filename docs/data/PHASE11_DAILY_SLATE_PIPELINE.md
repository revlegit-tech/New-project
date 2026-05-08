# Phase 11 — Daily Slate Data Pipeline

Phase 11 makes the retired `mlb_app` runtime usable day to day by turning slate refresh into a repeatable, auditable pipeline.

The pipeline is intentionally conservative:

- it prefers canonical `data/odds/propline_props_<date>.csv` for the selected slate;
- it rebuilds Playerboard for the exact date and replaces old rows for that date;
- it records pipeline output in `data/health/pipeline_runs/`;
- it runs post-refresh validation instead of silently trusting stale files;
- it keeps optional enrichment failures visible as warnings rather than hiding them behind fallback UI.

## Normal local command

```powershell
cd "C:\Users\RevLe\OneDrive\Documents\New project"
$env:PYTHONPATH = (Get-Location).Path
$Date = "2026-05-07"

python .\tools\run_daily_slate_pipeline.py --date $Date --season 2026 --limit 500 --source-mode canonical
```

Then open:

```text
http://127.0.0.1:8765/?view=outlier
```

## Fast board-only rebuild

Use this after you already fetched PropLine and only need to rebuild Playerboard:

```powershell
python .\tools\run_daily_slate_pipeline.py --date $Date --season 2026 --skip-fetch --skip-schedule --skip-weather --skip-odds-movement
```

## Full enrichment run

Stats catchup can take longer, so it is opt-in:

```powershell
python .\tools\run_daily_slate_pipeline.py `
  --date $Date `
  --season 2026 `
  --include-stats-catchup `
  --stats-start-date 2026-05-01 `
  --stats-end-date 2026-05-06 `
  --max-stats-dates 7
```

## Validate a slate

```powershell
python .\tools\validate_daily_slate.py --date $Date --season 2026
```

Validation checks:

- canonical PropLine file exists and has rows;
- Playerboard has rows for the selected date;
- sportsbook duplicates were merged into single prop rows;
- hit-rate and recent-game payloads exist where available;
- warnings remain explicit for missing enrichment.

## Output artifact

Each run writes:

```text
data/health/pipeline_runs/daily_slate_<date>.json
```

That JSON includes each step command, return code, stdout/stderr tail, data-health payload, and slate validation result.

## Trust-surface rule

Do not patch the UI to hide missing data. If schedule, weather, odds movement, game logs, or grading are absent, the UI should keep displaying `Research Only`, `Missing Data`, or explicit warnings until the pipeline produces those files.
