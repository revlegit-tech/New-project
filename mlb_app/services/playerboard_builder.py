from __future__ import annotations

import argparse
import copy
import importlib
import os
import re
import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from mlb_app.config import settings as default_settings
from mlb_app.contracts.playerboard_schema import (
    PLAYERBOARD_FIELDS,
    PLAYERBOARD_SCHEMA_VERSION,
    normalize_playerboard_row,
    validate_playerboard_header,
)

from mlb_app.domain.team_game_markets import TEAM_GAME_MARKETS, TEAM_GAME_MARKET_LABELS, load_oddspapi_game_market_props

ROOT = default_settings.root_dir
PLAYERBOARD_DIR = default_settings.data_dir / "playerboard"

_CSV_CACHE: dict[Path, tuple[tuple[int, int], list[dict[str, str]]]] = {}
_SAVED_PLAYERBOARD_CACHE: dict[tuple[int, str, str, int, tuple[int, int] | None], dict[str, Any]] = {}

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

MARKET_CAPABILITY_MAP = {
    "batter_hits": "model_supported",
    "batter_hits_alt": "research_only",
    "batter_total_bases": "model_supported",
    "batter_total_bases_alt": "research_only",
    "batter_home_runs": "research_only",
    "batter_home_runs_alt": "research_only",
    "batter_rbis": "research_only",
    "batter_stolen_bases": "unsupported_skip",
    "pitcher_strikeouts": "model_supported",
    "pitcher_strikeouts_alt": "research_only",
    "pitcher_hits_allowed": "research_only",
    "pitcher_hits_allowed_alt": "research_only",
    "pitcher_earned_runs": "research_only",
    "pitcher_earned_runs_alt": "research_only",
    "team_total_runs": "research_only",
    "team_first_to_score": "research_only",
    "moneyline": "research_only",
    "moneyline_first_five": "research_only",
    "run_line": "research_only",
    "run_line_first_five": "research_only",
    "run_line_first_inning": "research_only",
    "run_line_second_inning": "research_only",
    "run_line_third_inning": "research_only",
    "run_line_fourth_inning": "research_only",
    "run_line_fifth_inning": "research_only",
    "run_line_sixth_inning": "research_only",
    "run_line_seventh_inning": "research_only",
    "run_line_eighth_inning": "research_only",
    "run_line_ninth_inning": "research_only",
    "game_total_runs": "research_only",
    "first_five_total_runs": "research_only",
    "first_inning_total_runs": "research_only",
    "second_inning_total_runs": "research_only",
    "third_inning_total_runs": "research_only",
    "fourth_inning_total_runs": "research_only",
    "fifth_inning_total_runs": "research_only",
    "sixth_inning_total_runs": "research_only",
    "seventh_inning_total_runs": "research_only",
    "eighth_inning_total_runs": "research_only",
    "ninth_inning_total_runs": "research_only",
}


def market_capability(market: Any) -> str:
    return MARKET_CAPABILITY_MAP.get(normalize_market(market), "unsupported_skip")


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
    """Return a structured schema issue code for a saved playerboard CSV.

    Known legacy schemas are accepted because they can be normalized by the
    contract layer. Unknown/destructive schemas are reported as actionable
    errors instead of being silently accepted by the app runtime.
    """
    if not path.exists():
        return ""

    header = csv_header(path)
    validation = validate_playerboard_header(header)
    if not validation.ok:
        return validation.reason or "schema_invalid"

    if path.name.startswith("playerboard_"):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                for index, row in enumerate(reader):
                    if index >= 100:
                        break
                    normalized = normalize_playerboard_row(row)
                    if playerboard_row_looks_shifted(normalized):
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
    """Ensure a writable CSV uses the current playerboard contract.

    Safe legacy column sets are upgraded in place. Destructive or unknown
    schemas are still rotated before writing so pipeline writes remain safe.
    """
    if not path.exists():
        return {"ok": True, "rotated": False, "reason": "", "schemaVersion": PLAYERBOARD_SCHEMA_VERSION}

    header = csv_header(path)
    if header == fieldnames:
        return {"ok": True, "rotated": False, "reason": "", "schemaVersion": PLAYERBOARD_SCHEMA_VERSION}

    validation = validate_playerboard_header(header)
    if validation.ok:
        existing = [normalize_playerboard_row(row) for row in read_csv_rows(path)]
        write_csv_rows(path, fieldnames, existing)
        return {
            "ok": True,
            "rotated": False,
            "migrated": True,
            "reason": "known_legacy_schema_migrated",
            "schemaVersion": PLAYERBOARD_SCHEMA_VERSION,
            "previousSchemaVersion": validation.version,
            "warnings": validation.warnings,
        }

    rotated = rotate_schema_bad_csv(path, validation.reason or "schema_invalid")
    return {
        "ok": True,
        "rotated": True,
        "reason": validation.reason or "schema_invalid",
        "rotatedFile": str(rotated),
        "schemaVersion": PLAYERBOARD_SCHEMA_VERSION,
        "schemaError": validation.to_dict(),
    }


def _csv_contract_value(field: str, value: Any) -> Any:
    if field in {"books", "missingData", "hitRates", "recentGames"}:
        if isinstance(value, str):
            return value
        return json.dumps(value or [], ensure_ascii=False)
    if value is None:
        return ""
    return value


def _csv_contract_row(row: dict[str, Any], fieldnames: list[str]) -> dict[str, Any]:
    return {field: _csv_contract_value(field, row.get(field, "")) for field in fieldnames}


def append_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ensure_csv_schema(path, fieldnames)
    exists = path.exists()

    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(_csv_contract_row(row, fieldnames))

    invalidate_path_cache(path)



def write_csv_rows(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    """Rewrite a CSV file with a fixed schema and invalidate local caches."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(_csv_contract_row(row, fieldnames))
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

    snapshot_repository = None
    activated_snapshot_id = ""
    db_write_error = ""
    source_mode = "canonical" if canonical_prop_files(date_label) else "legacy"
    csv_path = playerboard_file(season)

    try:
        from mlb_app.repositories.board_snapshot_repository import BoardSnapshotRepository

        snapshot_repository = BoardSnapshotRepository(default_settings)
        activated = snapshot_repository.replace_active_snapshot(
            season=season,
            date_label=date_label,
            rows=rows,
            market=market,
            snapshot_at=snapshot_at,
            source="playerboard_builder",
            source_mode=source_mode,
            csv_path=csv_path,
            metadata={
                "replaceDate": bool(replace_date),
                "market": market,
                "csvExport": str(csv_path),
            },
        )
        activated_snapshot_id = activated.id
    except Exception as error:
        # Keep the transition safe: if the indexed serving store is temporarily
        # unavailable, the CSV artifact is still exported so cold-start fallback
        # reads remain viable. The error is surfaced in the pipeline payload.
        db_write_error = str(error)

    removedRows = prune_playerboard_snapshot(season, date_label, market=market) if replace_date else 0
    append_csv(csv_path, PLAYERBOARD_FIELDS, rows)

    return {
        "snapshotAt": snapshot_at,
        "rowsSaved": len(rows),
        "removedRows": removedRows,
        "replaceDate": bool(replace_date),
        "sourceMode": source_mode,
        "file": str(csv_path),
        "servingStore": {
            "sourceOfTruth": "sqlite" if activated_snapshot_id else "csv_fallback",
            "snapshotId": activated_snapshot_id,
            "atomic": bool(activated_snapshot_id),
            "error": db_write_error,
        },
        "csvExport": {
            "derivedArtifact": True,
            "file": str(csv_path),
        },
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
        "season": int(to_float(row.get("season"), default_settings.current_season)),
        "date": clean(row.get("date")),
        "snapshotAt": clean(row.get("snapshotAt")),
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


def load_saved_playerboard(season: int = default_settings.current_season, date_label: str = "", market: str = "", limit: int = 5000) -> dict[str, Any]:
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


_PLAYER_DESCRIPTION_SUFFIXES = (
    "Strikeouts Thrown",
    "Pitcher Strikeouts",
    "Hits Allowed",
    "Earned Runs",
    "Stolen Bases",
    "Total Bases",
    "Home Runs",
    "Strikeouts",
    "Doubles",
    "Singles",
    "Walks",
    "RBIs",
    "Runs",
    "Hits",
)


def _looks_like_player_name(value: str) -> bool:
    tokens = re.findall(r"[A-Za-z][A-Za-z'.-]*", value)
    return len(tokens) >= 2


def _strip_descriptive_player_suffix(value: Any) -> str:
    text = clean(value)
    if not text:
        return ""

    side_match = re.search(r"\s+(?:Over|Under)\b", text, flags=re.IGNORECASE)
    if side_match:
        candidate = text[:side_match.start()].strip()
        if _looks_like_player_name(candidate):
            return candidate

    for suffix in _PLAYER_DESCRIPTION_SUFFIXES:
        pattern = rf"\s+(?:\d+(?:\.\d+)?\+?\s+)?{re.escape(suffix)}$"
        candidate = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
        if candidate != text and _looks_like_player_name(candidate):
            return candidate

    return text


def player_name_from_prop_row(row: dict[str, Any]) -> str:
    player = first_value(row, [
        "player", "playerName", "player_name", "participant",
        "athlete", "batter", "pitcher_name",
    ])
    if player:
        return player

    fallback = first_value(row, ["name", "description", "title", "selection", "outcome"])
    return _strip_descriptive_player_suffix(fallback)



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

    player = player_name_from_prop_row(row)

    label = first_value(row, ["side", "label", "title", "outcome", "outcome_name", "selection", "description"])
    if not player and label:
        player = _strip_descriptive_player_suffix(label)

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
    rows.extend(
        load_oddspapi_game_market_props(
            date_label,
            market_set,
            limit=limit,
            projections_enabled=default_settings.team_game_market_projections_enabled,
        )
    )

    out = aggregate_book_prices(rows)
    return out[:limit]


def infer_missing_context(prop: dict[str, Any], season: int) -> dict[str, Any]:
    """Use player_autofill to fill team/opponent/pitcher if the prop source omitted them."""
    if prop.get("team") and prop.get("opponent"):
        return prop

    try:
        from mlb_app.domain.player_autofill import autofill_player

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


def _card_cache_key(row: dict[str, Any], season: int, date_label: str) -> tuple[str, ...]:
    return (
        str(season),
        clean(row.get("date"))[:10] or date_label,
        clean(row.get("player")).casefold(),
        canonical_team_abbr(row.get("team")),
        canonical_team_abbr(row.get("opponent")),
        normalize_market(row.get("market")),
        base_market(row.get("market")),
        canonical_prop_line(row),
        side_for_prop(row),
        clean(row.get("american_odds") or row.get("americanOdds")),
        clean(row.get("pitcher")).casefold(),
    )


def _build_batter_summary_index(unified_module: Any, season: int) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in unified_module.regular_rows(unified_module.read_cached_rows(f"batter_game_logs_{season}.csv"), season):
        groups.setdefault(unified_module.norm(row.get("player")), []).append(row)
    out: dict[str, dict[str, Any]] = {}
    for player, rows in groups.items():
        games = len(rows)
        ab = sum(to_float(row.get("atBats")) for row in rows)
        pa = sum(to_float(row.get("plateAppearances")) for row in rows)
        hits = sum(to_float(row.get("hits")) for row in rows)
        hr = sum(to_float(row.get("homeRuns")) for row in rows)
        tb = sum(to_float(row.get("totalBases")) for row in rows)
        so = sum(to_float(row.get("strikeOuts")) for row in rows)
        bb = sum(to_float(row.get("baseOnBalls")) for row in rows)
        out[player] = {
            "available": games > 0,
            "games": games,
            "plateAppearances": pa,
            "atBats": ab,
            "hits": hits,
            "homeRuns": hr,
            "totalBases": tb,
            "strikeOuts": so,
            "baseOnBalls": bb,
            "avg": round(hits / ab, 3) if ab else 0,
            "hitsPerGame": round(hits / games, 3) if games else 0,
            "totalBasesPerGame": round(tb / games, 3) if games else 0,
            "homeRunsPerGame": round(hr / games, 3) if games else 0,
            "strikeoutsPerGame": round(so / games, 3) if games else 0,
            "team": clean(rows[-1].get("team")) if rows else "",
        }
    return out


def _build_pitcher_summary_index(unified_module: Any, season: int) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in unified_module.regular_rows(unified_module.read_cached_rows(f"pitcher_game_logs_{season}.csv"), season):
        groups.setdefault(unified_module.norm(row.get("player")), []).append(row)
    out: dict[str, dict[str, Any]] = {}
    for player, rows in groups.items():
        games = len(rows)
        hits = sum(to_float(row.get("hits")) for row in rows)
        er = sum(to_float(row.get("earnedRuns")) for row in rows)
        runs = sum(to_float(row.get("runs")) for row in rows)
        hr = sum(to_float(row.get("homeRuns")) for row in rows)
        bb = sum(to_float(row.get("baseOnBalls")) for row in rows)
        so = sum(to_float(row.get("strikeOuts")) for row in rows)
        bf = sum(to_float(row.get("battersFaced")) for row in rows)
        pitches = sum(to_float(row.get("pitchesThrown")) for row in rows)
        out[player] = {
            "available": games > 0,
            "games": games,
            "hitsAllowed": hits,
            "earnedRuns": er,
            "runs": runs,
            "homeRunsAllowed": hr,
            "baseOnBalls": bb,
            "strikeOuts": so,
            "battersFaced": bf,
            "pitchesThrown": pitches,
            "strikeoutsPerGame": round(so / games, 3) if games else 0,
            "hitsAllowedPerGame": round(hits / games, 3) if games else 0,
            "earnedRunsPerGame": round(er / games, 3) if games else 0,
            "team": clean(rows[-1].get("team")) if rows else "",
        }
    return out


def _build_team_summary_index(unified_module: Any, season: int) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in unified_module.regular_rows(unified_module.read_cached_rows(f"team_game_logs_{season}.csv"), season):
        groups.setdefault(clean(row.get("team")).upper(), []).append(row)
    out: dict[str, dict[str, Any]] = {}
    for team, rows in groups.items():
        games = len(rows)
        runs = sum(to_float(row.get("runs")) for row in rows)
        hits = sum(to_float(row.get("hits")) for row in rows)
        hr = sum(to_float(row.get("homeRuns")) for row in rows)
        so = sum(to_float(row.get("strikeOuts")) for row in rows)
        p_runs = sum(to_float(row.get("pitchingRuns")) for row in rows)
        p_hits = sum(to_float(row.get("pitchingHits")) for row in rows)
        p_so = sum(to_float(row.get("pitchingStrikeOuts")) for row in rows)
        out[team] = {
            "available": games > 0,
            "team": team,
            "games": games,
            "runsPerGame": round(runs / games, 3) if games else 0,
            "hitsPerGame": round(hits / games, 3) if games else 0,
            "homeRunsPerGame": round(hr / games, 3) if games else 0,
            "strikeoutsPerGame": round(so / games, 3) if games else 0,
            "runsAllowedPerGame": round(p_runs / games, 3) if games else 0,
            "hitsAllowedPerGame": round(p_hits / games, 3) if games else 0,
            "pitchingStrikeoutsPerGame": round(p_so / games, 3) if games else 0,
        }
    return out


def build_playerboard(season: int = default_settings.current_season, date_label: str = "", market: str = "", limit: int = 5000, save: bool = True, replace_date: bool = False, source_mode: str = "auto") -> dict[str, Any]:
    unified_module = importlib.import_module("mlb_app.domain.unified_prop_card")

    started = time.perf_counter()
    timings = {
        "marketFilterMs": 0.0,
        "unifiedPropCardMs": 0.0,
        "hitProfileMs": 0.0,
        "historyLookupMs": 0.0,
        "contextJoinMs": 0.0,
        "cardPostProcessMs": 0.0,
    }
    counters = {
        "cacheHits": 0,
        "cacheMisses": 0,
        "hitProfileCacheHits": 0,
        "hitProfileCacheMisses": 0,
        "historyCacheHits": 0,
        "historyCacheMisses": 0,
        "contextCacheHits": 0,
        "contextCacheMisses": 0,
    }
    markets = [market] if market else DEFAULT_MARKETS
    load_limit = max(1, int(limit or 5000))
    load_started = time.perf_counter()
    props = load_saved_props(date_label, markets=markets, limit=load_limit, source_mode=source_mode)
    load_ms = (time.perf_counter() - load_started) * 1000.0

    cards = []
    errors = []
    skipped: dict[str, Any] = {"unsupportedMarkets": {}, "filtered": {}}
    hit_profile_cache: dict[tuple[str, ...], dict[str, Any]] = {}
    unified_card_cache: dict[tuple[str, ...], dict[str, Any]] = {}
    context_cache: dict[tuple[str, ...], dict[str, Any]] = {}
    original_helpers: dict[str, Any] = {}

    def elapsed_ms(start: float) -> float:
        return (time.perf_counter() - start) * 1000.0

    def add_timing(name: str, start: float) -> None:
        timings[name] = timings.get(name, 0.0) + elapsed_ms(start)

    def count_skip(bucket: str, key: Any) -> None:
        normalized = normalize_market(key) if bucket == "unsupportedMarkets" else clean(key)
        skipped.setdefault(bucket, {})
        skipped[bucket][normalized] = int(skipped[bucket].get(normalized, 0)) + 1

    def install_cached_helper(name: str, bucket: str, key_builder) -> None:
        original = getattr(unified_module, name)
        original_helpers[name] = original

        def wrapper(*args, **kwargs):
            key = (name, *key_builder(*args, **kwargs))
            cached = context_cache.get(key)
            if cached is not None:
                if bucket == "historyLookupMs":
                    counters["historyCacheHits"] += 1
                else:
                    counters["contextCacheHits"] += 1
                return copy.deepcopy(cached)
            if bucket == "historyLookupMs":
                counters["historyCacheMisses"] += 1
            else:
                counters["contextCacheMisses"] += 1
            call_started = time.perf_counter()
            value = original(*args, **kwargs)
            add_timing(bucket, call_started)
            context_cache[key] = copy.deepcopy(value)
            return value

        setattr(unified_module, name, wrapper)

    def install_unified_caches() -> None:
        original_helpers["summarize_batter"] = getattr(unified_module, "summarize_batter")
        original_helpers["summarize_pitcher"] = getattr(unified_module, "summarize_pitcher")
        original_helpers["summarize_team"] = getattr(unified_module, "summarize_team")
        index_started = time.perf_counter()
        batter_index = _build_batter_summary_index(unified_module, season)
        pitcher_index = _build_pitcher_summary_index(unified_module, season)
        team_index = _build_team_summary_index(unified_module, season)
        add_timing("historyLookupMs", index_started)

        def summarize_batter_cached(player, requested_season):
            key = unified_module.norm(player)
            value = batter_index.get(key)
            if value is not None:
                counters["historyCacheHits"] += 1
                return copy.deepcopy(value)
            counters["historyCacheMisses"] += 1
            return {"available": False, "games": 0, "plateAppearances": 0, "atBats": 0, "hits": 0, "homeRuns": 0, "totalBases": 0, "strikeOuts": 0, "baseOnBalls": 0, "avg": 0, "hitsPerGame": 0, "totalBasesPerGame": 0, "homeRunsPerGame": 0, "strikeoutsPerGame": 0, "team": ""}

        def summarize_pitcher_cached(player, requested_season):
            key = unified_module.norm(player)
            value = pitcher_index.get(key)
            if value is not None:
                counters["historyCacheHits"] += 1
                return copy.deepcopy(value)
            counters["historyCacheMisses"] += 1
            return {"available": False, "games": 0, "hitsAllowed": 0, "earnedRuns": 0, "runs": 0, "homeRunsAllowed": 0, "baseOnBalls": 0, "strikeOuts": 0, "battersFaced": 0, "pitchesThrown": 0, "strikeoutsPerGame": 0, "hitsAllowedPerGame": 0, "earnedRunsPerGame": 0, "team": ""}

        def summarize_team_cached(team, requested_season):
            key = clean(team).upper()
            value = team_index.get(key)
            if value is not None:
                counters["historyCacheHits"] += 1
                return copy.deepcopy(value)
            counters["historyCacheMisses"] += 1
            return {"available": False, "team": key, "games": 0, "runsPerGame": 0, "hitsPerGame": 0, "homeRunsPerGame": 0, "strikeoutsPerGame": 0, "runsAllowedPerGame": 0, "hitsAllowedPerGame": 0, "pitchingStrikeoutsPerGame": 0}

        setattr(unified_module, "summarize_batter", summarize_batter_cached)
        setattr(unified_module, "summarize_pitcher", summarize_pitcher_cached)
        setattr(unified_module, "summarize_team", summarize_team_cached)
        install_cached_helper("find_weather_feature", "contextJoinMs", lambda season, date, team, opponent: (str(season), clean(date)[:10], canonical_team_abbr(team), canonical_team_abbr(opponent)))
        install_cached_helper("find_odds_movement_context", "contextJoinMs", lambda season, date, market, player, team, opponent, pitcher: (str(season), clean(date)[:10], normalize_market(market), clean(player).casefold(), canonical_team_abbr(team), canonical_team_abbr(opponent), clean(pitcher).casefold()))
        install_cached_helper("find_savant_context", "historyLookupMs", lambda season, player, pitcher, market: (str(season), clean(player).casefold(), clean(pitcher).casefold(), normalize_market(market)))
        install_cached_helper("all_data_predict", "contextJoinMs", lambda row: _card_cache_key(row, season, date_label))

    def restore_unified_caches() -> None:
        for name, original in original_helpers.items():
            setattr(unified_module, name, original)

    def cached_unified_prop_card(row: dict[str, Any]) -> dict[str, Any]:
        key = _card_cache_key(row, season, date_label)
        cached = unified_card_cache.get(key)
        if cached is not None:
            counters["cacheHits"] += 1
            return copy.deepcopy(cached)
        counters["cacheMisses"] += 1
        call_started = time.perf_counter()
        card = unified_module.unified_prop_card(row)
        add_timing("unifiedPropCardMs", call_started)
        unified_card_cache[key] = copy.deepcopy(card)
        return card

    def attach_hit_profile(card: dict[str, Any], row_for_profile: dict[str, Any]) -> dict[str, Any]:
        cache_key = _card_cache_key(row_for_profile, season, date_label)
        cached = hit_profile_cache.get(cache_key)
        if cached is not None:
            counters["hitProfileCacheHits"] += 1
            card["hitRates"] = copy.deepcopy(cached.get("hitRates") or {})
            card["recentGames"] = copy.deepcopy(cached.get("recentGames") or [])
            return card
        counters["hitProfileCacheMisses"] += 1
        hit_started = time.perf_counter()
        try:
            from mlb_app.domain.player_hit_rates import hit_profile_for_row, parse_date
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
        hit_profile_cache[cache_key] = {
            "hitRates": copy.deepcopy(card.get("hitRates") or {}),
            "recentGames": copy.deepcopy(card.get("recentGames") or []),
        }
        add_timing("hitProfileMs", hit_started)
        return card

    def build_card(prop: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
        filter_started = time.perf_counter()
        capability = market_capability(prop.get("market"))
        add_timing("marketFilterMs", filter_started)
        if capability == "unsupported_skip":
            return None, {"type": "unsupported_market", "market": normalize_market(prop.get("market"))}

        context_key = ("infer", str(season), clean(prop.get("date"))[:10] or date_label, clean(prop.get("player")).casefold(), normalize_market(prop.get("market")), canonical_team_abbr(prop.get("team")), canonical_team_abbr(prop.get("opponent")))
        cached_context = context_cache.get(context_key)
        if cached_context is not None:
            counters["contextCacheHits"] += 1
            prop = copy.deepcopy(cached_context)
        else:
            counters["contextCacheMisses"] += 1
            context_started = time.perf_counter()
            prop = infer_missing_context(prop, season)
            add_timing("contextJoinMs", context_started)
            context_cache[context_key] = copy.deepcopy(prop)

        if can_use_direct_team_game_card(prop):
            if not team_game_market_display_allowed(prop):
                return None, {"type": "filtered", "reason": "extreme_alt_line_filtered", "market": normalize_market(prop.get("market"))}
            post_started = time.perf_counter()
            card = team_game_prop_to_playerboard_card(prop)
            add_timing("cardPostProcessMs", post_started)
            return attach_hit_profile(card, {**prop, **card, "date": clean(prop.get("date"))[:10] or date_label}), None

        if not prop.get("team") or not prop.get("opponent"):
            if clean(prop.get("americanOdds")):
                post_started = time.perf_counter()
                card = odds_only_player_card(prop)
                add_timing("cardPostProcessMs", post_started)
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
            card = cached_unified_prop_card(row)
            post_started = time.perf_counter()
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
            add_timing("cardPostProcessMs", post_started)
            return attach_hit_profile(out, row), None
        except Exception as error:
            return None, {
                "player": row["player"],
                "market": row["market"],
                "error": str(error),
            }

    requested_workers = int(os.environ.get("PLAYERBOARD_BUILD_WORKERS", "1") or "1")
    max_workers = max(1, min(12, requested_workers, (os.cpu_count() or 4)))

    build_started = time.perf_counter()
    install_unified_caches()
    try:
        if max_workers <= 1:
            for prop in props:
                card, error = build_card(prop)
                if card:
                    cards.append(card)
                if error:
                    if error.get("type") == "unsupported_market":
                        count_skip("unsupportedMarkets", error.get("market"))
                    elif error.get("type") == "filtered":
                        count_skip("filtered", error.get("reason"))
                    else:
                        errors.append(error)
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(build_card, prop) for prop in props]
                for future in as_completed(futures):
                    card, error = future.result()
                    if card:
                        cards.append(card)
                    if error:
                        if error.get("type") == "unsupported_market":
                            count_skip("unsupportedMarkets", error.get("market"))
                        elif error.get("type") == "filtered":
                            count_skip("filtered", error.get("reason"))
                        else:
                            errors.append(error)
    finally:
        restore_unified_caches()
    build_ms = (time.perf_counter() - build_started) * 1000.0

    # Final aggregation after context inference/model card creation.
    # This collapses remaining book/alias duplicates into one clean prop card.
    aggregate_started = time.perf_counter()
    cards = sorted(aggregate_book_prices(cards), key=rank_value, reverse=True)
    aggregate_ms = (time.perf_counter() - aggregate_started) * 1000.0

    top_cards = cards[:limit]
    save_started = time.perf_counter()
    saved = save_playerboard_snapshot(season, date_label, top_cards, replace_date=replace_date, market=market) if save and top_cards else None
    save_ms = (time.perf_counter() - save_started) * 1000.0
    total_ms = (time.perf_counter() - started) * 1000.0
    elapsed_seconds = max(total_ms / 1000.0, 0.000001)

    return {
        "season": season,
        "date": date_label,
        "market": market,
        "propsLoaded": len(props),
        "cardsBuilt": len(cards),
        "errors": errors[:10],
        "skipped": skipped,
        "timings": {
            "loadPropsMs": round(load_ms, 3),
            "buildCardsMs": round(build_ms, 3),
            "marketFilterMs": round(timings["marketFilterMs"], 3),
            "unifiedPropCardMs": round(timings["unifiedPropCardMs"], 3),
            "hitProfileMs": round(timings["hitProfileMs"], 3),
            "historyLookupMs": round(timings["historyLookupMs"], 3),
            "contextJoinMs": round(timings["contextJoinMs"], 3),
            "cardPostProcessMs": round(timings["cardPostProcessMs"], 3),
            "aggregateMs": round(aggregate_ms, 3),
            "saveMs": round(save_ms, 3),
            "totalMs": round(total_ms, 3),
        },
        "performance": {
            "propsPerSecond": round(len(props) / elapsed_seconds, 3),
            "cardsPerSecond": round(len(cards) / elapsed_seconds, 3),
            "workers": max_workers,
            "loadLimit": load_limit,
        },
        "cacheHits": counters["cacheHits"],
        "cacheMisses": counters["cacheMisses"],
        "hitProfileCacheHits": counters["hitProfileCacheHits"],
        "hitProfileCacheMisses": counters["hitProfileCacheMisses"],
        "historyCacheHits": counters["historyCacheHits"],
        "historyCacheMisses": counters["historyCacheMisses"],
        "contextCacheHits": counters["contextCacheHits"],
        "contextCacheMisses": counters["contextCacheMisses"],
        "marketCapabilities": dict(MARKET_CAPABILITY_MAP),
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
