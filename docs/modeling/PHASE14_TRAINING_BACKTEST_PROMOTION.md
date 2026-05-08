# Phase 14 — Training Data Expansion and Backtest Promotion

Phase 13 created readiness gates and trained experimental artifacts for markets that had usable two-class training data. Phase 14 adds the promotion workflow.

## Why this exists

The app should never silently treat a market as production-ready just because a model file exists. A model file is only one requirement. We also need enough graded examples and acceptable backtest metrics.

## Scripts

### `tools/phase14_market_gap_report.py`

Reports training rows, class balance, artifact presence, calibration, and the missing requirements for production promotion.

```powershell
python .\tools\phase14_market_gap_report.py --json
```

### `tools/phase14_expand_training_data.py`

Scans existing training files, playerboard snapshots, and prediction history files for graded rows. It only adds rows when a target label can be confidently derived from explicit outcome/result fields. It does not fabricate labels.

```powershell
python .\tools\phase14_expand_training_data.py --markets batter_hits batter_total_bases --write
```

### `tools/phase14_backtest_market_artifacts.py`

Loads the exact market artifact and its feature metadata, evaluates it against a held-out/labeled CSV, writes a backtest report, and can update the model registry.

```powershell
python .\tools\phase14_backtest_market_artifacts.py --markets batter_hits batter_total_bases --update-registry
```

### `tools/phase14_promote_market_models.py`

Promotes registry entries from `experimental` to `production` only when every gate passes.

```powershell
python .\tools\phase14_promote_market_models.py --markets batter_hits batter_total_bases --write
```

## Expected current state

After Phase 13, `batter_hits` and `batter_total_bases` may have experimental artifacts. They should remain non-production until they have at least 100 graded backtest rows.

Markets with one-class labels, such as all zeros, must remain Research Only until more graded positive examples are available.
