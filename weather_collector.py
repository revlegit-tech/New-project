from __future__ import annotations

"""Weather collector and feature builder for MLB games.

Uses:
- MLB game cache from data/cache/incremental_stats/games_YEAR.csv
- Open-Meteo forecast/archive APIs
- stadium coordinates

Writes:
- data/cache/weather/game_weather_YEAR.csv
- data/cache/weather/weather_features_YEAR.csv
- data/cache/weather/weather_status_YEAR.json

Design:
- Regular-season first
- Safe upsert by gamePk
- Conservative weather adjustments
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
DATA_DIR = ROOT / "data"
INCREMENTAL_DIR = DATA_DIR / "cache" / "incremental_stats"
WEATHER_DIR = DATA_DIR / "cache" / "weather"
RAW_DIR = WEATHER_DIR / "raw"

FORECAST_BASE = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_BASE = "https://archive-api.open-meteo.com/v1/archive"

REGULAR_SEASON_START_DATES = {
    2024: "2024-03-20",
    2025: "2025-03-18",
    2026: "2026-03-25",
}

# Stadium coordinate approximations.
# roof: open, dome, retractable
STADIUM_CF_BEARINGS: dict[str, int] = {
    "Yankee Stadium": 65,
    "Fenway Park": 93,
    "Camden Yards": 90,
    "Oriole Park at Camden Yards": 90,
    "Rogers Centre": 45,
    "Tropicana Field": 0,
    "Guaranteed Rate Field": 315,
    "Rate Field": 315,
    "Progressive Field": 30,
    "Comerica Park": 5,
    "Target Field": 330,
    "Kauffman Stadium": 325,
    "T-Mobile Park": 360,
    "Globe Life Field": 0,
    "Angel Stadium": 0,
    "Oakland Coliseum": 325,
    "Minute Maid Park": 25,
    "Citi Field": 44,
    "Citizens Bank Park": 25,
    "Nationals Park": 15,
    "Truist Park": 355,
    "loanDepot park": 45,
    "Wrigley Field": 45,
    "Busch Stadium": 15,
    "PNC Park": 25,
    "Great American Ball Park": 360,
    "American Family Field": 355,
    "Dodger Stadium": 50,
    "Oracle Park": 70,
    "Petco Park": 300,
    "Coors Field": 35,
    "Chase Field": 340,
}

TURF_STADIUMS = {
    "Tropicana Field", "Rogers Centre", "Globe Life Field", "T-Mobile Park",
    "Chase Field", "loanDepot park", "Minute Maid Park", "American Family Field",
}

STADIUMS = {
    "Angel Stadium": {"lat": 33.8003, "lon": -117.8827, "roof": "open", "team": "LAA"},
    "Busch Stadium": {"lat": 38.6226, "lon": -90.1928, "roof": "open", "team": "STL"},
    "Chase Field": {"lat": 33.4455, "lon": -112.0667, "roof": "retractable", "team": "ARI"},
    "Citi Field": {"lat": 40.7571, "lon": -73.8458, "roof": "open", "team": "NYM"},
    "Citizens Bank Park": {"lat": 39.9061, "lon": -75.1665, "roof": "open", "team": "PHI"},
    "Comerica Park": {"lat": 42.3390, "lon": -83.0485, "roof": "open", "team": "DET"},
    "Coors Field": {"lat": 39.7559, "lon": -104.9942, "roof": "open", "team": "COL"},
    "Dodger Stadium": {"lat": 34.0739, "lon": -118.2400, "roof": "open", "team": "LAD"},
    "Fenway Park": {"lat": 42.3467, "lon": -71.0972, "roof": "open", "team": "BOS"},
    "Globe Life Field": {"lat": 32.7473, "lon": -97.0842, "roof": "retractable", "team": "TEX"},
    "Great American Ball Park": {"lat": 39.0979, "lon": -84.5081, "roof": "open", "team": "CIN"},
    "Guaranteed Rate Field": {"lat": 41.8300, "lon": -87.6339, "roof": "open", "team": "CHW"},
    "Kauffman Stadium": {"lat": 39.0517, "lon": -94.4803, "roof": "open", "team": "KCR"},
    "loanDepot park": {"lat": 25.7781, "lon": -80.2197, "roof": "retractable", "team": "MIA"},
    "Minute Maid Park": {"lat": 29.7573, "lon": -95.3555, "roof": "retractable", "team": "HOU"},
    "Nationals Park": {"lat": 38.8730, "lon": -77.0074, "roof": "open", "team": "WSN"},
    "Oakland Coliseum": {"lat": 37.7516, "lon": -122.2005, "roof": "open", "team": "ATH"},
    "Oracle Park": {"lat": 37.7786, "lon": -122.3893, "roof": "open", "team": "SFG"},
    "Oriole Park at Camden Yards": {"lat": 39.2840, "lon": -76.6217, "roof": "open", "team": "BAL"},
    "Petco Park": {"lat": 32.7073, "lon": -117.1566, "roof": "open", "team": "SDP"},
    "PNC Park": {"lat": 40.4469, "lon": -80.0057, "roof": "open", "team": "PIT"},
    "Progressive Field": {"lat": 41.4962, "lon": -81.6852, "roof": "open", "team": "CLE"},
    "Rate Field": {"lat": 41.8300, "lon": -87.6339, "roof": "open", "team": "CHW"},
    "Rogers Centre": {"lat": 43.6414, "lon": -79.3894, "roof": "retractable", "team": "TOR"},
    "T-Mobile Park": {"lat": 47.5914, "lon": -122.3325, "roof": "retractable", "team": "SEA"},
    "Target Field": {"lat": 44.9817, "lon": -93.2776, "roof": "open", "team": "MIN"},
    "Tropicana Field": {"lat": 27.7682, "lon": -82.6534, "roof": "dome", "team": "TBR"},
    "Truist Park": {"lat": 33.8907, "lon": -84.4677, "roof": "open", "team": "ATL"},
    "Wrigley Field": {"lat": 41.9484, "lon": -87.6553, "roof": "open", "team": "CHC"},
    "Yankee Stadium": {"lat": 40.8296, "lon": -73.9262, "roof": "open", "team": "NYY"},
    "American Family Field": {"lat": 43.0280, "lon": -87.9712, "roof": "retractable", "team": "MIL"},
}

for _venue, _info in STADIUMS.items():
    _info["cf_bearing"] = STADIUM_CF_BEARINGS.get(_venue, 45)
    _info["surface"] = "turf" if _venue in TURF_STADIUMS else "grass"



WEATHER_FIELDS = [
    "season", "seasonPhase", "date", "gamePk", "gameDate", "venue", "home", "away",
    "latitude", "longitude", "roof", "weatherSource", "matchedHour",
    "temperatureF", "feelsLikeF", "humidity", "precipitationProbability", "precipitation",
    "windMph", "windDirection", "windGustMph", "pressureMsl",
    "cloudCover", "parkSurface", "updatedAt",
]

FEATURE_FIELDS = [
    "season", "seasonPhase", "date", "gamePk", "venue", "home", "away", "roof",
    "temperatureF", "feelsLikeF", "humidity", "precipitationProbability", "windMph",
    "windDirection", "windOutScore", "windOutFlag", "windSpeedScore", "windScore",
    "temperatureScore", "humidityScore", "rainScore", "coldGameFlag", "turfFlag",
    "hrWeatherAdjustment", "totalBasesWeatherAdjustment", "hitsWeatherAdjustment",
    "pitcherStrikeoutsWeatherAdjustment", "pitcherHitsAllowedWeatherAdjustment",
    "pitcherEarnedRunsWeatherAdjustment", "weatherConfidence", "weatherSummary",
]


def clean(value: Any) -> str:
    return str(value or "").strip()


# Returns 0.0 for missing values. Appropriate for weather/stat aggregation.
# For ML feature extraction use ml_prop_model.to_float() instead.
def to_float(value: Any, default: float = 0.0) -> float:
    text = clean(value).replace(",", "")
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


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


def upsert_csv(path: Path, key_fields: list[str], fieldnames: list[str], rows: list[dict[str, Any]]) -> dict[str, int]:
    existing = {}

    if path.exists():
        for row in read_csv_rows(path):
            key = tuple(clean(row.get(field)) for field in key_fields)
            existing[key] = row

    before = len(existing)

    for row in rows:
        normalized = {field: clean(row.get(field, "")) for field in fieldnames}
        key = tuple(clean(normalized.get(field)) for field in key_fields)
        existing[key] = normalized

    write_csv(path, fieldnames, list(existing.values()))

    return {
        "inputRows": len(rows),
        "beforeRows": before,
        "afterRows": len(existing),
        "netNewRows": max(0, len(existing) - before),
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def fetch_json(url: str, timeout: int = 35) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "baseball-prop-predictor"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def season_phase_for_date(date_label: str, season: int) -> str:
    regular_start = REGULAR_SEASON_START_DATES.get(season, f"{season}-03-25")
    return "regular" if date_label >= regular_start else "practice"


def phase_allowed(date_label: str, season: int, phase: str) -> bool:
    phase = clean(phase).lower() or "regular"
    if phase in {"all", "any"}:
        return True
    return season_phase_for_date(date_label, season) == phase


def game_rows(season: int, phase: str = "regular") -> list[dict[str, str]]:
    rows = read_csv_rows(INCREMENTAL_DIR / f"games_{season}.csv")
    return [row for row in rows if phase_allowed(clean(row.get("date")), season, phase)]


def stadium_for_game(game: dict[str, Any]) -> dict[str, Any]:
    venue = clean(game.get("venue"))

    if venue in STADIUMS:
        return {"venue": venue, **STADIUMS[venue]}

    home = clean(game.get("home")).upper()
    for name, info in STADIUMS.items():
        if clean(info.get("team")).upper() == home:
            return {"venue": name, **info}

    return {"venue": venue, "lat": "", "lon": "", "roof": "unknown", "team": home}


def is_past_date(date_label: str) -> bool:
    return date_label < datetime.now().strftime("%Y-%m-%d")


def open_meteo_url(lat: float, lon: float, date_label: str) -> tuple[str, str]:
    hourly = [
        "temperature_2m",
        "apparent_temperature",
        "relative_humidity_2m",
        "precipitation",
        "wind_speed_10m",
        "wind_direction_10m",
        "wind_gusts_10m",
        "pressure_msl",
        "cloud_cover",
    ]

    # precipitation_probability is forecast-only, so we include it only on forecast endpoint.
    if is_past_date(date_label):
        base = ARCHIVE_BASE
        source = "open_meteo_archive"
    else:
        base = FORECAST_BASE
        source = "open_meteo_forecast"
        hourly.append("precipitation_probability")

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": date_label,
        "end_date": date_label,
        "hourly": ",".join(hourly),
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "auto",
    }

    return f"{base}?{urllib.parse.urlencode(params)}", source


def nearest_hour_index(times: list[str], game_date: str) -> int:
    if not times:
        return -1

    # MLB gameDate is usually UTC. Open-Meteo timezone=auto returns local timestamps.
    # For v1, choose the closest hour by hour-of-day after parsing what we can.
    try:
        dt = datetime.fromisoformat(game_date.replace("Z", "+00:00"))
        target_hour = dt.hour
    except Exception:
        target_hour = 19

    best_index = 0
    best_diff = 99

    for i, stamp in enumerate(times):
        try:
            hour = int(stamp[11:13])
        except Exception:
            hour = target_hour

        diff = abs(hour - target_hour)
        if diff < best_diff:
            best_index = i
            best_diff = diff

    return best_index


def collect_weather(season: int = 2026, phase: str = "regular", force: bool = False) -> dict[str, Any]:
    WEATHER_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    existing = read_csv_rows(WEATHER_DIR / f"game_weather_{season}.csv")
    existing_keys = {clean(row.get("gamePk")) for row in existing}

    rows = []
    errors = []
    skipped = 0

    for game in game_rows(season, phase):
        game_pk = clean(game.get("gamePk"))
        date_label = clean(game.get("date"))
        if not game_pk or not date_label:
            continue

        if game_pk in existing_keys and not force:
            skipped += 1
            continue

        stadium = stadium_for_game(game)
        lat = to_float(stadium.get("lat"))
        lon = to_float(stadium.get("lon"))

        if not lat or not lon:
            errors.append({"gamePk": game_pk, "date": date_label, "error": "Missing stadium coordinates", "venue": game.get("venue")})
            continue

        if stadium.get("roof") == "dome":
            rows.append({
                "season": season,
                "seasonPhase": season_phase_for_date(date_label, season),
                "date": date_label,
                "gamePk": game_pk,
                "gameDate": clean(game.get("gameDate")),
                "venue": clean(stadium.get("venue")),
                "home": clean(game.get("home")),
                "away": clean(game.get("away")),
                "latitude": lat,
                "longitude": lon,
                "roof": stadium.get("roof"),
                "weatherSource": "dome_weather_neutral",
                "matchedHour": "",
                "temperatureF": 72,
                "feelsLikeF": 72,
                "humidity": 45,
                "precipitationProbability": 0,
                "precipitation": 0,
                "windMph": 0,
                "windDirection": 0,
                "windGustMph": 0,
                "pressureMsl": "",
                "cloudCover": 0,
                "parkSurface": stadium.get("surface", "grass"),
                "updatedAt": now_iso(),
            })
            continue

        try:
            url, source = open_meteo_url(lat, lon, date_label)
            payload = fetch_json(url)
            write_json(RAW_DIR / f"weather_{game_pk}_{date_label}.json", payload)

            hourly = payload.get("hourly", {})
            times = hourly.get("time", [])
            idx = nearest_hour_index(times, clean(game.get("gameDate")))

            def value(name: str, default: Any = "") -> Any:
                values = hourly.get(name, [])
                if idx < 0 or idx >= len(values):
                    return default
                return values[idx]

            rows.append({
                "season": season,
                "seasonPhase": season_phase_for_date(date_label, season),
                "date": date_label,
                "gamePk": game_pk,
                "gameDate": clean(game.get("gameDate")),
                "venue": clean(stadium.get("venue")),
                "home": clean(game.get("home")),
                "away": clean(game.get("away")),
                "latitude": lat,
                "longitude": lon,
                "roof": stadium.get("roof"),
                "weatherSource": source,
                "matchedHour": times[idx] if idx >= 0 and idx < len(times) else "",
                "temperatureF": value("temperature_2m"),
                "feelsLikeF": value("apparent_temperature", value("temperature_2m")),
                "humidity": value("relative_humidity_2m"),
                "precipitationProbability": value("precipitation_probability", 0),
                "precipitation": value("precipitation", 0),
                "windMph": value("wind_speed_10m"),
                "windDirection": value("wind_direction_10m"),
                "windGustMph": value("wind_gusts_10m"),
                "pressureMsl": value("pressure_msl"),
                "cloudCover": value("cloud_cover"),
                "parkSurface": stadium.get("surface", "grass"),
                "updatedAt": now_iso(),
            })
        except Exception as error:
            errors.append({"gamePk": game_pk, "date": date_label, "venue": game.get("venue"), "error": str(error)})

    upsert = upsert_csv(WEATHER_DIR / f"game_weather_{season}.csv", ["gamePk"], WEATHER_FIELDS, rows)

    summary = {
        "season": season,
        "phase": phase,
        "rowsCollected": len(rows),
        "skippedExisting": skipped,
        "upsert": upsert,
        "errors": errors[:50],
        "errorCount": len(errors),
        "weatherFile": str(WEATHER_DIR / f"game_weather_{season}.csv"),
        "updatedAt": now_iso(),
    }

    write_json(WEATHER_DIR / f"weather_collect_status_{season}.json", summary)
    return summary


def angle_diff(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def wind_out_score(wind_direction: float, venue: str) -> float:
    cf_bearing = STADIUM_CF_BEARINGS.get(venue, 45)

    # Meteorological wind direction is where wind comes FROM.
    # Blowing toward center is approximately from opposite center bearing.
    blowing_toward = (wind_direction + 180) % 360
    diff = angle_diff(blowing_toward, cf_bearing)

    if diff <= 45:
        return 1.0
    if diff <= 90:
        return 0.4
    if diff >= 135:
        return -1.0
    if diff >= 100:
        return -0.4
    return 0.0


def weather_adjustments(row: dict[str, Any]) -> dict[str, Any]:
    roof = clean(row.get("roof")).lower()
    venue = clean(row.get("venue"))
    temp = to_float(row.get("temperatureF"), 72)
    feels_like = to_float(row.get("feelsLikeF"), temp)
    humidity = to_float(row.get("humidity"), 50)
    rain_prob = to_float(row.get("precipitationProbability"), 0)
    precip = to_float(row.get("precipitation"), 0)
    wind_mph = to_float(row.get("windMph"), 0)
    wind_dir = to_float(row.get("windDirection"), 0)

    if roof == "dome":
        return {
            "windOutScore": 0,
            "windOutFlag": 0,
            "windSpeedScore": 0,
            "windScore": 0,
            "temperatureScore": 0,
            "humidityScore": 0,
            "rainScore": 0,
            "coldGameFlag": 0,
            "turfFlag": 1 if clean(row.get("parkSurface")).lower() == "turf" else 0,
            "hrWeatherAdjustment": 0,
            "totalBasesWeatherAdjustment": 0,
            "hitsWeatherAdjustment": 0,
            "pitcherStrikeoutsWeatherAdjustment": 0,
            "pitcherHitsAllowedWeatherAdjustment": 0,
            "pitcherEarnedRunsWeatherAdjustment": 0,
            "weatherConfidence": "High",
            "weatherSummary": "Dome environment; weather neutral.",
        }

    roof_multiplier = 0.5 if roof == "retractable" else 1.0

    temp_score = clamp((temp - 70) / 20, -1, 1)
    humidity_score = clamp((humidity - 50) / 50, -1, 1)
    rain_score = clamp(max(rain_prob / 100, precip / 0.25), 0, 1)
    out_score = wind_out_score(wind_dir, venue)
    speed_score = clamp(wind_mph / 15, 0, 1)
    w_score = out_score * speed_score

    hr_adj = clamp(
        (temp_score * 0.010) + (w_score * 0.020) + (humidity_score * 0.003) - (rain_score * 0.005),
        -0.030,
        0.030,
    ) * roof_multiplier

    tb_adj = clamp(
        (temp_score * 0.007) + (w_score * 0.012) + (humidity_score * 0.002) - (rain_score * 0.003),
        -0.020,
        0.020,
    ) * roof_multiplier

    hits_adj = clamp(
        (temp_score * 0.004) + (w_score * 0.006) - (rain_score * 0.002),
        -0.010,
        0.010,
    ) * roof_multiplier

    pitcher_k_adj = clamp(
        (-max(0, w_score) * 0.004) - (max(0, temp_score) * 0.003),
        -0.012,
        0.008,
    ) * roof_multiplier

    pitcher_hits_adj = clamp(
        (temp_score * 0.004) + (w_score * 0.007) - (rain_score * 0.002),
        -0.015,
        0.015,
    ) * roof_multiplier

    pitcher_er_adj = clamp(
        (temp_score * 0.005) + (w_score * 0.008) - (rain_score * 0.002),
        -0.015,
        0.015,
    ) * roof_multiplier

    confidence = "Medium"
    if rain_score >= 0.5:
        confidence = "Low"
    elif roof == "retractable":
        confidence = "Medium"

    parts = []
    if temp >= 78:
        parts.append("warm temperature favors carry")
    elif temp <= 55:
        parts.append("cold temperature suppresses carry")

    if w_score >= 0.4:
        parts.append("wind appears hitter-friendly")
    elif w_score <= -0.4:
        parts.append("wind appears pitcher-friendly")

    if rain_score >= 0.3:
        parts.append("rain/precipitation risk lowers confidence")

    if roof == "retractable":
        parts.append("retractable roof uncertainty halves adjustment")

    summary = "; ".join(parts) if parts else "Weather mostly neutral."

    return {
        "windOutScore": round(out_score, 3),
        "windOutFlag": 1 if out_score >= 0.4 else 0,
        "windSpeedScore": round(speed_score, 3),
        "windScore": round(w_score, 3),
        "temperatureScore": round(temp_score, 3),
        "humidityScore": round(humidity_score, 3),
        "rainScore": round(rain_score, 3),
        "coldGameFlag": 1 if feels_like < 45 else 0,
        "turfFlag": 1 if clean(row.get("parkSurface")).lower() == "turf" else 0,
        "hrWeatherAdjustment": round(hr_adj, 4),
        "totalBasesWeatherAdjustment": round(tb_adj, 4),
        "hitsWeatherAdjustment": round(hits_adj, 4),
        "pitcherStrikeoutsWeatherAdjustment": round(pitcher_k_adj, 4),
        "pitcherHitsAllowedWeatherAdjustment": round(pitcher_hits_adj, 4),
        "pitcherEarnedRunsWeatherAdjustment": round(pitcher_er_adj, 4),
        "weatherConfidence": confidence,
        "weatherSummary": summary,
    }


def build_weather_features(season: int = 2026, phase: str = "regular") -> dict[str, Any]:
    rows = read_csv_rows(WEATHER_DIR / f"game_weather_{season}.csv")
    feature_rows = []

    for row in rows:
        if not phase_allowed(clean(row.get("date")), season, phase):
            continue

        adj = weather_adjustments(row)
        feature_rows.append({
            "season": season,
            "seasonPhase": season_phase_for_date(clean(row.get("date")), season),
            "date": clean(row.get("date")),
            "gamePk": clean(row.get("gamePk")),
            "venue": clean(row.get("venue")),
            "home": clean(row.get("home")),
            "away": clean(row.get("away")),
            "roof": clean(row.get("roof")),
            "temperatureF": clean(row.get("temperatureF")),
            "feelsLikeF": clean(row.get("feelsLikeF")),
            "humidity": clean(row.get("humidity")),
            "precipitationProbability": clean(row.get("precipitationProbability")),
            "windMph": clean(row.get("windMph")),
            "windDirection": clean(row.get("windDirection")),
            **adj,
        })

    write_csv(WEATHER_DIR / f"weather_features_{season}.csv", FEATURE_FIELDS, feature_rows)

    summary = {
        "season": season,
        "phase": phase,
        "inputWeatherRows": len(rows),
        "featureRows": len(feature_rows),
        "featureFile": str(WEATHER_DIR / f"weather_features_{season}.csv"),
        "updatedAt": now_iso(),
    }

    write_json(WEATHER_DIR / f"weather_feature_status_{season}.json", summary)
    return summary


def collect_and_build(season: int = 2026, phase: str = "regular", force: bool = False) -> dict[str, Any]:
    collect = collect_weather(season=season, phase=phase, force=force)
    features = build_weather_features(season=season, phase=phase)
    return {"collect": collect, "features": features}


def lookup_game_weather(season: int, date_label: str, team: str, opponent: str) -> dict[str, Any]:
    team = clean(team).upper()
    opponent = clean(opponent).upper()

    for row in read_csv_rows(WEATHER_DIR / f"weather_features_{season}.csv"):
        if clean(row.get("date")) != clean(date_label):
            continue

        home = clean(row.get("home")).upper()
        away = clean(row.get("away")).upper()
        teams = {home, away}

        if team in teams and opponent in teams:
            return row

    return {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect and build MLB game weather features.")
    sub = parser.add_subparsers(dest="command", required=True)

    collect = sub.add_parser("collect")
    collect.add_argument("--season", type=int, default=2026)
    collect.add_argument("--phase", default="regular", choices=["regular", "practice", "all"])
    collect.add_argument("--force", action="store_true")

    build = sub.add_parser("build")
    build.add_argument("--season", type=int, default=2026)
    build.add_argument("--phase", default="regular", choices=["regular", "practice", "all"])

    both = sub.add_parser("sync")
    both.add_argument("--season", type=int, default=2026)
    both.add_argument("--phase", default="regular", choices=["regular", "practice", "all"])
    both.add_argument("--force", action="store_true")

    args = parser.parse_args()

    if args.command == "collect":
        print(json.dumps(collect_weather(args.season, args.phase, args.force), indent=2))
    elif args.command == "build":
        print(json.dumps(build_weather_features(args.season, args.phase), indent=2))
    elif args.command == "sync":
        print(json.dumps(collect_and_build(args.season, args.phase, args.force), indent=2))


if __name__ == "__main__":
    main()
