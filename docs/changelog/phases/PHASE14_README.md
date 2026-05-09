# Phase 14 — Training Data Expansion and Backtest Promotion

Phase 14 turns the Phase 13 experimental model artifacts into a controlled promotion workflow.

The goal is not to mark models as production-ready prematurely. The goal is to:

1. measure which markets have enough two-class training data,
2. build expanded training CSVs only from labeled/graded rows,
3. backtest market-specific artifacts on held-out rows,
4. update the registry with audited backtest metrics, and
5. promote only markets that pass hard gates.

## Main commands

```powershell
cd "C:\Users\RevLe\OneDrive\Documents\New project"
$env:PYTHONPATH = (Get-Location).Path

python .\tools\phase14_market_gap_report.py --json
python .\tools\phase14_expand_training_data.py --markets batter_hits batter_total_bases batter_home_runs pitcher_strikeouts pitcher_hits_allowed pitcher_earned_runs --write
python .\tools\train_market_models.py --markets batter_hits batter_total_bases --calibrate
python .\tools\phase14_backtest_market_artifacts.py --markets batter_hits batter_total_bases --update-registry
python .\tools\phase14_promote_market_models.py --markets batter_hits batter_total_bases --write
python .\tools\validate_model_readiness.py --json
```

## Safety rule

A model can only be promoted when it has:

- exact market artifact,
- exact feature metadata,
- calibrated flag,
- at least 100 graded backtest rows,
- Brier score <= 0.25,
- log loss <= 0.75,
- and two-class training data.

If those are not true, the market remains `experimental` or `research_only`.
