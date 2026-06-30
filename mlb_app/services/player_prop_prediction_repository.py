from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings


@dataclass(frozen=True)
class PredictionJoinResult:
    rows: list[dict[str, Any]]
    meta: dict[str, Any]


class PlayerPropPredictionRepository:
    """Load UI-safe prop predictions and join them to playerboard rows."""

    def __init__(self, *, settings: Settings = default_settings) -> None:
        self.settings = settings

    def prediction_path(self, date_label: str) -> Path:
        return self.settings.data_dir / "predictions" / f"prop_predictions_{date_label}.csv"

    def join_predictions(self, rows: list[dict[str, Any]], *, date_label: str) -> PredictionJoinResult:
        path = self.prediction_path(date_label)
        predictions = self._load_predictions(path)
        source = str(path)
        by_market = Counter(_clean(row.get("market")) or "unknown" for row in predictions)
        meta: dict[str, Any] = {
            "predictionsLoaded": len(predictions),
            "predictionsMatched": 0,
            "predictionsMissing": len(rows),
            "predictionsAmbiguous": 0,
            "predictionSource": source if path.is_file() else "",
            "predictionsByMarket": dict(sorted(by_market.items())),
        }
        if not rows or not predictions:
            return PredictionJoinResult(rows=[dict(row) for row in rows], meta=meta)

        index = _PredictionIndex(predictions)
        enriched_rows: list[dict[str, Any]] = []
        matched = 0
        ambiguous = 0
        for row in rows:
            match = index.match(row, date_label=date_label)
            if match.status == "matched" and match.row is not None:
                enriched_rows.append(_apply_prediction(row, match.row, source=source))
                matched += 1
            else:
                enriched_rows.append(dict(row))
                if match.status == "ambiguous":
                    ambiguous += 1

        meta["predictionsMatched"] = matched
        meta["predictionsMissing"] = len(rows) - matched - ambiguous
        meta["predictionsAmbiguous"] = ambiguous
        return PredictionJoinResult(rows=enriched_rows, meta=meta)

    @staticmethod
    def _load_predictions(path: Path) -> list[dict[str, Any]]:
        if not path.is_file():
            return []
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                return [dict(row) for row in csv.DictReader(handle)]
        except Exception:
            return []


@dataclass(frozen=True)
class _PredictionMatch:
    status: str
    row: dict[str, Any] | None = None


class _PredictionIndex:
    def __init__(self, predictions: list[dict[str, Any]]) -> None:
        self.by_prediction_key = self._index(predictions, key_fn=lambda row: _clean(row.get("predictionKey")))
        self.by_composite_key = self._index(predictions, key_fn=_prediction_composite_key)

    def match(self, row: dict[str, Any], *, date_label: str) -> _PredictionMatch:
        prediction_key = prediction_key_for_board_row(row, date_label=date_label)
        for key, index in ((prediction_key, self.by_prediction_key), (_board_composite_key(row, date_label=date_label), self.by_composite_key)):
            if not key:
                continue
            candidates = index.get(key) or []
            if len(candidates) == 1:
                return _PredictionMatch("matched", candidates[0])
            if len(candidates) > 1:
                return _PredictionMatch("ambiguous")
        return _PredictionMatch("missing")

    @staticmethod
    def _index(predictions: list[dict[str, Any]], *, key_fn: Any) -> dict[str, list[dict[str, Any]]]:
        index: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in predictions:
            if _clean(row.get("joinKeyStrength")).lower() == "unsafe":
                continue
            key = key_fn(row)
            if key:
                index[key].append(row)
        return dict(index)


def prediction_key_for_board_row(row: dict[str, Any], *, date_label: str) -> str:
    date_value = _clean(row.get("date")) or date_label
    market = _clean(row.get("market"))
    player = _clean(_first(row, "player", "playerName", "name"))
    team = _clean(row.get("team"))
    opponent = _clean(row.get("opponent"))
    book = _clean(_first(row, "bookKey", "book_key", "sportsbookKey", "sportsbook_key", "book", "sportsbook"))
    line = _number_key(_first(row, "line", "sportsbook_line", "prop_line"))
    side = _side_key(row)
    odds = _number_key(_first(row, "americanOdds", "american_odds", "odds", "price"))
    if not all([date_value, market, player, book, side]):
        return ""
    return "|".join(
        [
            date_value,
            market,
            _prediction_identity_key(player),
            _prediction_identity_key(team),
            _prediction_identity_key(opponent),
            _prediction_identity_key(book),
            line,
            _prediction_identity_key(side),
            odds,
        ]
    )


def _apply_prediction(row: dict[str, Any], prediction: dict[str, Any], *, source: str) -> dict[str, Any]:
    enriched = dict(row)
    warnings = _prediction_warnings(prediction)
    enriched.update(
        {
            "modelProbabilityPercent": _clean(prediction.get("modelProbabilityPercent")),
            "impliedProbabilityPercent": _clean(prediction.get("impliedProbabilityPercent")),
            "edgePercent": _clean(prediction.get("edgePercent")),
            "fairOdds": _clean(prediction.get("fairOdds")),
            "expectedValue": _clean(prediction.get("expectedValue")),
            "readinessLabel": "Experimental",
            "modelReadiness": "Experimental",
            "action": "Research",
            "stakeUnits": 0,
            "predictionMatched": True,
            "predictionKey": _clean(prediction.get("predictionKey")) or prediction_key_for_board_row(row, date_label=_clean(prediction.get("date"))),
            "predictionSource": source,
            "predictionWarnings": warnings,
            "confidence": "Research",
            "recommendation": "Research",
        }
    )
    return enriched


def _prediction_composite_key(row: dict[str, Any]) -> str:
    date_value = _clean(row.get("date"))
    market = _clean(row.get("market"))
    player = _clean(row.get("player"))
    team = _clean(row.get("team"))
    opponent = _clean(row.get("opponent"))
    book = _clean(_first(row, "bookKey", "book_key", "book", "sportsbook"))
    line = _number_key(row.get("line"))
    side = _side_key(row)
    odds = _number_key(_first(row, "americanOdds", "american_odds", "odds", "price"))
    if not all([date_value, market, player, book, side]):
        return ""
    return "|".join(
        [
            date_value,
            _normalized_text(market),
            _normalized_text(player),
            _normalized_text(team),
            _normalized_text(opponent),
            _normalized_text(book),
            line,
            _normalized_text(side),
            odds,
        ]
    )


def _board_composite_key(row: dict[str, Any], *, date_label: str) -> str:
    prepared = dict(row)
    prepared["date"] = _clean(prepared.get("date")) or date_label
    return _prediction_composite_key(prepared)


def _prediction_warnings(row: dict[str, Any]) -> list[str]:
    raw = _clean(row.get("warnings"))
    if not raw:
        return []
    return [part.strip() for part in re.split(r"[|;]", raw) if part.strip()]


def _side_key(row: dict[str, Any]) -> str:
    side = _clean(row.get("side"))
    if side:
        return side[:1].upper() + side[1:].lower()
    raw_label = _clean(_first(row, "rawLabel", "raw_label", "label", "pickSide"))
    tokens = [token.strip(" :/-_()[]{}").lower() for token in raw_label.split()]
    if "under" in tokens:
        return "Under"
    return "Over"


def _prediction_identity_key(value: Any) -> str:
    return "_".join(str(value or "").strip().lower().split())


def _normalized_text(value: Any) -> str:
    text = str(value or "").strip().lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _number_key(value: Any) -> str:
    text = _clean(value)
    if not text:
        return ""
    try:
        parsed = float(text)
    except (TypeError, ValueError):
        return text
    return str(int(parsed)) if parsed.is_integer() else str(parsed)


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in {None, ""}:
            return value
    return ""


def _clean(value: Any) -> str:
    return str(value or "").strip()
