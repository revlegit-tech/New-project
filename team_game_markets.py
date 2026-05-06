from __future__ import annotations

"""OddsPapi team/game market helpers for Playerboard and matchup search.

This module intentionally returns rows in the same normalized shape that
playerboard.py already consumes for player props. That lets team/game markets
appear in the existing Playerboard and analysis UI without a separate panel.
"""

import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
ODDSPAPI_DIR = ROOT / "data" / "cache" / "oddspapi"
INCREMENTAL_DIR = ROOT / "data" / "cache" / "incremental_stats"
CLOUD_SUMMARY_DIR = ROOT / "data" / "cloud" / "summaries"

TEAM_GAME_MARKETS = {
    "moneyline",
    "moneyline_first_five",
    "run_line",
    "run_line_first_five",
    "run_line_first_inning",
    "run_line_second_inning",
    "run_line_third_inning",
    "run_line_fourth_inning",
    "run_line_fifth_inning",
    "run_line_sixth_inning",
    "run_line_seventh_inning",
    "run_line_eighth_inning",
    "run_line_ninth_inning",
    "game_total_runs",
    "first_five_total_runs",
    "first_inning_total_runs",
    "second_inning_total_runs",
    "third_inning_total_runs",
    "fourth_inning_total_runs",
    "fifth_inning_total_runs",
    "sixth_inning_total_runs",
    "seventh_inning_total_runs",
    "eighth_inning_total_runs",
    "ninth_inning_total_runs",
    "team_total_runs",
    "team_first_to_score",
}

TEAM_GAME_MARKET_LABELS = {
    "moneyline": "Moneyline",
    "moneyline_first_five": "Moneyline First Five",
    "run_line": "Run Line",
    "run_line_first_five": "Run Line First Five",
    "run_line_first_inning": "Run Line First Inning",
    "run_line_second_inning": "Run Line Second Inning",
    "run_line_third_inning": "Run Line Third Inning",
    "run_line_fourth_inning": "Run Line Fourth Inning",
    "run_line_fifth_inning": "Run Line Fifth Inning",
    "run_line_sixth_inning": "Run Line Sixth Inning",
    "run_line_seventh_inning": "Run Line Seventh Inning",
    "run_line_eighth_inning": "Run Line Eighth Inning",
    "run_line_ninth_inning": "Run Line Ninth Inning",
    "game_total_runs": "Game Total Runs",
    "first_five_total_runs": "First Five Total Runs",
    "first_inning_total_runs": "First Inning Total Runs",
    "second_inning_total_runs": "Second Inning Total Runs",
    "third_inning_total_runs": "Third Inning Total Runs",
    "fourth_inning_total_runs": "Fourth Inning Total Runs",
    "fifth_inning_total_runs": "Fifth Inning Total Runs",
    "sixth_inning_total_runs": "Sixth Inning Total Runs",
    "seventh_inning_total_runs": "Seventh Inning Total Runs",
    "eighth_inning_total_runs": "Eighth Inning Total Runs",
    "ninth_inning_total_runs": "Ninth Inning Total Runs",
    "team_total_runs": "Team Total Runs",
    "team_first_to_score": "Team First To Score",
}

TEAM_ABBRS = {
    "ARI", "ATL", "BAL", "BOS", "CHC", "CWS", "CHW", "CIN", "CLE", "COL", "DET",
    "HOU", "KC", "KCR", "LAA", "LAD", "MIA", "MIL", "MIN", "NYM", "NYY", "ATH", "OAK",
    "PHI", "PIT", "SD", "SDP", "SEA", "SF", "SFG", "STL", "TB", "TBR", "TEX", "TOR",
    "WSH", "WSN",
}

TEAM_ALIASES = {
    "CHW": "CWS",
    "KCR": "KC",
    "SDP": "SD",
    "SFG": "SF",
    "TBR": "TB",
    "WSN": "WSH",
    "OAK": "ATH",
}

_CSV_CACHE: dict[tuple[str, int, int], list[dict[str, str]]] = {}
_FIXTURE_CACHE: dict[str, tuple[str, str]] = {}


def clean(value: Any) -> str:
    return str(value or "").strip()


def norm_team(value: Any) -> str:
    text = clean(value).upper()
    return TEAM_ALIASES.get(text, text)


def to_float(value: Any, default: float = 0.0) -> float:
    text = clean(value).replace(",", "")
    if not text:
        return default
    try:
        return float(text)
    except Exception:
        return default


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    stat = path.stat()
    key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    cached = _CSV_CACHE.get(key)
    if cached is not None:
        return cached
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    _CSV_CACHE[key] = rows
    return rows


def normalize_market(value: Any) -> str:
    text = clean(value).lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "money_line": "moneyline",
        "ml": "moneyline",
        "runline": "run_line",
        "spread": "run_line",
        "spreads": "run_line",
        "game_total": "game_total_runs",
        "total_runs": "game_total_runs",
        "first_inning_total": "first_inning_total_runs",
        "first_inning_o_u": "first_inning_total_runs",
        "first_5_total": "first_five_total_runs",
        "first_five_total": "first_five_total_runs",
        "team_total": "team_total_runs",
        "team_totals": "team_total_runs",
    }
    return aliases.get(text, text)



def infer_specific_market(raw_market: Any, market_name: Any) -> str:
    """Convert generic OddsPapi totals/spreads into specific inning markets."""
    market = normalize_market(raw_market)
    name = clean(market_name).lower()

    total_by_name = {
        "over under first inning": "first_inning_total_runs",
        "over under second inning": "second_inning_total_runs",
        "over under third inning": "third_inning_total_runs",
        "over under fourth inning": "fourth_inning_total_runs",
        "over under fifth inning": "fifth_inning_total_runs",
        "over under sixth inning": "sixth_inning_total_runs",
        "over under seventh inning": "seventh_inning_total_runs",
        "over under eighth inning": "eighth_inning_total_runs",
        "over under ninth inning": "ninth_inning_total_runs",
        "over under first to fifth inning": "first_five_total_runs",
    }

    spread_by_name = {
        "handicap first inning": "run_line_first_inning",
        "handicap second inning": "run_line_second_inning",
        "handicap third inning": "run_line_third_inning",
        "handicap fourth inning": "run_line_fourth_inning",
        "handicap fifth inning": "run_line_fifth_inning",
        "handicap sixth inning": "run_line_sixth_inning",
        "handicap seventh inning": "run_line_seventh_inning",
        "handicap eighth inning": "run_line_eighth_inning",
        "handicap ninth inning": "run_line_ninth_inning",
        "handicap first to fifth inning": "run_line_first_five",
    }

    if market == "game_total_runs":
        return total_by_name.get(name, market)

    if market == "run_line":
        return spread_by_name.get(name, market)

    return market


def market_label(market: Any, side: Any = "") -> str:
    market = normalize_market(market)
    label = TEAM_GAME_MARKET_LABELS.get(market, market.replace("_", " ").title())
    side_text = clean(side)
    if side_text:
        return f"{label} - {side_text}"
    return label


def latest_market_files() -> list[Path]:
    if not ODDSPAPI_DIR.exists():
        return []

    patterns = [
        "historical_game_markets_pregame_latest_*.csv",
        "historical_team_props_pregame_latest_*.csv",
        "historical_team_props_one_fixture_pregame_latest.csv",
        "current_game_markets_latest_*.csv",
        "current_team_props_latest_*.csv",
    ]

    files: list[Path] = []
    seen = set()

    for pattern in patterns:
        for path in sorted(ODDSPAPI_DIR.glob(pattern)):
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            files.append(path)

    return files


def fixture_teams(fixture_id: str) -> tuple[str, str]:
    fixture_id = clean(fixture_id)
    if not fixture_id:
        return "", ""
    if fixture_id in _FIXTURE_CACHE:
        return _FIXTURE_CACHE[fixture_id]

    for path in ODDSPAPI_DIR.glob(f"historical_odds_{fixture_id}_*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        fixture = payload.get("fixture") or {}
        team1 = norm_team(fixture.get("participant1Abbr"))
        team2 = norm_team(fixture.get("participant2Abbr"))
        if team1 and team2:
            _FIXTURE_CACHE[fixture_id] = (team1, team2)
            return team1, team2

    return "", ""


def prop_identity(market: str, team: str, opponent: str, side: str) -> str:
    market = normalize_market(market)
    team = norm_team(team)
    opponent = norm_team(opponent)
    side = clean(side)

    if market in {
        "game_total_runs",
        "first_five_total_runs",
        "first_inning_total_runs",
        "second_inning_total_runs",
        "third_inning_total_runs",
        "fourth_inning_total_runs",
        "fifth_inning_total_runs",
        "sixth_inning_total_runs",
        "seventh_inning_total_runs",
        "eighth_inning_total_runs",
        "ninth_inning_total_runs",
    }:
        return f"{team} vs {opponent}" if team and opponent else "Game Total"
    if market == "team_first_to_score":
        return team or side or "First To Score"
    return team or f"{team} vs {opponent}".strip() or side


def normalize_side(row: dict[str, Any], team: str) -> str:
    outcome = clean(row.get("outcomeName"))
    market = normalize_market(row.get("market"))
    if market in {
        "moneyline",
        "moneyline_first_five",
        "run_line",
        "run_line_first_five",
        "run_line_first_inning",
        "run_line_second_inning",
        "run_line_third_inning",
        "run_line_fourth_inning",
        "run_line_fifth_inning",
        "run_line_sixth_inning",
        "run_line_seventh_inning",
        "run_line_eighth_inning",
        "run_line_ninth_inning",
        "team_first_to_score",
    }:
        return team or outcome
    if outcome.lower() in {"over", "under"}:
        return outcome.title()
    return outcome


def should_keep_outcome(market: str, side: str) -> bool:
    market = normalize_market(market)
    side = clean(side).lower()
    if market in {
        "game_total_runs",
        "first_five_total_runs",
        "first_inning_total_runs",
        "second_inning_total_runs",
        "third_inning_total_runs",
        "fourth_inning_total_runs",
        "fifth_inning_total_runs",
        "sixth_inning_total_runs",
        "seventh_inning_total_runs",
        "eighth_inning_total_runs",
        "ninth_inning_total_runs",
        "team_total_runs",
    }:
        return side in {"over", "under"}
    return True



def enrich_team_game_market_prediction(row: dict[str, Any]) -> dict[str, Any]:
    """Attach baseline model projection fields to a normalized team/game market row.

    If local generated model artifacts are unavailable, keep the row usable and
    expose modelAvailable=False instead of failing the UI/playerboard.
    """
    try:
        from team_game_market_predictor import predict_team_game_market
    except Exception:
        row.update({
            "projectedProbability": None,
            "sportsbookImpliedProbability": None,
            "edge": None,
            "edgePercent": None,
            "confidence": "Unavailable",
            "modelName": "",
            "modelAvailable": False,
        })
        return row

    try:
        season = int(clean(row.get("date"))[:4] or "2026")
    except Exception:
        season = 2026

    prediction_input = dict(row)
    prediction_input.setdefault("side", row.get("side") or row.get("rawLabel"))
    prediction_input.setdefault("outcomeName", row.get("rawLabel"))

    pred = predict_team_game_market(prediction_input, season=season)

    row.update({
        "projectedProbability": pred.get("projectedProbability"),
        "sportsbookImpliedProbability": pred.get("sportsbookImpliedProbability"),
        "edge": pred.get("edge"),
        "edgePercent": pred.get("edgePercent"),
        "finalEdgePercent": pred.get("edgePercent"),
        "confidence": pred.get("confidence", "Unavailable"),
        "modelName": pred.get("modelName", ""),
        "modelAvailable": bool(pred.get("modelAvailable")),
    })

    return row


def load_oddspapi_game_market_props(date_label: str, markets: set[str] | None = None, limit: int = 5000) -> list[dict[str, Any]]:
    """Load cached OddsPapi latest-pregame game/team markets as Playerboard props."""
    target_date = clean(date_label)[:10]
    market_set = {normalize_market(m) for m in (markets or TEAM_GAME_MARKETS)}
    rows: list[dict[str, Any]] = []

    for path in latest_market_files():
        for raw in read_rows(path):
            row_date = clean(raw.get("date"))[:10]
            if target_date and row_date != target_date:
                continue

            market = infer_specific_market(raw.get("market"), raw.get("marketName"))
            if market not in TEAM_GAME_MARKETS or market not in market_set:
                continue

            fixture_id = clean(raw.get("fixtureId"))
            team = norm_team(raw.get("team"))
            opponent = norm_team(raw.get("opponent"))

            if not team or not opponent:
                team1, team2 = fixture_teams(fixture_id)
                team = team or team1
                opponent = opponent or team2

            side = normalize_side(raw, team)
            if not should_keep_outcome(market, side):
                continue

            line = clean(raw.get("line"))
            if market in {"moneyline", "moneyline_first_five", "team_first_to_score"} and not line:
                line = "0"

            american = clean(raw.get("americanOdds"))
            if not american or not to_float(american):
                continue

            rows.append({
                "date": row_date,
                "market": market,
                "marketDisplay": market_label(market, side),
                "originalMarket": clean(raw.get("marketType")) or market,
                "rawLabel": side,
                "side": side,
                "marketFamily": "game" if market in {
                    "game_total_runs",
                    "first_five_total_runs",
                    "first_inning_total_runs",
                    "second_inning_total_runs",
                    "third_inning_total_runs",
                    "fourth_inning_total_runs",
                    "fifth_inning_total_runs",
                    "sixth_inning_total_runs",
                    "seventh_inning_total_runs",
                    "eighth_inning_total_runs",
                    "ninth_inning_total_runs",
                } else "team",
                "player": prop_identity(market, team, opponent, side),
                "team": team,
                "opponent": opponent,
                "pitcher": "",
                "line": line,
                "americanOdds": american,
                "bookmaker": clean(raw.get("bookmaker")),
                "fixtureId": fixture_id,
                "rawSource": str(path),
            })

    out: list[dict[str, Any]] = []
    seen = set()
    for row in rows:
        key = (
            clean(row.get("date")),
            clean(row.get("market")),
            clean(row.get("player")).lower(),
            clean(row.get("team")),
            clean(row.get("opponent")),
            clean(row.get("rawLabel")).lower(),
            clean(row.get("line")),
            clean(row.get("americanOdds")),
            clean(row.get("bookmaker")),
        )
        if key in seen:
            continue
        seen.add(key)
        row = enrich_team_game_market_prediction(row)
        out.append(row)
        if len(out) >= limit:
            break

    return out


def games_for_date(season: int, date_label: str) -> list[dict[str, str]]:
    rows = [
        row for row in read_rows(INCREMENTAL_DIR / f"games_{season}.csv")
        if clean(row.get("date")) == clean(date_label)
    ]
    if rows:
        return rows

    cloud_path = CLOUD_SUMMARY_DIR / f"games_{clean(date_label)[:10]}.json"
    if cloud_path.exists():
        try:
            payload = json.loads(cloud_path.read_text(encoding="utf-8"))
            return [dict(row) for row in payload if clean(row.get("date")) == clean(date_label)]
        except Exception:
            return []

    return []


def search_matchups(season: int, date_label: str, query: str, limit: int = 10) -> list[dict[str, Any]]:
    target = clean(query).upper().replace("@", " VS ").replace("-", " ")
    target_team = norm_team(query)
    if not target:
        return []

    matches = []
    for game in games_for_date(season, date_label):
        home = norm_team(game.get("home"))
        away = norm_team(game.get("away"))
        label = f"{away} vs {home}"
        haystack = f"{home} {away} {label}".upper()

        is_team_query = target_team in TEAM_ABBRS and target_team in {home, away}
        is_matchup_query = target in haystack or any(part in {home, away} for part in target.split())

        if not is_team_query and not is_matchup_query:
            continue

        if is_team_query:
            selected_team = target_team
            selected_opponent = away if target_team == home else home
            score = 95
            kind = "team"
            role = "Team"
        else:
            selected_team = away
            selected_opponent = home
            score = 90 if target in label.upper() else 70
            kind = "matchup"
            role = "Team Matchup"

        matches.append({
            "player": label if kind == "matchup" else selected_team,
            "team": selected_team,
            "opponent": selected_opponent,
            "kind": kind,
            "role": role,
            "score": score,
        })

    matches.sort(key=lambda item: (-int(item.get("score", 0)), item.get("player", "")))
    return matches[:limit]


def autofill_matchup(season: int, date_label: str, query: str) -> dict[str, Any]:
    matches = search_matchups(season, date_label, query, limit=8)
    if not matches:
        return {}

    match = matches[0]
    team = norm_team(match.get("team"))
    opponent = norm_team(match.get("opponent"))
    game = {}
    for row in games_for_date(season, date_label):
        if {norm_team(row.get("home")), norm_team(row.get("away"))} == {team, opponent}:
            game = row
            break

    home = norm_team(game.get("home"))
    away = norm_team(game.get("away"))
    display = f"{away} vs {home}" if away and home else clean(match.get("player"))

    return {
        "season": season,
        "date": date_label,
        "player": display,
        "playerId": "",
        "role": "team",
        "team": team,
        "opponent": opponent,
        "pitcher": "",
        "opposingPitcher": clean(game.get("homeProbablePitcher")) if team == away else clean(game.get("awayProbablePitcher")),
        "teamPitcher": clean(game.get("awayProbablePitcher")) if team == away else clean(game.get("homeProbablePitcher")),
        "home": home,
        "away": away,
        "venue": clean(game.get("venue")),
        "gamePk": clean(game.get("gamePk")),
        "gameDate": clean(game.get("gameDate")),
        "foundGame": True,
        "defaultMarket": "moneyline",
        "suggestedMarkets": [
            "moneyline",
            "run_line",
            "run_line_first_inning",
            "game_total_runs",
            "team_total_runs",
        ],
        "matches": matches,
        "summary": f"{display}" + (f", {clean(game.get('venue'))}" if clean(game.get("venue")) else ""),
    }

# Full-name and nickname aliases for streamlined team search.
# Appended after the original functions so norm_team can wrap the original implementation.
TEAM_NAME_ALIASES = {
    "ARIZONA DIAMONDBACKS": "AZ", "DIAMONDBACKS": "AZ", "D BACKS": "AZ", "DBACKS": "AZ",
    "ATHLETICS": "ATH", "OAKLAND ATHLETICS": "ATH", "A S": "ATH", "AS": "ATH",
    "ATLANTA BRAVES": "ATL", "BRAVES": "ATL",
    "BALTIMORE ORIOLES": "BAL", "ORIOLES": "BAL",
    "BOSTON RED SOX": "BOS", "RED SOX": "BOS",
    "CHICAGO CUBS": "CHC", "CUBS": "CHC",
    "CHICAGO WHITE SOX": "CWS", "WHITE SOX": "CWS", "CHW": "CWS",
    "CINCINNATI REDS": "CIN", "REDS": "CIN",
    "CLEVELAND GUARDIANS": "CLE", "GUARDIANS": "CLE",
    "COLORADO ROCKIES": "COL", "ROCKIES": "COL",
    "DETROIT TIGERS": "DET", "TIGERS": "DET",
    "HOUSTON ASTROS": "HOU", "ASTROS": "HOU",
    "KANSAS CITY ROYALS": "KC", "ROYALS": "KC", "KCR": "KC",
    "LOS ANGELES ANGELS": "LAA", "LA ANGELS": "LAA", "ANGELS": "LAA",
    "LOS ANGELES DODGERS": "LAD", "LA DODGERS": "LAD", "DODGERS": "LAD",
    "MIAMI MARLINS": "MIA", "MARLINS": "MIA",
    "MILWAUKEE BREWERS": "MIL", "BREWERS": "MIL",
    "MINNESOTA TWINS": "MIN", "TWINS": "MIN",
    "NEW YORK METS": "NYM", "METS": "NYM",
    "NEW YORK YANKEES": "NYY", "YANKEES": "NYY",
    "PHILADELPHIA PHILLIES": "PHI", "PHILLIES": "PHI",
    "PITTSBURGH PIRATES": "PIT", "PIRATES": "PIT",
    "SAN DIEGO PADRES": "SD", "PADRES": "SD", "SDP": "SD",
    "SAN FRANCISCO GIANTS": "SF", "GIANTS": "SF", "SFG": "SF",
    "SEATTLE MARINERS": "SEA", "MARINERS": "SEA",
    "ST LOUIS CARDINALS": "STL", "SAINT LOUIS CARDINALS": "STL", "CARDINALS": "STL",
    "TAMPA BAY RAYS": "TB", "RAYS": "TB", "TBR": "TB",
    "TEXAS RANGERS": "TEX", "RANGERS": "TEX",
    "TORONTO BLUE JAYS": "TOR", "BLUE JAYS": "TOR",
    "WASHINGTON NATIONALS": "WSH", "NATIONALS": "WSH", "WSN": "WSH",
}

_ORIGINAL_NORM_TEAM = norm_team

def _team_alias_key(value):
    text = str(value or "").upper().strip()
    text = text.replace(".", " ").replace("-", " ").replace("_", " ")
    text = text.replace("@", " VS ")
    for token in [",", "'", '"', "  "]:
        text = text.replace(token, " ")
    return " ".join(text.split())

def norm_team(value):
    key = _team_alias_key(value)
    if key in TEAM_NAME_ALIASES:
        return TEAM_NAME_ALIASES[key]
    return _ORIGINAL_NORM_TEAM(value)

