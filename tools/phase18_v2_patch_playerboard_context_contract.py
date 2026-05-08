from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLAYERBOARD = ROOT / "playerboard.py"
PROP_DETAIL = ROOT / "mlb_app" / "services" / "prop_detail_service.py"

CONTEXT_FIELDS = [
    "team_moneyline",
    "opponent_moneyline",
    "game_total",
    "open_team_moneyline",
    "close_team_moneyline",
    "moneyline_move",
    "open_game_total",
    "close_game_total",
    "total_move",
    "moneyline_implied_probability",
    "team_implied_runs",
    "opponent_implied_runs",
    "opponent_implied_runs_proxy",
    "park_factor",
    "weather_temperature_f",
    "weather_wind_mph",
    "weather_wind_direction",
    "weather_humidity",
    "weather_precip_probability",
    "roof_status",
    "venue",
    "game_context_source",
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def insert_after_anchor_once(text: str, anchor: str, insertion: str) -> tuple[str, bool]:
    if insertion.strip() in text:
        return text, False
    if anchor not in text:
        raise RuntimeError(f"Anchor not found: {anchor!r}")
    return text.replace(anchor, anchor + insertion, 1), True


def patch_playerboard_fields(text: str) -> tuple[str, bool]:
    if '"team_moneyline"' in text.split("ODDS_DIRS", 1)[0]:
        return text, False
    anchor = '    "recentGames",\n]'
    insertion = ''.join(f'    "{field}",\n' for field in CONTEXT_FIELDS)
    return insert_after_anchor_once(text, anchor, insertion)


def patch_save_snapshot(text: str) -> tuple[str, bool]:
    if '"team_moneyline": clean(card.get("team_moneyline"))' in text:
        return text, False
    anchor = '            "recentGames": json.dumps(card.get("recentGames") or [], ensure_ascii=False),\n'
    insertion = ''.join(f'            "{field}": clean(card.get("{field}")),\n' for field in CONTEXT_FIELDS)
    return insert_after_anchor_once(text, anchor, insertion)


def patch_saved_card(text: str) -> tuple[str, bool]:
    if '"team_moneyline": clean(row.get("team_moneyline"))' in text:
        return text, False
    anchor = '        "recentGames": parse_json_field(row.get("recentGames"), []),\n'
    insertion = ''.join(f'        "{field}": clean(row.get("{field}")),\n' for field in CONTEXT_FIELDS)
    return insert_after_anchor_once(text, anchor, insertion)


def patch_prop_detail_game_context(text: str) -> tuple[str, bool]:
    if '"teamMoneyline": _context_value(row, "team_moneyline"' in text:
        return text, False
    old = '''            "gameContext": {\n                "park": _context_value(row, "park", "venue", "ballpark"),\n                "weather": _context_value(row, "weather", "weatherSummary", "weatherContext"),\n                "lineupStatus": _context_value(row, "lineupStatus", "lineup", "battingOrder"),\n                "probablePitcher": _context_value(row, "pitcher", "probablePitcher", "opposingPitcher"),\n                "teamTotal": _context_value(row, "teamTotal", "teamTotalRuns", "impliedTeamTotal"),\n                "startTime": _clean(row.get("gameTime")) or "Not available",\n            },'''
    new = '''            "gameContext": {\n                "teamMoneyline": _context_value(row, "team_moneyline", "teamMoneyline"),\n                "opponentMoneyline": _context_value(row, "opponent_moneyline", "opponentMoneyline"),\n                "gameTotal": _context_value(row, "game_total", "gameTotal"),\n                "moneylineImpliedProbability": _context_value(row, "moneyline_implied_probability", "moneylineImpliedProbability"),\n                "teamImpliedRuns": _context_value(row, "team_implied_runs", "teamImpliedRuns", "teamTotal", "teamTotalRuns", "impliedTeamTotal"),\n                "opponentImpliedRuns": _context_value(row, "opponent_implied_runs", "opponentImpliedRuns"),\n                "parkFactor": _context_value(row, "park_factor", "parkFactor"),\n                "weatherTemperatureF": _context_value(row, "weather_temperature_f", "weatherTemperatureF"),\n                "weatherWindMph": _context_value(row, "weather_wind_mph", "weatherWindMph"),\n                "weatherWindDirection": _context_value(row, "weather_wind_direction", "weatherWindDirection"),\n                "weatherHumidity": _context_value(row, "weather_humidity", "weatherHumidity"),\n                "weatherPrecipProbability": _context_value(row, "weather_precip_probability", "weatherPrecipProbability"),\n                "roofStatus": _context_value(row, "roof_status", "roofStatus"),\n                "venue": _context_value(row, "venue", "park", "ballpark"),\n                "source": _context_value(row, "game_context_source", "gameContextSource"),\n                "park": _context_value(row, "park", "venue", "ballpark"),\n                "weather": _context_value(row, "weather", "weatherSummary", "weatherContext", "weather_temperature_f"),\n                "lineupStatus": _context_value(row, "lineupStatus", "lineup", "battingOrder"),\n                "probablePitcher": _context_value(row, "pitcher", "probablePitcher", "opposingPitcher"),\n                "teamTotal": _context_value(row, "team_implied_runs", "teamTotal", "teamTotalRuns", "impliedTeamTotal"),\n                "startTime": _clean(row.get("gameTime")) or "Not available",\n            },'''
    if old not in text:
        raise RuntimeError("Could not find PropDetailService gameContext block to patch")
    return text.replace(old, new, 1), True


def patch_prop_detail_js() -> dict[str, Any]:
    path = ROOT / "public" / "prop-detail.js"
    if not path.exists():
        return {"path": str(path), "changed": False, "skipped": True}
    text = read(path)
    if 'renderStat("Team ML", formatOdds(game.teamMoneyline))' in text:
        return {"path": str(path), "changed": False}
    old = '''          <div><h4>Game context</h4><div class="prop-detail-metric-row compact">\n            ${renderStat("Park", game.park)}\n            ${renderStat("Weather", game.weather)}\n            ${renderStat("Lineup", game.lineupStatus)}\n            ${renderStat("Pitcher", game.probablePitcher)}\n            ${renderStat("Team total", game.teamTotal)}\n            ${renderStat("Start", game.startTime)}\n          </div></div>'''
    new = '''          <div><h4>Game context</h4><div class="prop-detail-metric-row compact">\n            ${renderStat("Team ML", formatOdds(game.teamMoneyline))}\n            ${renderStat("Opp ML", formatOdds(game.opponentMoneyline))}\n            ${renderStat("Game total", game.gameTotal)}\n            ${renderStat("ML IP", pct(game.moneylineImpliedProbability))}\n            ${renderStat("Team runs", game.teamImpliedRuns)}\n            ${renderStat("Opp runs", game.opponentImpliedRuns)}\n            ${renderStat("Park factor", game.parkFactor)}\n            ${renderStat("Temp", game.weatherTemperatureF ? `${game.weatherTemperatureF}°F` : "Not available")}\n            ${renderStat("Wind", game.weatherWindMph ? `${game.weatherWindMph} mph` : "Not available")}\n            ${renderStat("Humidity", game.weatherHumidity ? `${game.weatherHumidity}%` : "Not available")}\n            ${renderStat("Roof", game.roofStatus)}\n            ${renderStat("Venue", game.venue || game.park)}\n          </div></div>'''
    if old not in text:
        return {"path": str(path), "changed": False, "warning": "game context block not found; leaving prop-detail.js unchanged"}
    write(path, text.replace(old, new, 1))
    return {"path": str(path), "changed": True}


def load_playerboard_fields_from_source() -> list[str]:
    text = read(PLAYERBOARD)
    match = re.search(r"PLAYERBOARD_FIELDS\s*=\s*\[(.*?)\]", text, flags=re.S)
    if not match:
        raise RuntimeError("PLAYERBOARD_FIELDS not found")
    fields = re.findall(r'"([^"]+)"', match.group(1))
    return fields


def migrate_playerboard_csv(season: int) -> dict[str, Any]:
    path = ROOT / "data" / "playerboard" / f"playerboard_{season}.csv"
    if not path.exists():
        return {"path": str(path), "exists": False, "changed": False}
    fields = load_playerboard_fields_from_source()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        old_fields = list(reader.fieldnames or [])
        rows = list(reader)
    changed = old_fields != fields
    if not changed:
        return {"path": str(path), "exists": True, "changed": False, "rows": len(rows), "fieldCount": len(fields)}
    backup = path.with_suffix(path.suffix + ".phase18v2_schema_backup")
    if not backup.exists():
        backup.write_text(path.read_text(encoding="utf-8-sig", errors="ignore"), encoding="utf-8")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
    return {"path": str(path), "exists": True, "changed": True, "rows": len(rows), "oldFieldCount": len(old_fields), "newFieldCount": len(fields), "backup": str(backup)}


def main() -> None:
    results: dict[str, Any] = {"status": "ok"}
    text = read(PLAYERBOARD)
    for name, fn in [
        ("playerboardFields", patch_playerboard_fields),
        ("saveSnapshot", patch_save_snapshot),
        ("savedCard", patch_saved_card),
    ]:
        text, changed = fn(text)
        results[name] = {"changed": changed}
    write(PLAYERBOARD, text)

    prop_text = read(PROP_DETAIL)
    prop_text, prop_changed = patch_prop_detail_game_context(prop_text)
    write(PROP_DETAIL, prop_text)
    results["propDetailService"] = {"changed": prop_changed}
    results["propDetailJs"] = patch_prop_detail_js()
    results["csvMigration2026"] = migrate_playerboard_csv(2026)

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
