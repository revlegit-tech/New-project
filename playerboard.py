from __future__ import annotations

import argparse
import copy
import os
import re
import csv
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from team_game_markets import TEAM_GAME_MARKETS, TEAM_GAME_MARKET_LABELS, load_oddspapi_game_market_props

ROOT = Path(__file__).resolve().parent
PLAYERBOARD_DIR = ROOT / "data" / "playerboard"

_CSV_CACHE: dict[Path, tuple[tuple[int, int], list[dict[str, str]]]] = {}
_SAVED_PLAYERBOARD_CACHE: dict[tuple[int, str, str, int, tuple[int, int] | None], dict[str, Any]] = {}

PLAYERBOARD_FIELDS = [
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

ODDS_DIRS = [
    ROOT / "data" / "odds",
    ROOT / "data" / "cache" / "odds_movement",
    ROOT / "data" / "prop_reports" / "web",
]

DEFAULT_MARKETS = [
    "batter_total_bases",
    "batter_total_bases_alt",
    "batter_hits",
    "batter_hits_alt",
    "batter_home_runs",
    "batter_home_runs_alt",
    "batter_rbis",
    "batter_stolen_bases",
    "team_total_runs",
    "team_first_to_score",
    "moneyline",
    "moneyline_first_five",
    "run_line",
    "run_line_first_five",
    "run_line_first_inning",
    "run_line_second_inning",
    "run_line_third_inning",
    "run_line_fourth_inning",
    "run_line_fifth_inning",
    "run_line_sixth_inning",
    "run_line_seventh_inning",
    "run_line_eighth_inning",
    "run_line_ninth_inning",
    "game_total_runs",
    "first_five_total_runs",
    "first_inning_total_runs",
    "second_inning_total_runs",
    "third_inning_total_runs",
    "fourth_inning_total_runs",
    "fifth_inning_total_runs",
    "sixth_inning_total_runs",
    "seventh_inning_total_runs",
    "eighth_inning_total_runs",
    "ninth_inning_total_runs",
    "pitcher_strikeouts",
    "pitcher_strikeouts_alt",
    "pitcher_hits_allowed",
    "pitcher_hits_allowed_alt",
    "pitcher_earned_runs",
    "pitcher_earned_runs_alt",
]


def clean(value: Any) -> str:
    return str(value or "").strip()


def to_float(value: Any, default: float = 0.0) -> float:
    """Convert numeric text to float, returning default for missing/invalid values.
    
    This helper is for aggregation/reporting where default=0.0 is intentional.
    Do not use it for ML feature extraction when missingness must stay explicit;
    use ml_prop_model.to_float() or a nullable parser instead.
    """
    text = clean(value).replace(",", "")
    if not text:
        return default
    try:
        return float(text)
    except Exception:
        return default




def parse_ladder_side(side: Any) -> tuple[str, str]:
    """Return implied line and display label from PropLine side text.

    Examples:
    - "4+ Hits" -> ("3.5", "4+ Hits")
    - "2+ Strikeouts" -> ("1.5", "2+ Strikeouts")
    """
    text = clean(side)
    match = re.search(r"\b(\d+)\s*\+\s*(.+)", text, flags=re.IGNORECASE)
    if not match:
        return "", text

    threshold = int(match.group(1))
    stat_name = " ".join(match.group(2).split())
    implied_line = str(round(threshold - 0.5, 1))
    return implied_line, f"{threshold}+ {stat_name}"


def market_display_label(market: Any, raw_label: Any = "") -> str:
    market_text = normalize_market(market)
    label = clean(raw_label)

    if market_text == "batter_hits_alt":
        return f"Batter Hits Ladder - {label}" if label else "Batter Hits Ladder"
    if market_text == "batter_total_bases_alt":
        return f"Batter Total Bases Ladder - {label}" if label else "Batter Total Bases Ladder"
    if market_text == "batter_home_runs_alt":
        return f"Batter Home Runs Alt - {label}" if label else "Batter Home Runs Alt"
    if market_text == "pitcher_strikeouts_alt":
        return f"Pitcher Strikeouts Ladder - {label}" if label else "Pitcher Strikeouts Ladder"
    if market_text == "pitcher_hits_allowed_alt":
        return f"Pitcher Hits Allowed Ladder - {label}" if label else "Pitcher Hits Allowed Ladder"
    if market_text == "pitcher_earned_runs_alt":
        return f"Pitcher Earned Runs Ladder - {label}" if label else "Pitcher Earned Runs Ladder"

    return market_text.replace("_", " ").title()


def base_market(market: Any) -> str:
    text = normalize_market(market)
    return text[:-4] if text.endswith("_alt") else text


def market_family(market: Any) -> str:
    text = base_market(market)
    if text.startswith("batter_"):
        return "batter"
    if text.startswith("pitcher_"):
        return "pitcher"
    if text in TEAM_GAME_MARKETS or text.startswith("team_"):
        return "team"
    if text.startswith("game_") or text.startswith("first_") or text.startswith("run_line") or text.startswith("moneyline"):
        return "game"
    return "other"


def classify_prop_market(raw_market: Any, raw_label: Any, line: Any, american_odds: Any) -> str:
    """Preserve special/ladder PropLine props as alt markets instead of filtering them out."""
    original = normalize_market(raw_market)
    text = f"{clean(raw_market)} {clean(raw_label)}".lower()
    line_value = to_float(line)
    odds = to_float(american_odds)

    # Explicit text clues first.
    is_alt = any(token in text for token in [
        "alternate", "alt ", "ladder", "2+", "3+", "4+", "5+",
        "milestone", "boost", "special", "laser",
    ])

    if re.search(r"\b\d+\s*\+\s*hits?\b", text, flags=re.IGNORECASE):
        return "batter_hits_alt"

    if re.search(r"\b\d+\s*\+\s*total bases?\b", text, flags=re.IGNORECASE):
        return "batter_total_bases_alt"

    if re.search(r"\b\d+\s*\+\s*strikeouts?\b", text, flags=re.IGNORECASE):
        return "pitcher_strikeouts_alt"

    # Cross-market text clues.
    if any(token in text for token in ["home run", "home runs", " homer", " hr ", "hrs", "laser"]):
        if original in {"batter_hits", "batter_total_bases"}:
            return "batter_home_runs_alt"
        if original == "batter_home_runs":
            return "batter_home_runs_alt" if is_alt else "batter_home_runs"

    if "total base" in text and original == "batter_hits":
        return "batter_total_bases_alt"

    if "hit" in text and original == "batter_total_bases" and "total base" not in text:
        return "batter_hits_alt"

    # Odds/line clues. These do not discard the row; they move it into an alt board.
    if original == "batter_hits":
        if is_alt or (line_value <= 0.5 and odds > 400) or (line_value >= 1.5 and odds > 900):
            return "batter_hits_alt"

    if original == "batter_total_bases":
        if is_alt or (line_value <= 1.5 and odds > 900):
            return "batter_total_bases_alt"

    if original == "batter_home_runs":
        if is_alt:
            return "batter_home_runs_alt"

    if original in {"batter_rbis", "batter_stolen_bases"}:
        return original

    if original in TEAM_GAME_MARKETS or original in {"team_total_runs", "team_first_to_score"}:
        return original

    if original == "pitcher_strikeouts":
        if is_alt or odds > 900:
            return "pitcher_strikeouts_alt"

    if original == "pitcher_hits_allowed":
        if is_alt or odds > 900:
            return "pitcher_hits_allowed_alt"

    if original == "pitcher_earned_runs":
        if is_alt or odds > 900:
            return "pitcher_earned_runs_alt"

    return original



def normalize_market(value: Any) -> str:
    text = clean(value).lower().replace("_", " ").replace("-", " ")
    text = " ".join(text.split())

    mapping = {
        "hits": "batter_hits",
        "batter hits": "batter_hits",
        "total bases": "batter_total_bases",
        "batter total bases": "batter_total_bases",
        "home run": "batter_home_runs",
        "home runs": "batter_home_runs",
        "batter home run": "batter_home_runs",
        "batter home runs": "batter_home_runs",
        "rbi": "batter_rbis",
        "rbis": "batter_rbis",
        "runs batted in": "batter_rbis",
        "batter rbi": "batter_rbis",
        "batter rbis": "batter_rbis",
        "stolen base": "batter_stolen_bases",
        "stolen bases": "batter_stolen_bases",
        "steals": "batter_stolen_bases",
        "batter stolen bases": "batter_stolen_bases",
        "team total": "team_total_runs",
        "team totals": "team_total_runs",
        "team total runs": "team_total_runs",
        "team runs": "team_total_runs",
        "total runs team": "team_total_runs",
        "first to score": "team_first_to_score",
        "first team to score": "team_first_to_score",
        "team first to score": "team_first_to_score",
        "first score": "team_first_to_score",
        "moneyline": "moneyline",
        "money line": "moneyline",
        "ml": "moneyline",
        "first five moneyline": "moneyline_first_five",
        "moneyline first five": "moneyline_first_five",
        "run line": "run_line",
        "runline": "run_line",
        "spread": "run_line",
        "first five run line": "run_line_first_five",
        "run line first five": "run_line_first_five",
        "first inning run line": "run_line_first_inning",
        "run line first inning": "run_line_first_inning",
        "game total": "game_total_runs",
        "game totals": "game_total_runs",
        "game total runs": "game_total_runs",
        "total runs": "game_total_runs",
        "first five total": "first_five_total_runs",
        "first five total runs": "first_five_total_runs",
        "first inning total": "first_inning_total_runs",
        "first inning total runs": "first_inning_total_runs",
        "strikeouts": "pitcher_strikeouts",
        "pitcher strikeouts": "pitcher_strikeouts",
        "hits allowed": "pitcher_hits_allowed",
        "pitcher hits allowed": "pitcher_hits_allowed",
        "earned runs": "pitcher_earned_runs",
        "pitcher earned runs": "pitcher_earned_runs",
    }

    return mapping.get(text, text.replace(" ", "_"))



def now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()



MLB_TEAM_ABBRS = {
    "ARI", "ATL", "BAL", "BOS", "CHC", "CWS", "CIN", "CLE", "COL", "DET",
    "HOU", "KC", "LAA", "LAD", "MIA", "MIL", "MIN", "NYM", "NYY", "ATH",
    "OAK", "PHI", "PIT", "SD", "SEA", "SF", "STL", "TB", "TEX", "TOR", "WSH",
}

TEAM_ABBR_ALIASES = {
    "SD": "SDP",
    "SF": "SFG",
    "CWS": "CHW",
    "CHW": "CHW",
    "WSH": "WSN",
    "WSN": "WSN",
    "TB": "TBR",
    "TBR": "TBR",
    "KC": "KCR",
    "KCR": "KCR",
    "ATH": "ATH",
    "OAK": "ATH",
}


def canonical_team_abbr(value: Any) -> str:
    text = clean(value).upper()
    return TEAM_ABBR_ALIASES.get(text, text)


def csv_header(path: Path) -> list[str]:
    if not path.exists():
        return []

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            return next(reader, [])
    except Exception:
        return []


def playerboard_value_looks_like_market(value: Any) -> bool:
    text = clean(value)
    if not text:
        return False

    normalized = normalize_market(text)
    if normalized in set(DEFAULT_MARKETS):
        return True

    lower = text.lower()
    return (
        ("ladder" in lower and ("hit" in lower or "base" in lower or "strikeout" in lower))
        or "home runs alt" in lower
        or "batter hits ladder" in lower
    )


def playerboard_row_looks_shifted(row: dict[str, Any]) -> bool:
    """Detect rows where values are shifted into the wrong CSV columns."""
    player = clean(row.get("player"))
    team = clean(row.get("team")).upper()
    opponent = clean(row.get("opponent")).upper()
    line = clean(row.get("line"))
    market = normalize_market(row.get("market"))

    if not player:
        return True

    # Example bad row: player = "Batter Home Runs Alt - 3+ Home Runs"
    if playerboard_value_looks_like_market(player):
        return True

    # Example bad row: team = "BATTER_HOME_RUNS" or market text.
    if playerboard_value_looks_like_market(team):
        return True

    # Example bad row: opponent = "TRUE" because isAltMarket shifted into opponent.
    if opponent in {"TRUE", "FALSE"}:
        return True

    # Example bad row: line accidentally contains team abbreviation.
    if line.upper() in MLB_TEAM_ABBRS:
        return True

    if market and market not in set(DEFAULT_MARKETS):
        # Allow future markets only if they still look namespaced.
        if not (market.startswith("batter_") or market.startswith("pitcher_") or market.startswith("team_") or market.startswith("game_") or market.startswith("first_") or market.startswith("run_line") or market.startswith("moneyline")):
            return True

    return False


def playerboard_schema_issue(path: Path, fieldnames: list[str]) -> str:
    if not path.exists():
        return ""

    header = csv_header(path)
    if header != fieldnames:
        return "header_mismatch"

    if path.name.startswith("playerboard_"):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                for index, row in enumerate(reader):
                    if index >= 100:
                        break
                    if playerboard_row_looks_shifted(row):
                        return "shifted_rows"
        except Exception:
            return "unreadable_rows"

    return ""


def rotate_schema_bad_csv(path: Path, reason: str) -> Path:
    from datetime import datetime, timezone

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rotated = path.with_name(f"{path.stem}.{reason}_{stamp}{path.suffix}")

    counter = 1
    while rotated.exists():
        rotated = path.with_name(f"{path.stem}.{reason}_{stamp}_{counter}{path.suffix}")
        counter += 1

    path.rename(rotated)
    invalidate_path_cache(path)
    invalidate_path_cache(rotated)
    return rotated


def ensure_csv_schema(path: Path, fieldnames: list[str]) -> dict[str, Any]:
    issue = playerboard_schema_issue(path, fieldnames)
    if not issue:
        return {"ok": True, "rotated": False, "reason": ""}

    rotated = rotate_schema_bad_csv(path, issue)
    return {
        "ok": True,
        "rotated": True,
        "reason": issue,
        "rotatedFile": str(rotated),
    }



def append_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ensure_csv_schema(path, fieldnames)
    exists = path.exists()

    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})

    invalidate_path_cache(path)



def write_csv_rows(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    """Rewrite a CSV file with a fixed schema and invalidate local caches."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    invalidate_path_cache(path)

def playerboard_file(season: int) -> Path:
    return PLAYERBOARD_DIR / f"playerboard_{season}.csv"


def file_signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
        return (stat.st_mtime_ns, stat.st_size)
    except OSError:
        return None


def invalidate_path_cache(path: Path) -> None:
    _CSV_CACHE.pop(path, None)
    for key in [key for key in _SAVED_PLAYERBOARD_CACHE if key[4] is None or key[4] != file_signature(path)]:
        _SAVED_PLAYERBOARD_CACHE.pop(key, None)


def prune_playerboard_snapshot(season: int, date_label: str, market: str = "") -> int:
    """Remove existing saved rows for an exact slate before writing fresh rows."""
    path = playerboard_file(season)
    if not path.exists():
        return 0
    target_market = normalize_market(market) if market else ""
    kept: list[dict[str, Any]] = []
    removed = 0
    for row in read_csv_rows(path):
        same_season = not clean(row.get("season")) or int(to_float(row.get("season"))) == int(season)
        same_date = clean(row.get("date")) == clean(date_label)
        same_market = not target_market or normalize_market(row.get("market")) == target_market
        if same_season and same_date and same_market:
            removed += 1
        else:
            kept.append(row)
    if removed:
        write_csv_rows(path, PLAYERBOARD_FIELDS, kept)
    return removed


def save_playerboard_snapshot(season: int, date_label: str, cards: list[dict[str, Any]], *, replace_date: bool = False, market: str = "") -> dict[str, Any]:
    snapshot_at = now_iso()
    rows = []

    for card in cards:
        rows.append({
            "snapshotAt": snapshot_at,
            "season": season,
            "date": date_label,
            "market": clean(card.get("market")),
            "marketDisplay": clean(card.get("marketDisplay")),
            "baseMarket": clean(card.get("baseMarket")),
            "isAltMarket": clean(card.get("isAltMarket")),
            "player": clean(card.get("player")),
            "team": clean(card.get("team")),
            "opponent": clean(card.get("opponent")),
            "pitcher": clean(card.get("pitcher")),
            "line": clean(card.get("line")),
            "americanOdds": clean(card.get("americanOdds")),
            "book": clean(card.get("book")),
            "bookKey": clean(card.get("bookKey")),
            "bookCount": clean(card.get("bookCount")),
            "books": json.dumps(card.get("books") or [], ensure_ascii=False),
            "finalProbabilityPercent": clean(card.get("finalProbabilityPercent")),
            "sportsbookImpliedPercent": clean(card.get("sportsbookImpliedPercent")),
            "finalEdgePercent": clean(card.get("finalEdgePercent")),
            "confidence": clean(card.get("confidence")),
            "recommendation": clean(card.get("recommendation")),
            "weatherAdjustmentPercent": clean(card.get("weatherAdjustmentPercent")),
            "savantAdjustmentPercent": clean(card.get("savantAdjustmentPercent")),
            "oddsMovementAdjustmentPercent": clean(card.get("oddsMovementAdjustmentPercent")),
            "missingData": " | ".join(clean(x) for x in (card.get("missingData") or [])),
            "originalMarket": clean(card.get("originalMarket")),
            "rawLabel": clean(card.get("rawLabel")),
            "marketFamily": clean(card.get("marketFamily")),
            "hitRates": json.dumps(card.get("hitRates") or {}, ensure_ascii=False),
            "recentGames": json.dumps(card.get("recentGames") or [], ensure_ascii=False),
        })

    removedRows = prune_playerboard_snapshot(season, date_label, market=market) if replace_date else 0
    append_csv(playerboard_file(season), PLAYERBOARD_FIELDS, rows)

    return {
        "snapshotAt": snapshot_at,
        "rowsSaved": len(rows),
        "removedRows": removedRows,
        "replaceDate": bool(replace_date),
        "sourceMode": "canonical" if canonical_prop_files(date_label) else "legacy",
        "file": str(playerboard_file(season)),
    }


def missing_data_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [clean(item) for item in value if clean(item)]
    return [item.strip() for item in clean(value).split("|") if item.strip()]


def rank_value(card: dict[str, Any]) -> tuple[float, float]:
    edge = to_float(card.get("finalEdgePercent"))
    prob = to_float(card.get("finalProbabilityPercent"))
    return (edge, prob)


def parse_json_field(value: Any, default: Any) -> Any:
    text = clean(value)
    if not text:
        return copy.deepcopy(default)
    try:
        return json.loads(text)
    except Exception:
        return copy.deepcopy(default)


def saved_card_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "player": clean(row.get("player")),
        "market": normalize_market(row.get("market")),
        "marketDisplay": clean(row.get("marketDisplay")) or market_display_label(row.get("market"), row.get("rawLabel")),
        "baseMarket": clean(row.get("baseMarket")) or base_market(row.get("market")),
        "isAltMarket": clean(row.get("isAltMarket")) or str(clean(row.get("market")).endswith("_alt")),
        "team": clean(row.get("team")).upper(),
        "opponent": clean(row.get("opponent")).upper(),
        "pitcher": clean(row.get("pitcher")),
        "line": clean(row.get("line")),
        "americanOdds": clean(row.get("americanOdds")),
        "book": clean(row.get("book")),
        "bookKey": clean(row.get("bookKey")),
        "bookCount": to_float(row.get("bookCount"), 0),
        "books": parse_json_field(row.get("books"), []),
        "finalProbabilityPercent": clean(row.get("finalProbabilityPercent")),
        "sportsbookImpliedPercent": clean(row.get("sportsbookImpliedPercent")),
        "finalEdgePercent": clean(row.get("finalEdgePercent")),
        "confidence": clean(row.get("confidence")),
        "recommendation": clean(row.get("recommendation")),
        "weatherAdjustmentPercent": clean(row.get("weatherAdjustmentPercent")),
        "savantAdjustmentPercent": clean(row.get("savantAdjustmentPercent")),
        "oddsMovementAdjustmentPercent": clean(row.get("oddsMovementAdjustmentPercent")),
        "missingData": missing_data_list(row.get("missingData")),
        "originalMarket": clean(row.get("originalMarket")),
        "rawLabel": clean(row.get("rawLabel")),
        "marketFamily": clean(row.get("marketFamily")) or market_family(row.get("market")),
        "hitRates": parse_json_field(row.get("hitRates"), {}),
        "recentGames": parse_json_field(row.get("recentGames"), []),
    }


def load_saved_playerboard(season: int = 2026, date_label: str = "", market: str = "", limit: int = 5000) -> dict[str, Any]:
    """Return the latest saved Playerboard snapshot without rebuilding model cards."""
    path = playerboard_file(season)
    target_market = normalize_market(market) if market else ""
    target_date = clean(date_label)
    signature = file_signature(path)
    cache_key = (season, target_date, target_market, limit, signature)
    if cache_key in _SAVED_PLAYERBOARD_CACHE:
        return copy.deepcopy(_SAVED_PLAYERBOARD_CACHE[cache_key])

    rows = read_csv_rows(path)

    filtered = []
    for row in rows:
        if clean(row.get("season")) and int(to_float(row.get("season"))) != int(season):
            continue
        if target_date and clean(row.get("date")) != target_date:
            continue
        if target_market and normalize_market(row.get("market")) != target_market:
            continue
        if not clean(row.get("snapshotAt")):
            continue
        filtered.append(row)

    if not filtered:
        payload = {
            "season": season,
            "date": date_label,
            "market": market,
            "propsLoaded": 0,
            "cardsBuilt": 0,
            "errors": [],
            "saved": None,
            "top": [],
            "source": "saved_playerboard",
            "cacheHit": False,
            "message": f"No saved Playerboard snapshot found for {date_label or 'latest date'}. Run the scheduled collector or request refresh=1 to rebuild.",
        }
        _SAVED_PLAYERBOARD_CACHE[cache_key] = payload
        return copy.deepcopy(payload)

    if target_market:
        latest_snapshot = max(clean(row.get("snapshotAt")) for row in filtered)
        latest_rows = [row for row in filtered if clean(row.get("snapshotAt")) == latest_snapshot]
        snapshots_used = [latest_snapshot]
    else:
        latest_rows = []
        snapshots_used = []
        by_market: dict[str, list[dict[str, str]]] = {}
        for row in filtered:
            by_market.setdefault(normalize_market(row.get("market")), []).append(row)
        for market_rows in by_market.values():
            latest_for_market = max(clean(row.get("snapshotAt")) for row in market_rows)
            snapshots_used.append(latest_for_market)
            latest_rows.extend(row for row in market_rows if clean(row.get("snapshotAt")) == latest_for_market)

        latest_snapshot = max(snapshots_used) if snapshots_used else ""

    deduped = []
    seen = set()
    for row in latest_rows:
        card = saved_card_from_row(row)
        key = (
            clean(card.get("market")),
            clean(card.get("player")).lower(),
            clean(card.get("team")).upper(),
            clean(card.get("opponent")).upper(),
            clean(card.get("pitcher")).lower(),
            clean(card.get("line")),
            clean(card.get("americanOdds")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(card)

    cards = sorted(deduped, key=rank_value, reverse=True)
    top_cards = cards[:limit]

    payload = {
        "season": season,
        "date": date_label or clean(latest_rows[0].get("date")),
        "market": market,
        "propsLoaded": len(latest_rows),
        "cardsBuilt": len(cards),
        "errors": [],
        "saved": {
            "source": "saved_playerboard",
            "snapshotAt": latest_snapshot,
            "snapshotsUsed": sorted(set(snapshots_used)),
            "rowsLoaded": len(top_cards),
            "file": str(path),
        },
        "top": top_cards,
        "source": "saved_playerboard",
        "cacheHit": True,
        "message": "Loaded latest saved Playerboard snapshot.",
    }
    _SAVED_PLAYERBOARD_CACHE[cache_key] = payload
    return copy.deepcopy(payload)



def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    signature = file_signature(path)
    if signature:
        cached = _CSV_CACHE.get(path)
        if cached and cached[0] == signature:
            return cached[1]
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if signature:
        _CSV_CACHE[path] = (signature, rows)
    return rows


def first_value(row: dict[str, Any], names: list[str]) -> str:
    lower = {clean(k).lower(): v for k, v in row.items()}
    for name in names:
        key = clean(name).lower()
        if key in lower and clean(lower[key]):
            return clean(lower[key])
    return ""



def is_ignored_prop_source(path: Path) -> bool:
    """Skip local backup/debug files so old bad rows do not enter Playerboard."""
    name = path.name.lower()
    full = str(path).lower()

    ignored_tokens = [
        ".before_",
        "before_quality_cleanup",
        "before_odds_cleanup",
        "debug_",
        ".backup",
        ".bak",
    ]

    return any(token in name or token in full for token in ignored_tokens)


def canonical_prop_files(date_label: str) -> list[Path]:
    """Return exact-date PropLine exports used as the trusted props source.

    Old prototype folders can contain stale all_props/prop_snapshots files. Once
    a canonical data/odds/propline_props_YYYY-MM-DD.csv exists, Playerboard
    should not silently blend those legacy files into the same slate.
    """
    files: list[Path] = []
    direct = ROOT / "data" / "odds" / f"propline_props_{date_label}.csv"
    if direct.exists():
        files.append(direct)

    snapshot_root = ROOT / "data" / "warehouse" / "odds_snapshots"
    if snapshot_root.exists():
        files.extend(sorted(snapshot_root.glob(f"propline_props_{date_label}_*.csv")))

    unique: list[Path] = []
    seen: set[str] = set()
    for path in files:
        key = str(path.resolve())
        if key not in seen and not is_ignored_prop_source(path):
            seen.add(key)
            unique.append(path)
    return unique


def saved_prop_files(date_label: str, source_mode: str = "auto") -> list[Path]:
    mode = clean(source_mode).lower() or "auto"
    canonical = canonical_prop_files(date_label)
    if mode in {"canonical", "propline"}:
        return canonical
    if mode == "auto" and canonical:
        return canonical

    candidates = []

    for root in ODDS_DIRS:
        if not root.exists():
            continue

        patterns = [
            f"*{date_label}*.csv",
            "all_props.csv",
            "prop_snapshots_*.csv",
        ]

        for pattern in patterns:
            candidates.extend(root.rglob(pattern))

    # Prefer data/odds direct PropLine exports, then snapshots.
    unique = []
    seen = set()
    for path in sorted(candidates, key=lambda p: (0 if "data\\odds" in str(p) or "data/odds" in str(p) else 1, str(p))):
        if is_ignored_prop_source(path):
            continue

        key = str(path.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(path)

    return unique



def is_plausible_market_odds(market: str, line: Any, american_odds: Any) -> bool:
    """Reject obvious market/odds mismatches.

    Example: +5100 is plausible for a HR prop, but not for over 0.5 batter hits.
    This protects Playerboard/backtests from source parsing errors.
    """
    market = clean(market)
    odds = to_float(american_odds)
    line_value = to_float(line)

    if not odds:
        return False

    abs_odds = abs(odds)

    # Alt/ladder markets can legitimately have long odds.
    if market.endswith("_alt"):
        return abs_odds <= 20000

    # Standard markets stay cleaner.
    if market != "batter_home_runs" and abs_odds > 2000:
        return False

    if market == "batter_hits" and line_value <= 0.5 and odds > 400:
        return False

    if market == "batter_total_bases" and line_value <= 1.5 and odds > 900:
        return False

    if market.startswith("pitcher_") and abs_odds > 1500:
        return False

    return True



def normalize_prop_row(row: dict[str, Any], date_label: str) -> dict[str, Any]:
    original_market = first_value(row, [
        "market", "prop_market", "market_key", "marketKey", "type", "target",
        "stat", "category", "bet_type", "betType", "propType", "prop_type"
    ])
    market = normalize_market(original_market)

    player = first_value(row, [
        "player", "playerName", "player_name", "name", "description",
        "participant", "athlete", "batter", "pitcher_name", "selection"
    ])

    label = first_value(row, ["side", "label", "title", "outcome", "outcome_name", "selection", "description"])
    if not player and label:
        player = label.split(" Over ")[0].split(" Under ")[0].strip()

    lower_player = player.lower()
    if " over " in lower_player:
        player = player[:lower_player.index(" over ")].strip()
    elif " under " in lower_player:
        player = player[:lower_player.index(" under ")].strip()

    team = canonical_team_abbr(first_value(row, [
        "team", "teamAbbr", "team_abbr", "team_abbreviation",
        "playerTeam", "player_team", "home_team", "home"
    ]))

    opponent = canonical_team_abbr(first_value(row, [
        "opponent", "opp", "opponentAbbr", "opponent_abbr",
        "opponent_abbreviation", "away_team", "away"
    ]))

    pitcher = first_value(row, [
        "pitcher", "opposingPitcher", "opposing_pitcher",
        "probablePitcher", "probable_pitcher", "starter"
    ])

    line = first_value(row, [
        "line", "point", "points", "handicap", "value",
        "over_line", "overLine", "prop_line", "latestLine"
    ])

    odds = first_value(row, [
        "americanOdds", "american_odds", "odds", "price",
        "overOdds", "over_odds", "overPrice", "over_price",
        "american", "american_price", "latestAmericanOdds"
    ])

    if not clean(line) and clean(label):
        ladder_line, ladder_label = parse_ladder_side(label)
        if ladder_line:
            line = ladder_line
            label = ladder_label

    # PropLine stores the real local slate date in eventDateLocal while date/commenceTime
    # can be UTC (for example 2026-05-07T01:20:00Z for a 2026-05-06 ET slate).
    # Playerboard must use the local slate date or late games disappear from the UI.
    row_date = first_value(row, [
        "eventDateLocal", "event_date_local", "localDate", "local_date",
        "date", "game_date", "gameDate", "start_date", "commence_time", "commenceTime"
    ]) or date_label

    home_team = first_value(row, ["homeTeam", "home_team", "home"])
    away_team = first_value(row, ["awayTeam", "away_team", "away"])
    game_text = first_value(row, ["game", "matchup", "event", "eventName"])

    market = classify_prop_market(market, label, line, odds)

    return {
        "date": row_date,
        "game": game_text,
        "homeTeam": home_team,
        "awayTeam": away_team,
        "market": market,
        "marketDisplay": market_display_label(market, label),
        "originalMarket": original_market,
        "rawLabel": label,
        "marketFamily": market_family(market),
        "player": player,
        "team": team,
        "opponent": opponent,
        "pitcher": pitcher,
        "line": line,
        "americanOdds": odds,
        "book": first_value(row, ["book", "bookmaker", "sportsbook", "book_title", "sourceBook"]),
        "bookKey": first_value(row, ["bookKey", "book_key", "bookmakerKey", "sportsbookKey"]),
        "lastUpdate": first_value(row, ["lastUpdate", "last_update", "updatedAt", "snapshotAt"]),
    }


def side_for_prop(row: dict[str, Any]) -> str:
    """Return a normalized betting side for grouping/display.

    PropLine sometimes returns player name or "Yes" as the outcome name instead
    of literal Over/Under. For player/stat props, those are Over-side prices.
    "No" and explicit Under stay under.
    """
    label = clean(row.get("rawLabel") or row.get("side") or row.get("outcome")).casefold()
    player = clean(row.get("player")).casefold()
    market = normalize_market(row.get("market"))

    if "under" in label or label in {"no", "n"}:
        return "under"
    if "over" in label or label in {"yes", "y"}:
        return "over"
    if re.search(r"\b\d+\s*\+", label):
        return "over"
    if player and player in label:
        return "over"
    if market.startswith(("batter_", "pitcher_")):
        return "over"
    return label or "over"


def display_side_for_prop(row: dict[str, Any]) -> str:
    side = side_for_prop(row)
    if side == "under":
        return "Under"
    if side == "over":
        return "Over"
    return clean(row.get("rawLabel")) or side.title()


def canonical_prop_line(row: dict[str, Any]) -> str:
    parsed = to_float(row.get("line"), None)
    if parsed is None:
        return clean(row.get("line"))
    return f"{parsed:g}"


def book_price_row(row: dict[str, Any]) -> dict[str, Any]:
    odds = clean(row.get("americanOdds"))
    return {
        "book": clean(row.get("book")) or "Book",
        "bookKey": clean(row.get("bookKey")),
        "americanOdds": odds,
        "impliedProbabilityPercent": round(american_implied_percent(odds), 2) if odds else "",
        "lastUpdate": clean(row.get("lastUpdate")),
        "rawSource": clean(row.get("rawSource")),
    }


def odds_sort_value(value: Any) -> float:
    parsed = to_float(value, None)
    return parsed if parsed is not None else -999999.0


def aggregate_book_prices(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse multi-book duplicates into one board row per prop identity.

    Identity intentionally excludes sportsbook/odds. The selected row carries the
    best available American odds and a `books` ladder for detail views.
    """
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in rows:
        key = (
            clean(row.get("date"))[:10],
            normalize_market(row.get("market")),
            clean(row.get("player")).casefold(),
            canonical_team_abbr(row.get("team")),
            canonical_team_abbr(row.get("opponent")),
            clean(row.get("pitcher")).casefold(),
            canonical_prop_line(row),
            side_for_prop(row),
        )
        groups.setdefault(key, []).append(row)

    collapsed: list[dict[str, Any]] = []
    for items in groups.values():
        by_book: dict[str, dict[str, Any]] = {}
        for item in items:
            book_key = clean(item.get("bookKey") or item.get("book") or item.get("rawSource") or "book").casefold()
            existing = by_book.get(book_key)
            # Keep the best price per book if duplicate snapshots leak into the source.
            if existing is None or odds_sort_value(item.get("americanOdds")) > odds_sort_value(existing.get("americanOdds")):
                by_book[book_key] = item

        unique_items = list(by_book.values())
        unique_items.sort(key=lambda item: odds_sort_value(item.get("americanOdds")), reverse=True)
        best = dict(unique_items[0])
        books = [book_price_row(item) for item in unique_items]
        best["americanOdds"] = clean(unique_items[0].get("americanOdds"))
        best["book"] = clean(unique_items[0].get("book")) or "Best available"
        best["bookKey"] = clean(unique_items[0].get("bookKey"))
        best["bookCount"] = len(books)
        best["books"] = books
        best["rawLabel"] = display_side_for_prop(best)
        best["line"] = canonical_prop_line(best) or clean(best.get("line"))
        collapsed.append(best)

    return collapsed


def load_saved_props(date_label: str, markets: list[str] | None = None, limit: int = 5000, source_mode: str = "auto") -> list[dict[str, Any]]:
    market_set = {normalize_market(m) for m in (markets or DEFAULT_MARKETS)}
    rows = []

    for path in saved_prop_files(date_label, source_mode=source_mode):
        for raw in read_csv_rows(path):
            prop = normalize_prop_row(raw, date_label)

            if not prop.get("player") or not prop.get("market"):
                continue

            if prop["market"] not in market_set:
                continue

            # Some snapshot rows use exact timestamp date. Keep only relevant date prefix when possible.
            if date_label and clean(prop.get("date")) and not clean(prop.get("date")).startswith(date_label):
                continue

            if not is_plausible_market_odds(
                prop.get("market"),
                prop.get("line"),
                prop.get("americanOdds"),
            ):
                continue

            prop["rawSource"] = str(path)
            rows.append(prop)

    # OddsPapi game/team markets use the same normalized prop shape.
    # They are cached in data/cache/oddspapi as latest-pregame rows.
    rows.extend(load_oddspapi_game_market_props(date_label, market_set, limit=limit))

    out = aggregate_book_prices(rows)
    return out[:limit]


def infer_missing_context(prop: dict[str, Any], season: int) -> dict[str, Any]:
    """Use player_autofill to fill team/opponent/pitcher if the prop source omitted them."""
    if prop.get("team") and prop.get("opponent"):
        return prop

    try:
        from player_autofill import autofill_player

        role = "pitcher" if clean(prop.get("market")).startswith("pitcher") else "team" if clean(prop.get("market")).startswith("team") else "batter"
        filled = autofill_player(season, clean(prop.get("date"))[:10], clean(prop.get("player")), role)

        if filled.get("foundGame"):
            prop["team"] = canonical_team_abbr(prop.get("team") or filled.get("team", ""))
            prop["opponent"] = canonical_team_abbr(prop.get("opponent") or filled.get("opponent", ""))
            prop["pitcher"] = prop.get("pitcher") or filled.get("pitcher", "")

    except Exception:
        pass

    return prop



def team_game_prop_to_playerboard_card(prop: dict[str, Any]) -> dict[str, Any]:
    """Convert a normalized OddsPapi team/game market row directly into a Playerboard card.

    If a trained model exists, use projected probability and edge.
    If no model exists yet, still show the odds row as an odds-only card.
    """
    implied = to_float(prop.get("sportsbookImpliedProbability")) * 100.0

    has_projection = clean(prop.get("projectedProbability")) != ""
    if has_projection:
        projected = to_float(prop.get("projectedProbability")) * 100.0
        edge = to_float(prop.get("finalEdgePercent") or prop.get("edgePercent"))
        confidence = clean(prop.get("confidence")) or "Unavailable"
        recommendation = "Positive edge" if edge > 0 else "Negative edge"
        missing_data = [] if prop.get("modelAvailable") else ["Team/game model artifact unavailable"]
    else:
        projected = implied
        edge = 0.0
        confidence = "Unmodeled"
        recommendation = "Odds only"
        missing_data = ["No trained model for this market yet"]

    return {
        "player": clean(prop.get("player")),
        "market": normalize_market(prop.get("market")),
        "marketDisplay": clean(prop.get("marketDisplay")) or market_display_label(prop.get("market"), prop.get("rawLabel")),
        "baseMarket": base_market(prop.get("market")),
        "isAltMarket": "False",
        "team": canonical_team_abbr(prop.get("team")),
        "opponent": canonical_team_abbr(prop.get("opponent")),
        "pitcher": clean(prop.get("pitcher")),
        "line": clean(prop.get("line")),
        "americanOdds": clean(prop.get("americanOdds")),
        "finalProbabilityPercent": round(projected, 2),
        "sportsbookImpliedPercent": round(implied, 2),
        "finalEdgePercent": round(edge, 2),
        "confidence": confidence,
        "recommendation": recommendation,
        "weatherAdjustmentPercent": "",
        "savantAdjustmentPercent": "",
        "oddsMovementAdjustmentPercent": "",
        "missingData": missing_data,
        "originalMarket": clean(prop.get("originalMarket")),
        "rawLabel": clean(prop.get("rawLabel")),
        "marketFamily": clean(prop.get("marketFamily")) or market_family(prop.get("market")),
        "book": clean(prop.get("book") or prop.get("bookmaker")),
        "bookKey": clean(prop.get("bookKey")),
        "bookCount": prop.get("bookCount") or len(prop.get("books") or []),
        "books": prop.get("books") or [],
        "bookmaker": clean(prop.get("bookmaker")),
        "fixtureId": clean(prop.get("fixtureId")),
        "modelName": clean(prop.get("modelName")),
        "modelAvailable": bool(prop.get("modelAvailable")),
        "rawSource": clean(prop.get("rawSource")),
    }


def team_game_market_display_allowed(prop: dict[str, Any]) -> bool:
    """Filter extreme alternate team/game lines out of the default Playerboard.

    OddsPapi can provide many alternate lines. We still collect them upstream,
    but default Playerboard rankings should focus on practical/displayable lines
    so extreme longshot alts do not dominate the top edge list.
    """
    market = normalize_market(prop.get("market"))
    try:
        line = float(clean(prop.get("line")) or 0)
    except Exception:
        line = 0.0

    try:
        odds = float(clean(prop.get("americanOdds") or prop.get("american_odds")) or 0)
    except Exception:
        odds = 0.0

    abs_odds = abs(odds)

    # Remove stale/extreme odds from default board.
    if abs_odds > 2000:
        return False

    if market in {"run_line", "run_line_first_five", "run_line_first_inning"}:
        return -2.5 <= line <= 2.5

    if market == "game_total_runs":
        return 4.5 <= line <= 13.5

    if market == "first_five_total_runs":
        return 1.5 <= line <= 8.5

    if market == "first_inning_total_runs":
        return 0.5 <= line <= 3.5

    if market == "team_total_runs":
        return 0.5 <= line <= 9.5

    return True


def can_use_direct_team_game_card(prop: dict[str, Any]) -> bool:
    market = normalize_market(prop.get("market"))
    if market not in TEAM_GAME_MARKETS:
        return False

    # OddsPapi team/game rows should render even before a model exists.
    # Modeled markets carry projectedProbability/edge; unmodeled markets render as odds-only.
    return clean(prop.get("americanOdds")) != ""


def american_implied_percent(value: Any) -> float:
    odds = to_float(value)
    if odds == 0:
        return 50.0
    if odds > 0:
        return 100.0 / (odds + 100.0) * 100.0
    return abs(odds) / (abs(odds) + 100.0) * 100.0


def game_context_from_prop(prop: dict[str, Any]) -> tuple[str, str, str]:
    """Return fallback team/opponent/game text when PropLine omits player team.

    This is display-safe: we mark the resulting card as odds-only instead of
    pretending the model knows the player's actual side.
    """
    team = clean(prop.get("team")).upper()
    opponent = clean(prop.get("opponent")).upper()
    home = clean(prop.get("homeTeam"))
    away = clean(prop.get("awayTeam"))
    game = clean(prop.get("game"))

    if team and opponent:
        return team, opponent, game

    if away and home:
        return away.upper(), home.upper(), game or f"{away} @ {home}"

    if game and " @ " in game:
        away_text, home_text = [part.strip() for part in game.split(" @ ", 1)]
        return away_text.upper(), home_text.upper(), game

    return team, opponent, game


def odds_only_player_card(prop: dict[str, Any]) -> dict[str, Any]:
    team, opponent, game = game_context_from_prop(prop)
    implied = american_implied_percent(prop.get("americanOdds"))
    missing = [
        "PropLine did not provide player team/opponent, so this row is shown as odds-only.",
        "Fill/verify team context before relying on model probability.",
    ]
    if game:
        missing.append(f"Game: {game}")

    return {
        "player": clean(prop.get("player")),
        "market": normalize_market(prop.get("market")),
        "marketDisplay": clean(prop.get("marketDisplay")) or market_display_label(prop.get("market"), prop.get("rawLabel")),
        "baseMarket": base_market(prop.get("market")),
        "isAltMarket": str(clean(prop.get("market")).endswith("_alt")),
        "team": team,
        "opponent": opponent,
        "pitcher": clean(prop.get("pitcher")),
        "line": clean(prop.get("line")) or "0.5",
        "americanOdds": clean(prop.get("americanOdds")),
        "finalProbabilityPercent": round(implied, 2),
        "sportsbookImpliedPercent": round(implied, 2),
        "finalEdgePercent": 0.0,
        "confidence": "Odds only",
        "recommendation": "Needs team context",
        "weatherAdjustmentPercent": "",
        "savantAdjustmentPercent": "",
        "oddsMovementAdjustmentPercent": "",
        "missingData": missing,
        "originalMarket": clean(prop.get("originalMarket")),
        "rawLabel": clean(prop.get("rawLabel")),
        "marketFamily": clean(prop.get("marketFamily")) or market_family(prop.get("market")),
        "book": clean(prop.get("book")),
        "bookKey": clean(prop.get("bookKey")),
        "bookCount": prop.get("bookCount") or len(prop.get("books") or []),
        "books": prop.get("books") or [],
    }


def build_playerboard(season: int = 2026, date_label: str = "", market: str = "", limit: int = 5000, save: bool = True, replace_date: bool = False, source_mode: str = "auto") -> dict[str, Any]:
    from unified_prop_card import unified_prop_card

    markets = [market] if market else DEFAULT_MARKETS
    props = load_saved_props(date_label, markets=markets, limit=5000, source_mode=source_mode)

    cards = []
    errors = []

    def attach_hit_profile(card: dict[str, Any], row_for_profile: dict[str, Any]) -> dict[str, Any]:
        try:
            from player_hit_rates import hit_profile_for_row, parse_date
            profile = hit_profile_for_row(row_for_profile, season, parse_date(clean(row_for_profile.get("date"))[:10] or date_label))
            card["hitRates"] = {
                "L5": profile.get("L5"),
                "L10": profile.get("L10"),
                "L20": profile.get("L20"),
                "H2H": profile.get("H2H"),
                "season": profile.get("season"),
                "prevSeason": profile.get("prevSeason"),
                "sourceStatus": profile.get("sourceStatus"),
            }
            card["recentGames"] = profile.get("recentGames") or []
        except Exception as error:
            card["hitRates"] = {"sourceStatus": "error", "error": str(error)}
            card["recentGames"] = []
        return card

    def build_card(prop: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
        prop = infer_missing_context(prop, season)

        if can_use_direct_team_game_card(prop):
            if not team_game_market_display_allowed(prop):
                return None, "extreme_alt_line_filtered"
            card = team_game_prop_to_playerboard_card(prop)
            return attach_hit_profile(card, {**prop, **card, "date": clean(prop.get("date"))[:10] or date_label}), None

        if not prop.get("team") or not prop.get("opponent"):
            if clean(prop.get("americanOdds")):
                card = odds_only_player_card(prop)
                return attach_hit_profile(card, {**prop, **card, "date": clean(prop.get("date"))[:10] or date_label}), None
            return None, None

        row = {
            "season": season,
            "date": clean(prop.get("date"))[:10] or date_label,
            "market": clean(prop.get("market")),
            "marketDisplay": clean(prop.get("marketDisplay")),
            "player": clean(prop.get("player")),
            "team": clean(prop.get("team")),
            "opponent": clean(prop.get("opponent")),
            "pitcher": clean(prop.get("pitcher")),
            "line": clean(prop.get("line")) or "0.5",
            "american_odds": clean(prop.get("americanOdds")) or "-110",
            "originalMarket": clean(prop.get("originalMarket")),
            "rawLabel": clean(prop.get("rawLabel")),
            "marketFamily": clean(prop.get("marketFamily")) or market_family(prop.get("market")),
        }

        try:
            card = unified_prop_card(row)
            out = {
                "player": card.get("player"),
                "market": card.get("market"),
                "marketDisplay": clean(prop.get("marketDisplay")) or market_display_label(card.get("market"), prop.get("rawLabel")),
                "baseMarket": card.get("baseMarket"),
                "isAltMarket": card.get("isAltMarket"),
                "team": card.get("team"),
                "opponent": card.get("opponent"),
                "pitcher": card.get("pitcher"),
                "line": card.get("line"),
                "americanOdds": card.get("americanOdds"),
                "finalProbabilityPercent": card.get("finalProbabilityPercent"),
                "sportsbookImpliedPercent": card.get("sportsbookImpliedPercent"),
                "finalEdgePercent": card.get("finalEdgePercent"),
                "confidence": card.get("confidence"),
                "recommendation": card.get("recommendation"),
                "weatherAdjustmentPercent": card.get("weatherAdjustmentPercent"),
                "savantAdjustmentPercent": card.get("savantAdjustmentPercent"),
                "oddsMovementAdjustmentPercent": card.get("oddsMovementAdjustmentPercent"),
                "missingData": card.get("missingData", []),
                "originalMarket": clean(prop.get("originalMarket")),
                "rawLabel": clean(prop.get("rawLabel")),
                "marketFamily": clean(prop.get("marketFamily")) or market_family(prop.get("market")),
                "book": clean(prop.get("book")),
                "bookKey": clean(prop.get("bookKey")),
                "bookCount": prop.get("bookCount") or len(prop.get("books") or []),
                "books": prop.get("books") or [],
            }
            return attach_hit_profile(out, row), None
        except Exception as error:
            return None, {
                "player": row["player"],
                "market": row["market"],
                "error": str(error),
            }

    max_workers = min(12, max(2, (os.cpu_count() or 4)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(build_card, prop) for prop in props]
        for future in as_completed(futures):
            card, error = future.result()
            if card:
                cards.append(card)
            if error:
                errors.append(error)

    # Final aggregation after context inference/model card creation.
    # This collapses remaining book/alias duplicates into one clean prop card.
    cards = sorted(aggregate_book_prices(cards), key=rank_value, reverse=True)

    top_cards = cards[:limit]
    saved = save_playerboard_snapshot(season, date_label, top_cards, replace_date=replace_date, market=market) if save and top_cards else None

    return {
        "season": season,
        "date": date_label,
        "market": market,
        "propsLoaded": len(props),
        "cardsBuilt": len(cards),
        "errors": errors[:10],
        "saved": saved,
        "sourceMode": source_mode,
        "canonicalSourceFiles": [str(path) for path in canonical_prop_files(date_label)],
        "top": top_cards,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build playerboard from saved PropLine props.")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--date", required=True)
    parser.add_argument("--market", default="")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()

    print(json.dumps(
        build_playerboard(
            args.season,
            args.date,
            args.market,
            args.limit,
            save=not args.no_save,
        ),
        indent=2
    ))


if __name__ == "__main__":
    main()
