from __future__ import annotations

import csv
import py_compile
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLAYERBOARD = ROOT / "playerboard.py"
PLAYERBOARD_CSV = ROOT / "data" / "playerboard" / "playerboard_2026.csv"
PLAYERBOARD_CSV_BACKUP = ROOT / "data" / "playerboard" / "playerboard_2026.csv.phase18v2_schema_backup"
EDGE_SERVICE = ROOT / "mlb_app" / "services" / "edge_board_service.py"
PROP_DETAIL_SERVICE = ROOT / "mlb_app" / "services" / "prop_detail_service.py"
PROP_DETAIL_JS = ROOT / "public" / "prop-detail.js"

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


def backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    target = path.with_suffix(path.suffix + ".phase18v4_backup")
    counter = 1
    while target.exists():
        target = path.with_suffix(path.suffix + f".phase18v4_backup_{counter}")
        counter += 1
    shutil.copy2(path, target)
    return target


def compile_ok(path: Path) -> tuple[bool, str]:
    try:
        py_compile.compile(str(path), doraise=True)
        return True, ""
    except Exception as exc:  # noqa: BLE001 - operator repair report
        return False, str(exc)


def restore_playerboard_from_git_if_needed() -> dict[str, Any]:
    before_ok, before_error = compile_ok(PLAYERBOARD)
    result: dict[str, Any] = {"beforeCompileOk": before_ok, "beforeError": before_error, "restored": False}
    if before_ok:
        return result

    backup_path = backup(PLAYERBOARD)
    result["backup"] = str(backup_path) if backup_path else ""
    completed = subprocess.run(["git", "restore", "--", "playerboard.py"], cwd=ROOT, text=True, capture_output=True)
    result["gitReturncode"] = completed.returncode
    result["gitStdout"] = completed.stdout.strip()
    result["gitStderr"] = completed.stderr.strip()
    after_ok, after_error = compile_ok(PLAYERBOARD)
    result["afterCompileOk"] = after_ok
    result["afterError"] = after_error
    result["restored"] = completed.returncode == 0 and after_ok
    if not result["restored"]:
        raise RuntimeError(
            "playerboard.py is still not importable after git restore. "
            f"Compile error: {after_error or before_error}"
        )
    return result


def restore_playerboard_csv_backup() -> dict[str, Any]:
    result: dict[str, Any] = {"exists": PLAYERBOARD_CSV.exists(), "backupExists": PLAYERBOARD_CSV_BACKUP.exists(), "restored": False}
    if not PLAYERBOARD_CSV.exists() or not PLAYERBOARD_CSV_BACKUP.exists():
        return result

    try:
        with PLAYERBOARD_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
            current_header = next(csv.reader(handle), [])
        with PLAYERBOARD_CSV_BACKUP.open("r", encoding="utf-8-sig", newline="") as handle:
            backup_header = next(csv.reader(handle), [])
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
        return result

    result["currentFieldCount"] = len(current_header)
    result["backupFieldCount"] = len(backup_header)
    result["currentHasAmericanOdds"] = "americanOdds" in current_header
    result["backupHasAmericanOdds"] = "americanOdds" in backup_header

    # The bad v2 migration narrowed the CSV and removed sportsbook fields. Restore only when the backup is richer.
    if len(backup_header) > len(current_header) and "americanOdds" in backup_header:
        backup_current = backup(PLAYERBOARD_CSV)
        shutil.copy2(PLAYERBOARD_CSV_BACKUP, PLAYERBOARD_CSV)
        result["restored"] = True
        result["currentBackup"] = str(backup_current) if backup_current else ""
    return result


def patch_edge_service() -> dict[str, Any]:
    text = EDGE_SERVICE.read_text(encoding="utf-8")
    original = text
    backup_path = None

    if "import csv" not in text:
        text = text.replace("from pathlib import Path\n", "from pathlib import Path\nimport csv\n", 1)

    # Remove stale v4 helper if re-running.
    text = re.sub(r"\n# PHASE18_V4_CONTEXT_HELPERS_START\n.*?# PHASE18_V4_CONTEXT_HELPERS_END\n", "\n", text, flags=re.DOTALL)

    if "game_context = _game_context_for_row(row)" not in text:
        text = text.replace("        enriched = dict(row)\n", "        enriched = dict(row)\n        game_context = _game_context_for_row(row)\n", 1)

    if "# PHASE18_V4_CONTEXT_JOIN_START" not in text:
        text = text.replace(
            "        return enriched\n\n    @staticmethod\n    def _filter_options",
            "        # PHASE18_V4_CONTEXT_JOIN_START\n"
            "        if game_context:\n"
            "            enriched.update(game_context)\n"
            "        # PHASE18_V4_CONTEXT_JOIN_END\n"
            "        return enriched\n\n    @staticmethod\n    def _filter_options",
            1,
        )

    helper = r'''
# PHASE18_V4_CONTEXT_HELPERS_START
_GAME_CONTEXT_CACHE: dict[tuple[str, tuple[int, int]], dict[tuple[str, str], dict[str, str]]] = {}
_GAME_CONTEXT_FIELDS = (
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
)
_TEAM_ALIASES = {"SD": "SDP", "SF": "SFG", "CWS": "CHW", "WSH": "WSN", "TB": "TBR", "KC": "KCR", "OAK": "ATH"}


def _context_team(value: Any) -> str:
    text = _clean(value).upper()
    return _TEAM_ALIASES.get(text, text)


def _context_file_signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
        return (stat.st_mtime_ns, stat.st_size)
    except OSError:
        return None


def _game_context_path(date_label: str) -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / "data" / "warehouse" / "game_context" / f"game_context_{date_label}.csv"


def _load_game_context(date_label: str) -> dict[tuple[str, str], dict[str, str]]:
    if not date_label:
        return {}
    path = _game_context_path(date_label)
    signature = _context_file_signature(path)
    if signature is None:
        return {}
    cache_key = (date_label, signature)
    cached = _GAME_CONTEXT_CACHE.get(cache_key)
    if cached is not None:
        return cached
    mapping: dict[tuple[str, str], dict[str, str]] = {}
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                team = _context_team(row.get("team"))
                opponent = _context_team(row.get("opponent"))
                if team and opponent:
                    mapping[(team, opponent)] = row
    except Exception:
        return {}
    # Drop stale entries for this date and store the current mtime-aware mapping.
    for key in [key for key in _GAME_CONTEXT_CACHE if key[0] == date_label]:
        _GAME_CONTEXT_CACHE.pop(key, None)
    _GAME_CONTEXT_CACHE[cache_key] = mapping
    return mapping


def _game_context_for_row(row: dict[str, Any]) -> dict[str, str]:
    date_label = _clean(row.get("date"))
    team = _context_team(row.get("team"))
    opponent = _context_team(row.get("opponent"))
    if not date_label or not team or not opponent:
        return {}
    context = _load_game_context(date_label).get((team, opponent)) or {}
    if not context:
        return {}
    return {field: _clean(context.get(field)) for field in _GAME_CONTEXT_FIELDS if _clean(context.get(field))}
# PHASE18_V4_CONTEXT_HELPERS_END
'''
    text = text.rstrip() + "\n" + helper + "\n"

    changed = text != original
    if changed:
        backup_path = backup(EDGE_SERVICE)
        EDGE_SERVICE.write_text(text, encoding="utf-8")
    ok, error = compile_ok(EDGE_SERVICE)
    if not ok:
        raise RuntimeError(f"edge_board_service.py failed compile after patch: {error}")
    return {"changed": changed, "backup": str(backup_path) if backup_path else ""}


def patch_prop_detail_service() -> dict[str, Any]:
    text = PROP_DETAIL_SERVICE.read_text(encoding="utf-8")
    original = text
    backup_path = None

    # Only patch if the old compact gameContext block is still present.
    pattern = re.compile(
        r'            "gameContext": \{\n'
        r'.*?'
        r'            \},\n'
        r'            "riskContext": \{',
        flags=re.DOTALL,
    )
    replacement = '''            "gameContext": {
                "park": _context_value(row, "park", "venue", "ballpark"),
                "weather": _weather_summary(row),
                "lineupStatus": _context_value(row, "lineupStatus", "lineup", "battingOrder"),
                "probablePitcher": _context_value(row, "pitcher", "probablePitcher", "opposingPitcher"),
                "teamTotal": _context_value(row, "team_implied_runs", "teamTotal", "teamTotalRuns", "impliedTeamTotal"),
                "startTime": _clean(row.get("gameTime")) or "Not available",
                "teamMoneyline": _context_value(row, "team_moneyline"),
                "opponentMoneyline": _context_value(row, "opponent_moneyline"),
                "gameTotal": _context_value(row, "game_total"),
                "moneylineImpliedProbability": _context_value(row, "moneyline_implied_probability"),
                "teamImpliedRuns": _context_value(row, "team_implied_runs"),
                "opponentImpliedRuns": _context_value(row, "opponent_implied_runs"),
                "parkFactor": _context_value(row, "park_factor"),
                "weatherTemperatureF": _context_value(row, "weather_temperature_f"),
                "weatherWindMph": _context_value(row, "weather_wind_mph"),
                "weatherHumidity": _context_value(row, "weather_humidity"),
                "weatherWindDirection": _context_value(row, "weather_wind_direction"),
                "weatherPrecipProbability": _context_value(row, "weather_precip_probability"),
                "roofStatus": _context_value(row, "roof_status"),
                "venue": _context_value(row, "venue"),
                "source": _context_value(row, "game_context_source"),
            },
            "riskContext": {'''
    text, count = pattern.subn(replacement, text, count=1)

    if "def _weather_summary" not in text:
        insert = r'''

def _weather_summary(row: dict[str, Any]) -> str:
    temp = _clean(row.get("weather_temperature_f"))
    wind = _clean(row.get("weather_wind_mph"))
    humidity = _clean(row.get("weather_humidity"))
    parts = []
    if temp:
        parts.append(f"{temp} F")
    if wind:
        parts.append(f"Wind {wind} mph")
    if humidity:
        parts.append(f"Humidity {humidity}%")
    return " · ".join(parts) if parts else _context_value(row, "weather", "weatherSummary", "weatherContext")
'''
        text = text.replace("\ndef _trend_profile", insert + "\ndef _trend_profile", 1)

    changed = text != original
    if changed:
        backup_path = backup(PROP_DETAIL_SERVICE)
        PROP_DETAIL_SERVICE.write_text(text, encoding="utf-8")
    ok, error = compile_ok(PROP_DETAIL_SERVICE)
    if not ok:
        raise RuntimeError(f"prop_detail_service.py failed compile after patch: {error}")
    return {"changed": changed, "replacementCount": count, "backup": str(backup_path) if backup_path else ""}


def patch_prop_detail_js() -> dict[str, Any]:
    if not PROP_DETAIL_JS.exists():
        return {"exists": False, "changed": False}
    text = PROP_DETAIL_JS.read_text(encoding="utf-8")
    original = text
    backup_path = None
    old = '''          <div><h4>Game context</h4><div class="prop-detail-metric-row compact">
            ${renderStat("Park", game.park)}
            ${renderStat("Weather", game.weather)}
            ${renderStat("Lineup", game.lineupStatus)}
            ${renderStat("Pitcher", game.probablePitcher)}
            ${renderStat("Team total", game.teamTotal)}
            ${renderStat("Start", game.startTime)}
          </div></div>'''
    new = '''          <div><h4>Game context</h4><div class="prop-detail-metric-row compact">
            ${renderStat("Team ML", formatOdds(game.teamMoneyline))}
            ${renderStat("Opp ML", formatOdds(game.opponentMoneyline))}
            ${renderStat("Game total", game.gameTotal)}
            ${renderStat("ML IP", pct(game.moneylineImpliedProbability))}
            ${renderStat("Team runs", game.teamImpliedRuns || game.teamTotal)}
            ${renderStat("Opp runs", game.opponentImpliedRuns)}
            ${renderStat("Park factor", game.parkFactor)}
            ${renderStat("Weather", game.weather)}
            ${renderStat("Wind", game.weatherWindMph ? `${game.weatherWindMph} mph` : "Not available")}
            ${renderStat("Humidity", game.weatherHumidity ? `${game.weatherHumidity}%` : "Not available")}
            ${renderStat("Roof", game.roofStatus)}
            ${renderStat("Venue", game.venue || game.park)}
          </div></div>'''
    if old in text:
        text = text.replace(old, new, 1)
    changed = text != original
    if changed:
        backup_path = backup(PROP_DETAIL_JS)
        PROP_DETAIL_JS.write_text(text, encoding="utf-8")
    return {"exists": True, "changed": changed, "backup": str(backup_path) if backup_path else ""}


def main() -> None:
    report = {
        "playerboardRestore": restore_playerboard_from_git_if_needed(),
        "playerboardCsvRestore": restore_playerboard_csv_backup(),
        "edgeBoardService": patch_edge_service(),
        "propDetailService": patch_prop_detail_service(),
        "propDetailJs": patch_prop_detail_js(),
    }
    print(report)


if __name__ == "__main__":
    main()
