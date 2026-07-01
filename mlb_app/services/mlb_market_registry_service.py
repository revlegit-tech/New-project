from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from mlb_app.config import Settings, settings as default_settings
from mlb_app.ml.market_config import supported_markets as model_supported_markets
from mlb_app.services.player_prop_market_stat_mapper import MARKET_STAT_KEYS
from mlb_app.services.playerboard_builder import DEFAULT_MARKETS, market_capability, normalize_market

MARKET_GROUP_ORDER = (
    ("all", "All Markets"),
    ("batter", "Batter Props"),
    ("alt", "Batter Alt Props"),
    ("pitcher", "Pitcher Props"),
    ("game", "Game Markets"),
    ("team", "Team Markets"),
    ("first5", "First 5 Innings"),
    ("unknown", "Unknown / Odds Only"),
)

DISPLAY_NAMES = {
    "batter_hits": "Hits",
    "batter_total_bases": "Total Bases",
    "batter_home_runs": "Home Runs",
    "batter_rbis": "RBIs",
    "batter_runs": "Runs",
    "batter_walks": "Walks",
    "batter_singles": "Singles",
    "batter_doubles": "Doubles",
    "batter_stolen_bases": "Stolen Bases",
    "batter_2plus_hits": "2+ Hits",
    "batter_2plus_home_runs": "2+ Home Runs",
    "batter_2plus_rbis": "2+ RBIs",
    "batter_3plus_rbis": "3+ RBIs",
    "batter_hits_alt": "Hits Alt",
    "batter_total_bases_alt": "Total Bases Alt",
    "batter_home_runs_alt": "Home Runs Alt",
    "pitcher_strikeouts": "Strikeouts",
    "pitcher_strikeouts_alt": "Strikeouts Alt",
    "pitcher_outs": "Outs",
    "pitcher_hits_allowed": "Hits Allowed",
    "pitcher_earned_runs": "Earned Runs",
    "pitcher_walks_allowed": "Walks Allowed",
    "pitcher_runs_allowed": "Runs Allowed",
    "moneyline": "Moneyline",
    "run_line": "Run Line",
    "game_total_runs": "Game Total Runs",
    "team_total_runs": "Team Total Runs",
    "team_first_to_score": "Team First To Score",
    "team_last_to_score": "Team Last To Score",
    "moneyline_first_five": "F5 Moneyline",
    "run_line_first_five": "F5 Run Line",
    "first_five_total_runs": "F5 Total",
}

SORT_ORDER = {key: index for index, key in enumerate(DISPLAY_NAMES)}


@dataclass
class MarketAccumulator:
    market_key: str
    sources: set[str] = field(default_factory=set)
    row_count: int = 0
    quote_count: int = 0
    books: set[str] = field(default_factory=set)
    warnings: set[str] = field(default_factory=set)
    hidden_reasons: set[str] = field(default_factory=set)

    def add_row(self, source: str, row: dict[str, Any], *, quote: bool = True) -> None:
        self.sources.add(source)
        self.row_count += 1
        if quote:
            self.quote_count += 1
        book = _clean(_first(row, "book", "bookKey", "sportsbook", "book_name", "bookmaker"))
        if book:
            self.books.add(book)


class MLBMarketRegistryService:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def payload(self, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
        query = query or {}
        season = self.settings.season_from_query(query)
        date_label = _clean((query.get("date") or [""])[0]) or self._latest_date_from_playerboard(season)
        markets: dict[str, MarketAccumulator] = {}

        source_counts = {
            "propline": self._discover_propline(markets, date_label),
            "actionnetwork": self._discover_actionnetwork(markets, date_label),
            "playerboard": self._discover_playerboard(markets, season, date_label),
            "model": self._discover_supported(markets, "model", model_supported_markets()),
            "report": self._discover_supported(markets, "report", tuple(DEFAULT_MARKETS) + tuple(MARKET_STAT_KEYS)),
        }
        entries = [self._entry(accumulator) for accumulator in markets.values()]
        entries.sort(key=lambda item: (_category_sort_key(item), SORT_ORDER.get(item["marketKey"], 999), item["displayName"]))
        diagnostics = _diagnostics(entries, source_counts)
        return {
            "status": "ok",
            "date": date_label,
            "season": season,
            "markets": entries,
            "groups": _groups(entries),
            "marketCoverage": diagnostics,
            "coverage": diagnostics,
            "sortableFields": ["edgePercent", "modelProbabilityPercent", "impliedProbabilityPercent", "line", "americanOdds", "rowCount", "quoteCount"],
            "defaultSort": "edgePercent",
            "researchLock": {"action": "Research", "readinessLabel": "Experimental", "stakeUnits": 0, "betActionAllowed": False},
        }

    def _latest_date_from_playerboard(self, season: int) -> str:
        dates = {_clean(row.get("date"))[:10] for row in _read_csv(self.settings.data_dir / "playerboard" / f"playerboard_{season}.csv") if _clean(row.get("date"))}
        return sorted(dates)[-1] if dates else ""

    def _discover_propline(self, markets: dict[str, MarketAccumulator], date_label: str) -> dict[str, Any]:
        path = self.settings.data_dir / "odds" / f"propline_props_{date_label}.csv"
        rows = _read_csv(path) if date_label else []
        for row in rows:
            key = _normalize_known_market(row.get("market"))
            if key:
                _market(markets, key).add_row("propline", row)
        return {"rows": len(rows), "file": str(path), "markets": sorted({_normalize_known_market(row.get("market")) for row in rows if _clean(row.get("market"))})}

    def _discover_actionnetwork(self, markets: dict[str, MarketAccumulator], date_label: str) -> dict[str, Any]:
        path = self.settings.data_dir / "warehouse" / "normalized" / "odds" / f"actionnetwork_all_markets_{date_label}.csv"
        rows = _read_csv(path) if date_label else []
        discovered: set[str] = set()
        for row in rows:
            key = _normalize_actionnetwork_market(row)
            if key:
                discovered.add(key)
                _market(markets, key).add_row("actionnetwork", row)
        return {"rows": len(rows), "file": str(path), "markets": sorted(discovered)}

    def _discover_playerboard(self, markets: dict[str, MarketAccumulator], season: int, date_label: str) -> dict[str, Any]:
        path = self.settings.data_dir / "playerboard" / f"playerboard_{season}.csv"
        rows = [row for row in _read_csv(path) if not date_label or _clean(row.get("date"))[:10] == date_label]
        for row in rows:
            key = _normalize_known_market(row.get("market") or row.get("baseMarket"))
            if key:
                _market(markets, key).add_row("playerboard", row)
        return {"rows": len(rows), "file": str(path), "markets": sorted({_normalize_known_market(row.get("market")) for row in rows if _clean(row.get("market"))})}

    def _discover_supported(self, markets: dict[str, MarketAccumulator], source: str, supported: Iterable[str]) -> dict[str, Any]:
        keys = sorted({_normalize_known_market(market) for market in supported if _clean(market)})
        for key in keys:
            _market(markets, key).sources.add(source)
        return {"rows": 0, "file": "", "markets": keys}

    def _entry(self, accumulator: MarketAccumulator) -> dict[str, Any]:
        key = accumulator.market_key
        category = _category(key)
        has_odds = bool({"propline", "actionnetwork", "playerboard"} & accumulator.sources) and accumulator.quote_count > 0
        has_model = key in set(model_supported_markets())
        supported_in_report = key in {_normalize_known_market(value) for value in tuple(DEFAULT_MARKETS) + tuple(MARKET_STAT_KEYS)}
        supported_in_board = market_capability(key) != "unsupported_skip" and category not in {"game", "first5"}
        has_alt = _is_alt_market(key)
        model_status = _model_status(has_odds=has_odds, has_model=has_model, key=key)
        warning = _warning(category=category, has_odds=has_odds, has_model=has_model, supported_in_board=supported_in_board, model_status=model_status)
        if warning:
            accumulator.warnings.add(warning)
        if not supported_in_board and category in {"game", "first5"}:
            accumulator.hidden_reasons.add("Game market board rendering not implemented yet")
        return {
            "marketKey": key,
            "displayName": DISPLAY_NAMES.get(key) or key.replace("_", " ").title(),
            "category": category,
            "propType": _prop_type(key),
            "sideType": _side_type(key),
            "hasOdds": has_odds,
            "hasModel": has_model,
            "hasAltLines": has_alt,
            "rowCount": accumulator.row_count,
            "quoteCount": accumulator.quote_count,
            "availableBooks": sorted(accumulator.books),
            "supportedInBoard": supported_in_board,
            "supportedInReport": supported_in_report,
            "supportedInModel": has_model,
            "modelStatus": model_status,
            "warning": warning,
            "warnings": sorted(accumulator.warnings),
            "sources": sorted(accumulator.sources),
            "missingModelMarket": has_odds and not has_model,
            "modelUnavailable": has_odds and not has_model,
            "hidden": bool(accumulator.hidden_reasons),
            "hiddenReason": "; ".join(sorted(accumulator.hidden_reasons)),
            "badges": _badges(category=category, has_model=has_model, has_odds=has_odds, has_alt=has_alt, model_status=model_status),
            "sortableFields": ["rowCount", "quoteCount", "line", "americanOdds"],
            "marketSupportsModelSort": has_model,
            "marketSupportsOddsSort": has_odds,
            "marketSupportsEdgeSort": has_model and has_odds,
            "marketSupportsLineSort": _side_type(key) in {"over_under", "spread", "milestone"},
        }


def _market(markets: dict[str, MarketAccumulator], key: str) -> MarketAccumulator:
    normalized = _normalize_known_market(key)
    markets.setdefault(normalized, MarketAccumulator(normalized))
    return markets[normalized]


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except Exception:
        return []


def _normalize_known_market(value: Any) -> str:
    key = normalize_market(value)
    return {
        "team_first_score": "team_first_to_score",
        "team_total": "team_total_runs",
        "game_total": "game_total_runs",
        "spread": "run_line",
        "f5_moneyline": "moneyline_first_five",
        "first_5_moneyline": "moneyline_first_five",
        "f5_run_line": "run_line_first_five",
        "first_5_run_line": "run_line_first_five",
        "f5_total": "first_five_total_runs",
        "first_5_total": "first_five_total_runs",
    }.get(key, key)


def _normalize_actionnetwork_market(row: dict[str, Any]) -> str:
    text = " ".join(_clean(row.get(key)).lower().replace("_", " ") for key in ("canonical_market", "market_key", "market_group", "market_group_label", "market", "market_type") if _clean(row.get(key)))
    if not text:
        return ""
    if "first" in text and ("five" in text or "5" in text):
        if "moneyline" in text or "money line" in text:
            return "moneyline_first_five"
        if "run line" in text or "spread" in text:
            return "run_line_first_five"
        if "total" in text:
            return "first_five_total_runs"
    if "moneyline" in text or "money line" in text:
        return "moneyline"
    if "run line" in text or "spread" in text:
        return "run_line"
    if "team" in text and "total" in text:
        return "team_total_runs"
    if "total" in text:
        return "game_total_runs"
    return _normalize_known_market(_first(row, "canonical_market", "market_key", "market_type", "market_group", "market"))


def _category(key: str) -> str:
    if key in {"moneyline_first_five", "run_line_first_five", "first_five_total_runs"} or key.startswith("first_five"):
        return "first5"
    if key.startswith("batter_"):
        return "batter"
    if key.startswith("pitcher_"):
        return "pitcher"
    if key.startswith("team_"):
        return "team"
    if key in {"moneyline", "run_line", "game_total_runs"} or key.startswith(("run_line_", "game_")):
        return "game"
    return "unknown"


def _prop_type(key: str) -> str:
    category = _category(key)
    if category in {"batter", "pitcher"}:
        return "player"
    if category == "team":
        return "team"
    if category in {"game", "first5"}:
        return "game"
    return "unknown"


def _side_type(key: str) -> str:
    if key.startswith("moneyline"):
        return "h2h"
    if key.startswith("run_line"):
        return "spread"
    if "first_to_score" in key or "last_to_score" in key:
        return "one_sided"
    if "total" in key or key.startswith(("batter_", "pitcher_")):
        return "milestone" if _is_alt_market(key) else "over_under"
    return "unknown"


def _is_alt_market(key: str) -> bool:
    return bool(key.endswith("_alt") or re.search(r"_(?:2|3|4|5)plus_", key))


def _model_status(*, has_odds: bool, has_model: bool, key: str) -> str:
    if has_odds and has_model:
        return "modeled"
    if has_odds and not has_model:
        return "odds_only"
    if has_model and not has_odds:
        return "missing_model"
    if market_capability(key) == "research_only":
        return "fallback_only"
    return "model_unavailable"


def _warning(*, category: str, has_odds: bool, has_model: bool, supported_in_board: bool, model_status: str) -> str:
    if category in {"game", "first5"} and not supported_in_board:
        return "Game market board rendering not implemented yet"
    if has_odds and not has_model:
        return "Odds available, but no market-specific model is available"
    if has_model and not has_odds:
        return "Model support configured, but no current odds were discovered"
    if model_status == "model_unavailable":
        return "Discovered market has no supported model mapping yet"
    return ""


def _badges(*, category: str, has_model: bool, has_odds: bool, has_alt: bool, model_status: str) -> list[str]:
    badges = []
    if has_model:
        badges.append("Modeled")
    if has_odds and not has_model:
        badges.append("Odds only")
    if has_alt:
        badges.append("Alt")
    if category in {"game", "first5"}:
        badges.append("Game market")
    if model_status in {"missing_model", "model_unavailable", "odds_only"}:
        badges.append("Missing model")
    return badges


def _category_sort_key(item: dict[str, Any]) -> int:
    group_key = "alt" if item.get("category") == "batter" and item.get("hasAltLines") else item.get("category")
    return {key: index for index, (key, _label) in enumerate(MARKET_GROUP_ORDER)}.get(group_key, 99)


def _groups(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        group_key = "alt" if entry["category"] == "batter" and entry["hasAltLines"] else entry["category"]
        grouped[group_key].append(entry)
    groups = [{
        "key": "all",
        "label": "All Markets",
        "markets": [],
        "rowCount": sum(int(entry.get("rowCount") or 0) for entry in entries),
        "quoteCount": sum(int(entry.get("quoteCount") or 0) for entry in entries),
    }]
    for key, label in MARKET_GROUP_ORDER[1:]:
        markets = grouped.get(key, [])
        if markets:
            groups.append({"key": key, "label": label, "markets": markets, "rowCount": sum(int(entry.get("rowCount") or 0) for entry in markets), "quoteCount": sum(int(entry.get("quoteCount") or 0) for entry in markets)})
    return groups


def _diagnostics(entries: list[dict[str, Any]], source_counts: dict[str, Any]) -> dict[str, Any]:
    by_market = {entry["marketKey"]: int(entry.get("rowCount") or 0) for entry in entries}
    quote_by_market = {entry["marketKey"]: int(entry.get("quoteCount") or 0) for entry in entries}
    hidden = [entry for entry in entries if entry.get("hidden")]
    odds_no_model = [entry for entry in entries if entry.get("hasOdds") and not entry.get("hasModel")]
    model_no_odds = [entry for entry in entries if entry.get("hasModel") and not entry.get("hasOdds")]
    unknown = [entry for entry in entries if entry.get("category") == "unknown"]
    return {
        "rawPropsPulled": int((source_counts.get("propline") or {}).get("rows") or 0),
        "marketsFound": len(entries),
        "marketsDiscoveredFromPropLine": (source_counts.get("propline") or {}).get("markets", []),
        "marketsDiscoveredFromActionNetwork": (source_counts.get("actionnetwork") or {}).get("markets", []),
        "marketsDiscoveredFromPlayerboard": (source_counts.get("playerboard") or {}).get("markets", []),
        "marketsWithRows": sorted([entry["marketKey"] for entry in entries if int(entry.get("rowCount") or 0) > 0]),
        "marketsShownInDropdown": sorted([entry["marketKey"] for entry in entries if not entry.get("hidden") or entry.get("hasOdds")]),
        "marketsHiddenFromDropdown": sorted([entry["marketKey"] for entry in hidden]),
        "marketsWithOddsButNoModel": sorted([entry["marketKey"] for entry in odds_no_model]),
        "marketsWithModelButNoOdds": sorted([entry["marketKey"] for entry in model_no_odds]),
        "altMarketsFound": sorted([entry["marketKey"] for entry in entries if entry.get("hasAltLines")]),
        "gameMarketsFound": sorted([entry["marketKey"] for entry in entries if entry.get("category") == "game"]),
        "teamMarketsFound": sorted([entry["marketKey"] for entry in entries if entry.get("category") == "team"]),
        "firstFiveMarketsFound": sorted([entry["marketKey"] for entry in entries if entry.get("category") == "first5"]),
        "moneylineRowsLoaded": by_market.get("moneyline", 0),
        "runLineRowsLoaded": by_market.get("run_line", 0),
        "totalsRowsLoaded": by_market.get("game_total_runs", 0),
        "teamTotalsRowsLoaded": by_market.get("team_total_runs", 0),
        "f5RowsLoaded": by_market.get("moneyline_first_five", 0) + by_market.get("run_line_first_five", 0) + by_market.get("first_five_total_runs", 0),
        "propsDroppedByUnsupportedMarket": 0,
        "propsDroppedByUnsupportedSide": 0,
        "unknownMarketsFound": sorted([entry["marketKey"] for entry in unknown]),
        "sampleUnknownMarkets": [entry["marketKey"] for entry in unknown[:8]],
        "sampleHiddenMarkets": [{"marketKey": entry["marketKey"], "reason": entry.get("hiddenReason", "")} for entry in hidden[:8]],
        "rowsByMarket": by_market,
        "quoteCountByMarket": quote_by_market,
        "booksByMarket": {entry["marketKey"]: entry.get("availableBooks", []) for entry in entries},
        "modelSupportStatus": {entry["marketKey"]: entry.get("modelStatus") for entry in entries},
        "oddsOnlyMarketCount": len(odds_no_model),
        "missingModelMarketCount": len(odds_no_model),
    }


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in {None, ""}:
            return value
    return ""


def _clean(value: Any) -> str:
    return str(value or "").strip()
