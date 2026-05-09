# Baseball Prop Predictor

> Architecture note: `mlb_app/` is the canonical production boundary. See [ARCHITECTURE.md](ARCHITECTURE.md) for runtime modes, dependency direction, and source-tree policy.

A lightweight local app for predicting baseball props using aggregate batting, pitching, batting-against, and team context CSVs.

## Run the production app

`mlb_app/` is the canonical runtime. The legacy root `app.py` entrypoint has been retired and is not shipped in the Phase 10 production tree.

Local development:

```bash
make run
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765).

Production-style WSGI/Gunicorn runtime:

```bash
make serve
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765).

Experimental ASGI comparison runtime:

```bash
make serve-asgi
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765).

Modular Outlier UI preview:

```text
http://127.0.0.1:8765/?view=outlier
```

## Batch MLB Prop Analyzer

Use `mlb_prop_analyzer.py` when you want a ranked daily board instead of one prediction at a time. It analyzes home run props and pitcher strikeout props from your odds files, enriches them with today's schedule and probable pitchers from `toddrob99/MLB-StatsAPI`, and blends in uploaded HR/K data, last 5 logs, team K rates, Rotogrinders/Covers exports, and manual weather.

Example:

```powershell
python mlb_prop_analyzer.py `
  --date today `
  --odds examples/prop-odds-template.csv `
  --hr-data examples/hr-data-template.csv `
  --strikeout-data examples/strikeout-data-template.csv `
  --team-k-data examples/team-k-rates-template.csv `
  --pitching-logs examples/pitching-game-log-template.csv `
  --savant examples/batter-pitcher-advanced-template.csv `
  --weather examples/weather-template.csv `
  --rotogrinders examples/rotogrinders-template.csv `
  --covers examples/covers-template.csv
```

Outputs are written to `data/prop_reports/YYYY-MM-DD/`:

- `report.md`: best value, highest probability, HR props, pitcher K props, and parlay tables.
- `best_value.csv`: ranked by expected value and edge.
- `highest_probability.csv`: ranked by model probability.
- `all_props.csv`: every analyzed prop.
- `parlays.csv`: 2- and 3-leg combinations with combined probability, fair odds, EV, and $3/$10/$20 payouts.

Input templates:

- `examples/prop-odds-template.csv`: sportsbook player, market, line, American odds, and book.
- `examples/hr-data-template.csv`: batter season HR/power data.
- `examples/strikeout-data-template.csv`: pitcher season K/workload data.
- `examples/team-k-rates-template.csv`: opponent team strikeout rates.
- `examples/weather-template.csv`: manual park, roof, temperature, wind, and optional manual HR/K adjustments.
- `examples/rotogrinders-template.csv`: probable pitcher and lineup-status export.
- `examples/covers-template.csv`: matchup, probable pitcher, team K rate, venue, and weather export.
- `examples/batter-pitcher-advanced-template.csv`: summarized Baseball Savant/Statcast matchup quality.

The analyzer reads CSV, JSON, or simple HTML tables. It does not require Rotogrinders or Covers scraping; save/export the tables you use and point the CLI at those files.

### Screenshot/OCR Imports

Screenshots should be converted to CSV before analysis. The safest path is to export the original sheet as CSV, but `image_data_importer.py` can parse OCR text from sportsbook strikeout ladders and the two spreadsheet layouts shown in your examples.

If you have Tesseract OCR installed locally:

```powershell
python image_data_importer.py `
  --type strikeout-odds `
  --image "C:\Users\RevLe\OneDrive\Pictures\Screenshots\max fried.png" `
  --image "C:\Users\RevLe\OneDrive\Pictures\Screenshots\chase burns.png" `
  --out data\imports\strikeout_odds_from_images.csv
```

For sheet screenshots:

```powershell
python image_data_importer.py --type daily-strikeouts --image "C:\Users\RevLe\Downloads\Daily_Strikeouts.png" --out data\imports\daily_strikeouts_from_image.csv
python image_data_importer.py --type hr-sheet --image "C:\Users\RevLe\Downloads\HRSheet.png" --out data\imports\hr_sheet_from_image.csv
```

If OCR is not installed, use Windows Snipping Tool, Photos, OneNote, or another OCR app to copy text from the image into a `.txt` file, then run the same importer with `--text-file` instead of `--image`. After that, pass the CSVs into the analyzer:

```powershell
python mlb_prop_analyzer.py `
  --date today `
  --odds data\imports\strikeout_odds_from_images.csv `
  --strikeout-data data\imports\daily_strikeouts_from_image.csv `
  --strikeout-data data\imports\hr_sheet_from_image.csv `
  --team-k-data data\imports\daily_strikeouts_from_image.csv
```

## Daily URL Data Sources

You can use a URL instead of manually uploading a CSV file. Paste the link into `Dataset URL`, choose the CSV type, then click `Load URL`.

For team-by-team sources, open `Bulk links`, paste one URL per line, choose the dataset type, then click `Load URLs`. This is intended for workflows such as adding all 30 team game-log pages or team-specific batting/pitching pages. Each URL is saved as its own source and refreshed independently.

Supported URL formats:

- Direct `.csv` links.
- HTML pages that contain a data table. The app reads the first table and feeds it into the same parser as a CSV upload.

Loaded URLs are saved in `data/dataset_sources.json` with their dataset type, last row count, status, and refresh time. When the source updates, click `Refresh URLs` to reload every saved source, or use the per-source `Refresh` button to update one dataset.

Saved dataset URLs also auto-refresh once per day while the local app is running. The app checks sources at startup and then hourly, but it only refreshes a source when its last import is at least 24 hours old. Set `DATASET_AUTO_REFRESH=0` before starting the app to disable daily polling.

Baseball Reference season pages are supported for URL imports, including commented stat tables and `#all_...` table fragments. For example, import `https://www.baseball-reference.com/leagues/majors/2026-standard-pitching.shtml#all_players_standard_pitching` as `Player standard pitching`.

## Python Setup

Use Python 3.12 if possible. Install project requirements before running the canonical server:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
make run
```

Run the smoke tests with:

```powershell
make smoke
```

## GitHub Setup

This project includes:

- `.gitignore` for Python cache files, logs, virtual environments, and local uploaded data.
- `.github/workflows/python-ci.yml` to run syntax checks and tests on GitHub.
- `tests/test_smoke.py` for basic model and market-value checks.
- A `/api/github` endpoint and browser panel for checking repository metadata and recent GitHub Actions runs.

To publish it with Git installed:

```powershell
git init
git add .
git commit -m "Initial baseball prop predictor"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

If you use GitHub Desktop, choose `Add existing repository`, select this folder, commit the files, then publish the repository.

## GitHub API Setup

The GitHub API panel works with public repositories without a token. For private repositories or higher rate limits, create a fine-grained GitHub token with read access to repository metadata and Actions.

Create a local `.env` file from the template:

```powershell
Copy-Item .env.example .env
notepad .env
```

Then fill in:

```text
GITHUB_TOKEN=your_token_here
GITHUB_REPOSITORY=your-username/your-repo
```

Restart the app after changing `.env`:

```powershell
make run
```

In the browser, enter a repo like `octocat/Hello-World` or your own `username/repo` in the GitHub API panel and click `Check Repo`.

## MLB StatsAPI Integration

The app integrates the public [zero-sum-seattle/python-mlb-statsapi](https://github.com/zero-sum-seattle/python-mlb-statsapi) package for live MLB data. It is listed in `requirements.txt` as `python-mlb-statsapi`.

The batch analyzer also supports [toddrob99/MLB-StatsAPI](https://github.com/toddrob99/MLB-StatsAPI), imported as `statsapi`, for daily schedules and probable pitchers.

Install it with:

```powershell
python -m pip install -r requirements.txt
```

Then restart:

```powershell
make run
```

Use the `MLB StatsAPI` panel to look up a player by name and season. The backend endpoint is:

```text
GET /api/mlb/player?name=Aaron%20Judge&season=2026
```

Every player lookup is automatically saved into `data/batting.json` and merged into the app's batting dataset. Existing players are updated by MLB id or player name; new players are added. To test the API without writing to stored batting data, add `store=0`:

```text
GET /api/mlb/player?name=Aaron%20Judge&season=2026&store=0
```

The `MLB StatsAPI` panel also includes an advanced command console for the examples from `python-mlb-statsapi`. It uses:

```text
GET /api/mlb/command?command=playerStats&player=Ty%20France&season=2022&stats=season,career&groups=hitting,pitching
```

Supported command values:

- `playerStats`
- `teamStats`
- `expectedStats`
- `vsPlayerStats`
- `hotColdZones`
- `schedule`
- `game`
- `playByPlay`
- `lineScore`
- `boxScore`
- `gamepace`
- `people`
- `peopleId`
- `team`
- `teamRoster`
- `teamCoaches`
- `draft`
- `awards`
- `venue`
- `division`
- `league`
- `season`
- `standings`

## ESPN API Integration

The app also proxies ESPN's public MLB Site API endpoints:

- Scores: `GET /api/espn/scoreboard`
- Scores by date: `GET /api/espn/scoreboard?dates=20260502`
- All teams: `GET /api/espn/teams`
- Specific team: `GET /api/espn/teams/nyy`

The upstream ESPN URLs are:

- `http://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard`
- `http://site.api.espn.com/apis/site/v2/sports/baseball/mlb/teams`
- `http://site.api.espn.com/apis/site/v2/sports/baseball/mlb/teams/:team`

Use the `ESPN API` panel in the browser to load a scoreboard date, populate all MLB teams, and inspect one team. Scoreboard rows include probable starters when ESPN posts them. Use either team button in a score row to apply that game context to the predictor: batter props use the opposing team's probable starter, and pitcher strikeout props use the selected team's probable starter against the opposite lineup. The local specific-team route tries ESPN's `teams/:team` endpoint first, then falls back to the all-teams response if ESPN does not resolve that identifier directly.

## Supported CSV Types

Use the CSV type dropdown before uploading:

- `Batting/player stats`: replaces the player pool. Expected columns include `Player`, `Team`, `G`, `PA`, `AB`, `H`, `BB`, `SO`, `BA`, `OBP`, `SLG`, and `OPS`.
- `Opponent pitching/team stats`: adds team difficulty adjustments. Useful columns include `Team` or `Tm`, plus `BAA`, `BA`, `AVG Allowed`, `H`, `IP`, `ERA`, or `WHIP`.
- `Batter game logs`: adds player-vs-opponent context. Expected columns include `Player`, `Opp` or `Opponent`, `AB`, and `H`.
- `Pitching game logs`: adds pitcher recent workload and opponent-specific pitching context. Expected columns include `Pitcher` or `Player`, `Opp` or `Opponent`, `IP`, `H`, `ER`, `HR`, `BB`, `SO`, and `BF`.
- `Team standard batting`: stores team offense context. Useful columns include `Tm` or `Team`, `G`, `PA`, `AB`, `H`, `BA`, `OPS`, and `R/G`.
- `Player base running`: stores speed/running context. Useful columns include `Player`, `Team`, `SB`, `CS`, `SB%`, `XBT%`, and `Rbaser`.
- `Player standard pitching`: adds selectable opposing pitcher context. Useful columns include `Player`, `Team`, `IP`, `H`, `ERA`, `WHIP`, `H9`, `SO`, and `BB`.
- `Player batting against`: adds allowed batting profile for selectable opposing pitchers. Useful columns include `Player`, `Team`, `AB`, `H`, `BA`, `OBP`, `SLG`, and `OPS`.
- `Team batting against`: adds team-level allowed batting profile. Useful columns include `Tm` or `Team`, `AB`, `H`, `BA`, `OBP`, `SLG`, and `OPS`.
- `Team advanced pitching`: adds team-level pitching quality. Useful columns include `Tm` or `Team`, `K%`, `BB%`, `K-BB%`, `ERA-`, `FIP-`, `SIERA`, `xFIP`, and `FIP`.
- `Player advanced pitching`: adds advanced metrics to the opposing pitcher selector. Useful columns include `Player`, `Tm` or `Team`, `K%`, `BB%`, `K-BB%`, `ERA-`, `FIP-`, `SIERA`, `xFIP`, and `FIP`.
- `Team standard pitching`: adds team-level standard pitching. Useful columns include `Tm` or `Team`, `IP`, `H`, `ERA`, `WHIP`, `H9`, `SO`, and `BB`.
- `Advanced batter vs pitcher`: adds exact matchup history and Statcast-style quality. Useful columns include `Batter`, `Pitcher`, `PA`, `AB`, `H`, `HR`, `SO`, `BB`, `wOBA`, `xwOBA`, `xBA`, `xSLG`, `EV`, `HardH%`, `Barrel%`, and `Whiff%`.

Example templates are in the `examples` folder:

- `examples/batting-template.csv`
- `examples/opponent-pitching-template.csv`
- `examples/game-log-template.csv`
- `examples/pitching-game-log-template.csv`
- `examples/team-standard-batting-template.csv`
- `examples/player-baserunning-template.csv`
- `examples/player-standard-pitching-template.csv`
- `examples/player-batting-against-template.csv`
- `examples/team-batting-against-template.csv`
- `examples/team-advanced-pitching-template.csv`
- `examples/player-advanced-pitching-template.csv`
- `examples/team-standard-pitching-template.csv`
- `examples/batter-pitcher-advanced-template.csv`

## Most Useful Missing Data

The biggest accuracy upgrades from here are:

- Confirmed starter data when ESPN has not posted a probable pitcher or the starter cannot be matched to uploaded pitching rows.
- Batter and pitcher handedness splits, especially vs LHP/RHP for AVG, OPS, HR%, K%, BB%, wOBA, and xwOBA.
- Recent rolling form for last 7, 14, and 30 days.
- Confirmed lineup spot and batting order.
- Park factor, weather, roof status, wind direction, and wind speed.
- Pitch arsenal and batter performance by pitch type.
- Statcast quality metrics such as xBA, xSLG, xwOBA, barrel%, hard-hit%, launch angle, exit velocity, whiff%, and chase%.
- Historical sportsbook prop lines and results if you want to back-test and train a better model.

## Current Model

The app currently predicts:

- Hits
- Total bases
- Home runs
- Batter strikeouts
- Pitcher strikeouts vs an opposing team and its uploaded batter pool

Enter the sportsbook line and American odds before running a prediction. The app returns the model's over probability, the book's implied probability, fair odds, edge, and expected value per unit.

The model combines:

- Batting average
- Slugging and total bases
- At-bats per game
- Plate appearances per game
- OPS
- Strikeout/contact rate
- Walk rate
- Batter home run rate
- Pitcher/team batting-against profile
- Pitcher/team strikeout and walk rates
- Team standard and advanced pitching context
- Opponent team batting strikeout rate
- Player-level opposing batter strikeout rates for pitcher K targets

For pitcher strikeout props, choose `Pitcher strikeouts`, select the opposing lineup/team, select the pitcher, and set the sportsbook strikeout line. The app returns expected Ks, chance to go over the selected line, and the highest-risk opposing batters for 1+ strikeout.

Because the original batting CSV does not include game-by-game opponents or opponent pitching stats, opponent selection starts neutral unless you move the matchup adjustment slider. For better team-specific predictions, upload either:

- Batter game logs with an `Opponent` column
- Opponent pitching/team allowed hits data
- Probable pitcher data

## CSV Columns

The parser expects common batting columns such as `Player`, `Team`, `G`, `PA`, `AB`, `H`, `BB`, `SO`, `BA`, `OBP`, `SLG`, and `OPS`.

---

## P2 Developer Workflow

`mlb_app/` is now the only runtime shipped in the production tree. Historical endpoint mapping lives in `docs/endpoint-triage/`.

Recommended checks:

```bash
make security
make lint
make typecheck
make test
make test-contracts
make safe-export
```

UI smoke tests are available with Playwright:

```bash
npm install
npm run install:browsers
make test-ui
```

See `docs/DEVELOPER_GUIDE.md`, `docs/API_CONTRACTS.md`, `docs/DATA_SCHEMAS.md`, and `docs/RELEASE_CHECKLIST.md` for the production workflow.


## Frontend build

Sprint 5 adds the Vite-built Outlier production UI. See `docs/SPRINT5_OUTLIER_UI_PRODUCTIONIZATION.md` for the entrypoints, build commands, and legacy UI split.
