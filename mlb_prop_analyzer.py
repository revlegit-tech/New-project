from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import app


STAKE_SIZES = (3, 10, 20)
DEFAULT_REPORT_DIR = app.DATA_DIR / "prop_reports"


@dataclass
class ScheduleGame:
    game_id: str = ""
    game_date: str = ""
    away_team: str = ""
    home_team: str = ""
    away_name: str = ""
    home_name: str = ""
    away_probable_pitcher: str = ""
    home_probable_pitcher: str = ""
    venue: str = ""
    status: str = ""
    source: str = ""

    def opponent_for(self, team_code: str) -> str:
        if team_code == self.away_team:
            return self.home_team
        if team_code == self.home_team:
            return self.away_team
        return ""

    def probable_pitcher_for(self, team_code: str) -> str:
        if team_code == self.away_team:
            return self.away_probable_pitcher
        if team_code == self.home_team:
            return self.home_probable_pitcher
        return ""


@dataclass
class ContextOverrides:
    probable_by_team: dict[str, str] = field(default_factory=dict)
    team_k_rate: dict[str, float] = field(default_factory=dict)
    weather_rows: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class AnalyzerData:
    players: list[app.Player]
    opponents: list[dict[str, Any]]
    game_logs: list[dict[str, Any]]
    pitching_game_logs: list[dict[str, Any]]
    team_game_logs: list[dict[str, Any]]
    team_batting: list[dict[str, Any]]
    pitching: list[dict[str, Any]]
    batting_against: list[dict[str, Any]]
    team_batting_against: list[dict[str, Any]]
    team_advanced_pitching: list[dict[str, Any]]
    player_advanced_pitching: list[dict[str, Any]]
    team_standard_pitching: list[dict[str, Any]]
    batter_pitcher_advanced: list[dict[str, Any]]

    @classmethod
    def from_app(cls) -> "AnalyzerData":
        return cls(
            players=app.load_players(),
            opponents=app.load_opponents(),
            game_logs=app.load_game_logs(),
            pitching_game_logs=app.load_pitching_game_logs(),
            team_game_logs=app.load_team_game_logs(),
            team_batting=app.load_team_batting(),
            pitching=app.load_pitching(),
            batting_against=app.load_batting_against(),
            team_batting_against=app.load_team_batting_against(),
            team_advanced_pitching=app.load_team_advanced_pitching(),
            player_advanced_pitching=app.load_player_advanced_pitching(),
            team_standard_pitching=app.load_team_standard_pitching(),
            batter_pitcher_advanced=app.load_batter_pitcher_advanced(),
        )


TEAM_NAME_TO_CODE = {code.lower(): code for code in app.TEAM_NAMES}
for team_code, team_name in app.TEAM_NAMES.items():
    TEAM_NAME_TO_CODE[team_name.lower()] = team_code
    TEAM_NAME_TO_CODE[team_name.replace(".", "").lower()] = team_code
TEAM_NAME_TO_CODE.update(
    {
        "arizona": "ARI",
        "atlanta": "ATL",
        "baltimore": "BAL",
        "boston": "BOS",
        "chicago cubs": "CHC",
        "cubs": "CHC",
        "chicago white sox": "CHW",
        "white sox": "CHW",
        "cincinnati": "CIN",
        "cleveland": "CLE",
        "colorado": "COL",
        "detroit": "DET",
        "houston": "HOU",
        "kansas city": "KCR",
        "los angeles angels": "LAA",
        "angels": "LAA",
        "los angeles dodgers": "LAD",
        "dodgers": "LAD",
        "miami": "MIA",
        "milwaukee": "MIL",
        "minnesota": "MIN",
        "new york mets": "NYM",
        "mets": "NYM",
        "new york yankees": "NYY",
        "yankees": "NYY",
        "philadelphia": "PHI",
        "pittsburgh": "PIT",
        "san diego": "SDP",
        "padres": "SDP",
        "san francisco": "SFG",
        "giants": "SFG",
        "seattle": "SEA",
        "st louis": "STL",
        "st. louis": "STL",
        "tampa bay": "TBR",
        "texas": "TEX",
        "toronto": "TOR",
        "washington": "WSN",
    }
)


def first_value(row: dict[str, Any], names: Iterable[str]) -> str:
    lowered = {str(key).strip().lower(): value for key, value in row.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def normalize_team(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    code = app.normalize_team_code(text)
    if code in app.TEAM_NAMES:
        return code
    compact = text.replace(".", "").lower()
    return TEAM_NAME_TO_CODE.get(compact, TEAM_NAME_TO_CODE.get(text.lower(), code))


def normalize_name(value: Any) -> str:
    return app.clean_name(str(value or "")).strip()


def name_key(value: Any) -> str:
    return "".join(ch for ch in normalize_name(value).lower() if ch.isalnum())


def parse_float(value: Any, default: float = 0.0) -> float:
    return app.to_float(value, default)


def parse_american(value: Any, default: int = -110) -> int:
    text = str(value or "").strip().replace("−", "-")
    if not text:
        return default
    if text.lower() in {"even", "ev", "pk"}:
        return 100
    return app.to_int(text.replace("+", ""), default)


def table_to_csv(path: Path) -> str:
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    if path.suffix.lower() == ".json":
        payload = json.loads(raw)
        if isinstance(payload, dict):
            for key in ["rows", "data", "props", "odds", "projections", "players"]:
                if isinstance(payload.get(key), list):
                    payload = payload[key]
                    break
        if not isinstance(payload, list):
            return ""
        fieldnames: list[str] = []
        for row in payload:
            if isinstance(row, dict):
                for key in row:
                    if key not in fieldnames:
                        fieldnames.append(key)
        output = []
        from io import StringIO

        buffer = StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        for row in payload:
            if isinstance(row, dict):
                writer.writerow(row)
        output.append(buffer.getvalue())
        return "".join(output)
    if path.suffix.lower() in {".html", ".htm"}:
        return app.html_table_to_csv(raw)
    return raw


def read_rows(path: Path) -> list[dict[str, str]]:
    return app.normalize_rows(table_to_csv(path))


def merge_players(players: list[app.Player]) -> list[app.Player]:
    merged: dict[str, app.Player] = {}
    for player in players:
        key = player.player_id.strip() or f"{name_key(player.player)}|{normalize_team(player.team)}"
        if key.strip("|"):
            merged[key] = player
    return list(merged.values())


def merge_records(records: list[dict[str, Any]], key_fields: list[str]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for record in records:
        key_parts = [str(record.get(field, "")).strip().lower() for field in key_fields]
        key = "|".join(key_parts)
        if key.strip("|"):
            merged[key] = {**merged.get(key, {}), **record}
    return list(merged.values())


def parse_prop_market(row: dict[str, Any]) -> str:
    text = " ".join(
        [
            first_value(row, ["Market", "Prop", "Bet Type", "Type", "Target", "Stat"]),
            first_value(row, ["Description", "Name"]),
        ]
    ).lower()
    text = text.replace("_", " ").replace("-", " ")
    if "home run" in text or text.strip() in {"hr", "hrs"} or "to homer" in text:
        return "homeRuns"
    if ("strikeout" in text or " ks" in f" {text} " or text.strip() in {"k", "ks"}) and "batter" not in text:
        return "pitcherStrikeouts"
    return ""


def parse_prop_rows(rows: Iterable[dict[str, Any]], source_name: str = "input") -> list[dict[str, Any]]:
    props: list[dict[str, Any]] = []
    for row in rows:
        market = parse_prop_market(row)
        if not market:
            continue
        side = first_value(row, ["Side", "Bet", "Selection", "Over/Under", "OU"]).lower()
        if side and side not in {"over", "yes", "y", "to hit", "to record"}:
            continue
        player = normalize_name(first_value(row, ["Player", "Batter", "Pitcher", "Name", "Participant"]))
        pitcher = normalize_name(first_value(row, ["Pitcher", "Starting Pitcher", "Probable Pitcher"]))
        if market == "pitcherStrikeouts" and pitcher and not player:
            player = pitcher
        team = normalize_team(first_value(row, ["Team", "Tm", "Player Team", "Pitcher Team"]))
        opponent = normalize_team(first_value(row, ["Opponent", "Opp", "Opp Team", "Against"]))
        line = parse_float(first_value(row, ["Line", "Prop Line", "Total", "Strikeout Line", "K Line"]), 0.5)
        if market == "homeRuns" and line <= 0:
            line = 0.5
        odds = parse_american(first_value(row, ["Odds", "American Odds", "Price", "Over Odds", "Yes Odds"]), -110)
        if not player:
            continue
        props.append(
            {
                "market": market,
                "player": player,
                "team": team,
                "opponent": opponent,
                "pitcher": pitcher,
                "line": line,
                "odds": odds,
                "book": first_value(row, ["Book", "Sportsbook", "Source"]) or source_name,
                "sourceFile": source_name,
                "raw": row,
            }
        )
    return props


def parse_prop_odds(paths: list[Path]) -> list[dict[str, Any]]:
    props: list[dict[str, Any]] = []
    for path in paths:
        props.extend(parse_prop_rows(read_rows(path), str(path)))
    return props


def parse_context_file(path: Path, source_name: str) -> ContextOverrides:
    overrides = ContextOverrides()
    for row in read_rows(path):
        home_team = normalize_team(first_value(row, ["Home Team", "Home", "HomeTeam"]))
        away_team = normalize_team(first_value(row, ["Away Team", "Away", "AwayTeam"]))
        if home_team:
            pitcher = normalize_name(first_value(row, ["Home Probable Pitcher", "Home Starter", "Home Pitcher"]))
            if pitcher:
                overrides.probable_by_team[home_team] = pitcher
        if away_team:
            pitcher = normalize_name(first_value(row, ["Away Probable Pitcher", "Away Starter", "Away Pitcher"]))
            if pitcher:
                overrides.probable_by_team[away_team] = pitcher
        if home_team:
            home_k_rate = app.to_rate(first_value(row, ["Home K%", "Home SO%", "Home Strikeout Rate"]))
            if home_k_rate:
                overrides.team_k_rate[home_team] = home_k_rate
        if away_team:
            away_k_rate = app.to_rate(first_value(row, ["Away K%", "Away SO%", "Away Strikeout Rate"]))
            if away_k_rate:
                overrides.team_k_rate[away_team] = away_k_rate

        team = normalize_team(first_value(row, ["Team", "Tm", "Player Team", "Pitcher Team"]))
        pitcher = normalize_name(first_value(row, ["Probable Pitcher", "Starting Pitcher", "Starter"]))
        if team and pitcher:
            overrides.probable_by_team[team] = pitcher

        k_team = team or normalize_team(first_value(row, ["Opponent", "Opp"]))
        k_rate = app.to_rate(first_value(row, ["K%", "SO%", "Strikeout Rate", "Team K%", "Opponent K%"]))
        if k_team and k_rate:
            overrides.team_k_rate[k_team] = k_rate

        if any(first_value(row, names) for names in WEATHER_FIELD_GROUPS):
            weather = dict(row)
            weather["_source"] = source_name
            if team:
                weather["_team"] = team
            if home_team:
                weather["_homeTeam"] = home_team
            if away_team:
                weather["_awayTeam"] = away_team
            overrides.weather_rows.append(weather)
    if overrides.probable_by_team or overrides.team_k_rate or overrides.weather_rows:
        overrides.notes.append(f"Loaded {source_name} context from {path.name}.")
    return overrides


WEATHER_FIELD_GROUPS = [
    ["Temperature", "Temp"],
    ["Wind MPH", "Wind Speed", "Wind"],
    ["Wind Direction", "Wind Dir"],
    ["Roof", "Dome"],
    ["Park Factor", "HR Park Factor"],
    ["HR Adjustment", "Home Run Adjustment"],
    ["Pitcher K Adjustment", "K Adjustment"],
]


def combine_overrides(overrides: Iterable[ContextOverrides]) -> ContextOverrides:
    combined = ContextOverrides()
    for item in overrides:
        combined.probable_by_team.update({key: value for key, value in item.probable_by_team.items() if value})
        combined.team_k_rate.update({key: value for key, value in item.team_k_rate.items() if value})
        combined.weather_rows.extend(item.weather_rows)
        combined.notes.extend(item.notes)
    return combined


def schedule_date_text(value: str) -> str:
    if not value or value.lower() == "today":
        return date.today().isoformat()
    parsed = app.parse_game_date(value)
    if parsed != datetime.min:
        return parsed.date().isoformat()
    return value


def statsapi_schedule(date_text: str) -> tuple[list[ScheduleGame], list[str]]:
    notes: list[str] = []
    games: list[ScheduleGame] = []
    try:
        import statsapi  # type: ignore

        query_date = datetime.strptime(date_text, "%Y-%m-%d").strftime("%m/%d/%Y")
        for item in statsapi.schedule(date=query_date, sportId=1):
            games.append(
                ScheduleGame(
                    game_id=str(item.get("game_id", "")),
                    game_date=str(item.get("game_date") or date_text),
                    away_team=normalize_team(item.get("away_name")),
                    home_team=normalize_team(item.get("home_name")),
                    away_name=str(item.get("away_name", "")),
                    home_name=str(item.get("home_name", "")),
                    away_probable_pitcher=normalize_name(item.get("away_probable_pitcher")),
                    home_probable_pitcher=normalize_name(item.get("home_probable_pitcher")),
                    venue=str(item.get("venue_name", "")),
                    status=str(item.get("status", "")),
                    source="toddrob99/MLB-StatsAPI",
                )
            )
        notes.append(f"Loaded {len(games)} scheduled game(s) from toddrob99/MLB-StatsAPI.")
        return games, notes
    except Exception as error:
        notes.append(f"toddrob99/MLB-StatsAPI schedule unavailable: {error}")

    try:
        payload = app.mlb_statsapi_get(
            "/schedule",
            {"sportId": 1, "date": date_text, "hydrate": "probablePitcher,venue"},
        )
        for game in payload.get("dates", [{}])[0].get("games", []):
            away = game.get("teams", {}).get("away", {})
            home = game.get("teams", {}).get("home", {})
            away_team = away.get("team", {})
            home_team = home.get("team", {})
            games.append(
                ScheduleGame(
                    game_id=str(game.get("gamePk", "")),
                    game_date=str(game.get("officialDate") or date_text),
                    away_team=normalize_team(away_team.get("name")),
                    home_team=normalize_team(home_team.get("name")),
                    away_name=str(away_team.get("name", "")),
                    home_name=str(home_team.get("name", "")),
                    away_probable_pitcher=normalize_name((away.get("probablePitcher") or {}).get("fullName")),
                    home_probable_pitcher=normalize_name((home.get("probablePitcher") or {}).get("fullName")),
                    venue=str((game.get("venue") or {}).get("name", "")),
                    status=str(((game.get("status") or {}).get("detailedState")) or ""),
                    source="MLB StatsAPI direct fallback",
                )
            )
        notes.append(f"Loaded {len(games)} scheduled game(s) from MLB StatsAPI fallback.")
    except Exception as error:
        notes.append(f"MLB StatsAPI fallback schedule unavailable: {error}")
    return games, notes


def apply_schedule_overrides(games: list[ScheduleGame], overrides: ContextOverrides) -> list[ScheduleGame]:
    for game in games:
        if overrides.probable_by_team.get(game.away_team):
            game.away_probable_pitcher = overrides.probable_by_team[game.away_team]
        if overrides.probable_by_team.get(game.home_team):
            game.home_probable_pitcher = overrides.probable_by_team[game.home_team]
    return games


def add_team_k_overrides(team_batting: list[dict[str, Any]], team_rates: dict[str, float]) -> list[dict[str, Any]]:
    records = list(team_batting)
    existing = {record.get("team"): record for record in records}
    for team, rate in team_rates.items():
        pa = 1000
        record = {
            "team": team,
            "name": app.TEAM_NAMES.get(team, team),
            "games": 25,
            "plateAppearances": pa,
            "atBats": 900,
            "hits": 0,
            "homeRuns": 0,
            "walks": 0,
            "strikeouts": int(round(rate * pa)),
            "battingAverage": 0.0,
            "onBase": 0.0,
            "slugging": 0.0,
            "ops": 0.0,
            "runsPerGame": 0.0,
        }
        existing[team] = {**existing.get(team, {}), **record}
    return list(existing.values())


def load_analyzer_data(args: argparse.Namespace, overrides: ContextOverrides) -> AnalyzerData:
    data = AnalyzerData.from_app()

    for path in args.hr_data:
        data.players.extend(app.parse_players(table_to_csv(path)))
    data.players = merge_players(data.players)

    for path in args.strikeout_data:
        raw = table_to_csv(path)
        data.pitching.extend(app.parse_pitching(raw))
        data.player_advanced_pitching.extend(app.parse_player_advanced_pitching(raw))
    data.pitching = merge_records(data.pitching, ["pitcherId", "pitcher", "team"])
    data.player_advanced_pitching = merge_records(data.player_advanced_pitching, ["pitcherId", "pitcher", "team"])

    for path in args.team_k_data:
        raw = table_to_csv(path)
        parsed = app.parse_team_batting(raw)
        rows = read_rows(path)
        for row in rows:
            team = normalize_team(first_value(row, ["Team", "Tm"]))
            rate = app.to_rate(first_value(row, ["K%", "SO%", "Strikeout Rate"]))
            if team and rate:
                overrides.team_k_rate[team] = rate
            opponent = normalize_team(first_value(row, ["Opponent", "Opp"]))
            opponent_rate = app.to_rate(first_value(row, ["Opp K%", "Opponent K%", "Opp 2026 K%", "Opp Strikeout Rate"]))
            if opponent and opponent_rate:
                overrides.team_k_rate[opponent] = opponent_rate
        data.team_batting.extend(parsed)
    data.team_batting = add_team_k_overrides(merge_records(data.team_batting, ["team"]), overrides.team_k_rate)

    for path in args.pitching_logs:
        data.pitching_game_logs.extend(app.parse_pitching_game_logs(table_to_csv(path)))
    data.pitching_game_logs = merge_records(data.pitching_game_logs, ["sourceId", "pitcherId", "pitcher", "date", "opponent"])

    for path in args.batter_logs:
        data.game_logs.extend(app.parse_game_logs(table_to_csv(path)))
    data.game_logs = merge_records(data.game_logs, ["sourceId", "playerId", "player", "date", "opponent"])

    for path in args.savant:
        data.batter_pitcher_advanced.extend(app.parse_batter_pitcher_advanced(table_to_csv(path)))
    data.batter_pitcher_advanced = merge_records(data.batter_pitcher_advanced, ["batterId", "batter", "pitcherId", "pitcher"])
    return data


@contextmanager
def patched_app_data(data: AnalyzerData):
    originals = {
        "load_players": app.load_players,
        "load_opponents": app.load_opponents,
        "load_game_logs": app.load_game_logs,
        "load_pitching_game_logs": app.load_pitching_game_logs,
        "load_team_game_logs": app.load_team_game_logs,
        "load_team_batting": app.load_team_batting,
        "load_pitching": app.load_pitching,
        "load_batting_against": app.load_batting_against,
        "load_team_batting_against": app.load_team_batting_against,
        "load_team_advanced_pitching": app.load_team_advanced_pitching,
        "load_player_advanced_pitching": app.load_player_advanced_pitching,
        "load_team_standard_pitching": app.load_team_standard_pitching,
        "load_batter_pitcher_advanced": app.load_batter_pitcher_advanced,
    }
    app.load_players = lambda: data.players
    app.load_opponents = lambda: data.opponents
    app.load_game_logs = lambda: data.game_logs
    app.load_pitching_game_logs = lambda: data.pitching_game_logs
    app.load_team_game_logs = lambda: data.team_game_logs
    app.load_team_batting = lambda: data.team_batting
    app.load_pitching = lambda: data.pitching
    app.load_batting_against = lambda: data.batting_against
    app.load_team_batting_against = lambda: data.team_batting_against
    app.load_team_advanced_pitching = lambda: data.team_advanced_pitching
    app.load_player_advanced_pitching = lambda: data.player_advanced_pitching
    app.load_team_standard_pitching = lambda: data.team_standard_pitching
    app.load_batter_pitcher_advanced = lambda: data.batter_pitcher_advanced
    try:
        yield
    finally:
        for name, original in originals.items():
            setattr(app, name, original)


def find_player(players: list[app.Player], player_name: str, team: str = "") -> app.Player | None:
    target = name_key(player_name)
    exact = [
        player
        for player in players
        if name_key(player.player) == target and (not team or normalize_team(player.team) == team)
    ]
    if exact:
        return exact[0]
    partial = [player for player in players if target and target in name_key(player.player)]
    return partial[0] if len(partial) == 1 else None


def find_pitcher(pitchers: list[dict[str, Any]], pitcher_name: str, team: str = "") -> dict[str, Any] | None:
    target = name_key(pitcher_name)
    exact = [
        pitcher
        for pitcher in pitchers
        if name_key(pitcher.get("pitcher", "")) == target and (not team or normalize_team(pitcher.get("team")) == team)
    ]
    if exact:
        return exact[0]
    partial = [pitcher for pitcher in pitchers if target and target in name_key(pitcher.get("pitcher", ""))]
    return partial[0] if len(partial) == 1 else None


def find_game(prop: dict[str, Any], games: list[ScheduleGame]) -> ScheduleGame | None:
    team = prop.get("team", "")
    opponent = prop.get("opponent", "")
    pitcher = name_key(prop.get("player", ""))
    for game in games:
        teams = {game.away_team, game.home_team}
        if team and opponent and {team, opponent}.issubset(teams):
            return game
        if team and team in teams:
            return game
        if pitcher and pitcher in {name_key(game.away_probable_pitcher), name_key(game.home_probable_pitcher)}:
            return game
    return None


def weather_matches(row: dict[str, Any], team: str, opponent: str, game: ScheduleGame | None) -> bool:
    row_team = normalize_team(first_value(row, ["Team", "Tm", "_team"]))
    row_opp = normalize_team(first_value(row, ["Opponent", "Opp"]))
    home = normalize_team(first_value(row, ["Home Team", "Home", "_homeTeam"]))
    away = normalize_team(first_value(row, ["Away Team", "Away", "_awayTeam"]))
    if row_team and row_team == team and (not row_opp or row_opp == opponent):
        return True
    if home and away and {team, opponent}.issubset({home, away}):
        return True
    if game:
        venue = first_value(row, ["Venue", "Ballpark", "Park"])
        if venue and game.venue and venue.lower() == game.venue.lower():
            return True
    return False


def computed_weather_adjustment(row: dict[str, Any], market: str) -> tuple[float, dict[str, Any]]:
    manual_names = ["HR Adjustment", "Home Run Adjustment"] if market == "homeRuns" else ["Pitcher K Adjustment", "K Adjustment"]
    manual = first_value(row, manual_names)
    if manual:
        return parse_float(manual), {"manualWeatherAdjustment": parse_float(manual)}

    temp = parse_float(first_value(row, ["Temperature", "Temp"]), 0.0)
    wind_mph = parse_float(first_value(row, ["Wind MPH", "Wind Speed", "Wind"]), 0.0)
    wind_dir = first_value(row, ["Wind Direction", "Wind Dir", "Wind"]).lower()
    roof = first_value(row, ["Roof", "Dome"]).lower()
    park_factor = parse_float(first_value(row, ["Park Factor", "HR Park Factor"]), 0.0)
    closed = any(token in roof for token in ["closed", "dome", "indoor"])
    adjustment = 0.0

    if market == "homeRuns":
        if park_factor:
            factor = park_factor / 100 if park_factor > 2 else park_factor
            adjustment += app.clamp((factor - 1.0) * 25, -4.0, 4.0)
        if temp and not closed:
            adjustment += app.clamp((temp - 70) * 0.12, -3.0, 3.0)
        if wind_mph and not closed:
            if "out" in wind_dir or "to " in wind_dir:
                adjustment += app.clamp(wind_mph * 0.35, 0.0, 5.0)
            elif "in" in wind_dir or "from " in wind_dir:
                adjustment -= app.clamp(wind_mph * 0.28, 0.0, 4.5)
    else:
        if temp and not closed:
            adjustment += app.clamp((55 - temp) * 0.035, -0.8, 0.8)
        condition = first_value(row, ["Condition", "Weather", "Forecast"]).lower()
        if any(token in condition for token in ["rain", "delay", "storm"]):
            adjustment -= 0.6
    return round(adjustment, 2), {
        "temperature": temp,
        "windMph": wind_mph,
        "windDirection": wind_dir,
        "roof": roof,
        "parkFactor": park_factor,
    }


def weather_context(
    rows: list[dict[str, Any]],
    market: str,
    team: str,
    opponent: str,
    game: ScheduleGame | None,
) -> tuple[float, dict[str, Any]]:
    for row in rows:
        if weather_matches(row, team, opponent, game):
            adjustment, details = computed_weather_adjustment(row, market)
            details["source"] = row.get("_source") or first_value(row, ["Source"]) or "weather file"
            details["adjustment"] = adjustment
            return adjustment, details
    return 0.0, {}


def batter_last_n_summary(player: app.Player, data: AnalyzerData, n: int) -> dict[str, Any]:
    entries = app.game_log_entries_for_player(player, data.game_logs)
    return app.summarize_batter_entries(entries, n, f"Last {n}") if entries else {}


def pitcher_last_n_summary(pitcher: dict[str, Any], data: AnalyzerData, n: int) -> dict[str, Any]:
    pitcher_id = str(pitcher.get("pitcherId", "")).strip()
    pitcher_name = str(pitcher.get("pitcher", "")).strip().lower()
    matches = []
    for index, row in enumerate(data.pitching_game_logs):
        same_id = pitcher_id and str(row.get("pitcherId", "")) == pitcher_id
        same_name = pitcher_name and str(row.get("pitcher", "")).strip().lower() == pitcher_name
        if same_id or same_name:
            item = dict(row)
            item["_order"] = index
            matches.append(item)
    matches = sorted(matches, key=lambda item: (app.parse_game_date(item.get("date")), item.get("_order", 0)), reverse=True)[:n]
    innings = sum(app.to_float(item.get("innings")) for item in matches)
    games = len(matches)
    bf = sum(app.to_int(item.get("battersFaced")) for item in matches)
    strikeouts = sum(app.to_int(item.get("strikeouts")) for item in matches)
    if not bf and innings:
        bf = int(round(innings * 4.25))
    return {
        "games": games,
        "innings": round(innings, 1),
        "battersFaced": bf,
        "strikeouts": strikeouts,
        "strikeoutRate": round(strikeouts / bf, 3) if bf else 0.0,
        "strikeoutsPerGame": round(strikeouts / games, 2) if games else 0.0,
    }


def batter_recent_adjustment(player: app.Player, summary: dict[str, Any]) -> float:
    if not summary or not summary.get("games"):
        return 0.0
    season_rate = player.home_runs / max(player.plate_appearances, player.at_bats, 1)
    recent_rate = summary.get("homeRunRate", 0.0)
    return app.clamp((recent_rate - season_rate) * 45, -4.0, 5.0)


def pitcher_recent_adjustment(pitcher: dict[str, Any], summary: dict[str, Any]) -> float:
    if not summary or not summary.get("games") or not summary.get("strikeoutRate"):
        return 0.0
    season_rate = app.pitcher_strikeout_rate(pitcher)
    return app.clamp((summary["strikeoutRate"] - season_rate) * 28, -5.0, 5.0)


def payout_columns(row: dict[str, Any], odds: int, ev_per_unit: float) -> None:
    profit = app.american_profit_per_unit(odds)
    for stake in STAKE_SIZES:
        row[f"payout_${stake}"] = round(stake * (1 + profit), 2)
        row[f"profit_${stake}"] = round(stake * profit, 2)
        row[f"expected_profit_${stake}"] = round(stake * ev_per_unit, 2)


def pick_row(
    prop: dict[str, Any],
    payload: dict[str, Any],
    game: ScheduleGame | None,
    weather: dict[str, Any],
    recent: dict[str, Any],
) -> dict[str, Any]:
    prediction = payload["prediction"]
    market = prediction["market"]
    if prop["market"] == "homeRuns":
        player_name = payload["player"]["player"]
        team = normalize_team(payload["player"]["team"])
        opponent = payload["opponent"]["code"]
        pitcher = (payload["opponent"].get("pitcher") or {}).get("pitcher", prop.get("pitcher", ""))
        market_label = "Home Run"
        unit = "HR"
    else:
        player_name = payload["pitcher"]["pitcher"]
        team = normalize_team(payload["pitcher"].get("team"))
        opponent = payload["opponent"]["code"]
        pitcher = player_name
        market_label = "Pitcher Strikeouts"
        unit = "Ks"

    row = {
        "market": market_label,
        "selection": f"{player_name} over {market['line']:g} {unit}",
        "player": player_name,
        "team": team,
        "opponent": opponent,
        "opponent_name": app.TEAM_NAMES.get(opponent, opponent),
        "pitcher": pitcher,
        "line": market["line"],
        "odds": market["odds"],
        "book": prop.get("book", ""),
        "model_probability": market["modelProbability"],
        "implied_probability": market["impliedProbability"],
        "edge": market["edge"],
        "fair_odds": market["fairAmerican"],
        "expected_value_per_unit": market["expectedValuePerUnit"],
        "expected": prediction["expected"],
        "game_id": game.game_id if game else "",
        "venue": game.venue if game else "",
        "game_status": game.status if game else "",
        "weather_adjustment": weather.get("adjustment", 0.0),
        "weather_source": weather.get("source", ""),
        "last5_games": recent.get("games", 0),
        "last5_hr": recent.get("homeRuns", ""),
        "last5_ks": recent.get("strikeouts", ""),
        "last5_k_rate": recent.get("strikeoutRate", ""),
        "source_file": prop.get("sourceFile", ""),
        "verdict": market["verdict"],
    }
    payout_columns(row, market["odds"], market["expectedValuePerUnit"])
    return row


def analyze_props(
    props: list[dict[str, Any]],
    data: AnalyzerData,
    games: list[ScheduleGame],
    overrides: ContextOverrides,
    recent_games: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    with patched_app_data(data):
        pitcher_options = app.load_pitcher_options()
        for prop in props:
            game = find_game(prop, games)
            if game:
                if not prop.get("team"):
                    if prop["market"] == "pitcherStrikeouts":
                        if name_key(prop["player"]) == name_key(game.away_probable_pitcher):
                            prop["team"] = game.away_team
                        elif name_key(prop["player"]) == name_key(game.home_probable_pitcher):
                            prop["team"] = game.home_team
                    elif prop["market"] == "homeRuns":
                        player = find_player(data.players, prop["player"])
                        prop["team"] = normalize_team(player.team) if player else prop.get("team", "")
                if not prop.get("opponent") and prop.get("team"):
                    prop["opponent"] = game.opponent_for(prop["team"])

            if prop["market"] == "homeRuns":
                player = find_player(data.players, prop["player"], prop.get("team", ""))
                if not player:
                    warnings.append(f"Skipped HR prop: no batter data for {prop['player']}.")
                    continue
                team = normalize_team(player.team)
                opponent = prop.get("opponent") or (game.opponent_for(team) if game else "")
                if not opponent:
                    warnings.append(f"Skipped HR prop: no opponent for {player.player}.")
                    continue
                opposing_pitcher_name = prop.get("pitcher") or (game.probable_pitcher_for(opponent) if game else "")
                opposing_pitcher = find_pitcher(pitcher_options, opposing_pitcher_name, opponent) if opposing_pitcher_name else None
                pitcher_key = opposing_pitcher.get("key", "") if opposing_pitcher else ""
                last5 = batter_last_n_summary(player, data, recent_games)
                recent_adj = batter_recent_adjustment(player, last5)
                weather_adj, weather = weather_context(overrides.weather_rows, prop["market"], team, opponent, game)
                payload = app.predict_prop(
                    player,
                    opponent,
                    recent_adj + weather_adj,
                    pitcher_key=pitcher_key,
                    target="homeRuns",
                    line=prop["line"],
                    odds=prop["odds"],
                )
                rows.append(pick_row(prop, payload, game, weather, last5))
                continue

            pitcher = find_pitcher(pitcher_options, prop["player"], prop.get("team", ""))
            if not pitcher:
                warnings.append(f"Skipped pitcher K prop: no pitcher data for {prop['player']}.")
                continue
            team = normalize_team(pitcher.get("team"))
            if not prop.get("team"):
                prop["team"] = team
            if not game:
                game = find_game({**prop, "team": team}, games)
            opponent = prop.get("opponent") or (game.opponent_for(team) if game else "")
            if not opponent:
                warnings.append(f"Skipped pitcher K prop: no opponent for {pitcher.get('pitcher')}.")
                continue
            last5 = pitcher_last_n_summary(pitcher, data, recent_games)
            recent_adj = pitcher_recent_adjustment(pitcher, last5)
            weather_adj, weather = weather_context(overrides.weather_rows, prop["market"], team, opponent, game)
            payload = app.predict_pitcher_strikeouts(
                pitcher["key"],
                opponent,
                recent_adj + weather_adj,
                line=prop["line"],
                odds=prop["odds"],
            )
            rows.append(pick_row(prop, payload, game, weather, last5))
    return rows, warnings


def decimal_return(odds: int) -> float:
    return 1 + app.american_profit_per_unit(odds)


def parlay_rows(candidates: list[dict[str, Any]], max_legs: int, pool_size: int, limit: int) -> list[dict[str, Any]]:
    pool = sorted(
        candidates,
        key=lambda row: (row["expected_value_per_unit"], row["model_probability"]),
        reverse=True,
    )[:pool_size]
    rows: list[dict[str, Any]] = []
    for legs in range(2, max_legs + 1):
        for combo in itertools.combinations(pool, legs):
            selection_keys = {row["selection"] for row in combo}
            if len(selection_keys) != len(combo):
                continue
            probability = math.prod(row["model_probability"] for row in combo)
            decimal = math.prod(decimal_return(row["odds"]) for row in combo)
            profit_per_unit = decimal - 1
            ev_per_unit = probability * profit_per_unit - (1 - probability)
            row = {
                "legs": legs,
                "selections": " + ".join(item["selection"] for item in combo),
                "model_probability": round(probability, 3),
                "implied_probability": round(1 / decimal, 3) if decimal else 0.0,
                "edge": round(probability - (1 / decimal if decimal else 0.0), 3),
                "fair_odds": app.fair_american(probability),
                "decimal_return": round(decimal, 3),
                "expected_value_per_unit": round(ev_per_unit, 3),
                "games": ", ".join(sorted({str(item.get("game_id", "")) for item in combo if item.get("game_id")})),
            }
            for stake in STAKE_SIZES:
                row[f"payout_${stake}"] = round(stake * decimal, 2)
                row[f"profit_${stake}"] = round(stake * profit_per_unit, 2)
                row[f"expected_profit_${stake}"] = round(stake * ev_per_unit, 2)
            rows.append(row)
    return sorted(rows, key=lambda row: (row["expected_value_per_unit"], row["model_probability"]), reverse=True)[:limit]


PICK_FIELDS = [
    "market",
    "selection",
    "team",
    "opponent",
    "pitcher",
    "line",
    "odds",
    "book",
    "model_probability",
    "implied_probability",
    "edge",
    "fair_odds",
    "expected_value_per_unit",
    "expected",
    "payout_$3",
    "payout_$10",
    "payout_$20",
    "expected_profit_$3",
    "expected_profit_$10",
    "expected_profit_$20",
    "last5_games",
    "last5_hr",
    "last5_ks",
    "last5_k_rate",
    "venue",
    "weather_adjustment",
    "weather_source",
    "verdict",
]

PARLAY_FIELDS = [
    "legs",
    "selections",
    "model_probability",
    "implied_probability",
    "edge",
    "fair_odds",
    "decimal_return",
    "expected_value_per_unit",
    "payout_$3",
    "payout_$10",
    "payout_$20",
    "expected_profit_$3",
    "expected_profit_$10",
    "expected_profit_$20",
    "games",
]


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return ""


def markdown_table(rows: list[dict[str, Any]], fields: list[str], limit: int = 20) -> str:
    if not rows:
        return "_No rows._\n"
    labels = [field.replace("_", " ").title().replace("$", "$") for field in fields]
    output = ["| " + " | ".join(labels) + " |", "| " + " | ".join("---" for _ in fields) + " |"]
    for row in rows[:limit]:
        cells = []
        for field in fields:
            value = row.get(field, "")
            if field.endswith("probability") or field in {"edge"}:
                cells.append(pct(value))
            elif isinstance(value, float):
                cells.append(f"{value:.3f}".rstrip("0").rstrip("."))
            else:
                cells.append(str(value))
        output.append("| " + " | ".join(cells) + " |")
    return "\n".join(output) + "\n"


def write_report(
    path: Path,
    date_text: str,
    picks: list[dict[str, Any]],
    parlays: list[dict[str, Any]],
    notes: list[str],
    warnings: list[str],
) -> None:
    best_value = sorted(picks, key=lambda row: (row["expected_value_per_unit"], row["edge"]), reverse=True)
    highest_probability = sorted(picks, key=lambda row: row["model_probability"], reverse=True)
    hr_rows = [row for row in best_value if row["market"] == "Home Run"]
    k_rows = [row for row in best_value if row["market"] == "Pitcher Strikeouts"]
    lines = [
        f"# MLB Prop Analysis Report ({date_text})",
        "",
        "## Source Notes",
        *(f"- {note}" for note in notes),
        "",
        "## Best Value",
        markdown_table(best_value, ["selection", "odds", "model_probability", "implied_probability", "edge", "fair_odds", "expected_value_per_unit", "payout_$10"], 25),
        "## Highest Probability",
        markdown_table(highest_probability, ["selection", "odds", "model_probability", "implied_probability", "fair_odds", "expected_value_per_unit", "payout_$10"], 25),
        "## Home Run Props",
        markdown_table(hr_rows, ["selection", "pitcher", "odds", "model_probability", "edge", "expected", "last5_hr", "weather_adjustment", "payout_$3", "payout_$20"], 25),
        "## Pitcher Strikeout Props",
        markdown_table(k_rows, ["selection", "opponent", "odds", "model_probability", "edge", "expected", "last5_ks", "last5_k_rate", "payout_$3", "payout_$20"], 25),
        "## Parlay Combinations",
        markdown_table(parlays, ["legs", "selections", "model_probability", "implied_probability", "edge", "fair_odds", "decimal_return", "expected_value_per_unit", "payout_$10"], 25),
        "## Warnings",
        *(f"- {warning}" for warning in warnings),
        "",
        "_Parlay probabilities assume independent legs. Treat same-game combinations as higher-correlation than shown._",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch MLB home run and pitcher strikeout prop analyzer.")
    parser.add_argument("--date", default="today", help="Schedule date, e.g. today or 2026-05-03.")
    parser.add_argument("--odds", action="append", type=Path, required=True, help="CSV/JSON/HTML prop odds file.")
    parser.add_argument("--hr-data", action="append", type=Path, default=[], help="Optional batter HR/stat CSV.")
    parser.add_argument("--strikeout-data", action="append", type=Path, default=[], help="Optional pitcher K/stat CSV.")
    parser.add_argument("--team-k-data", action="append", type=Path, default=[], help="Optional team opponent K-rate CSV.")
    parser.add_argument("--weather", action="append", type=Path, default=[], help="Manual weather/park context CSV.")
    parser.add_argument("--rotogrinders", action="append", type=Path, default=[], help="Rotogrinders export/HTML for probables/lineups.")
    parser.add_argument("--covers", action="append", type=Path, default=[], help="Covers export/HTML for matchups/weather/team rates.")
    parser.add_argument("--savant", action="append", type=Path, default=[], help="Baseball Savant summarized batter-vs-pitcher quality CSV.")
    parser.add_argument("--pitching-logs", action="append", type=Path, default=[], help="Optional pitcher game log CSV.")
    parser.add_argument("--batter-logs", action="append", type=Path, default=[], help="Optional batter game log CSV.")
    parser.add_argument("--recent-games", type=int, default=5, help="Recent game window for last-N context.")
    parser.add_argument("--max-parlay-legs", type=int, default=3, help="Maximum legs for generated parlays.")
    parser.add_argument("--parlay-pool", type=int, default=12, help="Use top N picks by EV for parlay generation.")
    parser.add_argument("--parlay-count", type=int, default=25, help="Number of parlay rows to output.")
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT_DIR, help="Output directory.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    date_text = schedule_date_text(args.date)
    context_sources = []
    for path in args.rotogrinders:
        context_sources.append(parse_context_file(path, "Rotogrinders"))
    for path in args.covers:
        context_sources.append(parse_context_file(path, "Covers"))
    for path in args.weather:
        context_sources.append(parse_context_file(path, "Manual weather"))
    overrides = combine_overrides(context_sources)

    schedule, notes = statsapi_schedule(date_text)
    schedule = apply_schedule_overrides(schedule, overrides)
    notes.extend(overrides.notes)

    props = parse_prop_odds(args.odds)
    data = load_analyzer_data(args, overrides)
    picks, warnings = analyze_props(props, data, schedule, overrides, args.recent_games)
    best_value = sorted(picks, key=lambda row: (row["expected_value_per_unit"], row["edge"]), reverse=True)
    highest_probability = sorted(picks, key=lambda row: row["model_probability"], reverse=True)
    parlays = parlay_rows([row for row in picks if row["model_probability"] > 0], args.max_parlay_legs, args.parlay_pool, args.parlay_count)

    out_dir = args.out / date_text if args.out == DEFAULT_REPORT_DIR else args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "best_value.csv", best_value, PICK_FIELDS)
    write_csv(out_dir / "highest_probability.csv", highest_probability, PICK_FIELDS)
    write_csv(out_dir / "all_props.csv", picks, PICK_FIELDS)
    write_csv(out_dir / "parlays.csv", parlays, PARLAY_FIELDS)
    write_report(out_dir / "report.md", date_text, picks, parlays, notes, warnings)

    print(f"Analyzed {len(picks)} prop(s) for {date_text}.")
    print(f"Wrote report files to {out_dir}")
    if warnings:
        print(f"{len(warnings)} warning(s); see report.md for details.")
    return 0 if picks else 1


if __name__ == "__main__":
    raise SystemExit(main())
