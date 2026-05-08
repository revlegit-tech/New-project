from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDGE = ROOT / "mlb_app" / "services" / "edge_board_service.py"
QA = ROOT / "tools" / "phase18_context_qa.py"
COLLECTOR = ROOT / "season_auto_collector.py"

NEW_BUILD_PAYLOAD = '''    def _build_payload(self, query: dict[str, list[str]]) -> dict[str, Any]:
        board = self.playerboard_service.board_payload(query)
        raw_rows = _list_rows(board.get("top") or board.get("rows") or [])
        self._cards = self._load_cards()
        rows = [self._enrich_row(row, index + 1, board) for index, row in enumerate(raw_rows)]
        rows = _attach_game_context_to_rows(rows, board, query)

        return {
            "status": "ok",
            "version": EDGE_BOARD_VERSION,
            "season": board.get("season"),
            "date": board.get("date") or board.get("latestAvailableDate"),
            "cacheHit": bool(board.get("cacheHit")),
            "rows": rows,
            "rowCount": len(rows),
            "source": {
                "cardsBuilt": board.get("cardsBuilt", 0),
                "propsLoaded": board.get("propsLoaded", 0),
                "message": board.get("message", ""),
                "saved": board.get("saved", {}),
            },
            "filters": self._filter_options(rows),
            "summary": self._summary(rows),
            "trust": board.get("trust", {}),
            "productState": board.get("productState"),
            "latestFullyGradedDate": board.get("latestFullyGradedDate", ""),
            "dataConfidence": board.get("dataConfidence", "Missing"),
            "modelReadiness": board.get("modelReadiness", {}),
        }
'''

HELPER = r'''

# Phase 18 v6: join canonical game context at the EdgeBoard API boundary.
# Playerboard remains a prop-row store; game context remains canonical under
# data/warehouse/game_context/game_context_YYYY-MM-DD.csv and is denormalized
# only in the service response for hot-path UI reads.
_GAME_CONTEXT_FIELDS = (
    "team_moneyline",
    "opponent_moneyline",
    "game_total",
    "moneyline_implied_probability",
    "team_implied_runs",
    "opponent_implied_runs",
    "opponent_implied_runs_proxy",
    "park_factor",
    "venue",
    "weather_temperature_f",
    "weather_wind_mph",
    "weather_humidity",
    "weather_wind_direction",
    "weather_precip_probability",
    "roof_status",
    "game_context_source",
)

_TEAM_ALIASES = {
    "SD": "SDP", "SDP": "SDP",
    "SF": "SFG", "SFG": "SFG",
    "TB": "TBR", "TBR": "TBR",
    "KC": "KCR", "KCR": "KCR",
    "WSH": "WSN", "WSN": "WSN",
    "CWS": "CHW", "CHW": "CHW",
    "OAK": "ATH", "ATH": "ATH",
}


def _team_key(value: Any) -> str:
    text = _clean(value).upper()
    return _TEAM_ALIASES.get(text, text)


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def _board_date(board: dict[str, Any], query: dict[str, list[str]]) -> str:
    return _query_value(query, "date") or _clean(board.get("date") or board.get("latestAvailableDate"))


def _context_file_for_board(board: dict[str, Any], query: dict[str, list[str]]) -> Path | None:
    date_label = _board_date(board, query)
    if not date_label:
        return None
    path = _root_dir() / "data" / "warehouse" / "game_context" / f"game_context_{date_label}.csv"
    return path if path.exists() else None


def _load_context_rows(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.exists():
        return []
    try:
        import csv
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except Exception:
        return []


def _ctx_value(row: dict[str, Any], *names: str) -> str:
    lower = {str(k).strip().lower(): v for k, v in row.items()}
    for name in names:
        value = lower.get(name.lower())
        if value not in {None, ""}:
            return _clean(value)
    return ""


def _context_team(row: dict[str, Any], role: str = "team") -> str:
    if role == "opponent":
        return _team_key(_ctx_value(row, "opponent", "opponent_team", "opponent_abbr"))
    return _team_key(_ctx_value(row, "team", "team_abbr", "team_code"))


def _context_index(context_rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    index: dict[tuple[str, str], dict[str, str]] = {}
    for ctx in context_rows:
        team = _context_team(ctx, "team")
        opponent = _context_team(ctx, "opponent")
        if team and opponent:
            index[(team, opponent)] = ctx
            continue
        # Support one-row-per-game context files that expose home/away teams.
        home = _team_key(_ctx_value(ctx, "home_team", "home", "home_abbr"))
        away = _team_key(_ctx_value(ctx, "away_team", "away", "away_abbr"))
        if home and away:
            index.setdefault((home, away), ctx)
            index.setdefault((away, home), ctx)
    return index


def _swap_orient(ctx: dict[str, str]) -> dict[str, str]:
    swapped = dict(ctx)
    pairs = (
        ("team_moneyline", "opponent_moneyline"),
        ("team_implied_runs", "opponent_implied_runs"),
        ("team_implied_runs_proxy", "opponent_implied_runs_proxy"),
    )
    for left, right in pairs:
        if left in ctx or right in ctx:
            swapped[left] = _clean(ctx.get(right))
            swapped[right] = _clean(ctx.get(left))
    return swapped


def _find_context(index: dict[tuple[str, str], dict[str, str]], team: str, opponent: str) -> dict[str, str]:
    if not team or not opponent:
        return {}
    direct = index.get((team, opponent))
    if direct:
        return direct
    reverse = index.get((opponent, team))
    if reverse:
        return _swap_orient(reverse)
    return {}


def _attach_context(row: dict[str, Any], ctx: dict[str, str]) -> dict[str, Any]:
    if not ctx:
        return row
    enriched = dict(row)
    for field in _GAME_CONTEXT_FIELDS:
        value = _ctx_value(ctx, field)
        if value:
            enriched[field] = value
    # UI convenience object for any rail/detail components that prefer nested data.
    enriched["gameContext"] = {
        field: enriched.get(field, "") for field in _GAME_CONTEXT_FIELDS
    }
    return enriched


def _attach_game_context_to_rows(rows: list[dict[str, Any]], board: dict[str, Any], query: dict[str, list[str]]) -> list[dict[str, Any]]:
    path = _context_file_for_board(board, query)
    index = _context_index(_load_context_rows(path))
    if not index:
        return rows
    enriched_rows: list[dict[str, Any]] = []
    for row in rows:
        team = _team_key(row.get("team"))
        opponent = _team_key(row.get("opponent"))
        enriched_rows.append(_attach_context(row, _find_context(index, team, opponent)))
    return enriched_rows
'''


def backup(path: Path) -> Path:
    backup_path = path.with_suffix(path.suffix + ".phase18v6_backup")
    if path.exists() and not backup_path.exists():
        backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return backup_path


def patch_edge() -> dict[str, object]:
    text = EDGE.read_text(encoding="utf-8")
    backup(EDGE)
    original = text

    # Remove older broken helper blocks if present.
    marker = "\n# Phase 18 v6: join canonical game context"
    if marker in text:
        text = text.split(marker)[0].rstrip() + "\n"
    legacy_marker = "\n# Phase 18 v4"
    if legacy_marker in text:
        text = text.split(legacy_marker)[0].rstrip() + "\n"

    pattern = re.compile(
        r"    def _build_payload\(self, query: dict\[str, list\[str\]\]\) -> dict\[str, Any\]:\n"
        r"(?:        .*\n)+?"
        r"(?=    def _with_board_cache_metadata\()",
        re.MULTILINE,
    )
    text, count = pattern.subn(NEW_BUILD_PAYLOAD + "\n", text, count=1)
    if count != 1:
        raise RuntimeError("Could not replace EdgeBoardService._build_payload")

    text = text.rstrip() + HELPER + "\n"
    EDGE.write_text(text, encoding="utf-8")
    return {"changed": text != original, "replacementCount": count, "path": str(EDGE)}


def patch_qa_timeout() -> dict[str, object]:
    if not QA.exists():
        return {"exists": False, "changed": False}
    text = QA.read_text(encoding="utf-8")
    original = text
    backup(QA)
    text = text.replace("urlopen(url, timeout=20)", "urlopen(url, timeout=90)")
    text = text.replace("urlopen(url, timeout = 20)", "urlopen(url, timeout=90)")
    QA.write_text(text, encoding="utf-8")
    return {"exists": True, "changed": text != original, "path": str(QA)}


def ensure_collector_hook() -> dict[str, object]:
    if not COLLECTOR.exists():
        return {"exists": False, "changed": False}
    text = COLLECTOR.read_text(encoding="utf-8")
    if "phase18_fill_missing_context" in text or "run_phase18_provider_context" in text:
        return {"exists": True, "changed": False, "alreadyHooked": True}
    backup(COLLECTOR)
    needle = "        try:\n            from playerboard import build_playerboard\n"
    hook = '''        try:
            from tools.phase18_fill_missing_context import run_phase18_context_fill

            summary["phase18ProviderContext"] = run_phase18_context_fill(
                date_label=date_label,
                season=int(date_label[:4]),
                markets=["batter_hits", "batter_total_bases"],
                line_source="propline",
            )
        except Exception as phase18_error:
            summary["phase18ProviderContext"] = {"error": str(phase18_error)}

'''
    if needle not in text:
        return {"exists": True, "changed": False, "alreadyHooked": False, "reason": "safe insertion point not found"}
    text = text.replace(needle, hook + needle, 1)
    COLLECTOR.write_text(text, encoding="utf-8")
    return {"exists": True, "changed": True, "path": str(COLLECTOR)}


def main() -> None:
    result = {
        "edgeBoardService": patch_edge(),
        "qaTimeout": patch_qa_timeout(),
        "collectorHook": ensure_collector_hook(),
    }
    print(result)


if __name__ == "__main__":
    main()
