from __future__ import annotations

"""Unified Prop Card.

Combines:
- All Data Prop Predictor
- cached 2026 batter/pitcher/team logs
- sportsbook implied probability
- transparent season-stat adjustments
"""

import csv
import json
from pathlib import Path
from typing import Any

from unified_prop_context import all_data_predict

ROOT = Path(__file__).resolve().parent
SEASON_CACHE_DIR = ROOT / "data" / "cache" / "season_stats"
INCREMENTAL_CACHE_DIR = ROOT / "data" / "cache" / "incremental_stats"
CLOUD_SEASON_DIR = ROOT / "data" / "cloud" / "season_logs"
CACHE_DIRS = [INCREMENTAL_CACHE_DIR, SEASON_CACHE_DIR, CLOUD_SEASON_DIR]
WEATHER_DIR = ROOT / "data" / "cache" / "weather"
_ROW_CACHE: dict[tuple[str, int, int], list[dict[str, str]]] = {}

TEAM_GAME_MARKETS = {
    "moneyline", "moneyline_first_five", "run_line", "run_line_first_five", "run_line_first_inning",
    "game_total_runs", "first_five_total_runs", "first_inning_total_runs", "team_total_runs", "team_first_to_score",
}

REGULAR_SEASON_START_DATES = {
    2024: "2024-03-20",
    2025: "2025-03-18",
    2026: "2026-03-25",
}


def row_season_phase(row: dict[str, Any], season: int) -> str:
    explicit = clean(row.get("seasonPhase"))
    if explicit:
        return explicit

    date_label = clean(row.get("date"))
    regular_start = REGULAR_SEASON_START_DATES.get(season, f"{season}-03-25")
    return "regular" if date_label >= regular_start else "practice"


def regular_rows(rows: list[dict[str, str]], season: int) -> list[dict[str, str]]:
    return [row for row in rows if row_season_phase(row, season) == "regular"]



def base_market(market: Any) -> str:
    text = clean(market)
    return text[:-4] if text.endswith("_alt") else text


def is_alt_market(market: Any) -> bool:
    return clean(market).endswith("_alt")



def clean(value: Any) -> str:
    return str(value or "").strip()


def to_float(value: Any, default: float = 0.0) -> float:
    text = clean(value).replace(",", "")
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def clamp(value: float, low: float = 0.01, high: float = 0.99) -> float:
    return max(low, min(high, value))


def pct(value: float) -> float:
    return round(value * 100, 2)


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    stat = path.stat()
    key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    cached = _ROW_CACHE.get(key)
    if cached is not None:
        return cached
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    _ROW_CACHE[key] = rows
    return rows


def read_cached_rows(filename: str) -> list[dict[str, str]]:
    for folder in CACHE_DIRS:
        rows = read_rows(folder / filename)
        if rows:
            return rows
    return []


def norm(value: Any) -> str:
    return " ".join(clean(value).lower().replace(".", "").replace(",", "").split())


def summarize_batter(player: str, season: int) -> dict[str, Any]:
    rows = [
        row for row in regular_rows(read_cached_rows(f"batter_game_logs_{season}.csv"), season)
        if norm(row.get("player")) == norm(player)
    ]

    games = len(rows)
    ab = sum(to_float(row.get("atBats")) for row in rows)
    pa = sum(to_float(row.get("plateAppearances")) for row in rows)
    hits = sum(to_float(row.get("hits")) for row in rows)
    hr = sum(to_float(row.get("homeRuns")) for row in rows)
    tb = sum(to_float(row.get("totalBases")) for row in rows)
    so = sum(to_float(row.get("strikeOuts")) for row in rows)
    bb = sum(to_float(row.get("baseOnBalls")) for row in rows)

    return {
        "available": games > 0,
        "games": games,
        "plateAppearances": pa,
        "atBats": ab,
        "hits": hits,
        "homeRuns": hr,
        "totalBases": tb,
        "strikeOuts": so,
        "baseOnBalls": bb,
        "avg": round(hits / ab, 3) if ab else 0,
        "hitsPerGame": round(hits / games, 3) if games else 0,
        "totalBasesPerGame": round(tb / games, 3) if games else 0,
        "homeRunsPerGame": round(hr / games, 3) if games else 0,
        "strikeoutsPerGame": round(so / games, 3) if games else 0,
        "team": clean(rows[-1].get("team")) if rows else "",
    }


def summarize_pitcher(player: str, season: int) -> dict[str, Any]:
    rows = [
        row for row in regular_rows(read_cached_rows(f"pitcher_game_logs_{season}.csv"), season)
        if norm(row.get("player")) == norm(player)
    ]

    games = len(rows)
    hits = sum(to_float(row.get("hits")) for row in rows)
    er = sum(to_float(row.get("earnedRuns")) for row in rows)
    runs = sum(to_float(row.get("runs")) for row in rows)
    hr = sum(to_float(row.get("homeRuns")) for row in rows)
    bb = sum(to_float(row.get("baseOnBalls")) for row in rows)
    so = sum(to_float(row.get("strikeOuts")) for row in rows)
    bf = sum(to_float(row.get("battersFaced")) for row in rows)
    pitches = sum(to_float(row.get("pitchesThrown")) for row in rows)

    return {
        "available": games > 0,
        "games": games,
        "hitsAllowed": hits,
        "earnedRuns": er,
        "runs": runs,
        "homeRunsAllowed": hr,
        "baseOnBalls": bb,
        "strikeOuts": so,
        "battersFaced": bf,
        "pitchesThrown": pitches,
        "strikeoutsPerGame": round(so / games, 3) if games else 0,
        "hitsAllowedPerGame": round(hits / games, 3) if games else 0,
        "earnedRunsPerGame": round(er / games, 3) if games else 0,
        "team": clean(rows[-1].get("team")) if rows else "",
    }


def summarize_team(team: str, season: int) -> dict[str, Any]:
    team = clean(team).upper()
    rows = [
        row for row in regular_rows(read_cached_rows(f"team_game_logs_{season}.csv"), season)
        if clean(row.get("team")).upper() == team
    ]

    games = len(rows)
    runs = sum(to_float(row.get("runs")) for row in rows)
    hits = sum(to_float(row.get("hits")) for row in rows)
    hr = sum(to_float(row.get("homeRuns")) for row in rows)
    so = sum(to_float(row.get("strikeOuts")) for row in rows)
    p_runs = sum(to_float(row.get("pitchingRuns")) for row in rows)
    p_hits = sum(to_float(row.get("pitchingHits")) for row in rows)
    p_so = sum(to_float(row.get("pitchingStrikeOuts")) for row in rows)

    return {
        "available": games > 0,
        "team": team,
        "games": games,
        "runsPerGame": round(runs / games, 3) if games else 0,
        "hitsPerGame": round(hits / games, 3) if games else 0,
        "homeRunsPerGame": round(hr / games, 3) if games else 0,
        "strikeoutsPerGame": round(so / games, 3) if games else 0,
        "runsAllowedPerGame": round(p_runs / games, 3) if games else 0,
        "hitsAllowedPerGame": round(p_hits / games, 3) if games else 0,
        "pitchingStrikeoutsPerGame": round(p_so / games, 3) if games else 0,
    }


def season_adjustment(market: str, line: float, batter: dict[str, Any], pitcher: dict[str, Any], team: dict[str, Any], opponent: dict[str, Any]) -> tuple[float, list[dict[str, Any]]]:
    adjustments = []

    def add(name: str, amount: float, reason: str) -> None:
        adjustments.append({
            "name": name,
            "amount": round(amount, 4),
            "amountPercent": pct(amount),
            "reason": reason,
        })

    amount = 0.0

    if market == "batter_hits" and batter.get("available"):
        hpg = to_float(batter.get("hitsPerGame"))
        if hpg >= 1.05:
            amount += 0.025
            add("Cached batter hits", 0.025, f"{hpg} hits/game in cached season logs")
        elif hpg <= 0.65:
            amount -= 0.02
            add("Cached batter hits", -0.02, f"{hpg} hits/game in cached season logs")

    if market == "batter_total_bases" and batter.get("available"):
        tbpg = to_float(batter.get("totalBasesPerGame"))
        if tbpg >= 1.65:
            amount += 0.025
            add("Cached total bases", 0.025, f"{tbpg} total bases/game in cached logs")
        elif tbpg <= 0.85:
            amount -= 0.02
            add("Cached total bases", -0.02, f"{tbpg} total bases/game in cached logs")

    if market == "batter_home_runs" and batter.get("available"):
        hrpg = to_float(batter.get("homeRunsPerGame"))
        if hrpg >= 0.20:
            amount += 0.015
            add("Cached HR profile", 0.015, f"{hrpg} HR/game in cached logs")
        elif hrpg <= 0.04:
            amount -= 0.01
            add("Cached HR profile", -0.01, f"{hrpg} HR/game in cached logs")

    if market == "pitcher_strikeouts" and pitcher.get("available"):
        kpg = to_float(pitcher.get("strikeoutsPerGame"))
        if kpg >= line + 0.75:
            amount += 0.03
            add("Cached pitcher strikeouts", 0.03, f"{kpg} K/game vs line {line}")
        elif kpg <= line - 0.75:
            amount -= 0.03
            add("Cached pitcher strikeouts", -0.03, f"{kpg} K/game vs line {line}")

    if market == "pitcher_hits_allowed" and pitcher.get("available"):
        hpg = to_float(pitcher.get("hitsAllowedPerGame"))
        if hpg >= line + 0.75:
            amount += 0.025
            add("Cached hits allowed", 0.025, f"{hpg} H allowed/game vs line {line}")
        elif hpg <= line - 0.75:
            amount -= 0.025
            add("Cached hits allowed", -0.025, f"{hpg} H allowed/game vs line {line}")

    if market == "pitcher_earned_runs" and pitcher.get("available"):
        erpg = to_float(pitcher.get("earnedRunsPerGame"))
        if erpg >= line + 0.4:
            amount += 0.025
            add("Cached earned runs", 0.025, f"{erpg} ER/game vs line {line}")
        elif erpg <= line - 0.4:
            amount -= 0.025
            add("Cached earned runs", -0.025, f"{erpg} ER/game vs line {line}")

    if market.startswith("batter") and team.get("available"):
        rpg = to_float(team.get("runsPerGame"))
        if rpg >= 5.0:
            amount += 0.01
            add("Cached team offense", 0.01, f"{team.get('team')} scores {rpg} runs/game")
        elif rpg <= 3.6:
            amount -= 0.01
            add("Cached team offense", -0.01, f"{team.get('team')} scores {rpg} runs/game")

    if market.startswith("batter") and opponent.get("available"):
        rag = to_float(opponent.get("runsAllowedPerGame"))
        if rag >= 5.0:
            amount += 0.01
            add("Cached opponent pitching", 0.01, f"{opponent.get('team')} allows {rag} runs/game")
        elif rag <= 3.6:
            amount -= 0.01
            add("Cached opponent pitching", -0.01, f"{opponent.get('team')} allows {rag} runs/game")

    if market in TEAM_GAME_MARKETS:
        team_rpg = to_float(team.get("runsPerGame"))
        opp_rpg = to_float(opponent.get("runsPerGame"))
        team_allowed = to_float(team.get("runsAllowedPerGame"))
        opp_allowed = to_float(opponent.get("runsAllowedPerGame"))

        if market in {"moneyline", "moneyline_first_five", "run_line", "run_line_first_five", "run_line_first_inning", "team_first_to_score"}:
            if team_rpg and opp_rpg and team_rpg >= opp_rpg + 0.6:
                amount += 0.015
                add("Cached team form", 0.015, f"{team.get('team')} scores {team_rpg}/game vs opponent {opp_rpg}/game")
            elif team_rpg and opp_rpg and team_rpg <= opp_rpg - 0.6:
                amount -= 0.015
                add("Cached team form", -0.015, f"{team.get('team')} scores {team_rpg}/game vs opponent {opp_rpg}/game")

            if team_allowed and opp_allowed and team_allowed <= opp_allowed - 0.5:
                amount += 0.01
                add("Cached run prevention", 0.010, f"{team.get('team')} allows fewer runs/game than opponent")
            elif team_allowed and opp_allowed and team_allowed >= opp_allowed + 0.5:
                amount -= 0.01
                add("Cached run prevention", -0.010, f"{team.get('team')} allows more runs/game than opponent")

        if market in {"team_total_runs", "game_total_runs", "first_five_total_runs", "first_inning_total_runs"}:
            if team_rpg >= 5.0 or opp_allowed >= 5.0:
                amount += 0.012
                add("Cached scoring environment", 0.012, f"Team offense/opponent prevention supports runs")
            elif team_rpg and team_rpg <= 3.6 and opp_allowed and opp_allowed <= 3.8:
                amount -= 0.012
                add("Cached scoring environment", -0.012, f"Run environment looks suppressed")

    return amount, adjustments



def find_weather_feature(season: int, date_label: str, team: str, opponent: str) -> dict[str, Any]:
    rows = read_rows(WEATHER_DIR / f"weather_features_{season}.csv")
    team = clean(team).upper()
    opponent = clean(opponent).upper()

    for row in rows:
        if clean(row.get("date")) != clean(date_label):
            continue

        teams = {clean(row.get("home")).upper(), clean(row.get("away")).upper()}
        if team in teams and opponent in teams:
            return row

    return {}


def weather_adjustment_for_market(market: str, weather: dict[str, Any]) -> float:
    if not weather:
        return 0.0

    if market == "batter_home_runs":
        return to_float(weather.get("hrWeatherAdjustment"))
    if market == "batter_total_bases":
        return to_float(weather.get("totalBasesWeatherAdjustment"))
    if market == "batter_hits":
        return to_float(weather.get("hitsWeatherAdjustment"))
    if market == "pitcher_strikeouts":
        return to_float(weather.get("pitcherStrikeoutsWeatherAdjustment"))
    if market == "pitcher_hits_allowed":
        return to_float(weather.get("pitcherHitsAllowedWeatherAdjustment"))
    if market == "pitcher_earned_runs":
        return to_float(weather.get("pitcherEarnedRunsWeatherAdjustment"))
    if market in {"game_total_runs", "team_total_runs", "first_five_total_runs", "first_inning_total_runs"}:
        return to_float(weather.get("totalBasesWeatherAdjustment")) * 0.5 + to_float(weather.get("hitsWeatherAdjustment")) * 0.5

    return 0.0


def infer_pitcher_from_game_context(base: dict[str, Any], team: str, market: str) -> tuple[str, str]:
    game = (base.get("contexts") or {}).get("game") or {}
    team = clean(team).upper()
    market = clean(market)

    home = clean(game.get("home")).upper()
    away = clean(game.get("away")).upper()

    home_pitcher = clean(game.get("homeProbablePitcher"))
    away_pitcher = clean(game.get("awayProbablePitcher"))

    if not game or not team:
        return "", ""

    if market.startswith("batter"):
        if team == home and away_pitcher:
            return away_pitcher, "inferred_opposing_pitcher_from_mlb_game_context"
        if team == away and home_pitcher:
            return home_pitcher, "inferred_opposing_pitcher_from_mlb_game_context"

    if market.startswith("pitcher"):
        if team == home and home_pitcher:
            return home_pitcher, "inferred_team_pitcher_from_mlb_game_context"
        if team == away and away_pitcher:
            return away_pitcher, "inferred_team_pitcher_from_mlb_game_context"

    return "", ""


def find_odds_movement_context(
    season: int,
    date_label: str,
    market: str,
    player: str,
    team: str,
    opponent: str,
    pitcher: str,
) -> dict[str, Any]:
    try:
        from odds_movement import find_movement

        return find_movement(
            season=season,
            date_label=date_label,
            market=market,
            player=player,
            team=team,
            opponent=opponent,
            pitcher=pitcher,
        )
    except Exception:
        return {}


def player_id_from_index(player: str, season: int) -> str:
    if not clean(player):
        return ""
    try:
        from savant_features import load_player_index
        index = load_player_index(season)
    except Exception:
        return ""
    target = norm(player)
    for player_id, item in index.items():
        name = norm(item.get("player"))
        if name == target or (target and target in name) or (name and name in target):
            return clean(player_id)
    return ""


def raw_statcast_rows(season: int) -> list[dict[str, str]]:
    try:
        from savant_features import latest_raw_file, read_csv_rows
        path = latest_raw_file(season)
        return read_csv_rows(path) if path else []
    except Exception:
        return []


def pitch_type_label(code: str) -> str:
    labels = {
        "FF": "Fastball", "FA": "Fastball", "SI": "Sinker", "FT": "Two-Seam",
        "FC": "Cutter", "SL": "Slider", "ST": "Sweeper", "CU": "Curveball",
        "KC": "Knuckle Curve", "CH": "Changeup", "FS": "Splitter", "FO": "Forkball",
        "KN": "Knuckleball", "EP": "Eephus", "SC": "Screwball",
    }
    return labels.get(clean(code).upper(), clean(code).upper() or "Unknown")


def zone_index(row: dict[str, Any]) -> int | None:
    x = to_float(row.get("plate_x"), None)
    z = to_float(row.get("plate_z"), None)
    if x is None or z is None:
        return None
    # Fixed 4x4 strike-zone-ish grid, clamped so edge pitches still render.
    col = int(max(0, min(3, ((x + 1.0) / 2.0) * 4)))
    band = int(max(0, min(3, ((z - 1.5) / 2.0) * 4)))
    row_idx = 3 - band
    return row_idx * 4 + col


def zone_frequency(rows: list[dict[str, str]]) -> list[float]:
    counts = [0] * 16
    for row in rows:
        idx = zone_index(row)
        if idx is not None:
            counts[idx] += 1
    total = sum(counts)
    return [round((count / total) * 100, 1) if total else 0 for count in counts]


def zone_performance(rows: list[dict[str, str]]) -> list[float]:
    values: list[list[float]] = [[] for _ in range(16)]
    hit_events = {"single", "double", "triple", "home_run"}
    for row in rows:
        idx = zone_index(row)
        if idx is None:
            continue
        xwoba = to_float(row.get("estimated_woba_using_speedangle"), None)
        if xwoba is not None and xwoba > 0:
            values[idx].append(xwoba)
            continue
        event = clean(row.get("events"))
        if event:
            values[idx].append(1.0 if event in hit_events else 0.0)
    return [round(sum(items) / len(items), 3) if items else 0 for items in values]


def savant_matchup_detail(season: int, batter: str, pitcher: str) -> dict[str, Any]:
    rows = raw_statcast_rows(season)
    if not rows:
        return {
            "pitcher": {"pitchMix": [], "zoneFrequency": {}},
            "batter": {"zonePerformance": {}},
            "available": False,
            "note": "No cached raw Statcast rows available; run savant sync/build to populate pitch mix and zone fields.",
        }

    pitcher_id = player_id_from_index(pitcher, season)
    batter_id = player_id_from_index(batter, season)
    pitcher_rows = [row for row in rows if pitcher_id and clean(row.get("pitcher")) == pitcher_id]
    batter_rows = [row for row in rows if batter_id and clean(row.get("batter")) == batter_id]

    pitch_counts: dict[str, int] = {}
    for row in pitcher_rows:
        code = clean(row.get("pitch_type")).upper()
        if code:
            pitch_counts[code] = pitch_counts.get(code, 0) + 1
    total_pitches = sum(pitch_counts.values())
    pitch_mix = [
        {
            "pitchType": code,
            "pitchName": pitch_type_label(code),
            "percentage": round((count / total_pitches) * 100, 1) if total_pitches else 0,
            "count": count,
        }
        for code, count in sorted(pitch_counts.items(), key=lambda item: item[1], reverse=True)
    ]

    pitcher_zone = {
        "ALL": zone_frequency(pitcher_rows),
        "LHB": zone_frequency([row for row in pitcher_rows if clean(row.get("stand")).upper() == "L"]),
        "RHB": zone_frequency([row for row in pitcher_rows if clean(row.get("stand")).upper() == "R"]),
    }
    batter_zone = {
        "ALL": zone_performance(batter_rows),
        "LHP": zone_performance([row for row in batter_rows if clean(row.get("p_throws")).upper() == "L"]),
        "RHP": zone_performance([row for row in batter_rows if clean(row.get("p_throws")).upper() == "R"]),
    }

    return {
        "pitcher": {
            "pitchMix": pitch_mix,
            "zoneFrequency": pitcher_zone,
        },
        "batter": {
            "zonePerformance": batter_zone,
        },
        "available": bool(pitch_mix or any(any(v for v in grid) for grid in pitcher_zone.values()) or any(any(v for v in grid) for grid in batter_zone.values())),
        "rawRowsUsed": {"pitcher": len(pitcher_rows), "batter": len(batter_rows)},
    }


def find_savant_context(season: int, player: str, pitcher: str, market: str) -> dict[str, Any]:
    if clean(market) in TEAM_GAME_MARKETS:
        return {"available": False, "batter": {}, "pitcher": {}, "fieldAudit": {}}
    try:
        from savant_features import lookup_batter, lookup_pitcher

        batter = lookup_batter(player, season) if player else {}
        pitcher_quality = lookup_pitcher(pitcher, season) if pitcher else {}
        detail = savant_matchup_detail(season, player, pitcher)

        batter = {**batter, **(detail.get("batter") or {})}
        pitcher_quality = {**pitcher_quality, **(detail.get("pitcher") or {})}

        return {
            "batter": batter,
            "pitcher": pitcher_quality,
            "available": bool(batter or pitcher_quality or detail.get("available")),
            "rawRowsUsed": detail.get("rawRowsUsed", {}),
            "note": detail.get("note", ""),
            "fieldAudit": {
                "pitchMix": "savant.pitcher.pitchMix",
                "zoneFrequency": "savant.pitcher.zoneFrequency",
                "zonePerformance": "savant.batter.zonePerformance",
                "gridShape": "flat 16-cell array, row-major 4x4 strike-zone grid",
            },
        }
    except Exception as error:
        return {"available": False, "batter": {}, "pitcher": {}, "fieldAudit": {}, "error": str(error)}


def savant_adjustment_for_market(market: str, savant: dict[str, Any]) -> tuple[float, list[dict[str, Any]]]:
    if not savant or not savant.get("available"):
        return 0.0, []

    batter = savant.get("batter") or {}
    pitcher = savant.get("pitcher") or {}

    adjustment = 0.0
    reasons = []

    def add(name: str, amount: float, reason: str) -> None:
        nonlocal adjustment
        adjustment += amount
        reasons.append({
            "name": name,
            "amount": amount,
            "amountPercent": pct(amount),
            "reason": reason,
        })

    if market in {"batter_home_runs", "batter_total_bases", "batter_hits"} and batter:
        barrel_rate = to_float(batter.get("barrelRate"))
        hard_hit_rate = to_float(batter.get("hardHitRate"))
        avg_xslg = to_float(batter.get("avgXSLG"))
        avg_xwoba = to_float(batter.get("avgXWOBA"))

        if market == "batter_home_runs":
            if barrel_rate >= 12:
                add("Savant barrel rate", 0.015, f"{barrel_rate}% barrel rate supports HR upside")
            elif barrel_rate <= 5:
                add("Savant barrel rate", -0.010, f"{barrel_rate}% barrel rate lowers HR upside")

            if hard_hit_rate >= 48:
                add("Savant hard-hit rate", 0.008, f"{hard_hit_rate}% hard-hit rate supports power")
            elif hard_hit_rate <= 35:
                add("Savant hard-hit rate", -0.006, f"{hard_hit_rate}% hard-hit rate is modest")

        if market == "batter_total_bases":
            if avg_xslg >= 0.500:
                add("Savant xSLG", 0.012, f"{avg_xslg} xSLG supports total bases")
            elif avg_xslg and avg_xslg <= 0.350:
                add("Savant xSLG", -0.008, f"{avg_xslg} xSLG lowers total-base confidence")

            if hard_hit_rate >= 45:
                add("Savant hard-hit rate", 0.006, f"{hard_hit_rate}% hard-hit rate adds TB support")

        if market == "batter_hits":
            avg_xba = to_float(batter.get("avgXBA"))
            if avg_xba >= 0.280:
                add("Savant xBA", 0.008, f"{avg_xba} xBA supports hit probability")
            elif avg_xba and avg_xba <= 0.220:
                add("Savant xBA", -0.006, f"{avg_xba} xBA lowers hit probability")

    if market in {"pitcher_strikeouts", "pitcher_hits_allowed", "pitcher_earned_runs"} and pitcher:
        whiff_rate = to_float(pitcher.get("whiffRate"))
        csw_rate = to_float(pitcher.get("cswRate"))
        xwoba_allowed = to_float(pitcher.get("avgXWOBAAllowed"))
        barrel_allowed = to_float(pitcher.get("barrelRateAllowed"))

        if market == "pitcher_strikeouts":
            if whiff_rate >= 28:
                add("Savant whiff rate", 0.012, f"{whiff_rate}% whiff rate supports strikeouts")
            elif whiff_rate and whiff_rate <= 20:
                add("Savant whiff rate", -0.008, f"{whiff_rate}% whiff rate lowers strikeout upside")

            if csw_rate >= 30:
                add("Savant CSW rate", 0.008, f"{csw_rate}% CSW supports strikeout skill")

        if market in {"pitcher_hits_allowed", "pitcher_earned_runs"}:
            if xwoba_allowed >= 0.350:
                add("Savant xwOBA allowed", 0.010, f"{xwoba_allowed} xwOBA allowed signals contact risk")
            elif xwoba_allowed and xwoba_allowed <= 0.290:
                add("Savant xwOBA allowed", -0.008, f"{xwoba_allowed} xwOBA allowed is strong")

            if barrel_allowed >= 10:
                add("Savant barrels allowed", 0.006, f"{barrel_allowed}% barrel rate allowed adds damage risk")

    # Keep Savant conservative.
    adjustment = clamp(adjustment, -0.025, 0.025)
    return adjustment, reasons

def build_insights(
    player: str,
    market: str,
    line: float,
    recommendation: str,
    cache_adjustments: list[dict[str, Any]],
    savant_adjustments: list[dict[str, Any]],
    weather_context: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for adjustment in (cache_adjustments or [])[:3]:
        reason = clean(adjustment.get("reason"))
        if reason:
            items.append({"type": "analysis", "text": reason, "source": "cached_stats"})
    for adjustment in (savant_adjustments or [])[:3]:
        reason = clean(adjustment.get("reason"))
        if reason:
            items.append({"type": "analysis", "text": reason, "source": "savant"})
    if weather_context:
        venue = clean(weather_context.get("venue"))
        wind = clean(weather_context.get("wind_mph") or weather_context.get("windMph"))
        if venue or wind:
            items.append({"type": "insight", "text": f"Weather context is available for {venue or 'this game'}{f' with wind {wind} mph' if wind else ''}.", "source": "weather"})
    if not items:
        label = market.replace("_", " ")
        items.append({"type": "insight", "text": f"{player or 'This player'} is priced at {label} line {line}; recommendation is {recommendation.lower()}.", "source": "model"})
    return items[:5]


def unified_prop_card(row: dict[str, Any]) -> dict[str, Any]:
    season = int(clean(row.get("season")) or clean(row.get("date"))[:4] or 2026)
    market = clean(row.get("market") or "batter_hits")
    model_market = base_market(market)
    player = clean(row.get("player"))
    pitcher_name = clean(row.get("pitcher"))
    team_name = clean(row.get("team")).upper()
    opponent_name = clean(row.get("opponent")).upper()
    if market in TEAM_GAME_MARKETS and not player:
        player = f"{team_name} vs {opponent_name}".strip()
    line = to_float(row.get("line"), 0.5)

    model_row = dict(row)
    model_row["market"] = model_market
    base = all_data_predict(model_row)

    pitcher_source = "user_entered" if pitcher_name else ""
    if not pitcher_name:
        inferred_pitcher, inferred_source = infer_pitcher_from_game_context(base, team_name, market)
        if inferred_pitcher:
            pitcher_name = inferred_pitcher
            pitcher_source = inferred_source

    batter_context = summarize_batter(player, season)
    pitcher_context = summarize_pitcher(player if model_market.startswith("pitcher") else pitcher_name, season)
    team_context = summarize_team(team_name, season)
    opponent_context = summarize_team(opponent_name, season)

    cache_adjustment, cache_adjustments = season_adjustment(
        model_market,
        line,
        batter_context,
        pitcher_context,
        team_context,
        opponent_context,
    )

    weather_context = find_weather_feature(
        season,
        clean(row.get("date")),
        team_name,
        opponent_name,
    )
    weather_adjustment = weather_adjustment_for_market(model_market, weather_context)

    odds_movement_context = find_odds_movement_context(
        season,
        clean(row.get("date")),
        model_market,
        player,
        team_name,
        opponent_name,
        pitcher_name,
    )

    odds_movement_adjustment = 0.0
    if odds_movement_context:
        implied_move = to_float(odds_movement_context.get("impliedProbabilityMove"))
        # Conservative: use half of implied move, capped to +/- 1.5%.
        odds_movement_adjustment = clamp(implied_move * 0.5, -0.015, 0.015)

    savant_context = find_savant_context(season, player, pitcher_name, model_market)
    savant_adjustment, savant_adjustments = savant_adjustment_for_market(model_market, savant_context)

    base_probability = to_float(base.get("probability"))
    final_probability = clamp(
        base_probability
        + cache_adjustment
        + weather_adjustment
        + odds_movement_adjustment
        + savant_adjustment
    )
    implied = to_float(base.get("sportsbookImpliedProbability"))

    # Alt/ladder/special markets should be preserved and displayed, but not
    # allowed to create fake huge edges when PropLine only gives us a generic
    # market name and no raw label. Treat them as informational until we have
    # a real market-specific model.
    if is_alt_market(market):
        # Alt/ladder markets are valid and should be displayed, but the current
        # model is still based on the standard stat family. Keep alt-market
        # probabilities conservative until we build true ladder-specific models.
        final_probability = clamp(implied + (final_probability - implied) * 0.15)

    final_edge = final_probability - implied

    used = list(base.get("dataUsed", []) or [])
    missing = list(base.get("missingData", []) or [])

    if batter_context.get("available") or pitcher_context.get("available") or team_context.get("available") or opponent_context.get("available"):
        used.append("Cached 2026 played-game logs")
    else:
        missing.append("Cached 2026 played-game logs")

    if pitcher_name:
        if pitcher_source and pitcher_source != "user_entered":
            used.append("Auto-inferred probable pitcher from MLB StatsAPI game context")
        missing = [
            item for item in missing
            if item != "Pitcher name needed for batter-vs-pitcher sample"
        ]

    if savant_context and (
        savant_context.get("available")
        or savant_context.get("batter")
        or savant_context.get("pitcher")
    ):
        used.append("Baseball Savant quality metrics")
        missing = [
            item for item in missing
            if item != "Baseball Savant quality metrics"
        ]

    if weather_context:
        used.append("Open-Meteo game weather features")
        missing = [
            item for item in missing
            if item not in {
                "Open-Meteo weather context",
                "Open-Meteo game weather features",
            }
        ]
    else:
        missing.append("Open-Meteo game weather features")

    if abs(final_edge) >= 0.06 and len(used) >= 6:
        confidence = "Medium-High"
    elif abs(final_edge) >= 0.04 and len(used) >= 4:
        confidence = "Medium"
    elif len(used) >= 4:
        confidence = "Low-Medium"
    else:
        confidence = "Low"

    if is_alt_market(market) and not clean(row.get("rawLabel")):
        confidence = "Low"
        recommendation = "Alt market / needs label review"
    elif is_alt_market(market):
        confidence = "Low"
        recommendation = "Alt ladder market"
    elif final_edge >= 0.04:
        recommendation = "Positive edge"
    elif final_edge <= -0.04:
        recommendation = "Negative edge / avoid"
    else:
        recommendation = "No clear edge"

    return {
        "season": season,
        "market": market,
        "marketDisplay": clean(row.get("marketDisplay")),
        "baseMarket": model_market,
        "isAltMarket": is_alt_market(market),
        "originalMarket": clean(row.get("originalMarket")),
        "rawLabel": clean(row.get("rawLabel")),
        "marketFamily": clean(row.get("marketFamily")),
        "player": player,
        "team": team_name,
        "opponent": opponent_name,
        "pitcher": pitcher_name,
        "pitcherSource": pitcher_source,
        "line": line,
        "americanOdds": base.get("americanOdds"),
        "allDataProbability": base_probability,
        "allDataProbabilityPercent": pct(base_probability),
        "cachedStatsAdjustment": cache_adjustment,
        "cachedStatsAdjustmentPercent": pct(cache_adjustment),
        "weatherAdjustment": weather_adjustment,
        "weatherAdjustmentPercent": pct(weather_adjustment),
        "oddsMovementAdjustment": odds_movement_adjustment,
        "oddsMovementAdjustmentPercent": pct(odds_movement_adjustment),
        "savantAdjustment": savant_adjustment,
        "savantAdjustmentPercent": pct(savant_adjustment),
        "finalProbability": final_probability,
        "finalProbabilityPercent": pct(final_probability),
        "sportsbookImpliedProbability": implied,
        "sportsbookImpliedPercent": pct(implied),
        "finalEdge": final_edge,
        "finalEdgePercent": pct(final_edge),
        "confidence": confidence,
        "recommendation": recommendation,
        "dataUsed": used,
        "missingData": missing,
        "allData": base,
        "cachedContexts": {
            "batter": batter_context,
            "pitcher": pitcher_context,
            "team": team_context,
            "opponent": opponent_context,
        },
        "weatherContext": weather_context,
        "savant": savant_context,
        "cachedAdjustments": cache_adjustments,
        "insights": build_insights(player, model_market, line, recommendation, cache_adjustments, savant_adjustments, weather_context),
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Unified Prop Card")
    parser.add_argument("--json", required=True)
    args = parser.parse_args()

    print(json.dumps(unified_prop_card(json.loads(args.json)), indent=2))


if __name__ == "__main__":
    main()
