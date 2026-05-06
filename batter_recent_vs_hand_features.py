from __future__ import annotations

"""Build true recent batter hit features split by opposing pitcher hand.

This module uses plate-appearance level BVP rows plus pitcher game-log throwing
hand to build leakage-safe pregame features:

- batter_recent_hits_vs_lhp
- batter_recent_hits_vs_rhp

The previous training join used season-long platoon AVG as a proxy for these
columns. This builder instead aggregates the batter's prior plate appearances
against actual left/right-handed pitchers and emits one row per batter/game date.
"""

from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta
from typing import Any


def clean(value: Any) -> str:
    return str(value or "").strip()


def norm_hand(value: Any) -> str:
    text = clean(value).upper()[:1]
    return text if text in {"L", "R"} else ""


def to_float(value: Any, default: float = 0.0) -> float:
    text = clean(value).replace(",", "")
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def safe_div(numerator: float, denominator: float, digits: int = 4) -> float | str:
    if not denominator:
        return ""
    return round(numerator / denominator, digits)


def parse_date(value: Any) -> datetime | None:
    try:
        return datetime.strptime(clean(value)[:10], "%Y-%m-%d")
    except ValueError:
        return None


def parse_ip(value: Any) -> float:
    """Parse baseball innings correctly: 5.1 = 5 + 1/3."""
    text = clean(value)
    if not text:
        return 0.0
    if "." not in text:
        return to_float(text)

    whole, frac = text.split(".", 1)
    innings = to_float(whole)
    if frac == "1":
        return innings + (1 / 3)
    if frac == "2":
        return innings + (2 / 3)
    return to_float(text)


def truthy_number(value: Any) -> float:
    text = clean(value).lower()
    if text in {"true", "yes", "y"}:
        return 1.0
    if text in {"false", "no", "n"}:
        return 0.0
    return to_float(value)


def build_pitcher_hand_indexes(pitcher_rows: list[dict[str, Any]]) -> tuple[dict[tuple[str, str], str], dict[str, str], dict[tuple[str, str], str]]:
    """Return hand lookup maps for PA-level joins and starter fallbacks."""
    by_game_pitcher: dict[tuple[str, str], str] = {}
    player_hand_counts: dict[str, Counter[str]] = defaultdict(Counter)
    starters_by_game_team: dict[tuple[str, str], tuple[float, float, str]] = {}

    for row in pitcher_rows:
        game_pk = clean(row.get("gamePk"))
        pitcher_id = clean(row.get("playerId"))
        team = clean(row.get("team")).upper()
        hand = norm_hand(row.get("throws"))

        if hand:
            if game_pk and pitcher_id:
                by_game_pitcher[(game_pk, pitcher_id)] = hand
            if pitcher_id:
                player_hand_counts[pitcher_id][hand] += 1

        if game_pk and team:
            rank = (parse_ip(row.get("inningsPitched")), to_float(row.get("battersFaced")), hand)
            key = (game_pk, team)
            current = starters_by_game_team.get(key)
            if current is None or rank[:2] > current[:2]:
                starters_by_game_team[key] = rank

    by_pitcher = {
        pitcher_id: counts.most_common(1)[0][0]
        for pitcher_id, counts in player_hand_counts.items()
        if counts
    }

    starter_hand_by_game_team = {
        key: value[2]
        for key, value in starters_by_game_team.items()
        if value[2]
    }

    return by_game_pitcher, by_pitcher, starter_hand_by_game_team


def build_daily_batter_hand_summaries(
    bvp_rows: list[dict[str, Any]],
    pitcher_rows: list[dict[str, Any]],
) -> dict[tuple[str, str, str, str, str], dict[str, Any]]:
    """Aggregate BVP plate appearances by batter/date/opposing pitcher hand."""
    by_game_pitcher, by_pitcher, starter_hand_by_game_team = build_pitcher_hand_indexes(pitcher_rows)
    daily: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}

    for row in bvp_rows:
        date_value = parse_date(row.get("date"))
        if date_value is None:
            continue

        game_pk = clean(row.get("gamePk"))
        batter_id = clean(row.get("batterId"))
        batter = clean(row.get("batter"))
        team = clean(row.get("battingTeam")).upper()
        pitcher_id = clean(row.get("pitcherId"))
        pitching_team = clean(row.get("pitchingTeam")).upper()

        if not batter and not batter_id:
            continue

        hand = (
            norm_hand(row.get("throws"))
            or by_game_pitcher.get((game_pk, pitcher_id), "")
            or by_pitcher.get(pitcher_id, "")
            or starter_hand_by_game_team.get((game_pk, pitching_team), "")
        )

        if hand not in {"L", "R"}:
            continue

        key = (date_value.strftime("%Y-%m-%d"), batter_id, batter, team, hand)
        item = daily.setdefault(key, {
            "date": date_value,
            "dateLabel": date_value.strftime("%Y-%m-%d"),
            "playerId": batter_id,
            "player": batter,
            "team": team,
            "hand": hand,
            "plateAppearances": 0.0,
            "atBats": 0.0,
            "hits": 0.0,
        })

        item["plateAppearances"] += truthy_number(row.get("isPlateAppearance")) or 1.0
        item["atBats"] += truthy_number(row.get("isAtBat"))
        item["hits"] += truthy_number(row.get("hit"))

    return daily



def build_daily_batter_game_summaries_by_starter_hand(
    batter_rows: list[dict[str, Any]],
    pitcher_rows: list[dict[str, Any]],
) -> dict[tuple[str, str, str, str, str], dict[str, Any]]:
    """Fallback daily summaries keyed by opponent starter hand.

    Use this when PA-level BVP rows are unavailable. It is still a true
    game-by-game recent split because each batter game is assigned to the
    opposing probable/actual starter hand derived from pitcher game logs.
    """
    _, _, starter_hand_by_game_team = build_pitcher_hand_indexes(pitcher_rows)
    daily: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}

    for row in batter_rows:
        date_value = parse_date(row.get("date"))
        if date_value is None:
            continue

        game_pk = clean(row.get("gamePk"))
        opponent = clean(row.get("opponent")).upper()
        hand = starter_hand_by_game_team.get((game_pk, opponent), "")
        if hand not in {"L", "R"}:
            continue

        batter_id = clean(row.get("playerId"))
        batter = clean(row.get("player"))
        team = clean(row.get("team")).upper()
        if not batter and not batter_id:
            continue

        key = (date_value.strftime("%Y-%m-%d"), batter_id, batter, team, hand)
        daily[key] = {
            "date": date_value,
            "dateLabel": date_value.strftime("%Y-%m-%d"),
            "playerId": batter_id,
            "player": batter,
            "team": team,
            "hand": hand,
            "plateAppearances": to_float(row.get("plateAppearances")),
            "atBats": to_float(row.get("atBats")),
            "hits": to_float(row.get("hits")),
        }

    return daily


def build_batter_recent_vs_hand(
    batter_rows: list[dict[str, Any]],
    pitcher_rows: list[dict[str, Any]],
    bvp_rows: list[dict[str, Any]],
    season: int,
    phase: str,
    window_days: int = 30,
) -> list[dict[str, Any]]:
    """Build leakage-safe batter recent hit features split by pitcher hand.

    Output rows are keyed by date/player/team and use only BVP plate appearances
    from dates before the output date.
    """
    daily = build_daily_batter_hand_summaries(bvp_rows, pitcher_rows)
    if not daily:
        daily = build_daily_batter_game_summaries_by_starter_hand(batter_rows, pitcher_rows)

    daily_by_player: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = defaultdict(lambda: {"L": [], "R": []})

    for item in daily.values():
        key = (clean(item.get("playerId")), clean(item.get("player")))
        hand = clean(item.get("hand"))
        if hand in {"L", "R"}:
            daily_by_player[key][hand].append(item)

    for hand_map in daily_by_player.values():
        for items in hand_map.values():
            items.sort(key=lambda item: item["date"])

    game_keys: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in batter_rows:
        date_value = parse_date(row.get("date"))
        if date_value is None:
            continue
        player_id = clean(row.get("playerId"))
        player = clean(row.get("player"))
        team = clean(row.get("team")).upper()
        if not player and not player_id:
            continue
        game_keys[(date_value.strftime("%Y-%m-%d"), player_id, player)] = {
            "date": date_value,
            "dateLabel": date_value.strftime("%Y-%m-%d"),
            "playerId": player_id,
            "player": player,
            "team": team,
        }

    output: list[dict[str, Any]] = []
    windows: dict[tuple[str, str], dict[str, deque[dict[str, Any]]]] = defaultdict(lambda: {"L": deque(), "R": deque()})
    idx_by_player: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"L": 0, "R": 0})

    for _, player_id, player in sorted(game_keys, key=lambda key: (game_keys[key]["date"], key[2].lower())):
        row = game_keys[(_, player_id, player)]
        current_date = row["date"]
        player_key = (player_id, player)
        window_start = current_date - timedelta(days=window_days)

        for hand in ["L", "R"]:
            items = daily_by_player.get(player_key, {}).get(hand, [])
            idx = idx_by_player[player_key][hand]
            queue = windows[player_key][hand]

            while idx < len(items) and items[idx]["date"] < current_date:
                queue.append(items[idx])
                idx += 1
            idx_by_player[player_key][hand] = idx

            while queue and queue[0]["date"] < window_start:
                queue.popleft()

        def hand_stats(hand: str) -> dict[str, Any]:
            queue = windows[player_key][hand]
            hits = sum(to_float(item.get("hits")) for item in queue)
            at_bats = sum(to_float(item.get("atBats")) for item in queue)
            pa = sum(to_float(item.get("plateAppearances")) for item in queue)
            games = len({clean(item.get("dateLabel")) for item in queue})
            return {
                "hits": round(hits, 3),
                "atBats": round(at_bats, 3),
                "plateAppearances": round(pa, 3),
                "games": games,
                "hitsPerGame": safe_div(hits, games, 4),
                "avg": safe_div(hits, at_bats, 4),
            }

        lhp = hand_stats("L")
        rhp = hand_stats("R")

        output.append({
            "season": season,
            "seasonPhase": phase,
            "date": row["dateLabel"],
            "playerId": row["playerId"],
            "player": row["player"],
            "team": row["team"],
            "windowDays": window_days,
            "batter_recent_hits_vs_lhp": lhp["hitsPerGame"],
            "batter_recent_hits_vs_rhp": rhp["hitsPerGame"],
            "batter_recent_avg_vs_lhp": lhp["avg"],
            "batter_recent_avg_vs_rhp": rhp["avg"],
            "batter_recent_pa_vs_lhp": lhp["plateAppearances"],
            "batter_recent_pa_vs_rhp": rhp["plateAppearances"],
            "batter_recent_ab_vs_lhp": lhp["atBats"],
            "batter_recent_ab_vs_rhp": rhp["atBats"],
            "batter_recent_games_vs_lhp": lhp["games"],
            "batter_recent_games_vs_rhp": rhp["games"],
        })

    return output
