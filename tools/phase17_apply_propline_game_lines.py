#!/usr/bin/env python3
"""Apply PropLine game-line context to playerboard rows.

This is a defensive Phase 17 v3 bridge. It consumes the local game-line
snapshot written by the Phase 17 API bridge and joins moneyline/total context
onto data/playerboard/playerboard_<season>.csv for a requested slate date.

Design rules:
- No generic fallback odds.
- No fabricated game totals.
- Team implied runs are only computed when both a game total and team/opponent
  moneylines are present.
- The script writes an audit JSON so matching failures are visible.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
PLAYERBOARD_DIR = ROOT / "data" / "playerboard"
GAME_CONTEXT_DIR = ROOT / "data" / "warehouse" / "game_context"
AUDIT_DIR = ROOT / "data" / "warehouse" / "audits"

MONEYLINE_FIELDS = [
    "team_moneyline",
    "opponent_moneyline",
    "open_team_moneyline",
    "close_team_moneyline",
    "moneyline_move",
    "moneyline_implied_probability",
]
TOTAL_FIELDS = [
    "game_total",
    "open_game_total",
    "close_game_total",
    "total_move",
]
IMPLIED_FIELDS = [
    "team_implied_runs",
    "opponent_implied_runs",
    "opponent_implied_runs_proxy",
    "implied_runs_source",
]
SOURCE_FIELDS = [
    "game_line_source",
    "game_line_book",
    "game_line_event_id",
]
ADDED_FIELDS = MONEYLINE_FIELDS + TOTAL_FIELDS + IMPLIED_FIELDS + SOURCE_FIELDS

TEAM_ALIASES = {
    "ari": "arizona diamondbacks", "arizona": "arizona diamondbacks", "diamondbacks": "arizona diamondbacks",
    "atl": "atlanta braves", "atlanta": "atlanta braves", "braves": "atlanta braves",
    "bal": "baltimore orioles", "baltimore": "baltimore orioles", "orioles": "baltimore orioles",
    "bos": "boston red sox", "boston": "boston red sox", "red sox": "boston red sox",
    "chc": "chicago cubs", "cubs": "chicago cubs",
    "cws": "chicago white sox", "chw": "chicago white sox", "white sox": "chicago white sox",
    "cin": "cincinnati reds", "cincinnati": "cincinnati reds", "reds": "cincinnati reds",
    "cle": "cleveland guardians", "cleveland": "cleveland guardians", "guardians": "cleveland guardians",
    "col": "colorado rockies", "colorado": "colorado rockies", "rockies": "colorado rockies",
    "det": "detroit tigers", "detroit": "detroit tigers", "tigers": "detroit tigers",
    "hou": "houston astros", "houston": "houston astros", "astros": "houston astros",
    "kc": "kansas city royals", "kcr": "kansas city royals", "royals": "kansas city royals",
    "laa": "los angeles angels", "angels": "los angeles angels",
    "lad": "los angeles dodgers", "dodgers": "los angeles dodgers",
    "mia": "miami marlins", "miami": "miami marlins", "marlins": "miami marlins",
    "mil": "milwaukee brewers", "milwaukee": "milwaukee brewers", "brewers": "milwaukee brewers",
    "min": "minnesota twins", "minnesota": "minnesota twins", "twins": "minnesota twins",
    "nym": "new york mets", "mets": "new york mets",
    "nyy": "new york yankees", "yankees": "new york yankees",
    "oak": "oakland athletics", "athletics": "oakland athletics", "a's": "oakland athletics",
    "phi": "philadelphia phillies", "philadelphia": "philadelphia phillies", "phillies": "philadelphia phillies",
    "pit": "pittsburgh pirates", "pittsburgh": "pittsburgh pirates", "pirates": "pittsburgh pirates",
    "sd": "san diego padres", "sdp": "san diego padres", "padres": "san diego padres",
    "sf": "san francisco giants", "sfg": "san francisco giants", "giants": "san francisco giants",
    "sea": "seattle mariners", "seattle": "seattle mariners", "mariners": "seattle mariners",
    "stl": "st. louis cardinals", "st louis": "st. louis cardinals", "cardinals": "st. louis cardinals",
    "tb": "tampa bay rays", "tbr": "tampa bay rays", "rays": "tampa bay rays",
    "tex": "texas rangers", "texas": "texas rangers", "rangers": "texas rangers",
    "tor": "toronto blue jays", "toronto": "toronto blue jays", "blue jays": "toronto blue jays",
    "wsh": "washington nationals", "was": "washington nationals", "nationals": "washington nationals",
}


def norm_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("&amp;", "&")
    text = re.sub(r"\s+", " ", text)
    text = text.replace("—", "-").replace("–", "-")
    return text


def norm_team(value: Any) -> str:
    text = norm_text(value)
    text = text.replace(".", "")
    text = re.sub(r"\bteam\b", "", text).strip()
    if text in TEAM_ALIASES:
        return TEAM_ALIASES[text]
    # Try suffix aliases, e.g. "SD Padres" -> padres.
    parts = text.split()
    for size in (2, 1):
        tail = " ".join(parts[-size:])
        if tail in TEAM_ALIASES:
            return TEAM_ALIASES[tail]
    return text


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isfinite(float(value)):
            return float(value)
        return None
    text = str(value).strip().replace("%", "")
    if not text:
        return None
    try:
        out = float(text)
        return out if math.isfinite(out) else None
    except ValueError:
        return None


def moneyline_to_probability(odds: Optional[float]) -> Optional[float]:
    if odds is None or odds == 0:
        return None
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


def implied_runs_proxy(total: Optional[float], team_ml: Optional[float], opp_ml: Optional[float]) -> Tuple[Optional[float], Optional[float]]:
    if total is None or team_ml is None or opp_ml is None:
        return None, None
    tp = moneyline_to_probability(team_ml)
    op = moneyline_to_probability(opp_ml)
    if tp is None or op is None:
        return None, None
    denom = tp + op
    if denom <= 0:
        return None, None
    # Remove rough vig, then shift runs around half the game total. Keep the
    # adjustment bounded so an outlier moneyline cannot create nonsense totals.
    win_share = tp / denom
    edge = max(-0.5, min(0.5, win_share - 0.5))
    adjustment = edge * 2.25
    team_runs = max(0.0, min(total, total / 2.0 + adjustment))
    opp_runs = max(0.0, min(total, total - team_runs))
    return round(team_runs, 3), round(opp_runs, 3)


def walk_json(obj: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk_json(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from walk_json(item)


def find_first_dicts(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("events", "games", "data", "results", "odds", "payload"):
            value = payload.get(key)
            if isinstance(value, list) and any(isinstance(x, dict) for x in value):
                return [x for x in value if isinstance(x, dict)]
    return []


def parse_game_title(text: Any) -> Tuple[str, str]:
    s = str(text or "")
    for sep in (" @ ", " at ", " vs ", " v ", " - "):
        if sep in s:
            left, right = s.split(sep, 1)
            return norm_team(left), norm_team(right)
    return "", ""


def get_event_teams(event: Dict[str, Any]) -> Tuple[str, str]:
    candidates = [
        (event.get("away_team"), event.get("home_team")),
        (event.get("awayTeam"), event.get("homeTeam")),
        (event.get("away"), event.get("home")),
        (event.get("visitor"), event.get("home")),
    ]
    for away, home in candidates:
        if away and home:
            return norm_team(away), norm_team(home)
    for key in ("game", "name", "title", "event", "description", "matchup"):
        away, home = parse_game_title(event.get(key))
        if away and home:
            return away, home
    teams = event.get("teams") or event.get("participants") or event.get("competitors")
    if isinstance(teams, list) and len(teams) >= 2:
        names = []
        for team in teams[:2]:
            if isinstance(team, dict):
                names.append(norm_team(team.get("name") or team.get("team") or team.get("displayName")))
            else:
                names.append(norm_team(team))
        return names[0], names[1]
    return "", ""


def is_moneyline_market(market: Dict[str, Any]) -> bool:
    text = " ".join(str(market.get(k, "")) for k in ("key", "market", "name", "title", "type", "label")).lower()
    return any(x in text for x in ("moneyline", "money line", "h2h", "head to head", "winner"))


def is_total_market(market: Dict[str, Any]) -> bool:
    text = " ".join(str(market.get(k, "")) for k in ("key", "market", "name", "title", "type", "label")).lower()
    if "team total" in text or "player" in text:
        return False
    return any(x in text for x in ("game total", "total runs", "totals", "total"))


def extract_outcomes(market: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in ("outcomes", "prices", "selections", "runners", "lines"):
        value = market.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def extract_markets(event: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    found: List[Tuple[str, Dict[str, Any]]] = []
    # Direct markets.
    for key in ("markets", "odds", "bookmakers"):
        value = event.get(key)
        if isinstance(value, list):
            for item in value:
                if not isinstance(item, dict):
                    continue
                book = str(item.get("bookmaker") or item.get("book") or item.get("title") or item.get("key") or "PropLine")
                if "markets" in item and isinstance(item["markets"], list):
                    for market in item["markets"]:
                        if isinstance(market, dict):
                            found.append((book, market))
                else:
                    found.append((book, item))
        elif isinstance(value, dict):
            for _, item in value.items():
                if isinstance(item, dict):
                    found.append((str(item.get("book") or "PropLine"), item))
                elif isinstance(item, list):
                    for x in item:
                        if isinstance(x, dict):
                            found.append((str(x.get("book") or "PropLine"), x))
    # Fallback: any nested dict that looks like a market.
    for d in walk_json(event):
        if ("outcomes" in d or "prices" in d or "selections" in d) and (is_moneyline_market(d) or is_total_market(d)):
            found.append((str(d.get("book") or d.get("bookmaker") or d.get("source") or "PropLine"), d))
    # Deduplicate by object identity-ish signature.
    unique: List[Tuple[str, Dict[str, Any]]] = []
    seen = set()
    for book, market in found:
        sig = json.dumps(market, sort_keys=True, default=str)[:1000]
        if sig not in seen:
            seen.add(sig)
            unique.append((book, market))
    return unique


@dataclass
class GameLine:
    away: str
    home: str
    event_id: str = ""
    source: str = "propline"
    book: str = ""
    moneylines: Dict[str, float] = field(default_factory=dict)
    total: Optional[float] = None

    @property
    def key(self) -> Tuple[str, str]:
        return tuple(sorted([self.away, self.home]))


def parse_game_lines(payload: Any) -> List[GameLine]:
    events = find_first_dicts(payload)
    if not events and isinstance(payload, dict):
        events = [payload]
    games: List[GameLine] = []
    for event in events:
        away, home = get_event_teams(event)
        if not away or not home:
            continue
        gl = GameLine(
            away=away,
            home=home,
            event_id=str(event.get("id") or event.get("event_id") or event.get("eventId") or ""),
        )
        for book, market in extract_markets(event):
            if is_moneyline_market(market):
                for outcome in extract_outcomes(market):
                    name = norm_team(outcome.get("name") or outcome.get("team") or outcome.get("label") or outcome.get("selection"))
                    price = to_float(outcome.get("price") or outcome.get("odds") or outcome.get("american_odds") or outcome.get("americanOdds"))
                    if name and price is not None:
                        gl.moneylines[name] = price
                        gl.book = gl.book or book
            elif is_total_market(market):
                for outcome in extract_outcomes(market):
                    label = norm_text(outcome.get("name") or outcome.get("label") or outcome.get("selection"))
                    point = to_float(outcome.get("point") or outcome.get("line") or outcome.get("total") or outcome.get("value"))
                    if point is not None and (not label or "over" in label or "total" in label):
                        gl.total = point
                        gl.book = gl.book or book
                        break
                # Sometimes the market itself has the point.
                if gl.total is None:
                    point = to_float(market.get("point") or market.get("line") or market.get("total"))
                    if point is not None:
                        gl.total = point
                        gl.book = gl.book or book
        # Preserve games that have either moneyline or total.
        if gl.moneylines or gl.total is not None:
            games.append(gl)
    # Last-resort extraction for flat game-line rows.
    if not games:
        for row in find_first_dicts(payload):
            away, home = get_event_teams(row)
            if not away or not home:
                continue
            gl = GameLine(away=away, home=home, event_id=str(row.get("event_id") or row.get("id") or ""), book=str(row.get("book") or row.get("bookmaker") or "PropLine"))
            for k, v in row.items():
                nk = norm_text(k)
                if "away" in nk and "money" in nk:
                    odds = to_float(v)
                    if odds is not None:
                        gl.moneylines[away] = odds
                if "home" in nk and "money" in nk:
                    odds = to_float(v)
                    if odds is not None:
                        gl.moneylines[home] = odds
                if "total" in nk and "team" not in nk:
                    total = to_float(v)
                    if total is not None and 3 <= total <= 20:
                        gl.total = total
            if gl.moneylines or gl.total is not None:
                games.append(gl)
    return games


def row_date(row: Dict[str, str]) -> str:
    for key in ("date", "game_date", "slate_date", "eventDateLocal"):
        if row.get(key):
            return str(row[key])[:10]
    return ""


def row_market(row: Dict[str, str]) -> str:
    for key in ("market", "market_key", "prop_market", "stat"):
        if row.get(key):
            return str(row[key])
    return ""


def row_team_pair(row: Dict[str, str]) -> Tuple[str, str]:
    team = row.get("team") or row.get("player_team") or row.get("abbr") or row.get("team_abbr") or row.get("teamName")
    opp = row.get("opponent") or row.get("opp") or row.get("opponent_team") or row.get("opponentName")
    if team and opp:
        return norm_team(team), norm_team(opp)
    for key in ("game", "matchup", "event", "game_name"):
        away, home = parse_game_title(row.get(key))
        if away and home:
            # For props, team/opponent may be unknown but the unordered key is enough.
            return away, home
    return "", ""


def write_csv_atomic(path: Path, fieldnames: List[str], rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", delete=False, dir=str(path.parent), suffix=".tmp") as tmp:
        writer = csv.DictWriter(tmp, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def apply_lines(date: str, season: int, markets: List[str], dry_run: bool = False) -> Dict[str, Any]:
    playerboard_path = PLAYERBOARD_DIR / f"playerboard_{season}.csv"
    game_lines_path = GAME_CONTEXT_DIR / f"game_lines_{date}.json"
    if not playerboard_path.exists():
        raise FileNotFoundError(playerboard_path)
    if not game_lines_path.exists():
        raise FileNotFoundError(game_lines_path)

    payload = json.loads(game_lines_path.read_text(encoding="utf-8"))
    games = parse_game_lines(payload)
    by_key = {g.key: g for g in games}

    with playerboard_path.open("r", newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = [dict(r) for r in reader]
        original_fields = list(reader.fieldnames or [])

    fieldnames = list(original_fields)
    for f in ADDED_FIELDS:
        if f not in fieldnames:
            fieldnames.append(f)

    market_set = {m.strip() for m in markets if m.strip()}
    target = matched = updated = no_game = no_line = 0
    unmatched_examples: List[Dict[str, str]] = []

    for row in rows:
        if row_date(row) != date:
            continue
        if market_set and row_market(row) not in market_set:
            continue
        target += 1
        a, b = row_team_pair(row)
        if not a or not b:
            no_game += 1
            if len(unmatched_examples) < 8:
                unmatched_examples.append({"reason": "missing_team_pair", "player": row.get("player", ""), "game": row.get("game", "")})
            continue
        game = by_key.get(tuple(sorted([a, b])))
        if not game:
            no_line += 1
            if len(unmatched_examples) < 8:
                unmatched_examples.append({"reason": "no_game_line_match", "team_a": a, "team_b": b, "game": row.get("game", "")})
            continue
        matched += 1
        team = norm_team(row.get("team") or row.get("player_team") or a)
        opponent = norm_team(row.get("opponent") or row.get("opp") or (b if team == a else a))
        team_ml = game.moneylines.get(team)
        opp_ml = game.moneylines.get(opponent)
        # If team/opponent are unknown, assign using away/home order only when possible.
        if team_ml is None and opp_ml is None and len(game.moneylines) >= 2:
            # Do not guess if row team is not recognizable.
            pass
        total = game.total
        changed = False
        if team_ml is not None:
            row["team_moneyline"] = str(int(team_ml)) if float(team_ml).is_integer() else str(team_ml)
            row["close_team_moneyline"] = row["team_moneyline"]
            row["moneyline_implied_probability"] = f"{moneyline_to_probability(team_ml):.6f}"
            changed = True
        if opp_ml is not None:
            row["opponent_moneyline"] = str(int(opp_ml)) if float(opp_ml).is_integer() else str(opp_ml)
            changed = True
        if total is not None:
            row["game_total"] = f"{total:.3f}".rstrip("0").rstrip(".")
            row["close_game_total"] = row["game_total"]
            changed = True
        if team_ml is not None and opp_ml is not None and total is not None:
            tr, oruns = implied_runs_proxy(total, team_ml, opp_ml)
            if tr is not None and oruns is not None:
                row["team_implied_runs"] = str(tr)
                row["opponent_implied_runs"] = str(oruns)
                row["opponent_implied_runs_proxy"] = str(oruns)
                row["implied_runs_source"] = "moneyline_total_proxy"
                changed = True
        if changed:
            row["game_line_source"] = game.source
            row["game_line_book"] = game.book or "PropLine"
            row["game_line_event_id"] = game.event_id
            updated += 1

    if not dry_run:
        write_csv_atomic(playerboard_path, fieldnames, rows)

    audit = {
        "status": "ok" if matched else "warning",
        "date": date,
        "season": season,
        "markets": sorted(market_set),
        "playerboardPath": str(playerboard_path),
        "gameLinesPath": str(game_lines_path),
        "parsedGames": len(games),
        "gamesWithMoneyline": sum(1 for g in games if g.moneylines),
        "gamesWithTotal": sum(1 for g in games if g.total is not None),
        "targetRows": target,
        "matchedRows": matched,
        "updatedRows": updated,
        "missingTeamPairRows": no_game,
        "unmatchedLineRows": no_line,
        "unmatchedExamples": unmatched_examples,
        "dryRun": dry_run,
    }
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIT_DIR / f"phase17_propline_game_line_match_{date}.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply PropLine game moneyline/total context to playerboard rows.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--markets", nargs="*", default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(apply_lines(args.date, args.season, args.markets, args.dry_run), indent=2))


if __name__ == "__main__":
    main()
