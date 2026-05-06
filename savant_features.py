from __future__ import annotations

"""Baseball Savant / pybaseball feature layer.

Purpose:
- Pull Statcast data through pybaseball when available.
- Cache raw Statcast rows by date range.
- Build hitter quality features:
  EV, max EV, launch angle, barrels, hard-hit rate, xBA, xSLG, xwOBA
- Build pitcher quality features:
  whiff rate, called-strike-whiff rate, EV allowed, barrel rate allowed,
  xBA allowed, xSLG allowed, xwOBA allowed

This module is optional-safe:
- If pybaseball is not installed, it returns a clear status instead of crashing.
"""

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SAVANT_DIR = ROOT / "data" / "cache" / "savant"
RAW_DIR = SAVANT_DIR / "raw"
_CSV_CACHE: dict[tuple[str, int, int], list[dict[str, str]]] = {}

BATTER_FIELDS = [
    "season", "player", "batterId", "team",
    "battedBalls", "paEvents", "avgExitVelocity", "maxExitVelocity",
    "avgLaunchAngle", "barrels", "barrelRate", "hardHits", "hardHitRate",
    "avgXBA", "avgXSLG", "avgXWOBA", "sweetSpotRate",
    "babip", "gbRate", "ldRate", "fbRate", "puRate",
    "sprintSpeed", "hpTo1b", "competitiveRuns",
]

SPRINT_SPEED_FIELDS = [
    "season", "playerId", "player", "team",
    "sprintSpeed", "hpTo1b", "competitiveRuns", "updatedAt",
]

PITCHER_FIELDS = [
    "season", "player", "pitcherId", "team",
    "pitches", "paEvents", "battedBalls", "whiffs", "swings",
    "whiffRate", "calledStrikes", "csw", "cswRate",
    "avgExitVelocityAllowed", "barrelsAllowed", "barrelRateAllowed",
    "hardHitsAllowed", "hardHitRateAllowed",
    "avgXBAAllowed", "avgXSLGAllowed", "avgXWOBAAllowed",
    "gbRateAllowed", "ldRateAllowed",
    "seasonAvgFastballVelo", "recentAvgFastballVelo", "veloDelta",
]

STATUS_FIELDS = [
    "season", "startDate", "endDate", "rawRows", "batterRows", "pitcherRows",
    "pybaseballAvailable", "updatedAt", "message",
]


def clean(value: Any) -> str:
    return str(value or "").strip()


# Returns 0.0 for missing values. Appropriate for stat aggregation.
# For ML feature extraction use ml_prop_model.to_float() instead.
def to_float(value: Any, default: float = 0.0) -> float:
    """Convert numeric text to float, returning default for missing/invalid values.
    
    This helper is for aggregation/reporting where default=0.0 is intentional.
    Do not use it for ML feature extraction when missingness must stay explicit;
    use ml_prop_model.to_float() or a nullable parser instead.
    """
    text = clean(value)
    if not text or text.lower() in {"nan", "none", "null"}:
        return default
    try:
        value = float(text)
        if math.isnan(value):
            return default
        return value
    except Exception:
        return default


def safe_div(num: float, den: float, digits: int = 4) -> float:
    if not den:
        return 0.0
    return round(num / den, digits)


def pct(num: float, den: float, digits: int = 2) -> float:
    if not den:
        return 0.0
    return round((num / den) * 100, digits)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return default


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




def load_player_index(season: int = 2026) -> dict[str, dict[str, str]]:
    """Load local MLB player index from the incremental stats warehouse."""
    index_path = ROOT / "data" / "cache" / "incremental_stats" / f"player_index_{season}.csv"
    players = {}

    for row in read_csv_rows(index_path):
        player_id = clean(
            row.get("playerId")
            or row.get("id")
            or row.get("mlbId")
            or row.get("personId")
        )

        if not player_id:
            continue

        name = clean(
            row.get("player")
            or row.get("name")
            or row.get("fullName")
            or row.get("full_name")
        )

        team = clean(row.get("team") or row.get("teamAbbr") or row.get("team_abbr"))

        players[player_id] = {
            "player": name,
            "team": team,
        }

    return players


def player_name_from_index(index: dict[str, dict[str, str]], player_id: str, fallback: str = "") -> str:
    item = index.get(clean(player_id), {})
    return clean(item.get("player")) or clean(fallback)


def player_team_from_index(index: dict[str, dict[str, str]], player_id: str, fallback: str = "") -> str:
    item = index.get(clean(player_id), {})
    return clean(item.get("team")) or clean(fallback)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def pybaseball_status() -> tuple[bool, str]:
    try:
        import pybaseball  # noqa: F401
        return True, "pybaseball is available."
    except Exception as error:
        return False, f"pybaseball is not installed or unavailable: {error}"


def enable_pybaseball_cache() -> None:
    try:
        from pybaseball import cache as pb_cache
        pb_cache.enable()
    except Exception:
        pass


def import_pybaseball_statcast():
    from pybaseball import statcast
    return statcast


def import_pybaseball_sprint_speed():
    from pybaseball import statcast_sprint_speed
    return statcast_sprint_speed


def dataframe_to_csv(df: Any, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return len(df)


def first_value(row: dict[str, Any], names: list[str], default: Any = "") -> Any:
    normalized = {clean(k).lower().replace(" ", "_"): v for k, v in row.items()}
    for name in names:
        key = clean(name).lower().replace(" ", "_")
        if key in normalized and clean(normalized[key]):
            return normalized[key]
    return default


def fetch_sprint_speed(season: int = 2026, min_opp: int = 10, force: bool = False) -> dict[str, Any]:
    SAVANT_DIR.mkdir(parents=True, exist_ok=True)
    path = SAVANT_DIR / f"sprint_speed_{season}.csv"
    if path.exists() and not force:
        return {"season": season, "rows": len(read_csv_rows(path)), "path": str(path), "message": "Using cached sprint speed file."}

    available, message = pybaseball_status()
    if not available:
        status = {"season": season, "rows": 0, "path": str(path), "message": message, "updatedAt": now_iso()}
        write_json(SAVANT_DIR / f"sprint_speed_status_{season}.json", status)
        return status

    enable_pybaseball_cache()
    try:
        sprint_speed = import_pybaseball_sprint_speed()
        df = sprint_speed(season, min_opp)
    except Exception as error:
        status = {"season": season, "rows": 0, "path": str(path), "message": f"Sprint speed pull failed: {error}", "updatedAt": now_iso()}
        write_json(SAVANT_DIR / f"sprint_speed_status_{season}.json", status)
        return status

    raw_rows = df.to_dict("records")
    output = []
    for row in raw_rows:
        output.append({
            "season": season,
            "playerId": clean(first_value(row, ["player_id", "playerid", "mlbamid", "entity_id"])),
            "player": clean(first_value(row, ["player_name", "name", "last_name, first_name"])),
            "team": clean(first_value(row, ["team", "team_name"])),
            "sprintSpeed": to_float(first_value(row, ["sprint_speed", "sprint speed"])),
            "hpTo1b": to_float(first_value(row, ["hp_to_1b", "hp to 1b"])),
            "competitiveRuns": to_float(first_value(row, ["competitive_runs", "competitive runs"])),
            "updatedAt": now_iso(),
        })

    write_csv(path, SPRINT_SPEED_FIELDS, output)
    status = {"season": season, "rows": len(output), "path": str(path), "message": "Pulled sprint speed with pybaseball.", "updatedAt": now_iso()}
    write_json(SAVANT_DIR / f"sprint_speed_status_{season}.json", status)
    return status


def load_sprint_speed_index(season: int = 2026) -> dict[str, dict[str, str]]:
    rows = read_csv_rows(SAVANT_DIR / f"sprint_speed_{season}.csv")
    return {clean(row.get("playerId")): row for row in rows if clean(row.get("playerId"))}


def collect_statcast(season: int = 2026, start_date: str = "", end_date: str = "", force: bool = False) -> dict[str, Any]:
    SAVANT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    available, message = pybaseball_status()
    if not available:
        status = {
            "season": season,
            "startDate": start_date,
            "endDate": end_date,
            "rawRows": 0,
            "pybaseballAvailable": False,
            "message": message,
            "updatedAt": now_iso(),
        }
        write_json(SAVANT_DIR / f"savant_collect_status_{season}.json", status)
        return status

    if not start_date:
        start_date = f"{season}-03-25"
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    raw_path = RAW_DIR / f"statcast_{season}_{start_date}_to_{end_date}.csv"

    if raw_path.exists() and not force:
        rows = read_csv_rows(raw_path)
        status = {
            "season": season,
            "startDate": start_date,
            "endDate": end_date,
            "rawRows": len(rows),
            "rawFile": str(raw_path),
            "pybaseballAvailable": True,
            "message": "Using cached Statcast file.",
            "updatedAt": now_iso(),
        }
        write_json(SAVANT_DIR / f"savant_collect_status_{season}.json", status)
        return status

    enable_pybaseball_cache()
    statcast = import_pybaseball_statcast()
    df = statcast(start_dt=start_date, end_dt=end_date)
    raw_rows = dataframe_to_csv(df, raw_path)

    status = {
        "season": season,
        "startDate": start_date,
        "endDate": end_date,
        "rawRows": raw_rows,
        "rawFile": str(raw_path),
        "pybaseballAvailable": True,
        "message": "Pulled Statcast rows with pybaseball.",
        "updatedAt": now_iso(),
    }
    write_json(SAVANT_DIR / f"savant_collect_status_{season}.json", status)
    return status


def latest_raw_file(season: int) -> Path | None:
    files = sorted(RAW_DIR.glob(f"statcast_{season}_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def event_rows_only(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    # One row per pitch. A completed PA has events populated.
    return [row for row in rows if clean(row.get("events"))]


def is_at_bat(row: dict[str, str]) -> bool:
    return bool(clean(row.get("events")))


def is_batted_ball(row: dict[str, str]) -> bool:
    return bool(clean(row.get("bb_type"))) or to_float(row.get("launch_speed")) > 0


def is_hard_hit(row: dict[str, str]) -> bool:
    return to_float(row.get("launch_speed")) >= 95


def is_barrel(row: dict[str, str]) -> bool:
    # Baseball Savant sometimes includes launch_speed_angle bucket.
    # Bucket 6 usually represents barrel. If unavailable, use conservative EV/LA approximation.
    bucket = clean(row.get("launch_speed_angle"))
    if bucket == "6":
        return True

    ev = to_float(row.get("launch_speed"))
    la = to_float(row.get("launch_angle"))
    return ev >= 98 and 26 <= la <= 30


def is_swing(row: dict[str, str]) -> bool:
    desc = clean(row.get("description")).lower()
    return desc in {
        "swinging_strike",
        "swinging_strike_blocked",
        "foul",
        "foul_tip",
        "foul_bunt",
        "hit_into_play",
        "hit_into_play_score",
        "hit_into_play_no_out",
        "missed_bunt",
    }


def is_whiff(row: dict[str, str]) -> bool:
    desc = clean(row.get("description")).lower()
    return desc in {"swinging_strike", "swinging_strike_blocked", "missed_bunt"}


def is_called_strike(row: dict[str, str]) -> bool:
    return clean(row.get("description")).lower() == "called_strike"


def avg(values: list[float], digits: int = 3) -> float:
    vals = [v for v in values if v != 0]
    if not vals:
        return 0.0
    return round(sum(vals) / len(vals), digits)


def build_savant_features(season: int = 2026, raw_file: str = "") -> dict[str, Any]:
    SAVANT_DIR.mkdir(parents=True, exist_ok=True)

    path = Path(raw_file) if raw_file else latest_raw_file(season)
    if not path or not path.exists():
        status = {
            "season": season,
            "rawRows": 0,
            "batterRows": 0,
            "pitcherRows": 0,
            "pybaseballAvailable": pybaseball_status()[0],
            "message": "No Statcast raw file found. Run collect first.",
            "updatedAt": now_iso(),
        }
        write_json(SAVANT_DIR / f"savant_status_{season}.json", status)
        return status

    rows = read_csv_rows(path)
    pa_rows = event_rows_only(rows)
    player_index = load_player_index(season)
    sprint_index = load_sprint_speed_index(season)

    batter_groups: dict[str, list[dict[str, str]]] = {}
    pitcher_groups: dict[str, list[dict[str, str]]] = {}

    for row in rows:
        batter_id = clean(row.get("batter"))
        pitcher_id = clean(row.get("pitcher"))

        if batter_id:
            batter_groups.setdefault(batter_id, []).append(row)
        if pitcher_id:
            pitcher_groups.setdefault(pitcher_id, []).append(row)

    batter_rows = []
    for batter_id, items in batter_groups.items():
        completed = [r for r in items if clean(r.get("events"))]
        batted = [r for r in completed if is_batted_ball(r)]

        # In Statcast, player_name often refers to the pitcher.
        # Batter identity should come from the batter ID and local player index.
        player = player_name_from_index(player_index, batter_id, clean(items[-1].get("player_name")))
        team = player_team_from_index(player_index, batter_id, clean(items[-1].get("home_team")))

        evs = [to_float(r.get("launch_speed")) for r in batted]
        las = [to_float(r.get("launch_angle")) for r in batted]
        xbas = [to_float(r.get("estimated_ba_using_speedangle")) for r in batted]
        xslgs = [to_float(r.get("estimated_slg_using_speedangle")) for r in batted]
        xwobas = [to_float(r.get("estimated_woba_using_speedangle")) for r in batted]

        barrels = sum(1 for r in batted if is_barrel(r))
        hard_hits = sum(1 for r in batted if is_hard_hit(r))
        sweet_spot = sum(1 for r in batted if 8 <= to_float(r.get("launch_angle")) <= 32)
        hits = sum(1 for r in completed if clean(r.get("events")) in {"single", "double", "triple", "home_run"})
        at_bats = sum(1 for r in completed if is_at_bat(r))
        strikeouts = sum(1 for r in completed if clean(r.get("events")) in {"strikeout", "strikeout_double_play"})
        home_runs = sum(1 for r in completed if clean(r.get("events")) == "home_run")
        sac_flies = sum(1 for r in completed if clean(r.get("events")) == "sac_fly")
        babip = safe_div(hits - home_runs, at_bats - strikeouts - home_runs + sac_flies, 3)
        gb = sum(1 for r in batted if clean(r.get("bb_type")) == "ground_ball")
        ld = sum(1 for r in batted if clean(r.get("bb_type")) == "line_drive")
        fb = sum(1 for r in batted if clean(r.get("bb_type")) == "fly_ball")
        pu = sum(1 for r in batted if clean(r.get("bb_type")) == "popup")
        sprint = sprint_index.get(clean(batter_id), {})

        batter_rows.append({
            "season": season,
            "player": player,
            "batterId": batter_id,
            "team": team,
            "battedBalls": len(batted),
            "paEvents": len(completed),
            "avgExitVelocity": avg(evs, 2),
            "maxExitVelocity": round(max(evs), 2) if evs else 0,
            "avgLaunchAngle": avg(las, 2),
            "barrels": barrels,
            "barrelRate": pct(barrels, len(batted), 2),
            "hardHits": hard_hits,
            "hardHitRate": pct(hard_hits, len(batted), 2),
            "avgXBA": avg(xbas, 3),
            "avgXSLG": avg(xslgs, 3),
            "avgXWOBA": avg(xwobas, 3),
            "sweetSpotRate": pct(sweet_spot, len(batted), 2),
            "babip": babip,
            "gbRate": pct(gb, len(batted), 2),
            "ldRate": pct(ld, len(batted), 2),
            "fbRate": pct(fb, len(batted), 2),
            "puRate": pct(pu, len(batted), 2),
            "sprintSpeed": to_float(sprint.get("sprintSpeed")),
            "hpTo1b": to_float(sprint.get("hpTo1b")),
            "competitiveRuns": to_float(sprint.get("competitiveRuns")),
        })

    pitcher_rows = []
    for pitcher_id, items in pitcher_groups.items():
        completed = [r for r in items if clean(r.get("events"))]
        batted = [r for r in completed if is_batted_ball(r)]

        # Pitcher name can come from Statcast player_name, but local index is safer.
        player = player_name_from_index(player_index, pitcher_id, clean(items[-1].get("player_name")))
        team = player_team_from_index(player_index, pitcher_id, clean(items[-1].get("away_team")))

        swings = sum(1 for r in items if is_swing(r))
        whiffs = sum(1 for r in items if is_whiff(r))
        called_strikes = sum(1 for r in items if is_called_strike(r))
        csw = whiffs + called_strikes

        evs = [to_float(r.get("launch_speed")) for r in batted]
        xbas = [to_float(r.get("estimated_ba_using_speedangle")) for r in batted]
        xslgs = [to_float(r.get("estimated_slg_using_speedangle")) for r in batted]
        xwobas = [to_float(r.get("estimated_woba_using_speedangle")) for r in batted]

        barrels = sum(1 for r in batted if is_barrel(r))
        hard_hits = sum(1 for r in batted if is_hard_hit(r))
        gb_allowed = sum(1 for r in batted if clean(r.get("bb_type")) == "ground_ball")
        ld_allowed = sum(1 for r in batted if clean(r.get("bb_type")) == "line_drive")
        sorted_items = sorted(items, key=lambda r: clean(r.get("game_date")) or clean(r.get("game_pk")))
        fastball_types = {"FF", "SI", "FC"}
        fb_pitches = [
            to_float(r.get("release_speed"))
            for r in sorted_items
            if clean(r.get("pitch_type")) in fastball_types and to_float(r.get("release_speed")) > 0
        ]
        recent_fb = fb_pitches[-75:] if len(fb_pitches) >= 75 else fb_pitches
        season_velo = avg(fb_pitches, 1) if fb_pitches else 0.0
        recent_velo = avg(recent_fb, 1) if recent_fb else season_velo
        velo_delta = round(recent_velo - season_velo, 2) if season_velo else 0.0

        pitcher_rows.append({
            "season": season,
            "player": player,
            "pitcherId": pitcher_id,
            "team": team,
            "pitches": len(items),
            "paEvents": len(completed),
            "battedBalls": len(batted),
            "whiffs": whiffs,
            "swings": swings,
            "whiffRate": pct(whiffs, swings, 2),
            "calledStrikes": called_strikes,
            "csw": csw,
            "cswRate": pct(csw, len(items), 2),
            "avgExitVelocityAllowed": avg(evs, 2),
            "barrelsAllowed": barrels,
            "barrelRateAllowed": pct(barrels, len(batted), 2),
            "hardHitsAllowed": hard_hits,
            "hardHitRateAllowed": pct(hard_hits, len(batted), 2),
            "avgXBAAllowed": avg(xbas, 3),
            "avgXSLGAllowed": avg(xslgs, 3),
            "avgXWOBAAllowed": avg(xwobas, 3),
            "gbRateAllowed": pct(gb_allowed, len(batted), 2),
            "ldRateAllowed": pct(ld_allowed, len(batted), 2),
            "seasonAvgFastballVelo": season_velo,
            "recentAvgFastballVelo": recent_velo,
            "veloDelta": velo_delta,
        })

    batter_rows = sorted(batter_rows, key=lambda x: (-to_float(x.get("battedBalls")), clean(x.get("player")).lower()))
    pitcher_rows = sorted(pitcher_rows, key=lambda x: (-to_float(x.get("pitches")), clean(x.get("player")).lower()))

    write_csv(SAVANT_DIR / f"savant_batter_quality_{season}.csv", BATTER_FIELDS, batter_rows)
    write_csv(SAVANT_DIR / f"savant_pitcher_quality_{season}.csv", PITCHER_FIELDS, pitcher_rows)

    status = {
        "season": season,
        "rawFile": str(path),
        "rawRows": len(rows),
        "batterRows": len(batter_rows),
        "pitcherRows": len(pitcher_rows),
        "batterFile": str(SAVANT_DIR / f"savant_batter_quality_{season}.csv"),
        "pitcherFile": str(SAVANT_DIR / f"savant_pitcher_quality_{season}.csv"),
        "pybaseballAvailable": pybaseball_status()[0],
        "message": "Built Savant quality features.",
        "updatedAt": now_iso(),
    }
    write_json(SAVANT_DIR / f"savant_status_{season}.json", status)
    return status


def sync_savant(season: int = 2026, start_date: str = "", end_date: str = "", force: bool = False) -> dict[str, Any]:
    collect = collect_statcast(season=season, start_date=start_date, end_date=end_date, force=force)
    if not collect.get("pybaseballAvailable"):
        return {"collect": collect, "features": None}

    sprint = fetch_sprint_speed(season=season, force=force)
    raw_file = clean(collect.get("rawFile"))
    features = build_savant_features(season=season, raw_file=raw_file)
    return {"collect": collect, "sprintSpeed": sprint, "features": features}


def normalize_name(value: Any) -> str:
    return " ".join(clean(value).lower().replace(".", "").replace(",", "").split())


def lookup_batter(player: str, season: int = 2026) -> dict[str, Any]:
    target = normalize_name(player)
    for row in read_csv_rows(SAVANT_DIR / f"savant_batter_quality_{season}.csv"):
        name = normalize_name(row.get("player"))
        if name == target or target in name or name in target:
            return row
    return {}


def lookup_pitcher(player: str, season: int = 2026) -> dict[str, Any]:
    target = normalize_name(player)
    for row in read_csv_rows(SAVANT_DIR / f"savant_pitcher_quality_{season}.csv"):
        name = normalize_name(row.get("player"))
        if name == target or target in name or name in target:
            return row
    return {}


def status(season: int = 2026) -> dict[str, Any]:
    payload = read_json(SAVANT_DIR / f"savant_status_{season}.json", {})
    available, message = pybaseball_status()
    payload["pybaseballAvailable"] = available
    payload["pybaseballMessage"] = message
    payload["batterRowsCurrent"] = len(read_csv_rows(SAVANT_DIR / f"savant_batter_quality_{season}.csv"))
    payload["pitcherRowsCurrent"] = len(read_csv_rows(SAVANT_DIR / f"savant_pitcher_quality_{season}.csv"))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Baseball Savant quality features.")
    sub = parser.add_subparsers(dest="command", required=True)

    sync = sub.add_parser("sync")
    sync.add_argument("--season", type=int, default=2026)
    sync.add_argument("--start-date", default="")
    sync.add_argument("--end-date", default="")
    sync.add_argument("--force", action="store_true")

    build = sub.add_parser("build")
    build.add_argument("--season", type=int, default=2026)
    build.add_argument("--raw-file", default="")

    sprint = sub.add_parser("sprint-speed")
    sprint.add_argument("--season", type=int, default=2026)
    sprint.add_argument("--min-opp", type=int, default=10)
    sprint.add_argument("--force", action="store_true")

    lookup = sub.add_parser("lookup")
    lookup.add_argument("--season", type=int, default=2026)
    lookup.add_argument("--player", required=True)
    lookup.add_argument("--kind", default="batter", choices=["batter", "pitcher"])

    stat = sub.add_parser("status")
    stat.add_argument("--season", type=int, default=2026)

    args = parser.parse_args()

    if args.command == "sync":
        print(json.dumps(sync_savant(args.season, args.start_date, args.end_date, args.force), indent=2))
    elif args.command == "build":
        print(json.dumps(build_savant_features(args.season, args.raw_file), indent=2))
    elif args.command == "sprint-speed":
        print(json.dumps(fetch_sprint_speed(args.season, args.min_opp, args.force), indent=2))
    elif args.command == "lookup":
        result = lookup_pitcher(args.player, args.season) if args.kind == "pitcher" else lookup_batter(args.player, args.season)
        print(json.dumps(result, indent=2))
    elif args.command == "status":
        print(json.dumps(status(args.season), indent=2))


if __name__ == "__main__":
    main()
