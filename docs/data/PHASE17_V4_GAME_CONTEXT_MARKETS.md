# Phase 17 v4 — Canonical Game Context Markets

This phase separates game/team context from batter and pitcher prop markets.

## Source of truth

The canonical game-context outputs are:

```text
data/warehouse/game_context/game_context_<DATE>.csv
data/warehouse/game_context/game_context_markets_<DATE>.csv
```

`playerboard_<SEASON>.csv` still receives a denormalized copy for UI speed, but the fields below are treated as game context, not batter data:

```text
team_moneyline
opponent_moneyline
game_total
moneyline_implied_probability
team_implied_runs
opponent_implied_runs
park_factor
weather_temperature_f
weather_wind_mph
```

## Run

```powershell
$Date = "2026-05-07"
python .\tools\run_phase17_v4_game_context_markets.py --date $Date --season 2026 --markets batter_hits batter_total_bases --refresh-provider --line-source propline
```

If provider payloads are already present:

```powershell
python .\tools\run_phase17_v4_game_context_markets.py --date $Date --season 2026 --markets batter_hits batter_total_bases
```

## Game context market markers

The workflow writes market-like rows for UI sections:

```text
game_moneyline
opponent_moneyline
moneyline_implied_probability
game_total
team_implied_runs
opponent_implied_runs
```

These are not player prop markets. They belong to `market_group=game_context`.

## Trust behavior

No totals are fabricated. `team_implied_runs` and `opponent_implied_runs` are computed only when both moneylines and a real game total exist.
