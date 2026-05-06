from __future__ import annotations

"""Collect umpire features for MLB prop models.

Sources:
- Umpire Scorecards seasonal umpire API for umpire tendencies.
- MLB StatsAPI linescore endpoint for the home-plate umpire assigned to each game.

Writes:
- data/cache/umpires/umpire_stats_YEAR.csv
- data/cache/umpires/game_umpires_YEAR.csv
- data/cache/umpires/umpire_status_YEAR.json
"""

import argparse
import csv
import json
import math
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
INCREMENTAL_DIR = ROOT / "data" / "cache" / "incremental_stats"
UMPIRE_DIR = ROOT / "data" / "cache" / "umpires"
MLB_BASE = "https://statsapi.mlb.com/api/v1"
UMPIRE_SCORECARDS_BASE = "https://umpscorecards.com/api/umpires"

UMPIRE_STAT_FIELDS = [
    "umpireId", "umpireName", "season", "gamesUmped",
    "kRateFavorBatter", "bbRateFavorBatter", "zoneSizeZscore",
    "favorHomePct", "runsScoredPerGame", "hitsPerGame", "updatedAt",
]

GAME_UMPIRE_FIELDS = [
    "gamePk", "date", "season", "homeTeam", "awayTeam",
    "homePlateUmpireId", "homePlateUmpireName", "updatedAt",
]


def clean(value: Any) -> str:
    return str(value or "").strip()


# Returns 0.0 for missing values. Appropriate for stat aggregation.
# For ML feature extraction use ml_prop_model.to_float() instead.
def to_float(value: Any, default: float = 0.0) -> float:
    text = clean(value).replace(",", "").replace("%", "")
    if not text:
        return default
    try:
        value = float(text)
        if math.isnan(value):
            return default
        return value
    except Exception:
        return default


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_json(url: str, timeout: int = 30) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "baseball-prop-predictor"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def mlb_get(endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    query = urllib.parse.urlencode(params or {})
    suffix = f"?{query}" if query else ""
    return fetch_json(f"{MLB_BASE}/{endpoint}{suffix}")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def first_value(row: dict[str, Any], names: list[str], default: Any = "") -> Any:
    normalized = {clean(k).lower().replace("_", ""): v for k, v in row.items()}
    for name in names:
        key = clean(name).lower().replace("_", "")
        if key in normalized and clean(normalized[key]):
            return normalized[key]
    return default


def fetch_umpire_stats(season: int = 2026) -> list[dict[str, Any]]:
    payload = fetch_json(f"{UMPIRE_SCORECARDS_BASE}?year={season}")
    items = payload if isinstance(payload, list) else payload.get("umpires", []) if isinstance(payload, dict) else []
    rows: list[dict[str, Any]] = []
    for ump in items:
        if not isinstance(ump, dict):
            continue
        games = to_float(first_value(ump, ["games", "games_umped", "gamesUmped"]))
        total_runs = to_float(first_value(ump, ["runs", "total_runs", "runs_scored"]))
        total_hits = to_float(first_value(ump, ["hits", "total_hits"]))
        rows.append({
            "umpireId": clean(first_value(ump, ["umpire_id", "id", "mlb_id"])),
            "umpireName": clean(first_value(ump, ["umpire_name", "name", "full_name"])),
            "season": season,
            "gamesUmped": games,
            "kRateFavorBatter": to_float(first_value(ump, ["k_rate", "strikeout_rate", "kRate"])),
            "bbRateFavorBatter": to_float(first_value(ump, ["bb_rate", "walk_rate", "bbRate"])),
            "zoneSizeZscore": to_float(first_value(ump, ["zone_size", "zone_size_zscore", "zoneSize"])),
            "favorHomePct": to_float(first_value(ump, ["favor_home", "home_favor", "favorHome"])),
            "runsScoredPerGame": round(total_runs / games, 3) if games and total_runs else to_float(first_value(ump, ["runs_per_game", "runsScoredPerGame"])),
            "hitsPerGame": round(total_hits / games, 3) if games and total_hits else to_float(first_value(ump, ["hits_per_game", "hitsPerGame"])),
            "updatedAt": now_iso(),
        })
    return rows


def extract_home_plate_umpire(payload: Any) -> dict[str, Any]:
    """Find home-plate umpire from MLB StatsAPI payloads."""
    if isinstance(payload, dict):
        officials = payload.get("officials")
        if isinstance(officials, list):
            for official in officials:
                if not isinstance(official, dict):
                    continue

                official_type = clean(
                    official.get("officialType")
                    or official.get("type")
                    or official.get("role")
                ).lower()

                if "home" in official_type and "plate" in official_type:
                    person = official.get("official") or official.get("person") or {}

                    if isinstance(person, dict):
                        return {
                            "homePlateUmpireId": clean(person.get("id")),
                            "homePlateUmpireName": clean(
                                person.get("fullName")
                                or person.get("name")
                                or person.get("full_name")
                            ),
                        }

                    return {
                        "homePlateUmpireId": clean(official.get("id")),
                        "homePlateUmpireName": clean(
                            official.get("fullName")
                            or official.get("name")
                            or official.get("full_name")
                        ),
                    }

        for value in payload.values():
            found = extract_home_plate_umpire(value)
            if found:
                return found

    elif isinstance(payload, list):
        for value in payload:
            found = extract_home_plate_umpire(value)
            if found:
                return found

    return {}


def fetch_game_umpire(game_pk: str) -> dict[str, Any]:
    endpoints = [
        f"game/{game_pk}/boxscore",
        f"game/{game_pk}/feed/live",
        f"game/{game_pk}/linescore",
    ]

    for endpoint in endpoints:
        try:
            data = mlb_get(endpoint)
        except Exception:
            continue

        found = extract_home_plate_umpire(data)
        if found:
            return found

    return {}


def collect_game_umpires(season: int = 2026, force: bool = False) -> list[dict[str, Any]]:
    games_path = INCREMENTAL_DIR / f"games_{season}.csv"
    existing_path = UMPIRE_DIR / f"game_umpires_{season}.csv"
    existing = {clean(row.get("gamePk")): row for row in read_csv_rows(existing_path)}
    rows: list[dict[str, Any]] = []

    for game in read_csv_rows(games_path):
        game_pk = clean(game.get("gamePk"))
        if not game_pk:
            continue
        if game_pk in existing and not force:
            rows.append(existing[game_pk])
            continue
        ump = fetch_game_umpire(game_pk)
        rows.append({
            "gamePk": game_pk,
            "date": clean(game.get("date")),
            "season": season,
            "homeTeam": clean(game.get("home")),
            "awayTeam": clean(game.get("away")),
            "homePlateUmpireId": ump.get("homePlateUmpireId", ""),
            "homePlateUmpireName": ump.get("homePlateUmpireName", ""),
            "updatedAt": now_iso(),
        })
    return rows


def build_fallback_umpire_stats(game_rows: list[dict[str, Any]], season: int = 2026) -> list[dict[str, Any]]:
    """Create neutral umpire features from game assignments when tendency data is unavailable.

    These are intentionally conservative. They let downstream joins populate stable
    neutral umpire values instead of all-null features, while preserving gamesUmped
    as useful availability/context.
    """
    grouped: dict[str, dict[str, Any]] = {}

    for game in game_rows:
        umpire_id = clean(game.get("homePlateUmpireId"))
        umpire_name = clean(game.get("homePlateUmpireName"))

        # Some future/scheduled games may not have announced umpires yet.
        if not umpire_id and not umpire_name:
            continue

        key = umpire_id or umpire_name.lower()
        if key not in grouped:
            grouped[key] = {
                "umpireId": umpire_id,
                "umpireName": umpire_name,
                "season": season,
                "gamesUmped": 0,
                # Neutral fallback values until real umpire tendency stats exist.
                "kRateFavorBatter": 0.0,
                "bbRateFavorBatter": 0.0,
                "zoneSizeZscore": 0.0,
                "favorHomePct": 0.0,
                "runsScoredPerGame": 0.0,
                "hitsPerGame": 0.0,
                "updatedAt": now_iso(),
            }

        grouped[key]["gamesUmped"] = int(grouped[key]["gamesUmped"]) + 1

        # Preserve better values if one row has an ID/name and another does not.
        if umpire_id and not grouped[key].get("umpireId"):
            grouped[key]["umpireId"] = umpire_id
        if umpire_name and not grouped[key].get("umpireName"):
            grouped[key]["umpireName"] = umpire_name

    return sorted(
        grouped.values(),
        key=lambda row: (-int(row.get("gamesUmped") or 0), clean(row.get("umpireName"))),
    )




def sync_umpires(season: int = 2026, force: bool = False) -> dict[str, Any]:
    UMPIRE_DIR.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    used_fallback_stats = False

    try:
        game_rows = collect_game_umpires(season, force=force)
    except Exception as error:
        game_rows = read_csv_rows(UMPIRE_DIR / f"game_umpires_{season}.csv")
        errors.append(f"game umpire lookup failed: {error}")

    try:
        stat_rows = fetch_umpire_stats(season)
    except Exception as error:
        stat_rows = read_csv_rows(UMPIRE_DIR / f"umpire_stats_{season}.csv")
        errors.append(f"umpire stats failed: {error}")

    if not stat_rows:
        stat_rows = build_fallback_umpire_stats(game_rows, season)
        used_fallback_stats = True

    write_csv(UMPIRE_DIR / f"umpire_stats_{season}.csv", UMPIRE_STAT_FIELDS, stat_rows)
    write_csv(UMPIRE_DIR / f"game_umpires_{season}.csv", GAME_UMPIRE_FIELDS, game_rows)

    summary = {
        "season": season,
        "umpireStatsRows": len(stat_rows),
        "gameUmpireRows": len(game_rows),
        "usedFallbackStats": used_fallback_stats,
        "errors": errors[:20],
        "errorCount": len(errors),
        "updatedAt": now_iso(),
    }
    write_json(UMPIRE_DIR / f"umpire_status_{season}.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect umpire stats and home-plate umpire game assignments.")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    print(json.dumps(sync_umpires(args.season, force=args.force), indent=2))


if __name__ == "__main__":
    main()
