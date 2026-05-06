from __future__ import annotations

import argparse
import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent
ODDSPAPI_DIR = ROOT / "data" / "cache" / "oddspapi"
OUT_DIR = ODDSPAPI_DIR

MLB_STATS_API_BASE = "https://statsapi.mlb.com/api/v1"

TEAM_FIX = {
    "ARI": "AZ", "AZ": "AZ",
    "ATH": "ATH", "OAK": "ATH",
    "ATL": "ATL",
    "BAL": "BAL",
    "BOS": "BOS",
    "CHC": "CHC",
    "CHW": "CWS", "CWS": "CWS",
    "CIN": "CIN",
    "CLE": "CLE",
    "COL": "COL",
    "DET": "DET",
    "HOU": "HOU",
    "KCR": "KC", "KC": "KC",
    "LAA": "LAA",
    "LAD": "LAD",
    "MIA": "MIA",
    "MIL": "MIL",
    "MIN": "MIN",
    "NYM": "NYM",
    "NYY": "NYY",
    "PHI": "PHI",
    "PIT": "PIT",
    "SDP": "SD", "SD": "SD",
    "SFG": "SF", "SF": "SF",
    "SEA": "SEA",
    "STL": "STL",
    "TBR": "TB", "TB": "TB",
    "TEX": "TEX",
    "TOR": "TOR",
    "WSN": "WSH", "WSH": "WSH",
}

TEAM_NAME_TO_ABBR = {
    "Arizona Diamondbacks": "AZ",
    "Athletics": "ATH",
    "Oakland Athletics": "ATH",
    "Atlanta Braves": "ATL",
    "Baltimore Orioles": "BAL",
    "Boston Red Sox": "BOS",
    "Chicago Cubs": "CHC",
    "Chicago White Sox": "CWS",
    "Cincinnati Reds": "CIN",
    "Cleveland Guardians": "CLE",
    "Colorado Rockies": "COL",
    "Detroit Tigers": "DET",
    "Houston Astros": "HOU",
    "Kansas City Royals": "KC",
    "Los Angeles Angels": "LAA",
    "Los Angeles Dodgers": "LAD",
    "Miami Marlins": "MIA",
    "Milwaukee Brewers": "MIL",
    "Minnesota Twins": "MIN",
    "New York Mets": "NYM",
    "New York Yankees": "NYY",
    "Philadelphia Phillies": "PHI",
    "Pittsburgh Pirates": "PIT",
    "San Diego Padres": "SD",
    "San Francisco Giants": "SF",
    "Seattle Mariners": "SEA",
    "St. Louis Cardinals": "STL",
    "Saint Louis Cardinals": "STL",
    "Tampa Bay Rays": "TB",
    "Texas Rangers": "TEX",
    "Toronto Blue Jays": "TOR",
    "Washington Nationals": "WSH",
}


def clean(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def norm_team(value: Any) -> str:
    text = clean(value)
    if not text:
        return ""
    if text in TEAM_NAME_TO_ABBR:
        return TEAM_NAME_TO_ABBR[text]
    upper = text.upper().replace(".", "").strip()
    return TEAM_FIX.get(upper, upper)


def to_float(value: Any, default: float = math.nan) -> float:
    text = clean(value).replace("+", "")
    if not text:
        return default
    try:
        return float(text)
    except Exception:
        return default


def first_value(row: dict[str, Any], names: list[str]) -> Any:
    lower = {str(k).lower(): k for k in row.keys()}
    for name in names:
        key = lower.get(name.lower())
        if key is not None:
            value = row.get(key)
            if clean(value):
                return value
    return ""


def fetch_json(url: str, timeout: int = 30) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "New-project-OddsPapi-grader/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def mlb_schedule(date_label: str, cache_dir: Path) -> list[dict[str, Any]]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"statsapi_schedule_linescore_{date_label}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8")).get("dates", [{}])[0].get("games", [])

    params = urllib.parse.urlencode({
        "sportId": 1,
        "date": date_label,
        "hydrate": "linescore,team,probablePitcher",
    })
    url = f"{MLB_STATS_API_BASE}/schedule?{params}"
    payload = fetch_json(url)
    cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    time.sleep(0.2)
    return payload.get("dates", [{}])[0].get("games", [])


def inning_runs(linescore: dict[str, Any], side: str, start: int, end: int) -> int:
    total = 0
    for inning in linescore.get("innings", []) or []:
        num = int(inning.get("num", 0) or 0)
        if start <= num <= end:
            total += int((inning.get(side, {}) or {}).get("runs", 0) or 0)
    return total


def first_to_score(linescore: dict[str, Any], away: str, home: str) -> str:
    for inning in linescore.get("innings", []) or []:
        away_runs = int((inning.get("away", {}) or {}).get("runs", 0) or 0)
        home_runs = int((inning.get("home", {}) or {}).get("runs", 0) or 0)

        # Away bats top half, so if both score in inning, away scored first.
        if away_runs > 0:
            return away
        if home_runs > 0:
            return home

    return ""


def build_game_index(dates: list[str]) -> dict[tuple[str, str, str], dict[str, Any]]:
    index: dict[tuple[str, str, str], dict[str, Any]] = {}
    cache_dir = OUT_DIR / "statsapi_cache"

    for date_label in sorted(set(dates)):
        games = mlb_schedule(date_label, cache_dir)
        for game in games:
            status = ((game.get("status") or {}).get("codedGameState") or "").upper()
            if status not in {"F", "O"}:
                # F = final, O can appear for completed/official in some feeds.
                continue

            teams = game.get("teams", {}) or {}
            away_obj = ((teams.get("away") or {}).get("team") or {})
            home_obj = ((teams.get("home") or {}).get("team") or {})

            away = norm_team(away_obj.get("abbreviation") or away_obj.get("teamCode") or away_obj.get("name"))
            home = norm_team(home_obj.get("abbreviation") or home_obj.get("teamCode") or home_obj.get("name"))

            if not away or not home:
                continue

            away_score = int((teams.get("away") or {}).get("score", 0) or 0)
            home_score = int((teams.get("home") or {}).get("score", 0) or 0)
            linescore = game.get("linescore", {}) or {}

            away_1 = inning_runs(linescore, "away", 1, 1)
            home_1 = inning_runs(linescore, "home", 1, 1)
            away_5 = inning_runs(linescore, "away", 1, 5)
            home_5 = inning_runs(linescore, "home", 1, 5)

            record = {
                "gamePk": game.get("gamePk"),
                "date": date_label,
                "away": away,
                "home": home,
                "awayScore": away_score,
                "homeScore": home_score,
                "awayFirstInningRuns": away_1,
                "homeFirstInningRuns": home_1,
                "awayFirstFiveRuns": away_5,
                "homeFirstFiveRuns": home_5,
                "firstToScore": first_to_score(linescore, away, home),
            }

            index[(date_label, away, home)] = record
            index[(date_label, home, away)] = record

    return index


def row_date(row: dict[str, Any]) -> str:
    return clean(first_value(row, ["date", "gameDate", "commence_time", "startTime", "fixtureDate"]))[:10]


def row_teams(row: dict[str, Any]) -> tuple[str, str]:
    team = norm_team(first_value(row, [
        "team", "selectionTeam", "outcomeTeam", "sideTeam", "participantAbbr", "participant",
        "teamAbbr", "team_abbr",
    ]))
    opponent = norm_team(first_value(row, [
        "opponent", "opponentTeam", "opponentAbbr", "opponent_abbr",
    ]))

    away = norm_team(first_value(row, ["away", "awayTeam", "participant1Abbr", "participant1", "visitor"]))
    home = norm_team(first_value(row, ["home", "homeTeam", "participant2Abbr", "participant2"]))

    # If row has game teams but no selected team, infer selected team from outcome text.
    outcome_text = " ".join(clean(first_value(row, [
        "outcome", "outcomeName", "selection", "label", "name", "participantName"
    ])).upper().replace("-", " ").split())

    if not team and away and away in outcome_text:
        team = away
    if not team and home and home in outcome_text:
        team = home

    for full_name, abbr in TEAM_NAME_TO_ABBR.items():
        if not team and full_name.upper() in outcome_text:
            team = abbr

    # Some team-total rows preserve market type as teamtotals-team1/team2.
    market_type = clean(first_value(row, ["marketType", "rawMarketType", "oddspapiMarketType"])).lower()
    if not team and away and home:
        if "team1" in market_type:
            team = away
        elif "team2" in market_type:
            team = home

    if team and not opponent and away and home:
        opponent = home if team == away else away if team == home else ""

    return team, opponent


def row_side(row: dict[str, Any]) -> str:
    over_raw = clean(first_value(row, ["over", "isOver", "is_over"])).lower()
    if over_raw in {"1", "true", "yes", "over"}:
        return "over"
    if over_raw in {"0", "false", "no", "under"}:
        return "under"

    text = clean(first_value(row, ["side", "outcome", "outcomeName", "selection", "label", "name"])).lower()
    if "over" in text:
        return "over"
    if "under" in text:
        return "under"
    return ""


def row_line(row: dict[str, Any]) -> float:
    value = first_value(row, ["line", "point", "points", "handicap", "spread", "total", "value"])
    return to_float(value)


def grade_over_under(actual: float, line: float, side: str) -> tuple[str, int | None]:
    if math.isnan(line) or side not in {"over", "under"}:
        return "missing_line_or_side", None
    if actual == line:
        return "push", None
    won = actual > line if side == "over" else actual < line
    return ("won" if won else "lost"), int(won)


def grade_team_spread(team_score: float, opponent_score: float, line: float) -> tuple[str, int | None]:
    if math.isnan(line):
        return "missing_line", None
    adjusted = team_score + line
    if adjusted == opponent_score:
        return "push", None
    won = adjusted > opponent_score
    return ("won" if won else "lost"), int(won)


def grade_moneyline(team_score: float, opponent_score: float) -> tuple[str, int | None]:
    if team_score == opponent_score:
        return "push", None
    won = team_score > opponent_score
    return ("won" if won else "lost"), int(won)


def grade_row(row: dict[str, Any], game_index: dict[tuple[str, str, str], dict[str, Any]]) -> dict[str, Any]:
    market = clean(row.get("market")).lower()
    date_label = row_date(row)
    team, opponent = row_teams(row)

    away = norm_team(first_value(row, ["away", "awayTeam", "participant1Abbr", "participant1", "visitor"]))
    home = norm_team(first_value(row, ["home", "homeTeam", "participant2Abbr", "participant2"]))

    game = None
    if team and opponent:
        game = game_index.get((date_label, team, opponent))
    if game is None and away and home:
        game = game_index.get((date_label, away, home))
    if game is None:
        return {
            **row,
            "gradeStatus": "missing_final_game",
            "graded": 0,
            "actualStat": "",
            "result": "",
            "label": "",
            "gradedTeam": team,
            "gradedOpponent": opponent,
        }

    if not team:
        # Totals do not need team, but team markets do.
        if market not in {"game_total_runs", "first_inning_total_runs", "first_five_total_runs"}:
            return {
                **row,
                "gradeStatus": "missing_team",
                "graded": 0,
                "actualStat": "",
                "result": "",
                "label": "",
                "gradedTeam": "",
                "gradedOpponent": opponent,
            }

    if team and not opponent:
        opponent = game["home"] if team == game["away"] else game["away"] if team == game["home"] else ""

    side = row_side(row)
    line = row_line(row)

    is_away_team = team == game["away"]
    team_full = game["awayScore"] if is_away_team else game["homeScore"]
    opp_full = game["homeScore"] if is_away_team else game["awayScore"]

    team_1 = game["awayFirstInningRuns"] if is_away_team else game["homeFirstInningRuns"]
    opp_1 = game["homeFirstInningRuns"] if is_away_team else game["awayFirstInningRuns"]

    team_5 = game["awayFirstFiveRuns"] if is_away_team else game["homeFirstFiveRuns"]
    opp_5 = game["homeFirstFiveRuns"] if is_away_team else game["awayFirstFiveRuns"]

    actual = ""
    result = "unsupported_market"
    label = None

    if market == "moneyline":
        actual = team_full - opp_full
        result, label = grade_moneyline(team_full, opp_full)

    elif market == "moneyline_first_five":
        actual = team_5 - opp_5
        result, label = grade_moneyline(team_5, opp_5)

    elif market == "run_line":
        actual = team_full - opp_full
        result, label = grade_team_spread(team_full, opp_full, line)

    elif market == "run_line_first_inning":
        actual = team_1 - opp_1
        result, label = grade_team_spread(team_1, opp_1, line)

    elif market == "run_line_first_five":
        actual = team_5 - opp_5
        result, label = grade_team_spread(team_5, opp_5, line)

    elif market == "game_total_runs":
        actual = game["awayScore"] + game["homeScore"]
        result, label = grade_over_under(actual, line, side)

    elif market == "first_inning_total_runs":
        actual = game["awayFirstInningRuns"] + game["homeFirstInningRuns"]
        result, label = grade_over_under(actual, line, side)

    elif market == "first_five_total_runs":
        actual = game["awayFirstFiveRuns"] + game["homeFirstFiveRuns"]
        result, label = grade_over_under(actual, line, side)

    elif market == "team_total_runs":
        actual = team_full
        result, label = grade_over_under(actual, line, side)

    elif market == "team_first_to_score":
        actual = game["firstToScore"]
        if not actual:
            result, label = "no_score", None
        else:
            won = team == actual
            result, label = ("won" if won else "lost"), int(won)

    return {
        **row,
        "gradeStatus": "graded" if label is not None else result,
        "graded": 1 if label is not None else 0,
        "actualStat": actual,
        "result": result,
        "label": "" if label is None else label,
        "gradedTeam": team,
        "gradedOpponent": opponent,
        "away": game["away"],
        "home": game["home"],
        "awayScore": game["awayScore"],
        "homeScore": game["homeScore"],
        "awayFirstInningRuns": game["awayFirstInningRuns"],
        "homeFirstInningRuns": game["homeFirstInningRuns"],
        "awayFirstFiveRuns": game["awayFirstFiveRuns"],
        "homeFirstFiveRuns": game["homeFirstFiveRuns"],
        "firstToScore": game["firstToScore"],
    }



def repair_total_markets_by_fixture(out: pd.DataFrame) -> pd.DataFrame:
    """Grade total markets that lack team columns by using fixtureId context.

    OddsPapi total rows often carry fixtureId but no away/home/team/opponent.
    Team-side rows from the same fixture already have final game context after
    grading, so use them as the fixture-level map.
    """
    if "fixtureId" not in out.columns:
        return out

    total_markets = {"game_total_runs", "first_inning_total_runs", "first_five_total_runs"}

    fixture_games: dict[str, dict[str, Any]] = {}

    context_cols = [
        "fixtureId",
        "away",
        "home",
        "awayScore",
        "homeScore",
        "awayFirstInningRuns",
        "homeFirstInningRuns",
        "awayFirstFiveRuns",
        "homeFirstFiveRuns",
        "firstToScore",
    ]

    for _, row in out.iterrows():
        fixture_id = clean(row.get("fixtureId"))
        if not fixture_id or fixture_id in fixture_games:
            continue

        away = norm_team(row.get("away"))
        home = norm_team(row.get("home"))
        if not away or not home:
            continue

        try:
            fixture_games[fixture_id] = {col: row.get(col, "") for col in context_cols}
        except Exception:
            continue

    if not fixture_games:
        return out

    repaired = 0
    pushed = 0

    for idx in out.index:
        market = clean(out.at[idx, "market"]).lower() if "market" in out.columns else ""
        if market not in total_markets:
            continue

        status = clean(out.at[idx, "gradeStatus"])
        if status not in {"missing_final_game", "", "nan"}:
            continue

        fixture_id = clean(out.at[idx, "fixtureId"]) if "fixtureId" in out.columns else ""
        game = fixture_games.get(fixture_id)
        if not game:
            continue

        row_dict = out.loc[idx].to_dict()
        side = row_side(row_dict)
        line = row_line(row_dict)

        away_score = to_float(game.get("awayScore"), 0.0)
        home_score = to_float(game.get("homeScore"), 0.0)
        away_1 = to_float(game.get("awayFirstInningRuns"), 0.0)
        home_1 = to_float(game.get("homeFirstInningRuns"), 0.0)
        away_5 = to_float(game.get("awayFirstFiveRuns"), 0.0)
        home_5 = to_float(game.get("homeFirstFiveRuns"), 0.0)

        if market == "game_total_runs":
            actual = away_score + home_score
        elif market == "first_inning_total_runs":
            actual = away_1 + home_1
        elif market == "first_five_total_runs":
            actual = away_5 + home_5
        else:
            continue

        result, label = grade_over_under(actual, line, side)

        for col in [
            "away",
            "home",
            "awayScore",
            "homeScore",
            "awayFirstInningRuns",
            "homeFirstInningRuns",
            "awayFirstFiveRuns",
            "homeFirstFiveRuns",
            "firstToScore",
        ]:
            if col in out.columns:
                out.at[idx, col] = game.get(col, "")

        out.at[idx, "actualStat"] = actual
        out.at[idx, "result"] = result

        if label is None:
            out.at[idx, "graded"] = 0
            out.at[idx, "label"] = ""
            out.at[idx, "gradeStatus"] = result
            if result == "push":
                pushed += 1
        else:
            out.at[idx, "graded"] = 1
            out.at[idx, "label"] = label
            out.at[idx, "gradeStatus"] = "graded"
            repaired += 1

    print("fixture total repair map:", len(fixture_games))
    print("fixture total markets repaired:", repaired)
    print("fixture total market pushes:", pushed)

    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Grade OddsPapi MLB team/game markets with MLB StatsAPI finals.")
    parser.add_argument(
        "--input",
        default=str(ODDSPAPI_DIR / "historical_game_markets_pregame_latest_2026_season_deduped.csv"),
    )
    parser.add_argument(
        "--output",
        default=str(ODDSPAPI_DIR / "historical_game_markets_graded_2026.csv"),
    )
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--markets", default="")
    parser.add_argument("--max-rows", type=int, default=0)
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Missing input file: {input_path}")

    df = pd.read_csv(input_path)
    if args.max_rows:
        df = df.head(args.max_rows).copy()

    if "market" not in df.columns:
        raise SystemExit(f"Input missing market column. Columns: {list(df.columns)}")

    if args.markets:
        wanted = {m.strip() for m in args.markets.split(",") if m.strip()}
        df = df[df["market"].astype(str).isin(wanted)].copy()

    dates = sorted({str(x)[:10] for x in df.apply(lambda row: row_date(row.to_dict()), axis=1) if str(x)[:10]})
    print("input:", input_path)
    print("rows:", len(df))
    print("dates:", dates[:5], "..." if len(dates) > 5 else "", "count:", len(dates))

    game_index = build_game_index(dates)
    print("final game index entries:", len(game_index))

    records = []
    for _, row in df.iterrows():
        records.append(grade_row(row.to_dict(), game_index))

    out = pd.DataFrame(records)
    out = repair_total_markets_by_fixture(out)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False)

    graded = out[out["graded"].astype(str).eq("1")].copy()

    print()
    print("saved:", output_path)
    print("output rows:", len(out))
    print("graded rows:", len(graded))

    print()
    print("Grade status counts:")
    print(out["gradeStatus"].value_counts(dropna=False).to_string())

    if len(graded):
        print()
        print("Graded rows by market:")
        print(graded["market"].value_counts().to_string())

        print()
        print("Class counts by market:")
        print(
            graded.groupby(["market", "label"])
            .size()
            .reset_index(name="rows")
            .sort_values(["market", "label"])
            .to_string(index=False)
        )


if __name__ == "__main__":
    main()
