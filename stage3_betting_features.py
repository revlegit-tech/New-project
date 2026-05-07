"""Stage 3 betting-product payload helpers.

Adds line shopping, steam alerts, Kelly sizing inputs, and P&L analytics without
changing the existing prediction engine.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return _clean(value).lower().replace("  ", " ")


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        n = float(value)
        if math.isfinite(n):
            return n
    except Exception:
        pass
    return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        return list(csv.DictReader(f))


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}


def american_to_decimal(odds: Any) -> float:
    n = _float(odds)
    if not n:
        return 0.0
    if n > 0:
        return 1.0 + (n / 100.0)
    return 1.0 + (100.0 / abs(n))


def american_implied_probability(odds: Any) -> float:
    n = _float(odds)
    if not n:
        return 0.0
    if n > 0:
        return 100.0 / (n + 100.0)
    return abs(n) / (abs(n) + 100.0)


def ev_per_unit(model_probability: float, odds: Any) -> float:
    p = max(0.0, min(1.0, model_probability))
    dec = american_to_decimal(odds)
    if dec <= 1:
        return 0.0
    profit = dec - 1.0
    return (p * profit) - (1.0 - p)


def kelly_fraction(model_probability: float, odds: Any) -> float:
    p = max(0.0, min(1.0, model_probability))
    q = 1.0 - p
    b = american_to_decimal(odds) - 1.0
    if b <= 0:
        return 0.0
    return max(0.0, (b * p - q) / b)


def line_comparison_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    season = _int(query.get("season", ["2026"])[0], 2026)
    date = _clean(query.get("date", [""])[0])
    market = _norm(query.get("market", [""])[0])
    player = _norm(query.get("player", [""])[0])
    team = _norm(query.get("team", [""])[0])
    opponent = _norm(query.get("opponent", [""])[0])
    pitcher = _norm(query.get("pitcher", [""])[0])
    model_probability_percent = _float(query.get("model_probability_percent", ["0"])[0])
    model_probability = model_probability_percent / 100.0

    path = ROOT / "data" / "cache" / "odds_movement" / f"prop_snapshots_{season}.csv"
    rows = _read_csv(path)

    def matches(row: dict[str, str]) -> bool:
        if market and _norm(row.get("market")) != market:
            return False
        if date and not _clean(row.get("date", "")).startswith(date):
            return False
        if player and player not in _norm(row.get("player")):
            return False
        if team and _norm(row.get("team")) and _norm(row.get("team")) != team:
            return False
        if opponent and _norm(row.get("opponent")) and _norm(row.get("opponent")) != opponent:
            return False
        if pitcher and _norm(row.get("pitcher")) and pitcher not in _norm(row.get("pitcher")):
            return False
        return True

    matches_rows = [r for r in rows if matches(r)]
    latest_by_book: dict[str, dict[str, str]] = {}
    for row in matches_rows:
        book = _clean(row.get("sportsbook")) or "Unknown book"
        prev = latest_by_book.get(book)
        if not prev or _clean(row.get("snapshotAt")) >= _clean(prev.get("snapshotAt")):
            latest_by_book[book] = row

    books = []
    for book, row in latest_by_book.items():
        odds = _float(row.get("americanOdds"))
        implied = american_implied_probability(odds)
        edge = (model_probability - implied) * 100.0 if model_probability else 0.0
        ev = ev_per_unit(model_probability, odds) if model_probability else 0.0
        kelly = kelly_fraction(model_probability, odds) if model_probability else 0.0
        books.append({
            "sportsbook": book,
            "line": _float(row.get("line")),
            "americanOdds": odds,
            "impliedProbabilityPercent": round(implied * 100.0, 2),
            "edgePercent": round(edge, 2),
            "evPerUnit": round(ev, 4),
            "kellyFractionPercent": round(kelly * 100.0, 2),
            "snapshotAt": _clean(row.get("snapshotAt")),
        })

    books.sort(key=lambda r: (r["evPerUnit"], r["edgePercent"], r["americanOdds"]), reverse=True)
    for idx, row in enumerate(books):
        row["isBest"] = idx == 0 and bool(books)

    return {
        "season": season,
        "date": date,
        "market": market,
        "player": query.get("player", [""])[0],
        "modelProbabilityPercent": round(model_probability_percent, 2),
        "snapshotFile": str(path),
        "rowsMatched": len(matches_rows),
        "books": books,
        "best": books[0] if books else None,
    }


def steam_alerts_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    season = _int(query.get("season", ["2026"])[0], 2026)
    date = _clean(query.get("date", [""])[0])
    market = _norm(query.get("market", [""])[0])
    limit = _int(query.get("limit", ["20"])[0], 20)

    path = ROOT / "data" / "cache" / "odds_movement" / f"prop_movement_{season}.csv"
    rows = _read_csv(path)
    alerts = []
    for row in rows:
        if date and not _clean(row.get("date", "")).startswith(date):
            continue
        if market and _norm(row.get("market")) != market:
            continue
        line_move = _float(row.get("lineMove") or row.get("line_move"))
        odds_move = _float(row.get("oddsMove") or row.get("odds_move"))
        if abs(line_move) < 0.5 and abs(odds_move) < 15:
            continue
        direction = _clean(row.get("movementDirection"))
        alerts.append({
            "date": _clean(row.get("date"))[:10],
            "market": _clean(row.get("market")),
            "player": _clean(row.get("player")),
            "team": _clean(row.get("team")),
            "opponent": _clean(row.get("opponent")),
            "pitcher": _clean(row.get("pitcher")),
            "firstLine": _float(row.get("firstLine")),
            "latestLine": _float(row.get("latestLine")),
            "lineMove": round(line_move, 2),
            "firstAmericanOdds": _float(row.get("firstAmericanOdds")),
            "latestAmericanOdds": _float(row.get("latestAmericanOdds")),
            "oddsMove": round(odds_move, 2),
            "impliedProbabilityMovePercent": round(_float(row.get("impliedProbabilityMove")) * 100.0, 2),
            "direction": direction,
            "tone": "steam" if direction == "over_price_up" or odds_move < 0 else "drift",
            "movementSummary": _clean(row.get("movementSummary")),
            "snapshots": _int(row.get("snapshots")),
            "latestSnapshotAt": _clean(row.get("latestSnapshotAt")),
            "score": abs(line_move) * 300.0 + abs(odds_move),
        })

    alerts.sort(key=lambda r: r["score"], reverse=True)
    for row in alerts:
        row.pop("score", None)
    return {"season": season, "date": date, "market": market, "alerts": alerts[:limit], "totalAlerts": len(alerts), "movementFile": str(path)}


def pnl_analytics_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    season = _int(query.get("season", ["2026"])[0], 2026)
    market = _norm(query.get("market", [""])[0])
    path = ROOT / "data" / "backtests" / f"playerboard_backtest_{season}.csv"
    rows = [r for r in _read_csv(path) if not market or _norm(r.get("market")) == market]

    graded = [r for r in rows if _norm(r.get("result")) in {"win", "loss", "push"}]
    wins = sum(1 for r in graded if _norm(r.get("result")) == "win")
    losses = sum(1 for r in graded if _norm(r.get("result")) == "loss")
    pushes = sum(1 for r in graded if _norm(r.get("result")) == "push")
    profit = sum(_float(r.get("profitUnits")) for r in graded)
    risked = sum(1 for r in graded if _norm(r.get("result")) in {"win", "loss"})

    by_day: dict[str, dict[str, Any]] = defaultdict(lambda: {"date": "", "picks": 0, "profitUnits": 0.0})
    by_market: dict[str, dict[str, Any]] = defaultdict(lambda: {"market": "", "picks": 0, "wins": 0, "losses": 0, "profitUnits": 0.0})
    running = 0.0
    for row in sorted(graded, key=lambda r: _clean(r.get("date"))):
        d = _clean(row.get("date"))[:10] or "Unknown"
        m = _clean(row.get("market")) or "unknown"
        units = _float(row.get("profitUnits"))
        by_day[d]["date"] = d
        by_day[d]["picks"] += 1
        by_day[d]["profitUnits"] += units
        by_market[m]["market"] = m
        by_market[m]["picks"] += 1
        by_market[m]["profitUnits"] += units
        if _norm(row.get("result")) == "win":
            by_market[m]["wins"] += 1
        elif _norm(row.get("result")) == "loss":
            by_market[m]["losses"] += 1

    day_rows = []
    for d in sorted(by_day):
        running += by_day[d]["profitUnits"]
        day_rows.append({**by_day[d], "profitUnits": round(by_day[d]["profitUnits"], 2), "cumulativeUnits": round(running, 2)})

    market_rows = []
    for m, r in by_market.items():
        decisions = r["wins"] + r["losses"]
        market_rows.append({**r, "profitUnits": round(r["profitUnits"], 2), "winRate": round((r["wins"] / decisions) * 100.0, 2) if decisions else 0.0})
    market_rows.sort(key=lambda r: r["profitUnits"], reverse=True)

    current_streak = 0
    current_type = ""
    longest_win = longest_loss = run = 0
    last_type = ""
    for row in sorted(graded, key=lambda r: (_clean(r.get("date")), _clean(r.get("gradedAt")))):
        typ = _norm(row.get("result"))
        if typ == "push":
            continue
        run = run + 1 if typ == last_type else 1
        last_type = typ
        if typ == "win": longest_win = max(longest_win, run)
        if typ == "loss": longest_loss = max(longest_loss, run)
        current_streak = run
        current_type = typ

    audit = _read_json(ROOT / "data" / "audit" / f"model_audit_{season}.json")
    return {
        "season": season,
        "summary": {
            "picks": len(graded), "wins": wins, "losses": losses, "pushes": pushes,
            "profitUnits": round(profit, 2), "winRate": round((wins / (wins + losses)) * 100.0, 2) if wins + losses else 0.0,
            "roiPercent": round((profit / risked) * 100.0, 2) if risked else 0.0,
            "longestWinStreak": longest_win, "longestLossStreak": longest_loss,
            "currentStreak": {"type": current_type, "count": current_streak},
        },
        "byDay": day_rows[-60:],
        "byMarket": market_rows,
        "recent": list(reversed(graded[-12:])),
        "modelAudit": {
            "updatedAt": audit.get("updatedAt"), "warningRows": audit.get("warningRows"),
            "profitUnits": audit.get("profitUnits"), "roiPercent": audit.get("roiPercent"),
            "topWarnings": audit.get("topWarnings", [])[:5],
        },
        "backtestFile": str(path),
    }


def _market_display(market: Any) -> str:
    text = _clean(market).replace("_", " ").strip()
    return text.title() if text else "Prop"


def _pct_window(item: dict[str, Any], key: str = "L10") -> dict[str, Any] | None:
    value = item.get(key)
    return value if isinstance(value, dict) and _float(value.get("pct"), -1) >= 0 else None


def _badge_for_pct(pct: float) -> str:
    if pct >= 80:
        return "ob-green"
    if pct >= 65:
        return "ob-amber"
    return "ob-red"


def _latest_playerboard_lookup(season: int, date: str = "") -> dict[tuple[str, str, str], dict[str, str]]:
    path = ROOT / "data" / "playerboard" / f"playerboard_{season}.csv"
    rows = _read_csv(path)
    if date:
        dated = [row for row in rows if _clean(row.get("date"))[:10] == date]
        if dated:
            rows = dated
    latest: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in rows:
        key = (_norm(row.get("player") or row.get("team")), _norm(row.get("market")), _clean(row.get("team")).upper())
        prev = latest.get(key)
        if not prev or _clean(row.get("snapshotAt")) >= _clean(prev.get("snapshotAt")):
            latest[key] = row
    return latest


def _team_recent_trends(season: int, limit: int = 8) -> list[dict[str, Any]]:
    path = ROOT / "data" / "cache" / "incremental_stats" / f"team_game_logs_{season}.csv"
    rows = _read_csv(path)
    by_team: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        team = _clean(row.get("team")).upper()
        if team:
            by_team[team].append(row)

    cards: list[dict[str, Any]] = []
    for team, team_rows in by_team.items():
        team_rows.sort(key=lambda row: (_clean(row.get("date")), _clean(row.get("gamePk"))))
        recent = team_rows[-15:]
        if len(recent) < 8:
            continue
        wins = 0
        run_diff = 0.0
        for row in recent:
            runs = _float(row.get("runs"))
            allowed = _float(row.get("pitchingRuns"))
            run_diff += runs - allowed
            if runs > allowed:
                wins += 1
        if wins <= 3 or wins >= 12:
            pct = round((wins / len(recent)) * 100.0)
            direction = "struggling" if wins <= 3 else "surging"
            cards.append({
                "type": "ats",
                "team": team,
                "player": team,
                "game": team,
                "gameTime": "Recent form",
                "text": f"{team} is {wins}-{len(recent) - wins} over its last {len(recent)} games with a {run_diff:+.0f} run differential. Treat this as a team-form proxy until spread results are available.",
                "market": "Team trend",
                "odds": "",
                "hitRateBar": {"pct": pct, "total": len(recent)},
                "badge": "ob-red" if wins <= 3 else "ob-green",
            })
    cards.sort(key=lambda card: abs(_float(card.get("hitRateBar", {}).get("pct"), 50) - 50), reverse=True)
    return cards[:limit]


def insights_feed_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    """Aggregate premium feed cards for the Outlier-style insights rail/page.

    Card scoring mirrors the audit plan:
      score = L10 hit rate + streak length × 5 + edge percent × 3 + steam flag × 20
    The feed intentionally mixes streak, H2H, split/recent-form, steam, and team-form cards.
    """
    season = _int(query.get("season", ["2026"])[0], 2026)
    date = _clean(query.get("date", [""])[0])
    limit = _int(query.get("limit", ["40"])[0], 40)
    cards: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    playerboard = _latest_playerboard_lookup(season, date)

    def add_card(card: dict[str, Any]) -> None:
        key = (_clean(card.get("type")), _norm(card.get("player")), _clean(card.get("market")))
        if key in seen:
            return
        seen.add(key)
        cards.append(card)

    def card_score(l10_pct: float, streak_length: int = 0, edge_percent: float = 0.0, steam_flag: bool = False) -> float:
        return l10_pct + (streak_length * 5.0) + (edge_percent * 3.0) + (20.0 if steam_flag else 0.0)

    try:
        from player_hit_rates import player_hit_rates_payload
        hit_payload = player_hit_rates_payload({"season": [str(season)], "date": [date], "limit": ["1000"]})
        for row in hit_payload.get("rows", []):
            l10 = _pct_window(row, "L10")
            if not l10:
                continue
            l10_pct = _float(l10.get("pct"))
            if l10_pct < 60:
                continue

            player = _clean(row.get("player")) or _clean(row.get("team"))
            team = _clean(row.get("team")).upper()
            opponent = _clean(row.get("opponent")).upper()
            market = _clean(row.get("market"))
            lookup = playerboard.get((_norm(player), _norm(market), team), {})
            side = _clean(row.get("rawLabel") or lookup.get("rawLabel") or "Under").title()
            line = row.get("line") if row.get("line") not in (None, "") else lookup.get("line")
            edge = _float(lookup.get("finalEdgePercent"))
            l10_hits = _int(l10.get("hits"))
            l10_total = _int(l10.get("total"))
            misses = max(0, l10_total - l10_hits)
            streak_length = l10_hits if misses == 0 else max(0, l10_hits - misses)
            market_text = f"{side} {line} {_market_display(market)}"
            game_text = f"{team} @ {opponent}" if opponent else team

            if l10_pct >= 80:
                add_card({
                    "type": "streak",
                    "player": player,
                    "team": team,
                    "game": game_text,
                    "gameTime": "Today",
                    "text": f"{player} has cleared this {market_text} profile in {l10_hits} of the last {l10_total} logged games.",
                    "market": market_text,
                    "odds": _clean(lookup.get("americanOdds")),
                    "hitRateBar": {"pct": round(l10_pct), "total": l10_total},
                    "badge": _badge_for_pct(l10_pct),
                    "sortScore": card_score(l10_pct, streak_length, edge),
                })

            h2h = _pct_window(row, "H2H")
            if h2h and _int(h2h.get("total")) >= 3:
                h2h_pct = _float(h2h.get("pct"))
                add_card({
                    "type": "h2h",
                    "player": player,
                    "team": team,
                    "game": game_text,
                    "gameTime": "Matchup history",
                    "text": f"{player} has cleared this line in {_int(h2h.get('hits'))} of {_int(h2h.get('total'))} matchups against {opponent or 'today’s opponent'}.",
                    "market": market_text,
                    "odds": _clean(lookup.get("americanOdds")),
                    "hitRateBar": {"pct": round(h2h_pct), "total": _int(h2h.get("total"))},
                    "badge": _badge_for_pct(h2h_pct),
                    "sortScore": card_score(l10_pct, streak_length, edge) + 8,
                })

            season_window = _pct_window(row, "season")
            if season_window and _int(season_window.get("total")) >= 10:
                season_pct = _float(season_window.get("pct"))
                delta = l10_pct - season_pct
                if abs(delta) >= 15:
                    direction = "well above" if delta > 0 else "well below"
                    add_card({
                        "type": "split",
                        "player": player,
                        "team": team,
                        "game": game_text,
                        "gameTime": "Recent split",
                        "text": f"{player}'s last-10 hit rate is {abs(delta):.0f} points {direction} his {season} season baseline for this market.",
                        "market": market_text,
                        "odds": _clean(lookup.get("americanOdds")),
                        "hitRateBar": {"pct": round(l10_pct), "total": l10_total},
                        "badge": "ob-green" if delta > 0 else "ob-amber",
                        "sortScore": card_score(l10_pct, streak_length, edge) + abs(delta) / 2,
                    })
    except Exception as error:
        add_card({
            "type": "streak",
            "player": "Hit-rate engine",
            "team": "MLB",
            "game": "MLB",
            "gameTime": "Today",
            "text": f"Hit-rate insights are temporarily unavailable: {error}",
            "market": "Hit-rate status",
            "odds": "",
            "hitRateBar": {"pct": 0, "total": 0},
            "badge": "ob-red",
            "sortScore": -1,
        })

    try:
        steam_payload = steam_alerts_payload({"season": [str(season)], "date": [date], "limit": [str(max(10, limit))]})
        for alert in steam_payload.get("alerts", []):
            latest_odds = alert.get("latestAmericanOdds")
            move = _float(alert.get("oddsMove"))
            pct_move = abs(_float(alert.get("impliedProbabilityMovePercent")))
            player = _clean(alert.get("player")) or "Market steam"
            team = _clean(alert.get("team")).upper()
            opponent = _clean(alert.get("opponent")).upper()
            line_move = _float(alert.get("lineMove"))
            text = _clean(alert.get("movementSummary"))
            if not text:
                text = f"{player} moved {line_move:+.1f} points on the line and {move:+.0f} cents in price across {_int(alert.get('snapshots'))} snapshots."
            add_card({
                "type": "steam",
                "player": player,
                "team": team or "MLB",
                "game": f"{team} @ {opponent}" if team and opponent else "MLB slate",
                "gameTime": _clean(alert.get("latestSnapshotAt")) or "Latest move",
                "text": text,
                "market": f"{_market_display(alert.get('market'))} {alert.get('latestLine')}",
                "odds": str(int(latest_odds)) if isinstance(latest_odds, (int, float)) and latest_odds else _clean(latest_odds),
                "hitRateBar": {"pct": max(5, min(100, round(pct_move * 4))), "total": _int(alert.get("snapshots"))},
                "badge": "ob-amber" if _clean(alert.get("tone")) == "drift" else "ob-green",
                "sortScore": card_score(55 + pct_move, abs(round(line_move)), 0, True) + abs(move) / 10.0,
            })
    except Exception:
        pass

    for card in _team_recent_trends(season, limit=8):
        card["sortScore"] = _float(card.get("hitRateBar", {}).get("pct"), 50)
        add_card(card)

    cards.sort(key=lambda card: _float(card.get("sortScore")), reverse=True)
    for card in cards:
        card.pop("sortScore", None)
    return {
        "ok": True,
        "season": season,
        "date": date,
        "cards": cards[:limit],
        "cardCount": min(len(cards), limit),
        "totalCards": len(cards),
        "generatedAt": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "sources": ["player_hit_rates", "steam_alerts", "team_game_logs"],
    }
