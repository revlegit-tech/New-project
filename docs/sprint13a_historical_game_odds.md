# Sprint 13A Historical Game Odds Warehouse

Sprint 13A adds a database-first warehouse for historical MLB game markets. This is separate from the existing PropLine player-prop pipeline.

## Dataset

Local source path:

```text
data/external/mlb_odds_dataset.json
```

The JSON is keyed by date. Each date contains games with `gameView` metadata, final scores, and odds groups for `moneyline`, `pointspread`, and `totals`.

Do not commit the raw dataset or generated warehouse exports.

## Schema

Migration files:

```text
mlb_app/db/migrations/sqlite/0002_historical_game_odds.sql
mlb_app/db/migrations/postgresql/0002_historical_game_odds.sql
```

Tables:

- `historical_game_odds_imports`
- `historical_game_odds_games`
- `historical_game_odds_lines`
- `historical_game_market_features`
- `historical_game_market_grades`

The lines table stores normalized long rows by game, sportsbook, market, and side. Markets map as:

- `moneyline` -> `moneyline`
- `pointspread` -> `run_line`
- `totals` -> `game_total_runs`

## Import Command

CLI import:

```powershell
python scripts/import_historical_game_odds.py --database-url sqlite:///data/warehouse.sqlite3
```

Optional CSV/debug export:

```powershell
python scripts/import_historical_game_odds.py --database-url sqlite:///data/warehouse.sqlite3 --export-csv
```

API import while the FastAPI app is running:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/api/admin/historical-game-odds/import -Headers @{"X-Baseball-Prop-Action"="1"}
```

Optional API CSV export:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8765/api/admin/historical-game-odds/import?exportCsv=1" -Headers @{"X-Baseball-Prop-Action"="1"}
```

## Endpoints

```text
POST /api/admin/historical-game-odds/import
GET  /api/game-odds/status
GET  /api/game-odds/lines?date=YYYY-MM-DD
GET  /api/game-odds/features?date=YYYY-MM-DD
GET  /api/game-odds/grades?date=YYYY-MM-DD
```

The admin import endpoint requires:

```text
X-Baseball-Prop-Action: 1
```

`/api/data/status` includes a `historical_game_odds` section with enablement, reachability, row counts, latest import timestamp, source-file presence, and warnings.

## Generated Debug Files

Only when export mode is enabled:

```text
data/warehouse/historical_game_odds/game_odds_long.csv
data/warehouse/historical_game_odds/game_odds_features.csv
data/warehouse/historical_game_odds/game_market_grades.csv
data/warehouse/historical_game_odds/import_manifest.json
```

These are debugging artifacts and should not be committed.

## Leakage Rules

Final scores are labels only. Pregame feature rows must not include:

- `home_score`
- `away_score`
- `total_runs`
- `home_win`
- `away_win`
- `game_status`
- `gameStatusText`

Scores and game status are allowed in the game and grade tables, but not in ML feature exports.

## Sprint 13B Hook

`mlb_app/services/game_market_feature_lookup_service.py` provides a fail-closed interface for future playerboard and edge-board enrichment:

```python
feature = lookup.feature_for_matchup(date="2021-04-01", team="TOR", opponent="NYY")
```

Sprint 13B can use this to join consensus totals, no-vig win probabilities, favorite team, book counts, and market disagreement into playerboard rows without making the current playerboard pipeline depend on the game odds warehouse.
