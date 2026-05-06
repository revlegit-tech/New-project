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
