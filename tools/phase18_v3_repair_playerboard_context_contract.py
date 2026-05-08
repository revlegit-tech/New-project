from __future__ import annotations

import ast
import csv
import json
import re
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLAYERBOARD = ROOT / "playerboard.py"
PLAYERBOARD_CSV = ROOT / "data" / "playerboard" / "playerboard_2026.csv"
PHASE18_BACKUP = ROOT / "data" / "playerboard" / "playerboard_2026.csv.phase18v2_schema_backup"

BASE_FIELDS = [
    "snapshotAt",
    "season",
    "date",
    "market",
    "marketDisplay",
    "baseMarket",
    "isAltMarket",
    "player",
    "team",
    "opponent",
    "pitcher",
    "line",
    "americanOdds",
    "book",
    "bookKey",
    "bookCount",
    "books",
    "finalProbabilityPercent",
    "sportsbookImpliedPercent",
    "finalEdgePercent",
    "confidence",
    "recommendation",
    "weatherAdjustmentPercent",
    "savantAdjustmentPercent",
    "oddsMovementAdjustmentPercent",
    "missingData",
    "originalMarket",
    "rawLabel",
    "marketFamily",
    "hitRates",
    "recentGames",
]

# Canonical Phase 17/18 live-game context fields. These are game/team context, not batter props.
CONTEXT_FIELDS = [
    "american_odds",
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
    "opponent_rate",
    "park_factor",
    "weather_temperature_f",
    "weather_wind_mph",
    "weather_wind_direction",
    "weather_humidity",
    "weather_precip_probability",
    "roof_status",
    "venue",
    "game_context_source",
    "best_book",
    "best_american_odds",
    "sportsbook_count",
    "sportsbook_implied_probability",
]


def read_header(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return next(csv.reader(handle), [])
    except Exception:
        return []


def dedupe(seq: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in seq:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def current_playerboard_fields_from_source(text: str) -> list[str]:
    match = re.search(r"PLAYERBOARD_FIELDS\s*=\s*(\[.*?\])\s*\n\s*ODDS_DIRS\s*=", text, flags=re.DOTALL)
    if not match:
        return []
    try:
        value = ast.literal_eval(match.group(1))
        if isinstance(value, list):
            return [str(item) for item in value]
    except Exception:
        return []
    return []


def python_list_source(name: str, values: list[str]) -> str:
    lines = [f"{name} = ["]
    for value in values:
        lines.append(f"    {value!r},")
    lines.append("]")
    return "\n".join(lines)


def repair_playerboard_fields() -> dict[str, Any]:
    text = PLAYERBOARD.read_text(encoding="utf-8")
    source_fields = current_playerboard_fields_from_source(text)
    backup_header = read_header(PHASE18_BACKUP)
    csv_header = read_header(PLAYERBOARD_CSV)

    # Prefer the widest known on-disk contract so we do not discard earlier phase columns.
    candidates = [BASE_FIELDS, source_fields, csv_header, backup_header]
    widest = max(candidates, key=lambda items: len(items) if items else 0)
    fields = dedupe(list(widest or BASE_FIELDS) + CONTEXT_FIELDS)

    replacement = python_list_source("PLAYERBOARD_FIELDS", fields) + "\n\nODDS_DIRS ="
    repaired, count = re.subn(
        r"PLAYERBOARD_FIELDS\s*=\s*\[.*?\]\s*\n\s*ODDS_DIRS\s*=",
        replacement,
        text,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise RuntimeError("Could not repair PLAYERBOARD_FIELDS block in playerboard.py")

    changed = repaired != text
    if changed:
        PLAYERBOARD.with_suffix(".py.phase18v3_backup").write_text(text, encoding="utf-8")
        PLAYERBOARD.write_text(repaired, encoding="utf-8")
    return {"changed": changed, "fieldCount": len(fields), "usedBackupHeader": bool(backup_header)}


def patch_saved_card_mapping() -> dict[str, Any]:
    text = PLAYERBOARD.read_text(encoding="utf-8")
    marker = '        "recentGames": parse_json_field(row.get("recentGames"), []),\n'
    if '"team_moneyline": clean(row.get("team_moneyline"))' in text:
        return {"changed": False, "reason": "already patched"}
    if marker not in text:
        raise RuntimeError("Could not find saved_card_from_row insertion marker")

    additions = ''.join([
        '        "american_odds": clean(row.get("american_odds")) or clean(row.get("americanOdds")),\n',
        '        "team_moneyline": clean(row.get("team_moneyline")),\n',
        '        "opponent_moneyline": clean(row.get("opponent_moneyline")),\n',
        '        "game_total": clean(row.get("game_total")),\n',
        '        "open_team_moneyline": clean(row.get("open_team_moneyline")),\n',
        '        "close_team_moneyline": clean(row.get("close_team_moneyline")),\n',
        '        "moneyline_move": clean(row.get("moneyline_move")),\n',
        '        "open_game_total": clean(row.get("open_game_total")),\n',
        '        "close_game_total": clean(row.get("close_game_total")),\n',
        '        "total_move": clean(row.get("total_move")),\n',
        '        "moneyline_implied_probability": clean(row.get("moneyline_implied_probability")),\n',
        '        "team_implied_runs": clean(row.get("team_implied_runs")),\n',
        '        "opponent_implied_runs": clean(row.get("opponent_implied_runs")),\n',
        '        "opponent_implied_runs_proxy": clean(row.get("opponent_implied_runs_proxy")),\n',
        '        "opponent_rate": clean(row.get("opponent_rate")),\n',
        '        "park_factor": clean(row.get("park_factor")),\n',
        '        "weather_temperature_f": clean(row.get("weather_temperature_f")),\n',
        '        "weather_wind_mph": clean(row.get("weather_wind_mph")),\n',
        '        "weather_wind_direction": clean(row.get("weather_wind_direction")),\n',
        '        "weather_humidity": clean(row.get("weather_humidity")),\n',
        '        "weather_precip_probability": clean(row.get("weather_precip_probability")),\n',
        '        "roof_status": clean(row.get("roof_status")),\n',
        '        "venue": clean(row.get("venue")),\n',
        '        "game_context_source": clean(row.get("game_context_source")),\n',
        '        "best_book": clean(row.get("best_book")) or clean(row.get("book")),\n',
        '        "best_american_odds": clean(row.get("best_american_odds")) or clean(row.get("americanOdds")),\n',
        '        "sportsbook_count": clean(row.get("sportsbook_count")) or clean(row.get("bookCount")),\n',
        '        "sportsbook_implied_probability": clean(row.get("sportsbook_implied_probability")) or clean(row.get("sportsbookImpliedPercent")),\n',
    ])
    updated = text.replace(marker, marker + additions, 1)
    PLAYERBOARD.write_text(updated, encoding="utf-8")
    return {"changed": True}


def restore_and_expand_csv() -> dict[str, Any]:
    restored = False
    if PHASE18_BACKUP.exists():
        current_header = read_header(PLAYERBOARD_CSV)
        backup_header = read_header(PHASE18_BACKUP)
        if backup_header and len(backup_header) > len(current_header):
            # The v2 migrator narrowed the file. Restore the wider backup before adding fields.
            shutil.copy2(PHASE18_BACKUP, PLAYERBOARD_CSV)
            restored = True

    if not PLAYERBOARD_CSV.exists():
        return {"exists": False, "restoredFromBackup": restored}

    with PLAYERBOARD_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        old_fields = reader.fieldnames or []

    new_fields = dedupe(list(old_fields or BASE_FIELDS) + CONTEXT_FIELDS)
    changed = restored or new_fields != old_fields
    if changed:
        csv_backup = PLAYERBOARD_CSV.with_suffix(".csv.phase18v3_backup")
        if PLAYERBOARD_CSV.exists() and not csv_backup.exists():
            shutil.copy2(PLAYERBOARD_CSV, csv_backup)
        with PLAYERBOARD_CSV.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=new_fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in new_fields})
    return {"exists": True, "restoredFromBackup": restored, "changed": changed, "oldFieldCount": len(old_fields), "newFieldCount": len(new_fields), "rows": len(rows)}


def patch_prop_detail_service() -> dict[str, Any]:
    path = ROOT / "mlb_app" / "services" / "prop_detail_service.py"
    if not path.exists():
        return {"exists": False}
    text = path.read_text(encoding="utf-8")
    if '"teamMoneyline": _context_value(row, "team_moneyline"' in text:
        return {"exists": True, "changed": False, "reason": "already patched"}
    marker = '                "teamTotal": _context_value(row, "teamTotal", "teamTotalRuns", "impliedTeamTotal"),\n'
    if marker not in text:
        return {"exists": True, "changed": False, "reason": "marker not found"}
    additions = ''.join([
        '                "teamMoneyline": _context_value(row, "team_moneyline", "teamMoneyline"),\n',
        '                "opponentMoneyline": _context_value(row, "opponent_moneyline", "opponentMoneyline"),\n',
        '                "gameTotal": _context_value(row, "game_total", "gameTotal"),\n',
        '                "moneylineImpliedProbability": _context_value(row, "moneyline_implied_probability", "moneylineImpliedProbability"),\n',
        '                "teamImpliedRuns": _context_value(row, "team_implied_runs", "teamImpliedRuns"),\n',
        '                "opponentImpliedRuns": _context_value(row, "opponent_implied_runs", "opponentImpliedRuns"),\n',
        '                "parkFactor": _context_value(row, "park_factor", "parkFactor"),\n',
        '                "temperatureF": _context_value(row, "weather_temperature_f", "temperatureF"),\n',
        '                "windMph": _context_value(row, "weather_wind_mph", "windMph"),\n',
        '                "humidity": _context_value(row, "weather_humidity", "humidity"),\n',
        '                "windDirection": _context_value(row, "weather_wind_direction", "windDirection"),\n',
        '                "roofStatus": _context_value(row, "roof_status", "roofStatus"),\n',
    ])
    updated = text.replace(marker, marker + additions, 1)
    path.write_text(updated, encoding="utf-8")
    return {"exists": True, "changed": True}


def main() -> None:
    result = {
        "playerboardFields": repair_playerboard_fields(),
        "savedCardMapping": patch_saved_card_mapping(),
        "csv": restore_and_expand_csv(),
        "propDetailService": patch_prop_detail_service(),
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
