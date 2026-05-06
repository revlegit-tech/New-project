from __future__ import annotations

"""Self-stored odds movement snapshots.

Purpose:
- Use your existing saved PropLine props as the source.
- Snapshot every prop row with a timestamp.
- Build movement features by comparing first vs latest snapshot.
- Avoid paid line movement APIs.

Files:
data/cache/odds_movement/prop_snapshots_2026.csv
data/cache/odds_movement/prop_movement_2026.csv
data/cache/odds_movement/status_2026.json
"""

import argparse
import csv
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
ODDS_DIR = ROOT / "data" / "cache" / "odds_movement"
_CSV_CACHE: dict[tuple[str, int, int], list[dict[str, str]]] = {}
PROPLINE_DIRS = [
    ROOT / "data" / "odds",
    ROOT / "data" / "propline",
    ROOT / "data" / "props",
    ROOT / "data" / "cloud" / "propline",
    ROOT / "data" / "cloud" / "props",
    ROOT / "data" / "imports",
    ROOT / "data" / "prop_reports",
]

SNAPSHOT_FIELDS = [
    "snapshotId", "snapshotAt", "season", "date", "market",
    "player", "playerId", "team", "opponent", "pitcher",
    "line", "americanOdds", "sportsbook", "propKey", "rawSource",
]

MOVEMENT_FIELDS = [
    "season", "date", "market", "player", "playerId", "team", "opponent", "pitcher",
    "firstSnapshotAt", "latestSnapshotAt", "snapshots",
    "firstLine", "latestLine", "lineMove", "line_move",
    "firstAmericanOdds", "latestAmericanOdds", "oddsMove", "odds_move",
    "firstImpliedProbability", "latestImpliedProbability", "impliedProbabilityMove",
    "movementDirection", "movementSummary",
]



def date_matches(row_date: object, query_date: object) -> bool:
    row_text = str(row_date or "").strip()
    query_text = str(query_date or "").strip()

    if not query_text:
        return True

    if row_text == query_text:
        return True

    # PropLine rows often store timestamped game dates like 2026-05-04T21:41:00Z,
    # while UI/model lookups usually pass 2026-05-04.
    if len(query_text) == 10 and row_text.startswith(query_text):
        return True

    if len(row_text) == 10 and query_text.startswith(row_text):
        return True

    return False


def clean(value: Any) -> str:
    return str(value or "").strip()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_float(value: Any, default: float = 0.0) -> float:
    text = clean(value).replace(",", "")
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def american_to_implied(odds: Any) -> float:
    value = to_float(odds)
    if value == 0:
        return 0.0
    if value < 0:
        return abs(value) / (abs(value) + 100)
    return 100 / (value + 100)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
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


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def append_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()

    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def normalize_market(value: Any) -> str:
    value = clean(value).lower().replace("_", " ").replace("-", " ")
    value = " ".join(value.split())

    mapping = {
        "hits": "batter_hits",
        "hit": "batter_hits",
        "batter hits": "batter_hits",
        "batter hit": "batter_hits",
        "total bases": "batter_total_bases",
        "total base": "batter_total_bases",
        "batter total bases": "batter_total_bases",
        "batter total base": "batter_total_bases",
        "home run": "batter_home_runs",
        "home runs": "batter_home_runs",
        "hr": "batter_home_runs",
        "hrs": "batter_home_runs",
        "batter home run": "batter_home_runs",
        "batter home runs": "batter_home_runs",
        "strikeout": "pitcher_strikeouts",
        "strikeouts": "pitcher_strikeouts",
        "pitcher strikeout": "pitcher_strikeouts",
        "pitcher strikeouts": "pitcher_strikeouts",
        "ks": "pitcher_strikeouts",
        "hits allowed": "pitcher_hits_allowed",
        "hit allowed": "pitcher_hits_allowed",
        "pitcher hits allowed": "pitcher_hits_allowed",
        "earned run": "pitcher_earned_runs",
        "earned runs": "pitcher_earned_runs",
        "pitcher earned run": "pitcher_earned_runs",
        "pitcher earned runs": "pitcher_earned_runs",
    }

    return mapping.get(value, value.replace(" ", "_"))



def clean_prop_player_name(player: Any, market: Any = "") -> str:
    text = clean(player)

    # Remove common PropLine/stat labels that get appended to pitcher/player names.
    suffixes = [
        " Strikeouts Thrown",
        " strikeouts thrown",
        " Pitcher Strikeouts",
        " pitcher strikeouts",
        " Total Bases",
        " total bases",
        " Home Runs",
        " home runs",
        " Home Run",
        " home run",
        " Hits Allowed",
        " hits allowed",
        " Earned Runs",
        " earned runs",
        " Hits",
        " hits",
    ]

    for suffix in suffixes:
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()

    lower = text.lower()
    if " over " in lower:
        text = text[: lower.index(" over ")].strip()
    elif " under " in lower:
        text = text[: lower.index(" under ")].strip()

    return text


def valid_prop_snapshot_row(row: dict[str, Any]) -> bool:
    market = normalize_market(row.get("market"))
    player = clean(row.get("player"))
    line_raw = clean(row.get("line"))
    odds_raw = clean(row.get("americanOdds"))

    if not market or not player:
        return False

    if market not in {
        "batter_hits",
        "batter_total_bases",
        "batter_home_runs",
        "pitcher_strikeouts",
        "pitcher_hits_allowed",
        "pitcher_earned_runs",
    }:
        return False

    if not line_raw:
        return False

    if not odds_raw:
        return False

    line = to_float(line_raw, default=-999)
    odds = to_float(odds_raw, default=0)
    abs_odds = abs(odds)

    if line < 0:
        return False

    if odds == 0:
        return False

    # +100 is valid sometimes, but when it came from malformed rows with blank context,
    # it created fake movement. Keep it only if the line is valid, which is already checked.
    if market != "batter_home_runs" and abs_odds > 2000:
        return False

    if market == "batter_hits" and line <= 0.5 and odds > 1000:
        return False

    if market == "batter_total_bases" and line <= 1.5 and odds > 1500:
        return False

    if market.startswith("pitcher_") and abs_odds > 1500:
        return False

    return True



def normalize_name(value: Any) -> str:
    return " ".join(clean(value).lower().replace(".", "").replace(",", "").split())


def prop_identity(row: dict[str, Any]) -> str:
    return "|".join([
        clean(row.get("date")),
        normalize_market(row.get("market")),
        normalize_name(row.get("player")),
        clean(row.get("team")).upper(),
        clean(row.get("opponent")).upper(),
        normalize_name(row.get("pitcher")),
    ])


def possible_prop_files(date_label: str) -> list[Path]:
    patterns = [
        f"*{date_label}*.csv",
        f"*props*.csv",
        f"*propline*.csv",
    ]

    out = []
    for folder in PROPLINE_DIRS:
        if not folder.exists():
            continue
        for pattern in patterns:
            out.extend(folder.rglob(pattern))

    # De-dupe while preserving order.
    seen = set()
    unique = []
    for path in out:
        key = str(path.resolve()).lower()
        if key not in seen:
            seen.add(key)
            unique.append(path)

    return unique


def row_get(row: dict[str, Any], candidates: list[str]) -> str:
    lower_map = {clean(k).lower(): v for k, v in row.items()}

    for name in candidates:
        key = clean(name).lower()
        if key in lower_map:
            return clean(lower_map[key])

    return ""




def flatten_dict(payload: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}

    if isinstance(payload, dict):
        for key, value in payload.items():
            key_name = f"{prefix}_{key}" if prefix else str(key)
            if isinstance(value, dict):
                out.update(flatten_dict(value, key_name))
            else:
                out[key_name] = value

    return out


def local_app_base_url() -> str:
    explicit = os.environ.get("BASEBALL_PROP_APP_URL") or os.environ.get("APP_BASE_URL")
    if explicit:
        return explicit.rstrip("/")
    port = os.environ.get("BASEBALL_PROP_APP_PORT") or os.environ.get("PORT") or "8766"
    return f"http://127.0.0.1:{port}"


def fetch_local_propline_rows(date_label: str = "", market: str = "") -> list[dict[str, Any]]:
    """Try to pull the 300-row PropLine response from the running local app."""
    markets = market or "pitcher_strikeouts,batter_hits,batter_total_bases,batter_home_runs,pitcher_hits_allowed,pitcher_earned_runs"

    query = urllib.parse.urlencode({
        "markets": markets,
        "date": date_label,
    })

    url = f"{local_app_base_url()}/api/propline/props?{query}"

    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "baseball-prop-predictor", "X-Baseball-Prop-Action": "1"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []

    if isinstance(payload, dict):
        candidates = (
            payload.get("props")
            or payload.get("data")
            or payload.get("rows")
            or payload.get("results")
            or []
        )
    elif isinstance(payload, list):
        candidates = payload
    else:
        candidates = []

    rows = []
    for item in candidates:
        flat = flatten_dict(item)

        row_date = row_get(flat, ["date", "game_date", "gameDate", "start_date", "commence_time"]) or date_label
        row_market = normalize_market(row_get(flat, [
            "market", "prop_market", "market_key", "marketKey", "type", "target",
            "stat", "category", "bet_type", "betType", "propType", "prop_type"
        ]))

        player = row_get(flat, [
            "player", "playerName", "player_name", "name", "description",
            "participant", "athlete", "batter", "pitcher_name", "selection"
        ])

        label = row_get(flat, ["label", "title", "outcome", "outcome_name", "selection"])
        if not player and label:
            player = label.split(" Over ")[0].split(" Under ")[0].strip()

        # Clean labels like "Aaron Judge over 1.5 Total Bases"
        lower_player = player.lower()
        if " over " in lower_player:
            player = player[:lower_player.index(" over ")].strip()
        elif " under " in lower_player:
            player = player[:lower_player.index(" under ")].strip()

        player = clean_prop_player_name(player, row_market)

        team = row_get(flat, [
            "team", "teamAbbr", "team_abbr", "team_abbreviation",
            "playerTeam", "player_team", "home_team", "home"
        ]).upper()

        opponent = row_get(flat, [
            "opponent", "opp", "opponentAbbr", "opponent_abbr",
            "opponent_abbreviation", "away_team", "away"
        ]).upper()

        pitcher = row_get(flat, [
            "pitcher", "opposingPitcher", "opposing_pitcher",
            "probablePitcher", "probable_pitcher", "starter"
        ])

        line = row_get(flat, [
            "line", "point", "points", "handicap", "value",
            "over_line", "overLine", "prop_line"
        ])

        odds = row_get(flat, [
            "americanOdds", "american_odds", "odds", "price",
            "overOdds", "over_odds", "overPrice", "over_price",
            "american", "american_price"
        ])

        sportsbook = row_get(flat, [
            "sportsbook", "book", "bookmaker", "bookName", "book_name"
        ])

        player_id = row_get(flat, [
            "playerId", "player_id", "mlbId", "mlb_id", "personId", "person_id"
        ])

        if not row_market or not player:
            continue

        normalized = {
            "date": row_date or date_label,
            "market": row_market,
            "player": player,
            "playerId": player_id,
            "team": team,
            "opponent": opponent,
            "pitcher": pitcher,
            "line": line,
            "americanOdds": odds,
            "sportsbook": sportsbook,
            "rawSource": url,
        }
        normalized["propKey"] = prop_identity(normalized)

        if not valid_prop_snapshot_row(normalized):
            continue

        rows.append(normalized)

    return rows

def load_saved_prop_rows(date_label: str = "", market: str = "") -> list[dict[str, Any]]:
    endpoint_rows = fetch_local_propline_rows(date_label=date_label, market=market)
    if endpoint_rows:
        return endpoint_rows

    rows = []
    files = possible_prop_files(date_label) if date_label else possible_prop_files("")
    market_filter = normalize_market(market)

    def first_value(raw: dict[str, Any], names: list[str]) -> str:
        lower_map = {clean(k).lower(): v for k, v in raw.items()}
        for name in names:
            key = clean(name).lower()
            if key in lower_map and clean(lower_map[key]):
                return clean(lower_map[key])
        return ""

    def detect_market(raw: dict[str, Any]) -> str:
        value = first_value(raw, [
            "market", "prop_market", "market_key", "marketKey", "type", "target",
            "stat", "category", "bet_type", "betType"
        ])
        value = normalize_market(value)

        # Normalize common display names.
        mapping = {
            "hits": "batter_hits",
            "batter hits": "batter_hits",
            "total bases": "batter_total_bases",
            "batter total bases": "batter_total_bases",
            "home runs": "batter_home_runs",
            "batter home runs": "batter_home_runs",
            "strikeouts": "pitcher_strikeouts",
            "pitcher strikeouts": "pitcher_strikeouts",
            "hits allowed": "pitcher_hits_allowed",
            "pitcher hits allowed": "pitcher_hits_allowed",
            "earned runs": "pitcher_earned_runs",
            "pitcher earned runs": "pitcher_earned_runs",
        }
        return mapping.get(value, value)

    for path in files:
        try:
            csv_rows = read_csv_rows(path)
        except Exception:
            continue

        for raw in csv_rows:
            row_date = first_value(raw, ["date", "game_date", "gameDate", "start_date", "commence_time"]) or date_label
            row_market = detect_market(raw)

            if date_label and row_date and not date_matches(row_date, date_label):
                continue

            if market_filter and row_market != market_filter:
                continue

            player = first_value(raw, [
                "player", "playerName", "player_name", "name", "description",
                "participant", "athlete", "batter", "pitcher_name"
            ])

            # Some PropLine rows may have a label like "Aaron Judge Over 1.5 Total Bases".
            if not player:
                label = first_value(raw, ["label", "title", "selection", "outcome", "outcome_name"])
                player = label.split(" Over ")[0].split(" Under ")[0].strip() if label else ""

            player = clean_prop_player_name(player, row_market)

            team = first_value(raw, [
                "team", "teamAbbr", "team_abbr", "team_abbreviation",
                "playerTeam", "player_team", "home_team", "home"
            ]).upper()

            opponent = first_value(raw, [
                "opponent", "opp", "opponentAbbr", "opponent_abbr",
                "opponent_abbreviation", "away_team", "away"
            ]).upper()

            pitcher = first_value(raw, [
                "pitcher", "opposingPitcher", "opposing_pitcher",
                "probablePitcher", "probable_pitcher", "starter"
            ])

            line = first_value(raw, [
                "line", "point", "points", "handicap", "value",
                "over_line", "overLine", "prop_line"
            ])

            odds = first_value(raw, [
                "americanOdds", "american_odds", "odds", "price",
                "overOdds", "over_odds", "overPrice", "over_price",
                "american", "american_price"
            ])

            sportsbook = first_value(raw, [
                "sportsbook", "book", "bookmaker", "bookName", "book_name"
            ])

            player_id = first_value(raw, [
                "playerId", "player_id", "mlbId", "mlb_id", "personId", "person_id"
            ])

            if not row_market:
                continue

            # Allow rows without player only if they are game odds; for prop movement we need player.
            if not player:
                continue

            normalized = {
                "date": row_date or date_label,
                "market": row_market,
                "player": player,
                "playerId": player_id,
                "team": team,
                "opponent": opponent,
                "pitcher": pitcher,
                "line": line,
                "americanOdds": odds,
                "sportsbook": sportsbook,
                "rawSource": str(path),
            }
            normalized["propKey"] = prop_identity(normalized)

            if not valid_prop_snapshot_row(normalized):
                continue

            rows.append(normalized)

    return rows

def snapshot_props(date_label: str = "", market: str = "", season: int = 2026) -> dict[str, Any]:
    ODDS_DIR.mkdir(parents=True, exist_ok=True)

    snapshot_at = now_iso()
    snapshot_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rows = load_saved_prop_rows(date_label=date_label, market=market)

    snapshot_rows = []
    for row in rows:
        if not valid_prop_snapshot_row(row):
            continue

        snapshot_rows.append({
            "snapshotId": snapshot_id,
            "snapshotAt": snapshot_at,
            "season": season,
            "date": row.get("date") or date_label,
            "market": normalize_market(row.get("market")),
            "player": row.get("player"),
            "playerId": row.get("playerId"),
            "team": row.get("team"),
            "opponent": row.get("opponent"),
            "pitcher": row.get("pitcher"),
            "line": row.get("line"),
            "americanOdds": row.get("americanOdds"),
            "sportsbook": row.get("sportsbook"),
            "propKey": row.get("propKey"),
            "rawSource": row.get("rawSource"),
        })

    append_csv(ODDS_DIR / f"prop_snapshots_{season}.csv", SNAPSHOT_FIELDS, snapshot_rows)

    summary = {
        "season": season,
        "date": date_label,
        "market": market,
        "snapshotId": snapshot_id,
        "snapshotAt": snapshot_at,
        "rowsSnapshotted": len(snapshot_rows),
        "snapshotFile": str(ODDS_DIR / f"prop_snapshots_{season}.csv"),
        "updatedAt": now_iso(),
    }

    write_json(ODDS_DIR / f"snapshot_status_{season}.json", summary)
    return summary


def movement_direction(line_move: float, implied_move: float) -> str:
    if abs(line_move) < 0.001 and abs(implied_move) < 0.003:
        return "flat"
    if line_move > 0 or implied_move > 0.003:
        return "over_price_up"
    if line_move < 0 or implied_move < -0.003:
        return "over_price_down"
    return "mixed"


def build_movement(season: int = 2026) -> dict[str, Any]:
    snapshots = read_csv_rows(ODDS_DIR / f"prop_snapshots_{season}.csv")

    grouped: dict[str, list[dict[str, str]]] = {}
    for row in snapshots:
        key = clean(row.get("propKey"))
        if not key:
            key = prop_identity(row)
        grouped.setdefault(key, []).append(row)

    rows = []
    for key, items in grouped.items():
        ordered = sorted(items, key=lambda x: clean(x.get("snapshotAt")))
        first = ordered[0]
        latest = ordered[-1]

        first_line_raw = clean(first.get("line"))
        latest_line_raw = clean(latest.get("line"))
        first_odds_raw = clean(first.get("americanOdds"))
        latest_odds_raw = clean(latest.get("americanOdds"))

        first_line = to_float(first_line_raw)
        latest_line = to_float(latest_line_raw)
        first_odds = to_float(first_odds_raw)
        latest_odds = to_float(latest_odds_raw)

        first_implied = american_to_implied(first_odds)
        latest_implied = american_to_implied(latest_odds)

        line_move = latest_line - first_line if first_line_raw and latest_line_raw else 0.0
        odds_move = latest_odds - first_odds if first_odds_raw and latest_odds_raw else 0.0
        implied_move = latest_implied - first_implied if first_odds_raw and latest_odds_raw else 0.0

        direction = movement_direction(line_move, implied_move)

        if len(ordered) <= 1:
            summary = "Only one odds snapshot available."
        elif direction == "flat":
            summary = "No meaningful odds movement."
        elif direction == "over_price_up":
            summary = "Market moved toward the over / higher implied probability."
        elif direction == "over_price_down":
            summary = "Market moved away from the over / lower implied probability."
        else:
            summary = "Mixed line and price movement."

        rows.append({
            "season": season,
            "date": latest.get("date"),
            "market": latest.get("market"),
            "player": latest.get("player"),
            "playerId": latest.get("playerId"),
            "team": latest.get("team"),
            "opponent": latest.get("opponent"),
            "pitcher": latest.get("pitcher"),
            "firstSnapshotAt": first.get("snapshotAt"),
            "latestSnapshotAt": latest.get("snapshotAt"),
            "snapshots": len(ordered),
            "firstLine": first.get("line"),
            "latestLine": latest.get("line"),
            "lineMove": round(line_move, 3),
            "line_move": round(line_move, 3),
            "firstAmericanOdds": first.get("americanOdds"),
            "latestAmericanOdds": latest.get("americanOdds"),
            "oddsMove": round(odds_move, 3),
            "odds_move": round(odds_move, 3),
            "firstImpliedProbability": round(first_implied, 5),
            "latestImpliedProbability": round(latest_implied, 5),
            "impliedProbabilityMove": round(implied_move, 5),
            "movementDirection": direction,
            "movementSummary": summary,
        })

    write_csv(ODDS_DIR / f"prop_movement_{season}.csv", MOVEMENT_FIELDS, rows)

    status = {
        "season": season,
        "snapshotRows": len(snapshots),
        "movementRows": len(rows),
        "snapshotFile": str(ODDS_DIR / f"prop_snapshots_{season}.csv"),
        "movementFile": str(ODDS_DIR / f"prop_movement_{season}.csv"),
        "updatedAt": now_iso(),
    }

    write_json(ODDS_DIR / f"status_{season}.json", status)
    return status


def snapshot_and_build(date_label: str = "", market: str = "", season: int = 2026) -> dict[str, Any]:
    snap = snapshot_props(date_label=date_label, market=market, season=season)
    movement = build_movement(season=season)
    return {"snapshot": snap, "movement": movement}


def find_movement(
    season: int,
    date_label: str,
    market: str,
    player: str,
    team: str = "",
    opponent: str = "",
    pitcher: str = "",
) -> dict[str, Any]:
    """Find the best odds movement row.

    Primary match:
    - date
    - market
    - player

    Team/opponent/pitcher are treated as tie-breakers because saved prop feeds
    often omit opponent or pitcher.
    """
    rows = read_csv_rows(ODDS_DIR / f"prop_movement_{season}.csv")

    target_player = normalize_name(player)
    target_market = normalize_market(market)
    target_team = clean(team).upper()
    target_opponent = clean(opponent).upper()
    target_pitcher = normalize_name(pitcher)

    candidates = []

    for row in rows:
        if not date_matches(row.get("date"), date_label):
            continue
        if normalize_market(row.get("market")) != target_market:
            continue
        if normalize_name(row.get("player")) != target_player:
            continue

        score = 100

        row_team = clean(row.get("team")).upper()
        row_opponent = clean(row.get("opponent")).upper()
        row_pitcher = normalize_name(row.get("pitcher"))

        if target_team and row_team:
            score += 10 if row_team == target_team else -20

        if target_opponent and row_opponent:
            score += 8 if row_opponent == target_opponent else -10

        if target_pitcher and row_pitcher:
            score += 6 if row_pitcher == target_pitcher else -5

        candidates.append((score, row))

    if not candidates:
        return {}

    candidates.sort(key=lambda item: item[0], reverse=True)
    best = dict(candidates[0][1])
    best["matchScore"] = candidates[0][0]
    best["matchNote"] = "Matched by date, market, player; team/opponent/pitcher used as tie-breakers."
    return best


def search_movement_rows(
    season: int,
    date_label: str = "",
    market: str = "",
    player: str = "",
    limit: int = 25,
) -> list[dict[str, Any]]:
    rows = read_csv_rows(ODDS_DIR / f"prop_movement_{season}.csv")
    target_market = normalize_market(market)
    target_player = normalize_name(player)

    matches = []
    for row in rows:
        if date_label and not date_matches(row.get("date"), date_label):
            continue
        if target_market and normalize_market(row.get("market")) != target_market:
            continue
        if target_player and target_player not in normalize_name(row.get("player")):
            continue
        matches.append(row)

    return matches[:limit]



def main() -> None:
    parser = argparse.ArgumentParser(description="Self-stored odds movement snapshots.")
    sub = parser.add_subparsers(dest="command", required=True)

    snap = sub.add_parser("snapshot")
    snap.add_argument("--season", type=int, default=2026)
    snap.add_argument("--date", default="")
    snap.add_argument("--market", default="")

    build = sub.add_parser("build")
    build.add_argument("--season", type=int, default=2026)

    both = sub.add_parser("sync")
    both.add_argument("--season", type=int, default=2026)
    both.add_argument("--date", default="")
    both.add_argument("--market", default="")

    lookup = sub.add_parser("lookup")
    lookup.add_argument("--season", type=int, default=2026)
    lookup.add_argument("--date", required=True)
    lookup.add_argument("--market", required=True)
    lookup.add_argument("--player", required=True)
    lookup.add_argument("--team", default="")
    lookup.add_argument("--opponent", default="")
    lookup.add_argument("--pitcher", default="")

    search = sub.add_parser("search")
    search.add_argument("--season", type=int, default=2026)
    search.add_argument("--date", default="")
    search.add_argument("--market", default="")
    search.add_argument("--player", default="")
    search.add_argument("--limit", type=int, default=25)

    args = parser.parse_args()

    if args.command == "snapshot":
        print(json.dumps(snapshot_props(args.date, args.market, args.season), indent=2))
    elif args.command == "build":
        print(json.dumps(build_movement(args.season), indent=2))
    elif args.command == "sync":
        print(json.dumps(snapshot_and_build(args.date, args.market, args.season), indent=2))
    elif args.command == "lookup":
        print(json.dumps(find_movement(args.season, args.date, args.market, args.player, args.team, args.opponent, args.pitcher), indent=2))
    elif args.command == "search":
        print(json.dumps(search_movement_rows(args.season, args.date, args.market, args.player, args.limit), indent=2))


if __name__ == "__main__":
    main()
