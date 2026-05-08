# Data Schemas

CSV inputs are part of the product contract. Missing columns, type drift, or postgame fields leaking into pregame models can create false confidence.

## Contract validator

Run:

```bash
python tools/validate_data_contracts.py --root . --season 2026
```

The validator checks required columns, numeric fields, date fields, and basic row-count expectations for core CSV families.

## Core files

### Playerboard

Pattern: `data/playerboard/playerboard_<season>.csv`

Required columns:

- `date`
- `market`
- `player`
- `team`
- `line`

### Playerboard backtest

Pattern: `data/backtests/playerboard_backtest_<season>.csv`

Required columns:

- `date`
- `market`
- `player`
- `team`
- `line`
- `result`

### Prediction history

Pattern: `data/predictions/*.csv`

Required columns:

- `createdAt`
- `market`
- `player`
- `line`
- `probability`

### Season logs

Patterns:

- `data/cloud/season_logs/batter_game_logs_<season>.csv`
- `data/cloud/season_logs/pitcher_game_logs_<season>.csv`

Required columns:

- `date`
- `player`
- `team`

## Modeling rule

Training and validation must split by time. Pregame prediction features must not include postgame results, graded outcomes, final scores, or any `actual_*`/`result` columns.
