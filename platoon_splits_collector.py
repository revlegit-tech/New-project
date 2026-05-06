from __future__ import annotations

"""Collect MLB StatsAPI platoon split features for batter hits and pitcher hits allowed props.

Writes:
- data/cache/incremental_stats/batter_platoon_splits_YEAR.csv
- data/cache/incremental_stats/pitcher_platoon_splits_YEAR.csv
- data/cache/incremental_stats/platoon_splits_status_YEAR.json
"""

import argparse
import csv
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "data" / "cache" / "incremental_stats"
MLB_BASE = "https://statsapi.mlb.com/api/v1"

BATTER_PLATOON_FIELDS = [
    "season", "playerId", "player", "team",
    "avgVsLHP", "obpVsLHP", "slgVsLHP", "opsVsLHP", "kRateVsLHP", "bbRateVsLHP", "paVsLHP",
    "avgVsRHP", "obpVsRHP", "slgVsRHP", "opsVsRHP", "kRateVsRHP", "bbRateVsRHP", "paVsRHP",
    "platoonAvgGap", "updatedAt",
]

PITCHER_PLATOON_FIELDS = [
    "season", "playerId", "player", "team",
    "avgAllowedVsLHB", "babipVsLHB", "kRateVsLHB", "paVsLHB",
    "avgAllowedVsRHB", "babipVsRHB", "kRateVsRHB", "paVsRHB",
    "platoonAvgGapAllowed", "updatedAt",
]


def clean(value: Any) -> str:
    return str(value or "").strip()


# Returns 0.0 for missing values. Appropriate for stat aggregation.
# For ML feature extraction use ml_prop_model.to_float() instead.
def to_float(value: Any, default: float = 0.0) -> float:
    text = clean(value).replace(",", "")
    if not text:
        return default
    try:
        if text.endswith("%"):
            return float(text[:-1]) / 100.0
        return float(text)
    except ValueError:
        return default


def safe_div(n: float, d: float, digits: int = 4) -> float:
    return round(n / d, digits) if d else 0.0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def fetch_json(url: str, timeout: int = 30) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "baseball-prop-predictor"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def mlb_get(endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
    return fetch_json(f"{MLB_BASE}/{endpoint}?{urllib.parse.urlencode(params)}")


def player_index(season: int, role: str) -> list[dict[str, str]]:
    path = CACHE_DIR / f"player_index_{season}.csv"
    rows = read_csv_rows(path)
    role = role.lower()
    out = []
    for row in rows:
        row_role = clean(row.get("role")).lower()
        if role == "batter" and row_role in {"batter", "two-way"}:
            out.append(row)
        elif role == "pitcher" and row_role in {"pitcher", "two-way"}:
            out.append(row)
    return out


def stat_rate(stat: dict[str, Any], numerator: str, denominator: str = "plateAppearances") -> float:
    return safe_div(to_float(stat.get(numerator)), to_float(stat.get(denominator)), 4)


def first_split_stat(data: dict[str, Any]) -> dict[str, Any]:
    for stat_group in data.get("stats", []):
        splits = stat_group.get("splits", [])
        if splits:
            return splits[0].get("stat", {}) or {}
    return {}


def fetch_player_split_stat(player_id: str, season: int, group: str, sit_code: str) -> dict[str, Any]:
    # StatsAPI returns platoon situational splits most reliably through statSplits
    # with one sitCode per request.
    data = mlb_get(f"people/{player_id}/stats", {
        "stats": "statSplits",
        "group": group,
        "sitCodes": sit_code,
        "season": season,
    })
    return first_split_stat(data)


def fetch_batter_platoon(player: dict[str, str], season: int) -> dict[str, Any]:
    player_id = clean(player.get("playerId"))
    result: dict[str, Any] = {
        "season": season,
        "playerId": player_id,
        "player": clean(player.get("player")),
        "team": clean(player.get("team")),
        "updatedAt": now_iso(),
    }

    split_map = {
        "vl": "VsLHP",
        "vr": "VsRHP",
    }

    for sit_code, suffix in split_map.items():
        stat = fetch_player_split_stat(player_id, season, "hitting", sit_code)
        result[f"avg{suffix}"] = stat.get("avg", "")
        result[f"obp{suffix}"] = stat.get("obp", "")
        result[f"slg{suffix}"] = stat.get("slg", "")
        result[f"ops{suffix}"] = stat.get("ops", "")
        result[f"kRate{suffix}"] = stat_rate(stat, "strikeOuts")
        result[f"bbRate{suffix}"] = stat_rate(stat, "baseOnBalls")
        result[f"pa{suffix}"] = stat.get("plateAppearances", "")

    result["platoonAvgGap"] = round(to_float(result.get("avgVsRHP")) - to_float(result.get("avgVsLHP")), 3)
    return result


def fetch_pitcher_platoon(player: dict[str, str], season: int) -> dict[str, Any]:
    player_id = clean(player.get("playerId"))
    result: dict[str, Any] = {
        "season": season,
        "playerId": player_id,
        "player": clean(player.get("player")),
        "team": clean(player.get("team")),
        "updatedAt": now_iso(),
    }

    split_map = {
        "vl": "VsLHB",
        "vr": "VsRHB",
    }

    for sit_code, suffix in split_map.items():
        stat = fetch_player_split_stat(player_id, season, "pitching", sit_code)
        result[f"avgAllowed{suffix}"] = stat.get("avg", "")
        result[f"babip{suffix}"] = stat.get("babip", "")
        result[f"kRate{suffix}"] = stat_rate(stat, "strikeOuts", "battersFaced")
        result[f"pa{suffix}"] = stat.get("battersFaced") or stat.get("plateAppearances", "")

    result["platoonAvgGapAllowed"] = round(to_float(result.get("avgAllowedVsRHB")) - to_float(result.get("avgAllowedVsLHB")), 3)
    return result


def sync_platoon_splits(season: int = 2026, max_players: int = 0) -> dict[str, Any]:
    batter_rows = []
    pitcher_rows = []
    errors: list[dict[str, Any]] = []

    for player in player_index(season, "batter")[: max_players or None]:
        try:
            batter_rows.append(fetch_batter_platoon(player, season))
        except Exception as error:
            errors.append({"playerId": player.get("playerId"), "player": player.get("player"), "role": "batter", "error": str(error)})

    for player in player_index(season, "pitcher")[: max_players or None]:
        try:
            pitcher_rows.append(fetch_pitcher_platoon(player, season))
        except Exception as error:
            errors.append({"playerId": player.get("playerId"), "player": player.get("player"), "role": "pitcher", "error": str(error)})

    batter_path = CACHE_DIR / f"batter_platoon_splits_{season}.csv"
    pitcher_path = CACHE_DIR / f"pitcher_platoon_splits_{season}.csv"
    write_csv(batter_path, BATTER_PLATOON_FIELDS, batter_rows)
    write_csv(pitcher_path, PITCHER_PLATOON_FIELDS, pitcher_rows)

    summary = {
        "season": season,
        "batterRows": len(batter_rows),
        "pitcherRows": len(pitcher_rows),
        "batterFile": str(batter_path),
        "pitcherFile": str(pitcher_path),
        "errors": errors[:50],
        "errorCount": len(errors),
        "updatedAt": now_iso(),
    }
    write_json(CACHE_DIR / f"platoon_splits_status_{season}.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect StatsAPI batter and pitcher platoon splits.")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--max-players", type=int, default=0, help="Debug limit; 0 means all players.")
    args = parser.parse_args()
    print(json.dumps(sync_platoon_splits(args.season, args.max_players), indent=2))


if __name__ == "__main__":
    main()
