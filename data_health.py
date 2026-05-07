from __future__ import annotations

"""Data Health + Prop dropdown support.

Reads local/cloud warehouse outputs and PropLine saved CSVs.
Provides:
- data health summary
- available saved props for a date/market
- prediction history save
"""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from build_game_odds_template import TEAM_NAME_TO_ABBR as MLB_TEAM_NAME_TO_ABBR
except Exception:
    MLB_TEAM_NAME_TO_ABBR = {}

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
WAREHOUSE_DIR = DATA_DIR / "warehouse"
CLOUD_DIR = DATA_DIR / "cloud"
PREDICTION_DIR = DATA_DIR / "predictions"
PREDICTION_HISTORY = PREDICTION_DIR / "all_data_prediction_history.csv"

_JSON_CACHE: dict[Path, tuple[tuple[int, int], Any]] = {}
_CSV_COUNT_CACHE: dict[Path, tuple[tuple[int, int], int]] = {}
_CSV_ROWS_CACHE: dict[Path, tuple[tuple[int, int], list[dict[str, str]]]] = {}

PROP_MARKETS = [
    "pitcher_strikeouts",
    "batter_hits",
    "batter_total_bases",
    "batter_home_runs",
    "pitcher_hits_allowed",
    "pitcher_earned_runs",
]


def clean(value: Any) -> str:
    return str(value or "").strip()


TEAM_ALIASES = {
    "KC": "KCR",
    "KCR": "KCR",
    "SD": "SDP",
    "SDP": "SDP",
    "SF": "SFG",
    "SFG": "SFG",
    "TB": "TBR",
    "TBR": "TBR",
    "WSH": "WSN",
    "WSN": "WSN",
    "CWS": "CHW",
    "CHW": "CHW",
    "OAK": "ATH",
    "ATH": "ATH",
    "AZ": "ARI",
    "ARI": "ARI",
    "LA": "LAD",
    "LAD": "LAD",
    "ANA": "LAA",
    "LAA": "LAA",
    "NY": "NYY",
    "NYY": "NYY",
}


def normalize_team(value: Any) -> str:
    raw = clean(value)
    text = raw.upper()
    if not text:
        return ""

    name_map = {str(name).upper(): abbr for name, abbr in MLB_TEAM_NAME_TO_ABBR.items()}
    if text in name_map:
        return name_map[text]

    return TEAM_ALIASES.get(text, text)


def file_signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
        return (stat.st_mtime_ns, stat.st_size)
    except OSError:
        return None


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    signature = file_signature(path)
    if signature:
        cached = _JSON_CACHE.get(path)
        if cached and cached[0] == signature:
            return cached[1]
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return default
    if signature:
        _JSON_CACHE[path] = (signature, payload)
    return payload


def count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    signature = file_signature(path)
    if signature:
        cached = _CSV_COUNT_CACHE.get(path)
        if cached and cached[0] == signature:
            return cached[1]
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            count = max(sum(1 for _ in csv.DictReader(handle)), 0)
    except Exception:
        return 0
    if signature:
        _CSV_COUNT_CACHE[path] = (signature, count)
    return count


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    signature = file_signature(path)
    if signature:
        cached = _CSV_ROWS_CACHE.get(path)
        if cached and cached[0] == signature:
            return cached[1]
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except Exception:
        return []
    if signature:
        _CSV_ROWS_CACHE[path] = (signature, rows)
    return rows


def latest_file(folder: Path, pattern: str) -> Path | None:
    files = sorted(folder.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def latest_mtime(path: Path | None) -> str:
    if not path or not path.exists():
        return ""
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def season_from_date(date_label: str) -> str:
    return clean(date_label)[:4] or str(datetime.now().year)


def data_health_payload(date_label: str = "") -> dict[str, Any]:
    if not date_label:
        date_label = datetime.now().strftime("%Y-%m-%d")

    season = season_from_date(date_label)

    latest_local = read_json(WAREHOUSE_DIR / "summaries" / f"daily_summary_{date_label}.json", {})
    latest_cloud = read_json(CLOUD_DIR / "summaries" / "latest_collector_run.json", {})
    cloud_daily = read_json(CLOUD_DIR / "summaries" / f"daily_summary_{date_label}.json", {})

    batter_log_local = WAREHOUSE_DIR / "season_logs" / f"batter_game_logs_{season}.csv"
    pitcher_log_local = WAREHOUSE_DIR / "season_logs" / f"pitcher_game_logs_{season}.csv"
    team_log_local = WAREHOUSE_DIR / "season_logs" / f"team_game_logs_{season}.csv"

    batter_log_cloud = CLOUD_DIR / "season_logs" / f"batter_game_logs_{season}.csv"
    pitcher_log_cloud = CLOUD_DIR / "season_logs" / f"pitcher_game_logs_{season}.csv"
    team_log_cloud = CLOUD_DIR / "season_logs" / f"team_game_logs_{season}.csv"

    props_file = DATA_DIR / "odds" / f"propline_props_{date_label}.csv"
    game_odds_file = DATA_DIR / "imports" / f"game_odds_template_{date_label}.csv"

    latest_snapshot = latest_file(WAREHOUSE_DIR / "odds_snapshots", f"propline_props_{date_label}_*.csv")
    latest_log = latest_file(WAREHOUSE_DIR / "logs", "season_collector_*.json")

    savant_status = read_json(WAREHOUSE_DIR / "summaries" / "savant_status.json", {})
    bvp_status = read_json(WAREHOUSE_DIR / "summaries" / "batter_pitcher_samples_status.json", {})

    source_summary = latest_local or cloud_daily or {}

    warnings = []

    if not props_file.exists() and not source_summary.get("propCount"):
        warnings.append("No PropLine props found for this date yet.")

    if not source_summary.get("mlbGames"):
        warnings.append("No MLB schedule/game summary found for this date yet.")

    if not source_summary.get("weatherRows"):
        warnings.append("No weather summary found for this date yet.")

    if not latest_snapshot:
        warnings.append("No local PropLine odds snapshot found for this date yet.")

    if count_csv_rows(batter_log_local) == 0 and count_csv_rows(batter_log_cloud) == 0:
        warnings.append(f"No batter game logs found for {season} yet.")

    if count_csv_rows(pitcher_log_local) == 0 and count_csv_rows(pitcher_log_cloud) == 0:
        warnings.append(f"No pitcher game logs found for {season} yet.")

    return {
        "date": date_label,
        "season": season,
        "dataRoot": str(DATA_DIR),
        "latestLocalSummary": source_summary,
        "latestCloudRun": latest_cloud,
        "health": {
            "mlbGames": source_summary.get("mlbGames", 0),
            "finalGames": source_summary.get("finalGames", 0),
            "boxscoresSaved": source_summary.get("boxscoresSaved", 0),
            "propCount": source_summary.get("propCount", count_csv_rows(props_file)),
            "propEvents": source_summary.get("propEvents", 0),
            "gameOddsAutoFilledRows": source_summary.get("gameOddsAutoFilledRows", 0),
            "rowsWithMoneyline": source_summary.get("rowsWithMoneyline", 0),
            "rowsWithTotal": source_summary.get("rowsWithTotal", 0),
            "weatherRows": source_summary.get("weatherRows", 0),
            "batterLogRows": count_csv_rows(batter_log_local) or count_csv_rows(batter_log_cloud),
            "pitcherLogRows": count_csv_rows(pitcher_log_local) or count_csv_rows(pitcher_log_cloud),
            "teamLogRows": count_csv_rows(team_log_local) or count_csv_rows(team_log_cloud),
            "savedPropRows": count_csv_rows(props_file),
            "gameOddsRows": count_csv_rows(game_odds_file),
            "predictionHistoryRows": count_csv_rows(PREDICTION_HISTORY),
        },
        "files": {
            "propsFile": str(props_file),
            "gameOddsFile": str(game_odds_file),
            "latestOddsSnapshot": str(latest_snapshot) if latest_snapshot else "",
            "latestCollectorLog": str(latest_log) if latest_log else "",
            "localBatterLog": str(batter_log_local),
            "localPitcherLog": str(pitcher_log_local),
            "localTeamLog": str(team_log_local),
            "cloudBatterLog": str(batter_log_cloud),
            "cloudPitcherLog": str(pitcher_log_cloud),
            "cloudTeamLog": str(team_log_cloud),
            "predictionHistory": str(PREDICTION_HISTORY),
        },
        "timestamps": {
            "propsFile": latest_mtime(props_file),
            "gameOddsFile": latest_mtime(game_odds_file),
            "latestOddsSnapshot": latest_mtime(latest_snapshot),
            "latestCollectorLog": latest_mtime(latest_log),
            "predictionHistory": latest_mtime(PREDICTION_HISTORY),
        },
        "savant": savant_status,
        "batterVsPitcher": bvp_status,
        "warnings": warnings,
        "ok": len(warnings) == 0,
    }


def first_value(row: dict[str, Any], keys: list[str], default: str = "") -> str:
    lower = {str(k).lower(): v for k, v in row.items()}
    for key in keys:
        if key in row and clean(row[key]):
            return clean(row[key])
        low = key.lower()
        if low in lower and clean(lower[low]):
            return clean(lower[low])
    return default


def prop_rows_payload(date_label: str, market: str = "") -> dict[str, Any]:
    if not date_label:
        date_label = datetime.now().strftime("%Y-%m-%d")

    props_file = DATA_DIR / "odds" / f"propline_props_{date_label}.csv"
    rows = []

    for i, row in enumerate(read_csv_rows(props_file)):
        row_market = first_value(row, ["market", "market_key", "marketKey"])
        if market and row_market != market:
            continue

        player = first_value(row, ["player", "description", "name", "selection"])
        team = first_value(row, ["team", "player_team", "team_abbr"])
        opponent = first_value(row, ["opponent", "opp", "opponent_team"])
        home_team = first_value(row, ["homeTeam", "home_team", "home"])
        away_team = first_value(row, ["awayTeam", "away_team", "away"])
        pitcher = first_value(row, ["pitcher", "probable_pitcher", "opposing_pitcher"])
        line = first_value(row, ["line", "point", "points"], "0.5")
        odds = first_value(row, ["americanOdds", "american_odds", "odds", "price"], "-110")
        game = first_value(row, ["game"], "") or f"{away_team} @ {home_team}".strip()

        label_bits = [
            player or f"Row {i + 1}",
            row_market,
            f"line {line}",
            f"odds {odds}",
            f"{team} vs {opponent}".strip(),
            game,
        ]

        rows.append({
            "id": str(i),
            "label": " | ".join(bit for bit in label_bits if bit),
            "date": date_label,
            "market": row_market,
            "player": player,
            "team": team,
            "opponent": opponent,
            "homeTeam": home_team,
            "awayTeam": away_team,
            "game": game,
            "pitcher": pitcher,
            "line": line,
            "americanOdds": odds,
            "raw": row,
        })

    return {
        "date": date_label,
        "market": market,
        "file": str(props_file),
        "count": len(rows),
        "rows": rows[:1000],
    }


def save_prediction_payload(prediction: dict[str, Any]) -> dict[str, Any]:
    PREDICTION_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "savedAt",
        "date",
        "market",
        "player",
        "team",
        "opponent",
        "pitcher",
        "line",
        "americanOdds",
        "probabilityPercent",
        "sportsbookImpliedPercent",
        "edgePercent",
        "fairOdds",
        "confidence",
        "recommendation",
        "dataUsed",
        "missingData",
    ]

    exists = PREDICTION_HISTORY.exists()

    row = {
        "savedAt": datetime.now(timezone.utc).isoformat(),
        "date": prediction.get("date", ""),
        "market": prediction.get("market", ""),
        "player": prediction.get("player", ""),
        "team": prediction.get("team", ""),
        "opponent": prediction.get("opponent", ""),
        "pitcher": prediction.get("pitcher", ""),
        "line": prediction.get("line", ""),
        "americanOdds": prediction.get("americanOdds", ""),
        "probabilityPercent": prediction.get("probabilityPercent", ""),
        "sportsbookImpliedPercent": prediction.get("sportsbookImpliedPercent", ""),
        "edgePercent": prediction.get("edgePercent", ""),
        "fairOdds": prediction.get("fairOdds", ""),
        "confidence": prediction.get("confidence", ""),
        "recommendation": prediction.get("recommendation", ""),
        "dataUsed": "; ".join(prediction.get("dataUsed", []) or []),
        "missingData": "; ".join(prediction.get("missingData", []) or []),
    }

    with PREDICTION_HISTORY.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow(row)

    return {
        "saved": True,
        "path": str(PREDICTION_HISTORY),
        "rows": count_csv_rows(PREDICTION_HISTORY),
        "prediction": row,
    }


def saved_games_payload(date_label: str) -> dict[str, Any]:
    """Return available games for a date.

    Order:
    1. local warehouse summary
    2. cloud summary
    3. live MLB StatsAPI sync if saved files are empty
    """
    if not date_label:
        date_label = datetime.now().strftime("%Y-%m-%d")

    def build_rows(games: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []

        for i, game in enumerate(games or []):
            away = clean(game.get("away"))
            home = clean(game.get("home"))
            away_name = clean(game.get("awayName")) or away
            home_name = clean(game.get("homeName")) or home

            if not away or not home:
                continue

            rows.append({
                "id": str(i),
                "date": date_label,
                "away": away,
                "home": home,
                "awayName": away_name,
                "homeName": home_name,
                "label": f"{away} @ {home}",
                "displayLabel": f"{away_name} @ {home_name}",
                "gamePk": clean(game.get("gamePk")),
                "gameDate": clean(game.get("gameDate")),
                "status": clean(game.get("status")),
                "final": bool(game.get("final")),
                "awayProbablePitcher": clean(game.get("awayProbablePitcher")),
                "homeProbablePitcher": clean(game.get("homeProbablePitcher")),
                "venue": clean(game.get("venue")),
                "raw": game,
            })

        return rows

    local_path = WAREHOUSE_DIR / "summaries" / f"games_{date_label}.json"
    cloud_path = CLOUD_DIR / "summaries" / f"games_{date_label}.json"

    games = read_json(local_path, [])
    source = str(local_path)
    rows = build_rows(games)

    if not rows:
        games = read_json(cloud_path, [])
        source = str(cloud_path)
        rows = build_rows(games)

    if not rows:
        try:
            from data_warehouse_sync import sync_mlb_schedule

            synced = sync_mlb_schedule(date_label)
            games = synced.get("games", [])
            rows = build_rows(games)
            source = f"live MLB StatsAPI sync -> {local_path}"
        except Exception as error:
            return {
                "date": date_label,
                "source": source,
                "count": 0,
                "games": [],
                "warning": f"No saved games found and live MLB StatsAPI sync failed: {error}",
            }

    return {
        "date": date_label,
        "source": source,
        "count": len(rows),
        "games": rows,
    }


def prop_rows_for_game_payload(date_label: str, market: str = "", away: str = "", home: str = "") -> dict[str, Any]:
    """Return saved PropLine props filtered to one selected matchup.

    If exact team/opponent filtering returns zero rows, return all market props
    with a warning instead of leaving the UI empty.
    """
    payload = prop_rows_payload(date_label, market)

    away_norm = normalize_team(away)
    home_norm = normalize_team(home)
    teams = {away_norm, home_norm} - {""}

    if not teams:
        return payload

    all_rows = payload.get("rows", [])
    filtered = []

    for row in all_rows:
        team = normalize_team(row.get("team"))
        opponent = normalize_team(row.get("opponent"))
        home_team = normalize_team(row.get("homeTeam") or (row.get("raw") or {}).get("homeTeam"))
        away_team = normalize_team(row.get("awayTeam") or (row.get("raw") or {}).get("awayTeam"))
        event_teams = {home_team, away_team} - {""}

        # Keep rows that clearly belong to this game. Player-team fields are
        # best when present; PropLine often only gives event home/away teams,
        # so use those too instead of making the UI fall back to every game.
        if team in teams and (not opponent or opponent in teams):
            filtered.append(row)
        elif opponent in teams and team in teams:
            filtered.append(row)
        elif len(event_teams) == 2 and event_teams == teams:
            filtered.append(row)

    payload["away"] = away_norm
    payload["home"] = home_norm

    if filtered:
        payload["count"] = len(filtered)
        payload["rows"] = filtered
        payload["fallback"] = False
        return payload

    # Fallback: show all saved props for that market. This is better than
    # blocking the user when PropLine team/opponent columns are missing or use
    # different abbreviations.
    payload["count"] = len(all_rows)
    payload["rows"] = all_rows
    payload["fallback"] = True
    payload["warning"] = (
        f"No exact props matched {away_norm} @ {home_norm}. "
        "Showing all saved props for this market instead."
    )
    return payload
