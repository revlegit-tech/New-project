from __future__ import annotations
from local_env import load_local_env
load_local_env()

"""Auto-fill game odds templates from PropLine.

Fills:
- team_moneyline
- opponent_moneyline
- game_total
- close_team_moneyline
- close_game_total
- favorite_status
- moneyline_implied_probability
- team_implied_runs / opponent_implied_runs proxy

If true open/close line movement is unavailable on the current API plan,
current PropLine odds are saved as the close/current line.
"""

import argparse
import csv
import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"

SPORT = "baseball_mlb"
GAME_MARKETS = ["h2h", "totals"]

TEAM_NAME_TO_ABBR = {
    "ARIZONA DIAMONDBACKS": "ARI",
    "ATLANTA BRAVES": "ATL",
    "BALTIMORE ORIOLES": "BAL",
    "BOSTON RED SOX": "BOS",
    "CHICAGO CUBS": "CHC",
    "CHICAGO WHITE SOX": "CHW",
    "CINCINNATI REDS": "CIN",
    "CLEVELAND GUARDIANS": "CLE",
    "COLORADO ROCKIES": "COL",
    "DETROIT TIGERS": "DET",
    "HOUSTON ASTROS": "HOU",
    "KANSAS CITY ROYALS": "KCR",
    "LOS ANGELES ANGELS": "LAA",
    "LOS ANGELES DODGERS": "LAD",
    "MIAMI MARLINS": "MIA",
    "MILWAUKEE BREWERS": "MIL",
    "MINNESOTA TWINS": "MIN",
    "NEW YORK METS": "NYM",
    "NEW YORK YANKEES": "NYY",
    "ATHLETICS": "ATH",
    "OAKLAND ATHLETICS": "ATH",
    "PHILADELPHIA PHILLIES": "PHI",
    "PITTSBURGH PIRATES": "PIT",
    "SAN DIEGO PADRES": "SDP",
    "SAN FRANCISCO GIANTS": "SFG",
    "SEATTLE MARINERS": "SEA",
    "ST. LOUIS CARDINALS": "STL",
    "SAINT LOUIS CARDINALS": "STL",
    "TAMPA BAY RAYS": "TBR",
    "TEXAS RANGERS": "TEX",
    "TORONTO BLUE JAYS": "TOR",
    "WASHINGTON NATIONALS": "WSN",
}

TEAM_ALIASES = {
    "ARI": "ARI",
    "ATL": "ATL",
    "BAL": "BAL",
    "BOS": "BOS",
    "CHC": "CHC",
    "CHI CUBS": "CHC",
    "CHW": "CHW",
    "CWS": "CHW",
    "CHI WHITE SOX": "CHW",
    "CIN": "CIN",
    "CLE": "CLE",
    "COL": "COL",
    "DET": "DET",
    "HOU": "HOU",
    "KCR": "KCR",
    "KC": "KCR",
    "LAA": "LAA",
    "LAD": "LAD",
    "LA DODGERS": "LAD",
    "LOS": "LAD",
    "MIA": "MIA",
    "MIL": "MIL",
    "MIN": "MIN",
    "NYM": "NYM",
    "NYY": "NYY",
    "NEW": "NYY",
    "ATH": "ATH",
    "OAK": "ATH",
    "PHI": "PHI",
    "PIT": "PIT",
    "SDP": "SDP",
    "SD": "SDP",
    "SAN": "SDP",
    "SFG": "SFG",
    "SF": "SFG",
    "SEA": "SEA",
    "STL": "STL",
    "ST.": "STL",
    "TBR": "TBR",
    "TB": "TBR",
    "TAM": "TBR",
    "TEX": "TEX",
    "TOR": "TOR",
    "WSN": "WSN",
    "WSH": "WSN",
    "WAS": "WSN",
}


REQUIRED_COLUMNS = [
    "team_moneyline",
    "opponent_moneyline",
    "game_total",
    "open_team_moneyline",
    "close_team_moneyline",
    "moneyline_move",
    "open_game_total",
    "close_game_total",
    "total_move",
    "moneyline_implied_probability",
    "favorite_status",
    "team_implied_runs",
    "opponent_implied_runs",
    "opponent_implied_runs_proxy",
]


def load_env() -> None:
    if not ENV_FILE.exists():
        return

    for line in ENV_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_lookup(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", clean_text(value).upper()).strip()


def normalize_team(value: Any) -> str:
    text = normalize_lookup(value)

    if not text:
        return ""

    if text in TEAM_NAME_TO_ABBR:
        return TEAM_NAME_TO_ABBR[text]

    if text in TEAM_ALIASES:
        return TEAM_ALIASES[text]

    for name, abbr in TEAM_NAME_TO_ABBR.items():
        if text == name or text in name or name in text:
            return abbr

    compact = text.replace(" ", "")
    if compact in TEAM_ALIASES:
        return TEAM_ALIASES[compact]

    return TEAM_ALIASES.get(text[:3], text[:3])


def to_float(value: Any, default: float = 0.0) -> float:
    """Convert numeric text to float, returning default for missing/invalid values.
    
    This helper is for aggregation/reporting where default=0.0 is intentional.
    Do not use it for ML feature extraction when missingness must stay explicit;
    use ml_prop_model.to_float() or a nullable parser instead.
    """
    text = clean_text(value).replace(",", "")
    if not text:
        return default

    try:
        return float(text)
    except ValueError:
        return default


def to_int_or_blank(value: Any) -> str:
    number = to_float(value, 0.0)
    if not number:
        return ""

    if int(number) == number:
        return str(int(number))

    return str(number)


def implied_probability_from_american(odds: float) -> float:
    if odds < 0:
        return abs(odds) / (abs(odds) + 100.0)
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return 0.5


def favorite_status(team_ml: float, opponent_ml: float) -> str:
    if not team_ml or not opponent_ml:
        return ""

    if team_ml < opponent_ml:
        return "favorite"

    if team_ml > opponent_ml:
        return "underdog"

    return "even"


def first_value(row: dict[str, Any], keys: list[str], default: Any = "") -> Any:
    lowered = {str(k).lower(): v for k, v in row.items()}

    for key in keys:
        if key in row and clean_text(row[key]):
            return row[key]

        low = key.lower()
        if low in lowered and clean_text(lowered[low]):
            return lowered[low]

    return default


def extract_event_id(row: dict[str, Any]) -> str:
    return clean_text(first_value(row, ["eventId", "event_id", "id", "gameId", "game_id"]))


def extract_market(row: dict[str, Any]) -> str:
    return clean_text(first_value(row, ["market", "marketKey", "market_key"])).lower()


def extract_home_team(row: dict[str, Any]) -> str:
    return normalize_team(first_value(row, ["homeTeam", "home_team", "home"]))


def extract_away_team(row: dict[str, Any]) -> str:
    return normalize_team(first_value(row, ["awayTeam", "away_team", "away"]))


def extract_selection(row: dict[str, Any]) -> str:
    return clean_text(first_value(row, [
        "selection",
        "outcome",
        "name",
        "side",
        "team",
        "label",
        "description",
        "player",
    ]))


def extract_price(row: dict[str, Any]) -> float:
    return to_float(first_value(row, [
        "american_odds",
        "americanOdds",
        "price",
        "odds",
        "moneyline",
    ]))


def extract_line(row: dict[str, Any]) -> float:
    return to_float(first_value(row, [
        "line",
        "point",
        "points",
        "total",
        "game_total",
    ]))


def selection_to_team(row: dict[str, Any], home: str, away: str) -> str:
    selection = extract_selection(row)
    normalized = normalize_team(selection)

    if normalized in {home, away}:
        return normalized

    text = normalize_lookup(selection)

    # Some APIs return side = home/away.
    if text == "HOME":
        return home

    if text == "AWAY":
        return away

    # Some APIs return the full team name elsewhere.
    for key in ["teamName", "outcomeName", "participant", "competitor"]:
        candidate = normalize_team(row.get(key))
        if candidate in {home, away}:
            return candidate

    return ""


def event_pair_key(team_a: str, team_b: str) -> tuple[str, str]:
    return tuple(sorted([team_a, team_b]))


def pull_propline_game_odds(date_label: str = "") -> dict[str, Any]:
    load_env()

    api_key = os.environ.get("PROPLINE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("PROPLINE_API_KEY is missing. Add it to your .env file.")

    try:
        from propline import PropLine
    except ImportError as error:
        raise RuntimeError("Install PropLine first: python -m pip install propline") from error

    client = PropLine(api_key)
    events = client.get_events(SPORT)

    moneylines_by_event: dict[str, dict[str, float]] = defaultdict(dict)
    totals_by_event: dict[str, float] = {}
    event_pairs: dict[str, tuple[str, str]] = {}
    moneylines_by_pair: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    totals_by_pair: dict[tuple[str, str], float] = {}

    odds_rows_read = 0
    events_with_odds = 0
    errors: list[str] = []

    for event in events:
        event_id = clean_text(event.get("id") or event.get("eventId"))
        home = normalize_team(event.get("home_team") or event.get("homeTeam"))
        away = normalize_team(event.get("away_team") or event.get("awayTeam"))

        if home and away:
            event_pairs[event_id] = (home, away)

        try:
            odds_rows = client.get_odds(SPORT, event_id=event_id, markets=GAME_MARKETS) or []
        except Exception as error:
            errors.append(f"{event_id}: {error}")
            continue

        if odds_rows:
            events_with_odds += 1

        for row in odds_rows:
            if not isinstance(row, dict):
                continue

            odds_rows_read += 1

            row_event_id = extract_event_id(row) or event_id
            row_home = extract_home_team(row) or home
            row_away = extract_away_team(row) or away
            market = extract_market(row)

            if row_home and row_away:
                event_pairs[row_event_id] = (row_home, row_away)

            if market == "h2h":
                team = selection_to_team(row, row_home, row_away)
                price = extract_price(row)

                if team and price:
                    moneylines_by_event[row_event_id][team] = price

                    if row_home and row_away:
                        moneylines_by_pair[event_pair_key(row_home, row_away)][team] = price

            elif market == "totals":
                line = extract_line(row)

                # Either over or under should have the same game total. Take the first usable one.
                if line:
                    totals_by_event.setdefault(row_event_id, line)

                    if row_home and row_away:
                        totals_by_pair.setdefault(event_pair_key(row_home, row_away), line)

    return {
        "events": events,
        "eventsRead": len(events),
        "eventsWithOdds": events_with_odds,
        "oddsRowsRead": odds_rows_read,
        "moneylinesByEvent": moneylines_by_event,
        "totalsByEvent": totals_by_event,
        "eventPairs": event_pairs,
        "moneylinesByPair": moneylines_by_pair,
        "totalsByPair": totals_by_pair,
        "errors": errors[:10],
    }


def add_required_columns(fieldnames: list[str]) -> list[str]:
    output = list(fieldnames)

    for column in REQUIRED_COLUMNS:
        if column not in output:
            output.append(column)

    return output


def estimate_implied_runs(game_total: float, team_ml: float, opponent_ml: float) -> tuple[float, float]:
    if not game_total:
        return 0.0, 0.0

    if not team_ml or not opponent_ml:
        half = round(game_total / 2.0, 2)
        return half, half

    team_prob = implied_probability_from_american(team_ml)
    opp_prob = implied_probability_from_american(opponent_ml)
    diff = max(min(team_prob - opp_prob, 0.20), -0.20)

    # Small proxy adjustment. This is not a sportsbook team total, but it gives
    # the model a directional signal until real implied team totals are available.
    team_runs = round(game_total / 2.0 + diff * 2.0, 2)
    opp_runs = round(game_total - team_runs, 2)
    return team_runs, opp_runs


def autofill_template(template_path: Path, date_label: str = "") -> dict[str, Any]:
    if not template_path.exists():
        raise FileNotFoundError(f"Missing game odds template: {template_path}")

    pulled = pull_propline_game_odds(date_label)

    with template_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = add_required_columns(reader.fieldnames or [])

    updated_rows = 0
    rows_with_moneyline = 0
    rows_with_total = 0
    missing_rows: list[dict[str, str]] = []

    for row in rows:
        team = normalize_team(first_value(row, ["team", "Team"]))
        opponent = normalize_team(first_value(row, ["opponent", "Opponent", "opp"]))

        event_id = clean_text(first_value(row, ["event_id", "eventId", "game_pk", "gamePk"]))

        moneylines = {}
        total = 0.0

        if event_id and event_id in pulled["moneylinesByEvent"]:
            moneylines = pulled["moneylinesByEvent"].get(event_id, {})
            total = pulled["totalsByEvent"].get(event_id, 0.0)

        if not moneylines and team and opponent:
            pair = event_pair_key(team, opponent)
            moneylines = pulled["moneylinesByPair"].get(pair, {})
            total = pulled["totalsByPair"].get(pair, 0.0)

        team_ml = moneylines.get(team, 0.0)
        opponent_ml = moneylines.get(opponent, 0.0)

        if team_ml:
            row["team_moneyline"] = to_int_or_blank(team_ml)
            row["close_team_moneyline"] = row.get("close_team_moneyline") or to_int_or_blank(team_ml)
            rows_with_moneyline += 1

        if opponent_ml:
            row["opponent_moneyline"] = to_int_or_blank(opponent_ml)

        if total:
            row["game_total"] = str(total)
            row["close_game_total"] = row.get("close_game_total") or str(total)
            rows_with_total += 1

        open_team = to_float(row.get("open_team_moneyline"))
        close_team = to_float(row.get("close_team_moneyline"))
        if open_team and close_team:
            row["moneyline_move"] = str(round(close_team - open_team, 2))
        else:
            row.setdefault("moneyline_move", "")

        open_total = to_float(row.get("open_game_total"))
        close_total = to_float(row.get("close_game_total"))
        if open_total and close_total:
            row["total_move"] = str(round(close_total - open_total, 2))
        else:
            row.setdefault("total_move", "")

        if team_ml:
            row["moneyline_implied_probability"] = str(round(implied_probability_from_american(team_ml), 4))

        if team_ml and opponent_ml:
            row["favorite_status"] = favorite_status(team_ml, opponent_ml)

        if total:
            team_runs, opp_runs = estimate_implied_runs(total, team_ml, opponent_ml)
            row["team_implied_runs"] = str(team_runs) if team_runs else ""
            row["opponent_implied_runs"] = str(opp_runs) if opp_runs else ""
            row["opponent_implied_runs_proxy"] = row["opponent_implied_runs"]

        if team_ml or opponent_ml or total:
            updated_rows += 1
        else:
            missing_rows.append({
                "team": team,
                "opponent": opponent,
                "eventId": event_id,
            })

    with template_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in fieldnames})

    return {
        "date": date_label,
        "templatePath": str(template_path),
        "rows": len(rows),
        "updatedRows": updated_rows,
        "rowsWithMoneyline": rows_with_moneyline,
        "rowsWithTotal": rows_with_total,
        "eventsRead": pulled["eventsRead"],
        "eventsWithOdds": pulled["eventsWithOdds"],
        "oddsRowsRead": pulled["oddsRowsRead"],
        "missingRows": missing_rows[:20],
        "errors": pulled["errors"],
        "lineMovement": {
            "available": False,
            "note": "Current odds were saved as close/current odds. True open/close movement requires a historical line-movement source or PropLine plan access that exposes it.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-fill game odds template from PropLine h2h/totals.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--template", default="")
    args = parser.parse_args()

    template = Path(args.template) if args.template else Path("data/imports") / f"game_odds_template_{args.date}.csv"

    summary = autofill_template(template, args.date)

    for key, value in summary.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
