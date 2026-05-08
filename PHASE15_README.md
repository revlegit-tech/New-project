# Phase 15 — Model Quality Improvement

Phase 15 keeps the trust surface honest by improving model quality without force-promoting weak markets.

The key additions are:

- Feature coverage audit for training/live slate alignment.
- Quality dataset builder that deduplicates labeled rows and rejects unlabeled rows.
- Walk-forward/holdout backtest that evaluates generalization instead of relying on optimistic in-sample metrics.
- Calibration report for model confidence buckets.
- One-command Phase 15 runner.

## Recommended workflow

```powershell
cd "C:\Users\RevLe\OneDrive\Documents\New project"
$env:PYTHONPATH = (Get-Location).Path

python .\tools\run_phase15_model_quality.py --markets batter_hits batter_total_bases --season 2026 --date 2026-05-07
python .\tools\phase15_feature_audit.py --markets batter_hits batter_total_bases --season 2026 --date 2026-05-07 --write
python .\tools\phase15_build_quality_dataset.py --markets batter_hits batter_total_bases --write
python .\tools\phase15_backtest_walk_forward.py --markets batter_hits batter_total_bases --update-registry
python .\tools\phase15_calibration_report.py --markets batter_hits batter_total_bases --write
python .\tools\validate_model_readiness.py --json
```

Do not promote markets unless readiness gates pass. The expected current state is still `experimental` for batter markets until backtests are strong and large enough.
