# Phase 15 — Model Quality Improvement

## Purpose

Phase 14 proved that the system can train exact market artifacts, but the expanded holdout metrics showed the models are not production-ready. Phase 15 focuses on improving model quality while preserving the non-negotiable trust rule: no silent model promotion.

## Gates this phase protects

A market should remain `experimental` or `research_only` unless all of these pass:

- Exact market-specific artifact exists.
- Feature metadata exists.
- Model is calibrated.
- Backtest has enough graded rows.
- Brier score is acceptable.
- Log-loss is acceptable.
- Training and live slate features align.

## New tools

### `tools/phase15_feature_audit.py`

Audits training feature coverage against model metadata and live Playerboard rows.

```powershell
python .\tools\phase15_feature_audit.py --markets batter_hits batter_total_bases --season 2026 --date 2026-05-07 --write
```

### `tools/phase15_build_quality_dataset.py`

Builds quality training CSVs from labeled local rows. It deduplicates player/market/date/line/outcome rows and does not fabricate labels.

```powershell
python .\tools\phase15_build_quality_dataset.py --markets batter_hits batter_total_bases --write
```

### `tools/phase15_backtest_walk_forward.py`

Runs a temporal or row-order holdout backtest against quality datasets. It can update registry backtest metadata, but it does not promote markets.

```powershell
python .\tools\phase15_backtest_walk_forward.py --markets batter_hits batter_total_bases --update-registry
```

### `tools/phase15_calibration_report.py`

Generates confidence-bucket calibration reports from Phase 15 backtest predictions.

```powershell
python .\tools\phase15_calibration_report.py --markets batter_hits batter_total_bases --write
```

### `tools/run_phase15_model_quality.py`

Runs the full controlled workflow.

```powershell
python .\tools\run_phase15_model_quality.py --markets batter_hits batter_total_bases --season 2026 --date 2026-05-07
```

## Reading the output

The most important fields are:

- `featureCoverage`: lower values mean training/live features are missing or sparse.
- `graded`: holdout rows available for backtest.
- `brierScore`: probability quality; lower is better.
- `logLoss`: confidence penalty; lower is better.
- `auc`: ranking quality; higher is better, but does not replace calibration.
- `productionEligible`: should remain false unless every gate passes.

## Expected current state

Batter hits and total bases can train, but should remain `experimental` until larger and cleaner backtests pass. Pitcher and home run markets need more positive examples before artifact training is meaningful.
