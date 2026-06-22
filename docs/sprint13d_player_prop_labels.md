# Sprint 13D Player Prop Labels

Sprint 13D adds the supervised label layer for player-prop backtesting. It does not train a production model. Its job is to create rows shaped as safe pregame features plus explicit postgame targets for Sprint 13E.

## Features vs Labels

Feature rows come from the Sprint 13C safe ML feature exporter. They contain only pregame fields such as player, team, market, side, line, odds, model probability, hit-rate summary, and leakage-protected game-market context.

Label rows are postgame-only target data. They contain actual stat values, win/loss/push/void result, hit flags, label status, grading time, and stat-source metadata. These fields are never merged into feature columns.

The joined training dataset keeps target fields prefixed:

- `target_result`
- `target_hit`
- `target_push`
- `target_actual_value`
- `target_label_status`

## Supported Markets

- `batter_hits`
- `batter_total_bases`
- `batter_home_runs`
- `batter_rbis`
- `batter_runs`
- `batter_walks`
- `batter_singles`
- `batter_doubles`
- `batter_stolen_bases`
- `batter_2plus_hits`
- `batter_2plus_home_runs`
- `batter_2plus_rbis`
- `batter_3plus_rbis`
- `pitcher_strikeouts`
- `pitcher_strikeouts_alt`
- `pitcher_outs`
- `pitcher_hits_allowed`
- `pitcher_earned_runs`

Alt and ladder markets use the feature row line when it is present. If a ladder line is missing, the builder can infer a fallback threshold from names like `2plus` or `3plus`.

## Label Statuses

- `graded`: a player log matched, the stat was available, and the result was graded.
- `missing_stat`: a player log matched, but the required stat key was absent or invalid.
- `missing_player`: no matching player log was found.
- `missing_market_mapping`: the row has no usable market key.
- `invalid_line`: the prop line could not be parsed.
- `unsupported_market`: the market has no Sprint 13D stat mapping.
- `game_not_final`: reserved for future final-state checks.
- `ambiguous_match`: multiple player log rows matched the same feature row.
- `void`: reserved for explicit void/no-action labels.

## Results

- `win`: the selected side beat the line.
- `loss`: the selected side did not beat the line.
- `push`: actual value equaled the line.
- `void`: no-action result.
- `ungraded`: no safe graded result is available.

## Output Paths

Labels:

- `data/warehouse/ml_labels/player_prop_labels_YYYY-MM-DD.csv`
- `data/warehouse/ml_labels/player_prop_labels_YYYY-MM-DD.json`
- `data/warehouse/ml_labels/player_prop_label_manifest_YYYY-MM-DD.json`

Training datasets:

- `data/warehouse/ml_training/player_prop_training_YYYY-MM-DD.csv`
- `data/warehouse/ml_training/player_prop_training_YYYY-MM-DD.json`
- `data/warehouse/ml_training/player_prop_training_manifest_YYYY-MM-DD.json`

## CLI Examples

```powershell
python scripts/build_player_prop_labels.py --date 2026-06-22 --source edge-board --dry-run
python scripts/build_player_prop_labels.py --date 2026-06-22 --source edge-board --include-ungraded
python scripts/build_backtest_dataset.py --date 2026-06-22 --source edge-board --dry-run
python scripts/build_backtest_dataset.py --date 2026-06-22 --source edge-board --include-ungraded
```

## API Examples

```powershell
Invoke-RestMethod "http://127.0.0.1:8765/api/ml-labels/status"
Invoke-RestMethod "http://127.0.0.1:8765/api/ml-labels/preview?date=2026-06-22&limit=10"
Invoke-RestMethod "http://127.0.0.1:8765/api/ml-training/preview?date=2026-06-22&limit=10"
```

Admin builds require `X-Baseball-Prop-Action: 1`:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/admin/ml-labels/build?date=2026-06-22&source=edge-board&dryRun=true&includeUngraded=true&format=both" -Method POST -Headers @{ "X-Baseball-Prop-Action" = "1" }
Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/admin/ml-training/build?date=2026-06-22&source=edge-board&dryRun=true&includeUngraded=true&format=both" -Method POST -Headers @{ "X-Baseball-Prop-Action" = "1" }
```

## Leakage Rules

Blocked postgame fields may not appear in model feature columns, including final scores, game status, grading result, hit/push flags, actual value, profit, CLV, risk bucket, and any postgame stat. In training outputs, postgame target data is allowed only with the `target_` prefix or inside the structured JSON `label` section.

## Sprint 13E Usage

Sprint 13E should train only from the safe feature column list in each training manifest. The model target should come from the explicit target columns, usually `target_hit` or `target_result`, filtered to `target_label_status == graded` and two-class markets.
