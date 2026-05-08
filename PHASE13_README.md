# Phase 13 — Model Readiness and Market Artifacts

Phase 13 makes model readiness auditable before any market can leave Research Only.

## New commands

Train/audit market-specific artifacts:

```powershell
$env:PYTHONPATH = (Get-Location).Path
python .\tools\train_market_models.py --markets batter_hits batter_total_bases batter_home_runs pitcher_strikeouts --calibrate
```

Validate trust gates:

```powershell
python .\tools\validate_model_readiness.py --json
```

Write an audit snapshot:

```powershell
python .\tools\audit_model_registry.py
```

## Production gate

A market is production eligible only when all of these are true:

- exact market-specific artifact exists
- feature metadata exists
- training rows meet minimum threshold
- training data has both classes
- calibration is verified
- registry status is `production_candidate` or `production`
- backtest gate clears minimum rows and quality thresholds

Generic fallback remains disabled for the trust surface.
