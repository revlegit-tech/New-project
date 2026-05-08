# Phase 13 Model Readiness Contract

The production app must not promote a betting market just because a generic prop model exists. Each market needs its own artifact, feature metadata, calibration flag, and backtest evidence.

## Registry location

Default registry:

```text
data/models/model_registry.json
```

Override:

```powershell
$env:MLB_MODEL_REGISTRY = "C:\path\to\model_registry.json"
```

## Registry entry

```json
{
  "batter_hits": {
    "artifact": "data/models/prop_model_batter_hits.joblib",
    "features": "data/models/prop_model_batter_hits_features.json",
    "status": "experimental",
    "trained_at": "2026-05-08T00:00:00Z",
    "training_rows": 204,
    "positive_rows": 43,
    "negative_rows": 161,
    "feature_count": 18,
    "calibrated": false,
    "model_type": "logistic_regression",
    "backtest": {
      "graded": 0,
      "brierScore": null,
      "logLoss": null,
      "roiPercent": null,
      "source": "not_available"
    }
  }
}
```

## Status meanings

| Status | Meaning |
|---|---|
| `not_ready` | Missing artifact or metadata. |
| `research_only` | Training data is too small or one-class only. |
| `experimental` | Artifact exists but is not calibrated or has not cleared production backtest gates. |
| `production_candidate` | Candidate artifact with calibration and backtest gates cleared. |
| `production` | Fully promoted artifact. |
| `disabled` | Explicitly blocked in registry. |

## Daily workflow

After refreshing a slate:

```powershell
python .\tools\validate_model_readiness.py --json
python .\tools\audit_model_registry.py
```

The trust surface will continue to say Research Only when no market is production eligible. That is intentional.
