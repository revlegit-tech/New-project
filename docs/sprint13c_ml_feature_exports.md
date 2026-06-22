# Sprint 13C ML Feature Exports

Sprint 13C turns the safe game-market enrichment from Sprint 13B into an auditable player-prop ML feature export layer. It does not train or promote a production model. Its job is to produce leakage-guarded feature rows, export manifests, previews, and market-level backtest readiness summaries so Sprint 13D can train models safely.

## Safe Feature List

Core prop/export metadata:

- `feature_schema_version`
- `exported_at`
- `source`
- `source_row_id`
- `prop_key`
- `date`
- `season`
- `player`
- `team`
- `opponent`
- `market`
- `side`
- `line`
- `book`
- `american_odds`
- `implied_probability_percent`
- `model_probability_percent`
- `hit_rate_summary`

Safe game-market fields:

- `game_market_available`
- `game_market_game_id`
- `game_market_consensus_open_total`
- `game_market_consensus_current_total`
- `game_market_total_line_movement`
- `game_market_favorite_team_open`
- `game_market_favorite_team_current`
- `game_market_team_is_favorite_open`
- `game_market_team_is_favorite_current`
- `game_market_team_no_vig_win_prob_open`
- `game_market_team_no_vig_win_prob_current`
- `game_market_opponent_no_vig_win_prob_open`
- `game_market_opponent_no_vig_win_prob_current`
- `game_market_book_count_moneyline`
- `game_market_book_count_total`
- `game_market_book_count_runline`
- `game_market_disagreement_score`
- `game_market_team_moneyline_movement`
- `game_market_opponent_moneyline_movement`
- `game_market_quality_flags`
- `game_market_enrichment_status`

## Blocked Leakage Fields

These fields are never allowed in ML feature exports or model inputs:

- `home_score`
- `away_score`
- `total_runs`
- `home_win`
- `away_win`
- `game_status`
- `gameStatusText`
- `result`
- `push_flag`
- `profit_1u`
- `graded_at`
- `grade`
- `riskBucket`
- `closing_line_value`
- historical game-market grade/result/profit/closing-line-value fields

Blocked fields can be used only as explicitly labeled outcomes inside historical grade or backtest-label workflows. They are detected in raw snapshots, reported in manifests, and filtered before features are exported.

## CLI Examples

```powershell
python scripts/export_ml_features.py --date 2026-06-22
python scripts/export_ml_features.py --date 2026-06-22 --source edge-board
python scripts/export_ml_features.py --date 2026-06-22 --source playerboard
python scripts/export_ml_features.py --date 2026-06-22 --dry-run
python scripts/export_ml_features.py --date 2026-06-22 --format json
```

Dry runs print row counts, market counts, safe feature counts, blocked leakage field counts, game-market match/missing counts, and the output paths that would be written.

## API Examples

```powershell
$base = "http://127.0.0.1:8765"

Invoke-RestMethod "$base/api/ml-features/status"
Invoke-RestMethod "$base/api/ml-features/preview?date=2026-06-22&limit=10"
Invoke-RestMethod "$base/api/ml-features/backtest-readiness?date=2026-06-22"

Invoke-RestMethod `
  -Uri "$base/api/admin/ml-features/export?date=2026-06-22&source=edge-board&dryRun=true&format=both" `
  -Method POST `
  -Headers @{ "X-Baseball-Prop-Action" = "1" }
```

The admin export endpoint requires `X-Baseball-Prop-Action: 1`.

## Output Paths

Generated artifacts are written under:

- `data/warehouse/ml_features/player_prop_features_YYYY-MM-DD.csv`
- `data/warehouse/ml_features/player_prop_features_YYYY-MM-DD.json`
- `data/warehouse/ml_features/ml_feature_export_manifest_YYYY-MM-DD.json`

These files are generated runtime artifacts and should not be committed.

## Manifest Shape

The export manifest includes:

- `feature_schema_version`
- `exported_at`
- `date`
- `season`
- `source`
- `format`
- `dry_run`
- `row_count`
- `market_counts`
- `source_counts`
- `safe_feature_count`
- `blocked_feature_count`
- `game_market_match_count`
- `game_market_missing_count`
- `game_market_coverage_pct`
- `leakage_blocked_fields`
- `leakage_check_passed`
- `output_paths`
- `warnings`

## Backtest Readiness

Readiness is reported by market:

- `not_ready`: too few rows, missing two-class labels, or leakage failed.
- `export_ready`: enough exported rows exist, but feature completeness needs work before backtesting.
- `backtest_ready`: enough rows and two-class labels exist for backtesting.
- `training_candidate`: enough rows, class balance, feature completeness, and game-market coverage exist for Sprint 13D training experiments.

## Sprint 13D Handoff

Sprint 13D should train only from the exported safe feature files or from the same schema service. It should keep outcome labels separate from feature rows, join labels only inside a backtest/training dataset builder, and fail closed if any blocked field appears in model inputs.
