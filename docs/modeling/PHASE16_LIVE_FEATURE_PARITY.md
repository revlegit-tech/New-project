# Phase 16 — Live Feature Parity

## Purpose

Phase 15 showed that the experimental batter models can train and pass small walk-forward quality checks, but live Playerboard rows are missing many of the fields used by the model metadata. Phase 16 adds a controlled live-feature workflow so the UI and model layer can tell the difference between:

- real same-date features available from PropLine / Playerboard context,
- missing enrichment that should remain visible,
- and training-only leakage fields that must never be faked at runtime.

## Non-negotiables preserved

- No silent fallback: missing moneyline, game total, weather, or park features remain blank and are reported.
- No leakage: final outcome fields such as `actual`, `target`, `result`, and `label` are excluded from live feature contracts.
- No generic model promotion: markets remain experimental unless readiness gates pass.

## New tools

### Feature contract

```powershell
python .\tools\phase16_feature_contract.py --markets batter_hits batter_total_bases --write
```

Audits model metadata and reports blocked features that are not valid live predictors.

### Live Playerboard enrichment

```powershell
python .\tools\phase16_enrich_live_playerboard.py --date 2026-05-07 --season 2026 --markets batter_hits batter_total_bases
```

Adds same-date PropLine-derived live fields to `data/playerboard/playerboard_2026.csv`, including:

- `american_odds`
- `best_american_odds`
- `best_book`
- `sportsbook_count`
- `sportsbook_implied_probability`
- `event_id`
- `books`
- `liveFeatureStatus`
- `liveFeatureMissing`

It only computes implied run features when real moneyline and total inputs already exist.

### Live feature audit

```powershell
python .\tools\phase16_live_feature_audit.py --markets batter_hits batter_total_bases --season 2026 --date 2026-05-07 --write
```

Compares live Playerboard rows to eligible live features and writes an audit under `data/models/audits/`.

### One-command workflow

```powershell
python .\tools\run_phase16_live_feature_parity.py --date 2026-05-07 --season 2026 --markets batter_hits batter_total_bases
```

## Expected current outcome

The workflow should improve coverage for PropLine-derived fields like odds and sportsbook ladder, while still warning about missing moneyline, total, park, and weather-derived features until those upstream enrichments are connected.
