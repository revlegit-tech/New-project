# Stage 8 + Stage 9 Implementation Notes

Implemented from `UPDATED_INTEGRATION_ROADMAP(5).txt` with MLB-only scope.

## Stage 8 — Games View

### Frontend
- Added routed `Games` view in `public/outlier-ui.js`.
- Added game list loaded from `/api/game-context`.
- Added active game card state and selected game detail screen.
- Added game detail header with team identity, venue, game time/score, and sub-tabs.
- Added `Gamelines` tab with Outlier-style sections:
  - Money Line
  - Run Line
  - Total O/U
  - Accordion stubs for Alternate Run Line, Win Margin, Alternate Total O/U, and Total O/U (3 Way)
- Added `Player props` tab filtered to the selected game’s two teams.
- Added skeleton loading and inline retry panel for game-context failures.

### Styling
- Added premium dark, compact Outlier-style layout classes in `public/outlier-ui.css`.
- Added team logo initials, probability bars, sportsbook chips, game cards, and responsive layout.

## Stage 9 — Insights Feed

### Backend
- Added `insights_feed_payload()` to `stage3_betting_features.py`.
- Registered `GET /api/insights/feed` in `app.py`.
- Feed aggregates:
  - Hit-rate streak cards from `player_hit_rates_payload()`.
  - Steam movement cards from existing `steam_alerts_payload()`.
  - Team-form proxy trend cards from `team_game_logs_{season}.csv` when spread/ATS fields are not available.

### Frontend
- Added routed `Insights` view in `public/outlier-ui.js`.
- Added fetch wiring for `/api/insights/feed`.
- Added 5-minute auto-refresh while the user is on the Insights page.
- Added insight cards with avatar, matchup metadata, market/odds pill, ticked hit-rate bar, skeletons, and retry errors.

## Validation Run

- `python -m py_compile app.py stage3_betting_features.py baseball_ui_tools.py`
- `node --check public/outlier-ui.js`
- Local HTTP smoke test:
  - `/api/insights/feed?season=2026&date=2026-05-06&limit=2`
  - `/api/game-context?season=2026&date=2026-05-06&limit=1`

## Notes

- `/api/game-context` in this uploaded project currently returns schedule-backed games even when odds market cache files are unavailable. In that case, the UI renders the section structure and shows `--` for missing odds/model fields instead of crashing.
- Team ATS fields are not present in `team_game_logs_2026.csv`; the insights endpoint uses a clearly labeled team-form proxy until spread-result data is added.
