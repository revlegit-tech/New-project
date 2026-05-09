# Phase 21 Daily Refresh Patch

Adds:

- `tools/run_daily_refresh.py`
- `tools/phase21_freshness_report.py`
- `tools/apply_phase21_collector_alias.py`
- `tests/test_phase21_daily_refresh.py`
- `docs/data/PHASE21_DAILY_REFRESH.md`

Apply and validate:

```powershell
cd "C:\Users\RevLe\OneDrive\Documents\New project"
Expand-Archive "$env:USERPROFILE\Downloads\phase21_daily_refresh_freshness_artifacts.zip" -DestinationPath . -Force
$env:PYTHONPATH = (Get-Location).Path
python -m py_compile tools/run_daily_refresh.py tools/phase21_freshness_report.py tools/apply_phase21_collector_alias.py
python -m pytest tests/test_phase21_daily_refresh.py -q
```
