# Phase 16 — Live Feature Parity

Phase 16 enriches live Playerboard rows with real same-date features and adds audits so training metadata, live board rows, and model readiness stay aligned.

## Merge

```powershell
cd "C:\Users\RevLe\OneDrive\Documents\New project"
Expand-Archive "$env:USERPROFILE\Downloads\phase16_live_feature_parity_artifacts.zip" -DestinationPath . -Force
$env:PYTHONPATH = (Get-Location).Path
python -m py_compile tools/phase16_common.py tools/phase16_feature_contract.py tools/phase16_enrich_live_playerboard.py tools/phase16_live_feature_audit.py tools/run_phase16_live_feature_parity.py
python -m pytest tests/test_phase16_live_feature_parity.py -q
```

## Run

```powershell
python .\tools\run_phase16_live_feature_parity.py --date 2026-05-07 --season 2026 --markets batter_hits batter_total_bases
python .\tools\phase16_live_feature_audit.py --markets batter_hits batter_total_bases --season 2026 --date 2026-05-07 --write
python .\tools\validate_model_readiness.py --json
```

## Commit

```powershell
git status
git add -A
git commit -m "Add Phase 16 live feature parity workflow"
git push origin main
```
