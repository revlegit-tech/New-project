# Phase 21 — Production Collector Automation + Freshness Hardening

Phase 21 adds one operator command for the daily refresh and a freshness report
that checks whether the files needed by the new `mlb_app` Outlier UI exist and
contain context coverage.

## Main command

```powershell
cd "C:\Users\RevLe\OneDrive\Documents\New project"
$env:PYTHONPATH = (Get-Location).Path

python .\tools\run_daily_refresh.py --date 2026-05-07 --season 2026 --run-type morning
```

`--run-type scheduled` is accepted by the wrapper and maps by local clock:

- 00:00-10:59 -> `morning`
- 11:00-17:59 -> `midday`
- 18:00-23:59 -> `midnight`

## Existing collector compatibility

The collector itself currently supports:

```text
morning, midday, midnight, manual, grading
```

Run this optional patch if you also want the direct collector command to accept
`--run-type scheduled` as an alias for `morning`:

```powershell
python .\tools\apply_phase21_collector_alias.py
```

## Freshness-only QA

```powershell
python .\tools\phase21_freshness_report.py --date 2026-05-07 --season 2026 --write
```

This writes:

```text
data/warehouse/audits/phase21_freshness_2026-05-07.json
```

## Trust rules

- Do not fabricate opening lines or line movement.
- Current moneyline/game total/weather comes from PropLine/Open-Meteo/local references.
- Opening-line movement stays `pending_or_single_snapshot` until multiple observed snapshots or an opening-line provider exist.
- OddsPapi is optional for Phase 21 and mainly improves true opening/CLV support later.
