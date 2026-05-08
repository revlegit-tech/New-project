from __future__ import annotations

"""Phase 18 context collector.

Purpose:
- Keep game/team context separate from batter/pitcher prop rows.
- Pull missing display/model fields from provider-specific collectors:
  PropLine: game lines + player props through the existing Phase 17 bridge
  OddsPapi: optional current/opening/CLV snapshots when ODDSPAPI_API_KEY is set
  Open-Meteo: venue weather supplements, including humidity and wind direction
- Denormalize verified context back onto playerboard rows for hot-path UI reads.

This script is intentionally conservative. It never fabricates moneylines, totals,
opening lines, or implied runs. Static roof_type is a reference attribute; roof_status
for retractable parks is marked retractable_unknown unless a future roof-status source
provides the actual open/closed state.
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
WAREHOUSE_GAME_CONTEXT = DATA / "warehouse" / "game_context"
REFERENCE = DATA / "reference"
AUDITS = DATA / "warehouse" / "audits"

TEAM_ALIASES = {
    "AZ": "ARI", "WSH": "WSN", "WAS": "WSN", "SD": "SDP", "SF": "SFG",
    "TB": "TBR", "KC": "KCR", "CWS": "CHW", "OAK": "ATH",
    "ST. LOUIS CARDINALS": "STL", "SAN DIEGO PADRES": "SDP",
}


@dataclass
class ProviderStep:
    name: str
    status: str
    returncode: int | None = None
    stdout_tail: str = ""
    stderr_tail: str = ""
    warning: str = ""


def clean(value: Any) -> str:
    return str(value or "").strip()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def norm_team(value: Any) -> str:
    text = clean(value).upper()
    return TEAM_ALIASES.get(text, text)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv(path: Path, rows: list[dict[str, Any]], field_order: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for field in field_order or []:
        if field and field not in fields:
            fields.append(field)
    for row in rows:
        for key in row.keys():
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: clean(row.get(field, "")) for field in fields})


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def run_command(args: list[str]) -> ProviderStep:
    try:
        proc = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)
        return ProviderStep(
            name=" ".join(args),
            status="ok" if proc.returncode == 0 else "warning",
            returncode=proc.returncode,
            stdout_tail=(proc.stdout or "")[-3000:],
            stderr_tail=(proc.stderr or "")[-3000:],
        )
    except FileNotFoundError as error:
        return ProviderStep(name=" ".join(args), status="skipped", warning=str(error))
    except Exception as error:  # noqa: BLE001
        return ProviderStep(name=" ".join(args), status="warning", warning=str(error))


def run_existing_provider_bridges(date_label: str, season: int, markets: list[str], line_source: str) -> list[dict[str, Any]]:
    steps: list[ProviderStep] = []
    scripts = [
        ROOT / "tools" / "run_phase17_context_from_apis.py",
        ROOT / "tools" / "run_phase17_v4_game_context_markets.py",
        ROOT / "tools" / "phase17_v6_wire_game_context_api_contract.py",
    ]

    if scripts[0].exists():
        steps.append(run_command([
            sys.executable, str(scripts[0].relative_to(ROOT)),
            "--date", date_label,
            "--season", str(season),
            "--line-source", line_source,
            "--markets", *markets,
        ]))
    else:
        steps.append(ProviderStep(name=str(scripts[0]), status="skipped", warning="Phase 17 provider bridge missing."))

    if scripts[1].exists():
        steps.append(run_command([
            sys.executable, str(scripts[1].relative_to(ROOT)),
            "--date", date_label,
            "--season", str(season),
            "--markets", *markets,
        ]))
    else:
        steps.append(ProviderStep(name=str(scripts[1]), status="skipped", warning="Phase 17 v4 context market builder missing."))

    if scripts[2].exists():
        steps.append(run_command([sys.executable, str(scripts[2].relative_to(ROOT))]))
    else:
        steps.append(ProviderStep(name=str(scripts[2]), status="skipped", warning="Phase 17 v6 API contract script missing; apply v6 if UI still shows blanks."))

    return [step.__dict__ for step in steps]


def load_venue_coordinates() -> dict[str, dict[str, str]]:
    coords: dict[str, dict[str, str]] = {}
    for filename in ["mlb_venue_coordinates.csv", "venue_coordinates.csv", "stadium_coordinates.csv"]:
        path = REFERENCE / filename
        for row in read_csv(path):
            venue = clean(row.get("venue") or row.get("stadium") or row.get("park") or row.get("name"))
            lat = clean(row.get("latitude") or row.get("lat"))
            lon = clean(row.get("longitude") or row.get("lon") or row.get("lng"))
            if venue and lat and lon:
                coords[venue.casefold()] = {"venue": venue, "latitude": lat, "longitude": lon}
    return coords


def load_roof_status() -> dict[str, dict[str, str]]:
    data: dict[str, dict[str, str]] = {}
    for row in read_csv(REFERENCE / "mlb_roof_status.csv"):
        venue = clean(row.get("venue"))
        if venue:
            data[venue.casefold()] = dict(row)
    return data


def schedule_games(date_label: str) -> list[dict[str, Any]]:
    """Parse MLB Stats API schedule shape used by Phase 17."""
    path = WAREHOUSE_GAME_CONTEXT / f"mlb_schedule_{date_label}.json"
    payload = read_json(path, {})
    games: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        if isinstance(payload.get("dates"), list):
            for date_obj in payload.get("dates") or []:
                for game in date_obj.get("games") or []:
                    games.append(game)
        elif isinstance(payload.get("games"), list):
            games.extend(payload.get("games") or [])
    elif isinstance(payload, list):
        games.extend(payload)
    return games


def teams_for_game(game: dict[str, Any]) -> tuple[str, str]:
    teams = game.get("teams") or {}
    away = teams.get("away") or {}
    home = teams.get("home") or {}
    away_team = away.get("team") or {}
    home_team = home.get("team") or {}
    return (
        norm_team(away_team.get("abbreviation") or away_team.get("teamCode") or away_team.get("fileCode") or away_team.get("name")),
        norm_team(home_team.get("abbreviation") or home_team.get("teamCode") or home_team.get("fileCode") or home_team.get("name")),
    )


def venue_for_game(game: dict[str, Any]) -> str:
    venue = game.get("venue") or {}
    return clean(venue.get("name") if isinstance(venue, dict) else venue)


def game_time_for_game(game: dict[str, Any]) -> str:
    return clean(game.get("gameDate") or game.get("commence_time") or game.get("commenceTime") or game.get("startTime"))


def fetch_json_url(url: str, timeout: int = 25) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "mlb-app-phase18-context-collector/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - operator configured provider URL
        return json.loads(resp.read().decode("utf-8"))


def nearest_hour_weather(payload: dict[str, Any], game_time_iso: str) -> dict[str, Any]:
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        return {}

    target_hour = ""
    if game_time_iso:
        try:
            target_hour = game_time_iso[:13]
        except Exception:
            target_hour = ""
    idx = 0
    if target_hour:
        for i, stamp in enumerate(times):
            if clean(stamp).startswith(target_hour):
                idx = i
                break
    else:
        idx = min(12, max(0, len(times) - 1))

    def val(key: str) -> Any:
        values = hourly.get(key) or []
        return values[idx] if idx < len(values) else ""

    return {
        "weather_temperature_f": val("temperature_2m"),
        "weather_humidity": val("relative_humidity_2m"),
        "weather_precip_probability": val("precipitation_probability"),
        "weather_wind_mph": val("wind_speed_10m"),
        "weather_wind_direction_degrees": val("wind_direction_10m"),
        "weather_wind_direction": wind_degrees_to_cardinal(val("wind_direction_10m")),
        "weather_source": "open_meteo_phase18",
        "weather_observed_hour": times[idx] if idx < len(times) else "",
    }


def wind_degrees_to_cardinal(value: Any) -> str:
    try:
        deg = float(value)
    except (TypeError, ValueError):
        return ""
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return dirs[int((deg + 11.25) // 22.5) % 16]


def fetch_open_meteo_supplement(date_label: str) -> dict[str, Any]:
    coords = load_venue_coordinates()
    roofs = load_roof_status()
    games = schedule_games(date_label)
    results: list[dict[str, Any]] = []
    warnings: list[str] = []

    for game in games:
        venue = venue_for_game(game)
        if not venue:
            warnings.append("schedule game missing venue")
            continue
        coord = coords.get(venue.casefold())
        if not coord:
            warnings.append(f"missing coordinates for {venue}")
            continue

        params = {
            "latitude": coord["latitude"],
            "longitude": coord["longitude"],
            "hourly": "temperature_2m,relative_humidity_2m,precipitation_probability,wind_speed_10m,wind_direction_10m",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "timezone": "America/New_York",
            "start_date": date_label,
            "end_date": date_label,
        }
        url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
        try:
            payload = fetch_json_url(url)
            weather = nearest_hour_weather(payload, game_time_for_game(game))
        except Exception as error:  # noqa: BLE001
            warnings.append(f"Open-Meteo failed for {venue}: {error}")
            continue

        away, home = teams_for_game(game)
        roof = roofs.get(venue.casefold(), {})
        base = {
            "date": date_label,
            "away_team": away,
            "home_team": home,
            "venue": venue,
            "game_time": game_time_for_game(game),
            "latitude": coord["latitude"],
            "longitude": coord["longitude"],
            "roof_type": clean(roof.get("roof_type")),
            "roof_status": clean(roof.get("roof_status_note") or roof.get("roof_type")),
            **weather,
        }
        results.append(base)

    path = WAREHOUSE_GAME_CONTEXT / f"weather_phase18_{date_label}.json"
    write_json(path, {
        "status": "ok" if results else "warning",
        "date": date_label,
        "generatedAt": now_iso(),
        "games": results,
        "warnings": warnings,
    })
    return {
        "status": "ok" if results else "warning",
        "path": str(path),
        "weatherGames": len(results),
        "warnings": warnings,
    }


def weather_by_team_pair(date_label: str) -> dict[tuple[str, str], dict[str, Any]]:
    payload = read_json(WAREHOUSE_GAME_CONTEXT / f"weather_phase18_{date_label}.json", {})
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for game in payload.get("games") or []:
        away = norm_team(game.get("away_team"))
        home = norm_team(game.get("home_team"))
        if away and home:
            result[(away, home)] = game
            result[(home, away)] = game
    return result


def patch_context_csv(date_label: str) -> dict[str, Any]:
    path = WAREHOUSE_GAME_CONTEXT / f"game_context_{date_label}.csv"
    rows = read_csv(path)
    if not rows:
        return {"status": "skipped", "reason": f"missing {path}"}
    weather = weather_by_team_pair(date_label)
    updated = 0
    for row in rows:
        key = (norm_team(row.get("team") or row.get("away_team")), norm_team(row.get("opponent") or row.get("home_team")))
        info = weather.get(key) or {}
        if not info:
            continue
        for field in [
            "weather_temperature_f", "weather_humidity", "weather_precip_probability",
            "weather_wind_mph", "weather_wind_direction", "weather_wind_direction_degrees",
            "weather_source", "weather_observed_hour", "roof_type", "roof_status",
        ]:
            value = info.get(field)
            if value not in {None, ""} and not clean(row.get(field)):
                row[field] = value
        updated += 1
    write_csv(path, rows)
    return {"status": "ok", "path": str(path), "rows": len(rows), "updatedRows": updated}


def patch_playerboard(date_label: str, season: int, markets: list[str]) -> dict[str, Any]:
    path = DATA / "playerboard" / f"playerboard_{season}.csv"
    rows = read_csv(path)
    if not rows:
        return {"status": "skipped", "reason": f"missing {path}"}
    weather = weather_by_team_pair(date_label)
    updated = 0
    target = set(markets)
    for row in rows:
        if clean(row.get("date")) != date_label:
            continue
        if target and clean(row.get("market")) not in target:
            continue
        key = (norm_team(row.get("team")), norm_team(row.get("opponent")))
        info = weather.get(key) or {}
        if not info:
            continue
        changed = False
        for field in [
            "weather_temperature_f", "weather_humidity", "weather_precip_probability",
            "weather_wind_mph", "weather_wind_direction", "weather_wind_direction_degrees",
            "weather_source", "weather_observed_hour", "roof_type", "roof_status",
        ]:
            value = info.get(field)
            if value not in {None, ""} and not clean(row.get(field)):
                row[field] = value
                changed = True
        if changed:
            updated += 1
    write_csv(path, rows)
    return {"status": "ok", "path": str(path), "rows": len(rows), "updatedRows": updated}


def fetch_oddspapi_optional(date_label: str) -> dict[str, Any]:
    """Optional snapshot pull for opening/closing line movement."""
    key = clean(os.getenv("ODDSPAPI_API_KEY") or os.getenv("ODDS_PAPI_API_KEY"))
    if not key:
        return {"status": "skipped", "reason": "ODDSPAPI_API_KEY not set"}

    base = clean(os.getenv("ODDSPAPI_BASE_URL") or "https://v5.oddspapi.io/en").rstrip("/")
    tournament_id = clean(os.getenv("ODDSPAPI_MLB_TOURNAMENT_ID"))
    sport_id = clean(os.getenv("ODDSPAPI_MLB_SPORT_ID"))
    outputs: dict[str, str] = {}
    warnings: list[str] = []

    try:
        if not tournament_id:
            if not sport_id:
                sports_url = f"{base}/sports?" + urllib.parse.urlencode({"apiKey": key})
                sports = fetch_json_url(sports_url)
                write_json(WAREHOUSE_GAME_CONTEXT / f"oddspapi_sports_{date_label}.json", sports)
                iterable = sports if isinstance(sports, list) else sports.get("data") or sports.get("sports") or []
                for item in iterable:
                    name = " ".join(clean(item.get(k)) for k in ("name", "title", "sportName", "slug")).lower() if isinstance(item, dict) else ""
                    if "baseball" in name or "mlb" in name:
                        sport_id = clean(item.get("sportId") or item.get("id"))
                        break
            if sport_id:
                tournaments_url = f"{base}/tournaments?" + urllib.parse.urlencode({"apiKey": key, "sportId": sport_id})
                tournaments = fetch_json_url(tournaments_url)
                write_json(WAREHOUSE_GAME_CONTEXT / f"oddspapi_tournaments_{date_label}.json", tournaments)
                iterable = tournaments if isinstance(tournaments, list) else tournaments.get("data") or tournaments.get("tournaments") or []
                for item in iterable:
                    name = " ".join(clean(item.get(k)) for k in ("name", "title", "tournamentName", "slug")).lower() if isinstance(item, dict) else ""
                    if "mlb" in name or "major league baseball" in name:
                        tournament_id = clean(item.get("tournamentId") or item.get("id"))
                        break

        if tournament_id:
            odds_url = f"{base}/fixtures/odds/main?" + urllib.parse.urlencode({"apiKey": key, "tournamentId": tournament_id})
            odds = fetch_json_url(odds_url)
            odds_path = WAREHOUSE_GAME_CONTEXT / f"oddspapi_fixtures_odds_main_{date_label}.json"
            write_json(odds_path, odds)
            outputs["mainOdds"] = str(odds_path)
        else:
            warnings.append("Could not discover MLB tournament id. Set ODDSPAPI_MLB_TOURNAMENT_ID to enable /fixtures/odds/main.")

    except Exception as error:  # noqa: BLE001
        warnings.append(str(error))

    return {
        "status": "ok" if outputs and not warnings else "warning" if warnings else "skipped",
        "outputs": outputs,
        "warnings": warnings,
    }


def run_audits(date_label: str, season: int, markets: list[str]) -> list[dict[str, Any]]:
    steps: list[ProviderStep] = []
    for script in ["phase17_game_context_audit.py", "phase16_live_feature_audit.py"]:
        path = ROOT / "tools" / script
        if path.exists():
            steps.append(run_command([
                sys.executable, str(path.relative_to(ROOT)),
                "--date", date_label,
                "--season", str(season),
                "--markets", *markets,
                "--write",
            ]))
    return [step.__dict__ for step in steps]


def run_context_fill(
    *,
    date_label: str,
    season: int,
    markets: list[str],
    line_source: str = "propline",
    refresh_provider: bool = True,
    write: bool = True,
) -> dict[str, Any]:
    WAREHOUSE_GAME_CONTEXT.mkdir(parents=True, exist_ok=True)
    AUDITS.mkdir(parents=True, exist_ok=True)

    provider_steps: list[dict[str, Any]] = []
    if refresh_provider:
        provider_steps = run_existing_provider_bridges(date_label, season, markets, line_source)

    weather = fetch_open_meteo_supplement(date_label)
    oddspapi = fetch_oddspapi_optional(date_label)
    context_patch = patch_context_csv(date_label) if write else {"status": "dry_run"}
    playerboard_patch = patch_playerboard(date_label, season, markets) if write else {"status": "dry_run"}
    audits = run_audits(date_label, season, markets) if write else []

    result = {
        "status": "ok" if weather.get("status") == "ok" else "warning",
        "date": date_label,
        "season": season,
        "markets": markets,
        "lineSource": line_source,
        "providerSteps": provider_steps,
        "weatherSupplement": weather,
        "oddspapi": oddspapi,
        "contextPatch": context_patch,
        "playerboardPatch": playerboard_patch,
        "audits": audits,
        "trustPolicy": {
            "noSilentFallbacks": True,
            "missingOpeningLinesRemainMissing": True,
            "retractableRoofStatus": "retractable_unknown unless actual open/closed source exists",
        },
    }
    write_json(AUDITS / f"phase18_context_collector_{date_label}.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 18 provider-backed context collector.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--markets", nargs="+", default=["batter_hits", "batter_total_bases"])
    parser.add_argument("--line-source", choices=["propline", "the_odds_api", "oddspapi", "auto"], default="propline")
    parser.add_argument("--no-refresh-provider", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    line_source = "propline" if args.line_source in {"auto", "oddspapi"} else args.line_source
    result = run_context_fill(
        date_label=args.date,
        season=args.season,
        markets=args.markets,
        line_source=line_source,
        refresh_provider=not args.no_refresh_provider,
        write=not args.dry_run,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
