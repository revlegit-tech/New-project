from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.player_prop_identity_confidence import parse_identity_warnings
from mlb_app.services.prop_side_normalization import normalize_prop_side


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

    def summary_path(self, date_label: str) -> Path:
        return self.settings.data_dir / "predictions" / f"prop_predictions_{date_label}_summary.json"

    def join_predictions(self, rows: list[dict[str, Any]], *, date_label: str) -> PredictionJoinResult:
        requested_date = _clean(date_label)
        path = self.prediction_path(date_label)
        summary_path = self.summary_path(date_label)
        summary = self._load_summary(summary_path)
        raw_predictions = self._load_predictions(path)
        predictions = [row for row in raw_predictions if _clean(row.get("date")) == requested_date]
        rejected_date_mismatch = len(raw_predictions) - len(predictions)
        summary_date = _clean(summary.get("date"))
        summary_date_mismatch = bool(summary_date and summary_date != requested_date)
        if summary_date_mismatch:
            predictions = []
            rejected_date_mismatch = len(raw_predictions)
        source = str(path)
        by_market = Counter(_clean(row.get("market")) or "unknown" for row in predictions)
        meta: dict[str, Any] = {
            "predictionsLoaded": len(predictions),
            "predictionsFileRows": len(raw_predictions),
            "predictionsMatched": 0,
            "predictionsMissing": len(rows),
            "predictionsAmbiguous": 0,
            "predictionsRejectedDateMismatch": rejected_date_mismatch,
            "predictionDate": requested_date,
            "predictionSummaryDate": summary_date,
            "predictionSummaryPath": str(summary_path) if summary_path.is_file() else "",
            "predictionSource": source if path.is_file() else "",
            "predictionGeneratedAt": _clean(_first(summary, "generatedAt", "generated_at")),
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

    @staticmethod
    def _load_summary(path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}


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
    identity_warnings = parse_identity_warnings(prediction.get("identityWarnings"))
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
            "identityConfidence": _clean(prediction.get("identityConfidence")) or _clean(row.get("identityConfidence")),
            "identityWarnings": identity_warnings,
            "playerTeamVerified": _truthy(prediction.get("playerTeamVerified")),
            "opponentVerified": _truthy(prediction.get("opponentVerified")),
            "joinKeyStrength": _clean(prediction.get("joinKeyStrength")) or _clean(row.get("joinKeyStrength")),
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
    return normalize_prop_side(
        row.get("side"),
        _first(row, "rawLabel", "raw_label"),
        _first(row, "label", "title", "name"),
        _first(row, "outcome", "outcomeName", "outcome_name", "selection", "pickSide"),
    )


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


def _truthy(value: Any) -> bool:
    return _clean(value).lower() in {"1", "true", "yes", "y", "verified"}
