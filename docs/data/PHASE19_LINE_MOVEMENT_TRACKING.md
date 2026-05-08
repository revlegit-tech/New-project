# Phase 19 — Observed Line Movement Tracking

Phase 19 adds a line-movement layer on top of the Phase 18 game-context collector.

## Purpose

Track first-observed and latest game lines without mixing those fields into batter/pitcher prop markets. The source of truth remains:

```text
data/warehouse/game_context/game_context_YYYY-MM-DD.csv
```

Line snapshots are stored at:

```text
data/warehouse/game_context/line_snapshots/game_line_snapshots_YYYY-MM-DD.csv
```

## Fields added

- `open_team_moneyline`
- `close_team_moneyline`
- `moneyline_move`
- `opponent_moneyline_move`
- `open_game_total`
- `close_game_total`
- `total_move`
- `line_snapshot_count`
- `line_movement_source`
- `line_movement_status`
- `line_open_snapshot_at`
- `line_close_snapshot_at`

## Trust rule

`open_*` means **first observed by our collector**, not a guaranteed sportsbook market opener. The status field makes this explicit.

- `single_snapshot_first_observed`: only one snapshot exists. Opening/current are first-observed values and movement remains blank.
- `ready`: two or more snapshots exist, so movement can be computed as latest minus first-observed.

## Commands

```powershell
cd "C:\Users\RevLe\OneDrive\Documents\New project"
$env:PYTHONPATH = (Get-Location).Path
$Date = "2026-05-07"

python -m py_compile tools/phase19_line_movement.py tools/run_phase19_line_movement.py tools/phase19_line_movement_qa.py tools/apply_phase19_collector_hook.py tools/apply_phase19_ui_movement_patch.py
python -m pytest tests/test_phase19_line_movement.py -q

python .\tools\run_phase19_line_movement.py --date $Date --season 2026 --markets batter_hits batter_total_bases --line-source propline
python .\tools\phase19_line_movement_qa.py --date $Date
python .\tools\apply_phase19_ui_movement_patch.py
python .\tools\apply_phase19_collector_hook.py
```

## Scheduled collector

The Phase 19 hook inserts line snapshots and movement calculation into `season_auto_collector.py` before cloud export. Multiple daily runs are needed to produce real movement.

Recommended schedule:

- Morning snapshot: captures first observed lines.
- Midday snapshot: updates latest line and movement.
- Pregame/manual snapshot: updates latest line and movement.
- Midnight/final snapshot: archives final observed line.

## OddsPapi

OddsPapi is optional. It can improve future true opening/closing-line support, but Phase 19 does not require it to compute observed movement from our own snapshots.
