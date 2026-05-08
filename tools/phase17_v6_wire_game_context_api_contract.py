from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_edge_board() -> bool:
    path = ROOT / "mlb_app" / "services" / "edge_board_service.py"
    text = read(path)
    changed = False

    if "import csv" not in text:
        text = text.replace("from __future__ import annotations\n\n", "from __future__ import annotations\n\nimport csv\n")
        changed = True

    old = "        rows = [self._enrich_row(row, index + 1, board) for index, row in enumerate(raw_rows)]\n"
    new = """        game_context_by_row = _load_game_context_for_board(board, query)
        rows = [
            self._enrich_row(_merge_game_context(row, game_context_by_row), index + 1, board)
            for index, row in enumerate(raw_rows)
        ]
"""
    if old in text and new not in text:
        text = text.replace(old, new)
        changed = True

    marker = "\ndef _board_cache_key(query: dict[str, list[str]]) -> Hashable:\n"
    helper = r'''
GAME_CONTEXT_FIELDS = (
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

GAME_CONTEXT_ALIASES = {
    "team_moneyline": "teamMoneyline",
    "opponent_moneyline": "opponentMoneyline",
    "game_total": "gameTotal",
    "moneyline_implied_probability": "moneylineImpliedProbability",
    "team_implied_runs": "teamImpliedRuns",
    "opponent_implied_runs": "opponentImpliedRuns",
    "opponent_implied_runs_proxy": "opponentImpliedRunsProxy",
    "park_factor": "parkFactor",
    "weather_temperature_f": "weatherTemperatureF",
    "weather_wind_mph": "weatherWindMph",
    "weather_wind_direction": "weatherWindDirection",
    "weather_humidity": "weatherHumidity",
    "weather_precip_probability": "weatherPrecipProbability",
    "roof_status": "roofStatus",
    "game_context_source": "gameContextSource",
}


def _load_game_context_for_board(board: dict[str, Any], query: dict[str, list[str]]) -> dict[tuple[str, str], dict[str, str]]:
    """Load canonical Phase 17 game context rows for API row enrichment.

    Playerboard remains the hot path, but the source of truth for game lines,
    implied runs, weather, venue, and park context is the separate game-context
    layer. This bridge joins those fields back onto EdgeBoard rows so the UI
    does not show stale `Missing` values after the context layer is populated.
    """

    date_label = _clean(board.get("date") or board.get("latestAvailableDate") or _query_value(query, "date"))
    if not date_label:
        return {}
    path = Path("data") / "warehouse" / "game_context" / f"game_context_{date_label}.csv"
    if not path.exists():
        return {}

    contexts: dict[tuple[str, str], dict[str, str]] = {}
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if not isinstance(row, dict):
                    continue
                team = _context_team(row, "team")
                opponent = _context_team(row, "opponent")
                if not team or not opponent:
                    continue
                contexts[(team, opponent)] = row
    except OSError:
        return {}
    return contexts


def _merge_game_context(row: dict[str, Any], contexts: dict[tuple[str, str], dict[str, str]]) -> dict[str, Any]:
    if not contexts:
        return row
    key = (_context_team(row, "team"), _context_team(row, "opponent"))
    context = contexts.get(key)
    if not context:
        return row

    merged = dict(row)
    for field in GAME_CONTEXT_FIELDS:
        value = context.get(field)
        if value not in {None, ""} and merged.get(field) in {None, ""}:
            merged[field] = value
        alias = GAME_CONTEXT_ALIASES.get(field)
        if alias and value not in {None, ""} and merged.get(alias) in {None, ""}:
            merged[alias] = value
    return merged


def _context_team(row: dict[str, Any], key: str) -> str:
    aliases = {
        "team": ("team", "team_abbr", "teamAbbr", "team_code", "teamCode"),
        "opponent": ("opponent", "opponent_abbr", "opponentAbbr", "opponent_code", "opponentCode"),
    }
    for alias in aliases.get(key, (key,)):
        value = _clean(row.get(alias)).upper()
        if value:
            return value
    return ""

'''
    if "GAME_CONTEXT_FIELDS = (" not in text and marker in text:
        text = text.replace(marker, "\n" + helper + marker)
        changed = True

    if changed:
        write(path, text)
    return changed


def patch_prop_detail_service() -> bool:
    path = ROOT / "mlb_app" / "services" / "prop_detail_service.py"
    text = read(path)
    changed = False

    old = '''            "gameContext": {
                "park": _context_value(row, "park", "venue", "ballpark"),
                "weather": _context_value(row, "weather", "weatherSummary", "weatherContext"),
                "lineupStatus": _context_value(row, "lineupStatus", "lineup", "battingOrder"),
                "probablePitcher": _context_value(row, "pitcher", "probablePitcher", "opposingPitcher"),
                "teamTotal": _context_value(row, "teamTotal", "teamTotalRuns", "impliedTeamTotal"),
                "startTime": _clean(row.get("gameTime")) or "Not available",
            },
'''
    new = '''            "gameContext": {
                "teamMoneyline": _context_value(row, "team_moneyline", "teamMoneyline"),
                "opponentMoneyline": _context_value(row, "opponent_moneyline", "opponentMoneyline"),
                "gameTotal": _context_value(row, "game_total", "gameTotal"),
                "closeGameTotal": _context_value(row, "close_game_total", "closeGameTotal", "game_total", "gameTotal"),
                "moneylineImpliedProbability": _context_value(row, "moneyline_implied_probability", "moneylineImpliedProbability"),
                "teamImpliedRuns": _context_value(row, "team_implied_runs", "teamImpliedRuns", "teamTotal", "teamTotalRuns", "impliedTeamTotal"),
                "opponentImpliedRuns": _context_value(row, "opponent_implied_runs", "opponentImpliedRuns"),
                "parkFactor": _context_value(row, "park_factor", "parkFactor"),
                "park": _context_value(row, "venue", "park", "ballpark", "park_factor", "parkFactor"),
                "weather": _weather_summary(row),
                "weatherTemperatureF": _context_value(row, "weather_temperature_f", "weatherTemperatureF"),
                "weatherWindMph": _context_value(row, "weather_wind_mph", "weatherWindMph"),
                "weatherPrecipProbability": _context_value(row, "weather_precip_probability", "weatherPrecipProbability"),
                "lineupStatus": _context_value(row, "lineupStatus", "lineup", "battingOrder"),
                "probablePitcher": _context_value(row, "pitcher", "probablePitcher", "opposingPitcher"),
                "teamTotal": _context_value(row, "team_implied_runs", "teamImpliedRuns", "teamTotal", "teamTotalRuns", "impliedTeamTotal"),
                "startTime": _clean(row.get("gameTime")) or "Not available",
                "source": _context_value(row, "game_context_source", "gameContextSource"),
            },
'''
    if old in text and new not in text:
        text = text.replace(old, new)
        changed = True

    helper_marker = "\ndef _trend_profile(row: dict[str, Any], lookup: dict[str, str], board: dict[str, Any]) -> dict[str, Any]:\n"
    helper = '''\n\ndef _weather_summary(row: dict[str, Any]) -> str:\n    direct = _context_value(row, "weather", "weatherSummary", "weatherContext")\n    if direct != "Not available":\n        return direct\n    pieces: list[str] = []\n    temp = _context_value(row, "weather_temperature_f", "weatherTemperatureF")\n    wind = _context_value(row, "weather_wind_mph", "weatherWindMph")\n    precip = _context_value(row, "weather_precip_probability", "weatherPrecipProbability")\n    if temp != "Not available":\n        pieces.append(f"{temp}°F")\n    if wind != "Not available":\n        pieces.append(f"{wind} mph wind")\n    if precip != "Not available":\n        pieces.append(f"{precip}% precip")\n    return " · ".join(pieces) if pieces else "Not available"\n'''
    if "def _weather_summary(" not in text and helper_marker in text:
        text = text.replace(helper_marker, helper + helper_marker)
        changed = True

    if changed:
        write(path, text)
    return changed


def patch_prop_detail_js() -> bool:
    path = ROOT / "public" / "prop-detail.js"
    text = read(path)
    changed = False

    old = '''            ${renderStat("Park", game.park)}
            ${renderStat("Weather", game.weather)}
            ${renderStat("Lineup", game.lineupStatus)}
            ${renderStat("Pitcher", game.probablePitcher)}
            ${renderStat("Team total", game.teamTotal)}
            ${renderStat("Start", game.startTime)}
'''
    new = '''            ${renderStat("Team ML", formatOdds(game.teamMoneyline))}
            ${renderStat("Opp ML", formatOdds(game.opponentMoneyline))}
            ${renderStat("Game total", game.gameTotal)}
            ${renderStat("ML IP", pct(game.moneylineImpliedProbability))}
            ${renderStat("Team runs", game.teamImpliedRuns)}
            ${renderStat("Opp runs", game.opponentImpliedRuns)}
            ${renderStat("Park", game.parkFactor)}
            ${renderStat("Weather", game.weather)}
            ${renderStat("Pitcher", game.probablePitcher)}
'''
    if old in text and new not in text:
        text = text.replace(old, new)
        changed = True

    if changed:
        write(path, text)
    return changed


def main() -> None:
    results = {
        "edgeBoardServiceChanged": patch_edge_board(),
        "propDetailServiceChanged": patch_prop_detail_service(),
        "propDetailJsChanged": patch_prop_detail_js(),
    }
    status = "ok" if any(results.values()) else "noop"
    print({"status": status, **results})


if __name__ == "__main__":
    main()
