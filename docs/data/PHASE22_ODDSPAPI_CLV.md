# Phase 22 — OddsPapi Opening Line / CLV Integration

Phase 22 adds an optional OddsPapi enrichment layer for true opening/closing line movement.

## Environment variables

```powershell
$env:ODDSPAPI_API_KEY = "YOUR_ROTATED_KEY"
$env:ODDSPAPI_MLB_TOURNAMENT_ID = "YOUR_MLB_TOURNAMENT_ID"
$env:ODDSPAPI_BOOKMAKERS = "pinnacle,draftkings,fanduel,betmgm,caesars"
```

Do not commit API keys.

## Run

```powershell
python .\tools\run_phase22_oddspapi_clv.py --date 2026-05-07 --season 2026
python .\tools\phase22_oddspapi_clv_qa.py --date 2026-05-07 --season 2026
```

## Trust rule

Phase 22 never fabricates opening lines. It applies OddsPapi CLV only when fixture/team/market mapping is confident. Otherwise it archives raw OddsPapi responses and leaves the existing Phase 19 observed movement values intact.
