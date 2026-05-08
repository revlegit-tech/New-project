from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDGE_PATH = ROOT / "mlb_app" / "services" / "edge_board_service.py"
QA_PATH = ROOT / "tools" / "phase18_context_qa.py"
COLLECTOR_PATH = ROOT / "season_auto_collector.py"

HELPER_MARKER = "# Phase 18 v7: canonical game-context join helpers"
COLLECTOR_MARKER = "# Phase 18 provider-backed context collector hook"

NEW_BUILD_PAYLOAD = '''    def _build_payload(self, query: dict[str, list[str]]) -> dict[str, Any]:
        board = self.playerboard_service.board_payload(query)
        raw_rows = _list_rows(board.get("top") or board.get("rows") or [])
        game_context_index = _phase18_v7_game_context_index(query, board)
        self._cards = self._load_cards()
        rows = [
            self._enrich_row(_phase18_v7_merge_game_context(row, game_context_index), index + 1, board)
            for index, row in enumerate(raw_rows)
        ]

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
                "gameContextJoin": {
                    "source": "data/warehouse/game_context/game_context_DATE.csv",
                    "contextRows": len(game_context_index),
                    "matchedRows": sum(1 for row in rows if _clean(row.get("game_context_source"))),
                    "date": _phase18_v7_context_date(query, board),
                },
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

HELPERS = r'''

# Phase 18 v7: canonical game-context join helpers
_PHASE18_V7_CONTEXT_FIELDS = [
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
    "moneyline_source",
    "total_source",
    "weather_source",
    "park_factor_source",
]

_PHASE18_V7_CAMEL_ALIASES = {
    "team_moneyline": "teamMoneyline",
    "opponent_moneyline": "opponentMoneyline",
    "game_total": "gameTotal",
    "moneyline_implied_probability": "moneylineImpliedProbability",
    "team_implied_runs": "teamImpliedRuns",
    "opponent_implied_runs": "opponentImpliedRuns",
    "park_factor": "parkFactor",
    "weather_temperature_f": "weatherTemperatureF",
    "weather_wind_mph": "weatherWindMph",
    "weather_wind_direction": "weatherWindDirection",
    "weather_humidity": "weatherHumidity",
    "weather_precip_probability": "weatherPrecipProbability",
    "roof_status": "roofStatus",
    "venue": "venue",
}

_PHASE18_V7_TEAM_ALIASES = {
    "ari": "ARI", "arizona": "ARI", "arizona diamondbacks": "ARI",
    "atl": "ATL", "atlanta": "ATL", "atlanta braves": "ATL",
    "bal": "BAL", "baltimore": "BAL", "baltimore orioles": "BAL",
    "bos": "BOS", "boston": "BOS", "boston red sox": "BOS",
    "chc": "CHC", "chicago cubs": "CHC", "cubs": "CHC",
    "chw": "CHW", "cws": "CHW", "chicago white sox": "CHW", "white sox": "CHW",
    "cin": "CIN", "cincinnati": "CIN", "cincinnati reds": "CIN",
    "cle": "CLE", "cleveland": "CLE", "cleveland guardians": "CLE",
    "col": "COL", "colorado": "COL", "colorado rockies": "COL",
    "det": "DET", "detroit": "DET", "detroit tigers": "DET",
    "hou": "HOU", "houston": "HOU", "houston astros": "HOU",
    "kc": "KCR", "kcr": "KCR", "kansas city": "KCR", "kansas city royals": "KCR",
    "laa": "LAA", "los angeles angels": "LAA", "angels": "LAA",
    "lad": "LAD", "los angeles dodgers": "LAD", "dodgers": "LAD",
    "mia": "MIA", "miami": "MIA", "miami marlins": "MIA",
    "mil": "MIL", "milwaukee": "MIL", "milwaukee brewers": "MIL",
    "min": "MIN", "minnesota": "MIN", "minnesota twins": "MIN",
    "nym": "NYM", "new york mets": "NYM", "mets": "NYM",
    "nyy": "NYY", "new york yankees": "NYY", "yankees": "NYY",
    "ath": "ATH", "oak": "ATH", "oakland athletics": "ATH", "athletics": "ATH", "a s": "ATH",
    "phi": "PHI", "philadelphia": "PHI", "philadelphia phillies": "PHI",
    "pit": "PIT", "pittsburgh": "PIT", "pittsburgh pirates": "PIT",
    "sd": "SDP", "sdp": "SDP", "san diego": "SDP", "san diego padres": "SDP", "padres": "SDP",
    "sea": "SEA", "seattle": "SEA", "seattle mariners": "SEA",
    "sf": "SFG", "sfg": "SFG", "san francisco": "SFG", "san francisco giants": "SFG",
    "stl": "STL", "st louis": "STL", "st louis cardinals": "STL", "saint louis cardinals": "STL", "cardinals": "STL",
    "tb": "TBR", "tbr": "TBR", "tampa bay": "TBR", "tampa bay rays": "TBR",
    "tex": "TEX", "texas": "TEX", "texas rangers": "TEX",
    "tor": "TOR", "toronto": "TOR", "toronto blue jays": "TOR",
    "wsh": "WSN", "wsn": "WSN", "washington": "WSN", "washington nationals": "WSN",
}


def _phase18_v7_context_date(query: dict[str, list[str]], board: dict[str, Any]) -> str:
    date_label = _query_value(query, "date")
    if date_label:
        return date_label
    return _clean(board.get("date") or board.get("latestAvailableDate"))


def _phase18_v7_context_path(date_label: str) -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / "data" / "warehouse" / "game_context" / f"game_context_{date_label}.csv"


def _phase18_v7_text_key(value: Any) -> str:
    text = _clean(value).lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _phase18_v7_team_key(value: Any) -> str:
    key = _phase18_v7_text_key(value)
    if not key:
        return ""
    return _PHASE18_V7_TEAM_ALIASES.get(key, key.upper())


def _phase18_v7_game_context_index(query: dict[str, list[str]], board: dict[str, Any]) -> dict[tuple[str, str], dict[str, str]]:
    date_label = _phase18_v7_context_date(query, board)
    path = _phase18_v7_context_path(date_label)
    if not date_label or not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            context_rows = list(csv.DictReader(handle))
    except Exception:
        return {}

    index: dict[tuple[str, str], dict[str, str]] = {}
    for context in context_rows:
        team = _phase18_v7_team_key(context.get("team") or context.get("team_abbr") or context.get("teamCode"))
        opponent = _phase18_v7_team_key(context.get("opponent") or context.get("opponent_abbr") or context.get("opponentCode"))
        if team and opponent:
            index[(team, opponent)] = context
    return index


def _phase18_v7_merge_game_context(row: dict[str, Any], index: dict[tuple[str, str], dict[str, str]]) -> dict[str, Any]:
    merged = dict(row)
    team = _phase18_v7_team_key(_first(merged, "team", "team_abbr", "teamCode"))
    opponent = _phase18_v7_team_key(_first(merged, "opponent", "opponent_abbr", "opponentCode"))
    context = index.get((team, opponent))
    if not context:
        return merged

    for field in _PHASE18_V7_CONTEXT_FIELDS:
        value = context.get(field)
        if _clean(value):
            merged[field] = value
        alias = _PHASE18_V7_CAMEL_ALIASES.get(field)
        if alias and _clean(value):
            merged[alias] = value

    source = _clean(merged.get("game_context_source"))
    if not source:
        merged["game_context_source"] = "phase18_game_context_join"
    return merged
'''


def backup(path: Path) -> str:
    if not path.exists():
        return ""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = path.with_name(f"{path.name}.phase18v7_backup_{stamp}")
    shutil.copy2(path, dest)
    return str(dest)


def ensure_import_csv(text: str) -> tuple[str, bool]:
    if re.search(r"^import csv$", text, flags=re.M):
        return text, False
    lines = text.splitlines()
    insert_at = 1 if lines and lines[0].startswith("from __future__") else 0
    lines.insert(insert_at + 1, "import csv")
    return "\n".join(lines) + "\n", True


def replace_build_payload(text: str) -> tuple[str, bool]:
    lines = text.splitlines()
    start = None
    for idx, line in enumerate(lines):
        if line.startswith("    def _build_payload("):
            start = idx
            break
    if start is None:
        raise RuntimeError("Could not find EdgeBoardService._build_payload")

    end = None
    for idx in range(start + 1, len(lines)):
        line = lines[idx]
        if line.startswith("    def ") and not line.startswith("        "):
            end = idx
            break
    if end is None:
        raise RuntimeError("Could not find end of EdgeBoardService._build_payload")

    new_lines = NEW_BUILD_PAYLOAD.rstrip("\n").splitlines()
    existing = "\n".join(lines[start:end]).strip()
    replacement = NEW_BUILD_PAYLOAD.strip()
    if existing == replacement:
        return text, False
    return "\n".join(lines[:start] + new_lines + lines[end:]) + "\n", True


def replace_helpers(text: str) -> tuple[str, bool]:
    if HELPER_MARKER in text:
        text = text[: text.index(HELPER_MARKER)].rstrip() + "\n"
    return text.rstrip() + HELPERS + "\n", True


def patch_edge() -> dict[str, object]:
    text = EDGE_PATH.read_text(encoding="utf-8")
    original = text
    backup_path = backup(EDGE_PATH)
    text, import_changed = ensure_import_csv(text)
    text, build_changed = replace_build_payload(text)
    text, helpers_changed = replace_helpers(text)
    changed = text != original
    if changed:
        EDGE_PATH.write_text(text, encoding="utf-8")
    return {
        "path": str(EDGE_PATH),
        "changed": changed,
        "backup": backup_path,
        "importChanged": import_changed,
        "buildPayloadChanged": build_changed,
        "helpersChanged": helpers_changed,
    }


def patch_qa_timeout() -> dict[str, object]:
    if not QA_PATH.exists():
        return {"exists": False, "changed": False}
    text = QA_PATH.read_text(encoding="utf-8")
    original = text
    backup_path = backup(QA_PATH)
    text = text.replace("urlopen(url, timeout=20)", "urlopen(url, timeout=90)")
    text = text.replace("timeout=20", "timeout=90")
    if text != original:
        QA_PATH.write_text(text, encoding="utf-8")
    return {"exists": True, "changed": text != original, "backup": backup_path}


def patch_collector_hook() -> dict[str, object]:
    if not COLLECTOR_PATH.exists():
        return {"exists": False, "changed": False}
    text = COLLECTOR_PATH.read_text(encoding="utf-8")
    if COLLECTOR_MARKER in text:
        return {"exists": True, "changed": False, "reason": "already_present"}

    needle = '''        try:
            from playerboard_backtest import grade_playerboard

            summary["playerboardBacktest"] = grade_playerboard(
                season=int(date_label[:4]),
            )
        except Exception as backtest_error:
            summary["playerboardBacktest"] = {"error": str(backtest_error)}
'''
    hook = '''
        # Phase 18 provider-backed context collector hook
        try:
            import subprocess
            import sys

            context_markets = [
                market.strip()
                for market in os.environ.get("PHASE18_MARKETS", "batter_hits,batter_total_bases").split(",")
                if market.strip()
            ]
            context_cmd = [
                sys.executable,
                str(ROOT / "tools" / "phase18_fill_missing_context.py"),
                "--date",
                date_label,
                "--season",
                str(int(date_label[:4])),
                "--line-source",
                os.environ.get("PHASE18_LINE_SOURCE", "propline"),
                "--markets",
                *context_markets,
            ]
            context_run = subprocess.run(
                context_cmd,
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=int(os.environ.get("PHASE18_COLLECTOR_TIMEOUT_SECONDS", "600")),
                check=False,
            )
            summary["phase18ProviderContext"] = {
                "status": "ok" if context_run.returncode == 0 else "warning",
                "returncode": context_run.returncode,
                "stdoutTail": context_run.stdout[-4000:],
                "stderrTail": context_run.stderr[-4000:],
            }
        except Exception as context_error:
            summary["phase18ProviderContext"] = {"error": str(context_error)}
'''
    if needle not in text:
        return {"exists": True, "changed": False, "reason": "playerboard_backtest_block_not_found"}
    backup_path = backup(COLLECTOR_PATH)
    text = text.replace(needle, hook + "\n" + needle)
    COLLECTOR_PATH.write_text(text, encoding="utf-8")
    return {"exists": True, "changed": True, "backup": backup_path}


def compile_targets() -> dict[str, object]:
    targets = [
        "playerboard.py",
        "mlb_app/services/edge_board_service.py",
        "mlb_app/services/prop_detail_service.py",
        "season_auto_collector.py",
        "tools/phase18_context_qa.py",
    ]
    result = subprocess.run([sys.executable, "-m", "py_compile", *targets], cwd=str(ROOT), capture_output=True, text=True)
    return {"ok": result.returncode == 0, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def main() -> None:
    summary = {
        "edgeBoardService": patch_edge(),
        "qaTimeout": patch_qa_timeout(),
        "collectorHook": patch_collector_hook(),
        "compile": compile_targets(),
    }
    print(json.dumps(summary, indent=2))
    if not summary["compile"]["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
