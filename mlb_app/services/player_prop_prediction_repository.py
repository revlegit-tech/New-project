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
from mlb_app.services.player_attribution import apply_attribution, attribution_blocks_context
from mlb_app.services.playerboard_builder import market_capability
from mlb_app.services.prop_side_normalization import normalize_prop_side


UNSCORED_REASON_TRUST_TIERS = {"unscored", "blocked", "unsupported"}
UNSCORED_REASON_FIELDS = (
    "unscoredReason",
    "unscoredReasonDetail",
    "missingPredictionReason",
    "scoringSkipReason",
)
SCORED_REASON_NOISE = {
    "missing_prediction",
    "prediction_join_no_match",
    "skipped_by_model_scoring",
    "unsupported_or_unscored_row",
}


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
            return PredictionJoinResult(rows=[apply_unscored_trust_defaults(row) for row in rows], meta=meta)

        index = _PredictionIndex(predictions)
        enriched_rows: list[dict[str, Any]] = []
        matched = 0
        ambiguous = 0
        blocked_by_attribution = 0
        for row in rows:
            row = apply_attribution(row)
            if attribution_blocks_context(row):
                enriched = apply_unscored_trust_defaults(row)
                warnings = list(enriched.get("predictionWarnings") or [])
                if "context_limited_by_attribution" not in warnings:
                    warnings.append("context_limited_by_attribution")
                enriched["predictionWarnings"] = warnings
                enriched_rows.append(enriched)
                blocked_by_attribution += 1
                continue
            match = index.match(row, date_label=date_label)
            if match.status == "matched" and match.row is not None:
                enriched_rows.append(_apply_prediction(row, match.row, source=source))
                matched += 1
            else:
                enriched = apply_unscored_trust_defaults(row)
                if match.status == "ambiguous":
                    reasons = list(enriched.get("trustReasons") or [])
                    if "ambiguous_prediction_match" not in reasons:
                        reasons.append("ambiguous_prediction_match")
                    enriched["trustReasons"] = reasons
                    enriched["unscoredReason"] = "scoring_skipped"
                enriched_rows.append(enriched)
                if match.status == "ambiguous":
                    ambiguous += 1

        meta["predictionsMatched"] = matched
        meta["predictionsMissing"] = len(rows) - matched - ambiguous
        meta["predictionsAmbiguous"] = ambiguous
        meta["predictionsBlockedByAttribution"] = blocked_by_attribution
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
            "rawModelProbability": _clean(prediction.get("rawModelProbability")),
            "calibratedProbability": _clean(prediction.get("calibratedProbability")),
            "calibrationApplied": _truthy(prediction.get("calibrationApplied")),
            "calibrationMethod": _clean(prediction.get("calibrationMethod")),
            "calibrationStatus": _clean(prediction.get("calibrationStatus")),
            "calibrationArtifactGeneratedAt": _clean(prediction.get("calibrationArtifactGeneratedAt")),
            "calibrationBucket": _clean(prediction.get("calibrationBucket")),
            "calibrationSampleSize": _clean(prediction.get("calibrationSampleSize")),
            "calibrationWarning": _clean(prediction.get("calibrationWarning")),
            "modelVersion": _clean(prediction.get("modelVersion")),
            "modelFamily": _clean(prediction.get("modelFamily")),
            "modelProbabilitySource": _clean(prediction.get("modelProbabilitySource")),
            "probabilityGuardrailStatus": _clean(prediction.get("probabilityGuardrailStatus")),
            "probabilityGuardrailReasons": _split_warnings(prediction.get("probabilityGuardrailReasons")),
            "trustTier": _clean(prediction.get("trustTier")),
            "trustScore": _clean(prediction.get("trustScore")),
            "trustReasons": _split_warnings(prediction.get("trustReasons")),
            "contextReadinessStatus": _clean(prediction.get("contextReadinessStatus")),
            "readyFeatureGroups": _split_warnings(prediction.get("readyFeatureGroups")),
            "partialFeatureGroups": _split_warnings(prediction.get("partialFeatureGroups")),
            "fallbackFeatureGroups": _split_warnings(prediction.get("fallbackFeatureGroups")),
            "missingFeatureGroups": _split_warnings(prediction.get("missingFeatureGroups")),
            "staleFeatureGroups": _split_warnings(prediction.get("staleFeatureGroups")),
            "unsupportedMarketReason": _clean(prediction.get("unsupportedMarketReason")),
            "attributionBlockReason": _clean(prediction.get("attributionBlockReason")),
            "dataFreshnessStatus": _clean(prediction.get("dataFreshnessStatus")),
            "researchOnlyReason": _clean(prediction.get("researchOnlyReason")),
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
            "modelQualityWarnings": _split_warnings(prediction.get("modelQualityWarnings")),
            "productionGateStatus": _clean(prediction.get("productionGateStatus")),
            "productionGateReasons": _split_warnings(prediction.get("productionGateReasons")),
            "productionEligible": _truthy(prediction.get("productionEligible")),
            "betActionAllowed": _truthy(prediction.get("betActionAllowed")),
            "identityConfidence": _clean(prediction.get("identityConfidence")) or _clean(row.get("identityConfidence")),
            "identityWarnings": identity_warnings,
            "playerTeamVerified": _truthy(prediction.get("playerTeamVerified")),
            "opponentVerified": _truthy(prediction.get("opponentVerified")),
            "joinKeyStrength": _clean(prediction.get("joinKeyStrength")) or _clean(row.get("joinKeyStrength")),
            "confidence": "Research",
            "recommendation": "Research",
        }
    )
    return clear_scored_unscored_reasons(enriched)


def apply_unscored_trust_defaults(row: dict[str, Any]) -> dict[str, Any]:
    """Attach an honest low-trust envelope without inventing model output."""
    if _truthy(row.get("predictionMatched")):
        return dict(row)
    enriched = dict(row)
    reason = classify_unscored_reason(enriched)
    trust_tier = _unscored_trust_tier(reason)
    trust_score = _unscored_trust_score(reason)
    trust_reasons = _unique_list(
        [
            *_list_value(enriched.get("trustReasons")),
            "no_model_prediction_available",
            _trust_reason_for_unscored(reason),
        ]
    )
    guardrail_reasons = _unique_list(
        [
            *_list_value(enriched.get("probabilityGuardrailReasons")),
            "model_probability_not_emitted",
            "edge_not_emitted",
            "unsupported_or_unscored_row",
        ]
    )
    warnings = _unique_list(_list_value(enriched.get("predictionWarnings")))
    if "skipped_by_model_scoring" not in warnings:
        warnings.append("skipped_by_model_scoring")

    enriched.update(
        {
            "action": "Research",
            "readinessLabel": "Experimental",
            "modelReadiness": "Experimental",
            "stakeUnits": 0,
            "betActionAllowed": False,
            "predictionMatched": False,
            "predictionKey": _clean(enriched.get("predictionKey")),
            "predictionSource": _clean(enriched.get("predictionSource")),
            "predictionWarnings": warnings,
            "modelProbabilityPercent": "",
            "rawModelProbability": "",
            "calibratedProbability": "",
            "edgePercent": "",
            "fairOdds": "",
            "expectedValue": "",
            "calibrationApplied": False,
            "calibrationMethod": "",
            "calibrationStatus": _clean(enriched.get("calibrationStatus")) or "not_applicable",
            "calibrationBucket": None,
            "calibrationSampleSize": None,
            "calibrationWarning": _clean(enriched.get("calibrationWarning")) or "no_calibration_applied_for_unscored_row",
            "modelProbabilitySource": _clean(enriched.get("modelProbabilitySource")) or "none",
            "probabilityGuardrailStatus": _clean(enriched.get("probabilityGuardrailStatus")) or _guardrail_status_for_unscored(reason),
            "probabilityGuardrailReasons": guardrail_reasons,
            "trustTier": _clean(enriched.get("trustTier")) or trust_tier,
            "trustScore": enriched.get("trustScore") if _clean(enriched.get("trustScore")) else trust_score,
            "trustReasons": trust_reasons,
            "contextReadinessStatus": _clean(enriched.get("contextReadinessStatus")) or _context_status_for_unscored(reason),
            "readyFeatureGroups": _list_value(enriched.get("readyFeatureGroups")),
            "partialFeatureGroups": _list_value(enriched.get("partialFeatureGroups")),
            "fallbackFeatureGroups": _list_value(enriched.get("fallbackFeatureGroups")),
            "missingFeatureGroups": _list_value(enriched.get("missingFeatureGroups")),
            "staleFeatureGroups": _list_value(enriched.get("staleFeatureGroups")),
            "unsupportedMarketReason": _unsupported_market_reason(enriched, reason),
            "attributionBlockReason": _attribution_block_reason(enriched, reason),
            "unscoredReasonDetail": _unscored_reason_detail(enriched, reason),
            "scoringSkipReason": _scoring_skip_reason(enriched, reason),
            "missingPredictionReason": _missing_prediction_reason(enriched, reason),
            "dataFreshnessStatus": _clean(enriched.get("dataFreshnessStatus")) or "unknown",
            "researchOnlyReason": _clean(enriched.get("researchOnlyReason")) or "research_only_unscored_row",
            "unscoredReason": reason,
            "confidence": _clean(enriched.get("confidence")) or "Research",
            "recommendation": _clean(enriched.get("recommendation")) or "Research",
        }
    )
    return clear_scored_unscored_reasons(enriched)


def clear_scored_unscored_reasons(row: dict[str, Any]) -> dict[str, Any]:
    """Hide unscored-only metadata once a row is in a scored/trusted tier."""
    enriched = dict(row)
    trust_tier = _clean(enriched.get("trustTier")).lower()
    if trust_tier in UNSCORED_REASON_TRUST_TIERS:
        return enriched

    for field in UNSCORED_REASON_FIELDS:
        enriched[field] = ""
    for field in ("trustReasons", "probabilityGuardrailReasons", "predictionWarnings"):
        values = _list_value(enriched.get(field))
        if values:
            enriched[field] = [value for value in values if _clean(value) not in SCORED_REASON_NOISE]
    return enriched


def classify_unscored_reason(row: dict[str, Any]) -> str:
    existing = _clean(row.get("unscoredReason"))
    if existing:
        return existing
    if _clean(_first(row, "scoringSkipReason", "skipReason")):
        return "scoring_skipped"
    if _clean(row.get("calibrationSkipReason")):
        return "missing_calibration"
    scope = _clean(row.get("trustCoverageScope") or row.get("scope")).lower()
    if scope in {"outside_active_slate", "season_row_not_active_slate"}:
        return "season_row_not_active_slate"
    if _clean(row.get("outsideActiveSlate")).lower() in {"1", "true", "yes", "y"}:
        return "outside_active_slate"
    status = _clean(_first(row, "attributionStatus", "attribution_status")).lower()
    if status in {"invalid_player_label", "conflict", "ambiguous"} or attribution_blocks_context(row):
        return "invalid_attribution"
    if status == "inferred_low_confidence" or _clean(row.get("identityConfidence")).lower() == "weak":
        return "inferred_low_confidence"
    if _clean(row.get("unsupportedMarketReason")):
        return "unsupported_market"
    if market_capability(row.get("market")) == "unsupported_skip":
        return "unsupported_market"
    side = _side_key(row)
    if not side:
        return "unsupported_side"
    if _line_missing_or_invalid(row):
        return "unsupported_line"
    if _missing_book(row):
        return "missing_book"
    if _missing_odds(row):
        return "missing_odds"
    if _clean(row.get("calibrationStatus")).lower() in {"missing", "not_available"}:
        return "missing_calibration"
    if _clean(row.get("modelPath")).lower() in {"missing", "not_available"}:
        return "missing_model"
    if row.get("predictionMatched") is False:
        if _clean(_first(row, "scoringSkipReason", "skipReason")):
            return "scoring_skipped"
        return "missing_prediction"
    if _clean(row.get("predictionSource")).lower() in {"missing", "not_available", "none"}:
        return "missing_prediction"
    return "missing_prediction"


def _unscored_trust_tier(reason: str) -> str:
    if reason == "unsupported_market":
        return "unsupported"
    if reason in {"invalid_attribution", "missing_odds", "missing_book", "unsupported_side", "unsupported_line"}:
        return "blocked"
    if reason == "inferred_low_confidence":
        return "low"
    return "unscored"


def _unscored_trust_score(reason: str) -> int:
    if reason == "unsupported_market":
        return 0
    if reason in {"invalid_attribution", "missing_odds", "missing_book", "unsupported_side", "unsupported_line"}:
        return 0
    if reason == "inferred_low_confidence":
        return 20
    return 10


def _trust_reason_for_unscored(reason: str) -> str:
    mapping = {
        "unsupported_market": "unsupported_market",
        "unsupported_side": "unsupported_side",
        "unsupported_line": "unsupported_line",
        "missing_odds": "missing_odds",
        "missing_book": "missing_book",
        "invalid_attribution": "attribution_blocked",
        "inferred_low_confidence": "inferred_low_confidence",
        "missing_model": "missing_model",
        "missing_prediction": "missing_prediction",
        "missing_calibration": "missing_calibration",
        "scoring_skipped": "skipped_by_model_scoring",
        "outside_active_slate": "outside_active_slate",
        "season_row_not_active_slate": "season_row_not_active_slate",
    }
    return mapping.get(reason, "unknown_unscored")


def _guardrail_status_for_unscored(reason: str) -> str:
    return "blocked" if reason not in {"unknown_unscored"} else "not_applicable"


def _context_status_for_unscored(reason: str) -> str:
    if reason in {"invalid_attribution", "unsupported_market", "missing_odds", "missing_book", "unsupported_side", "unsupported_line"}:
        return "blocked"
    if reason == "inferred_low_confidence":
        return "limited"
    return "unknown"


def _unscored_reason_detail(row: dict[str, Any], reason: str) -> str:
    existing = _clean(row.get("unscoredReasonDetail"))
    if existing:
        return existing
    if reason == "missing_prediction":
        return "No matching model prediction row was found for this board row."
    if reason == "scoring_skipped":
        return _clean(_first(row, "scoringSkipReason", "skipReason")) or "Model scoring skipped this row."
    if reason == "unsupported_market":
        return _unsupported_market_reason(row, reason)
    if reason == "invalid_attribution":
        return _attribution_block_reason(row, reason)
    if reason in {"outside_active_slate", "season_row_not_active_slate"}:
        return "Row is outside the active playerboard date/snapshot scope."
    return reason


def _scoring_skip_reason(row: dict[str, Any], reason: str) -> str:
    existing = _clean(_first(row, "scoringSkipReason", "skipReason"))
    if existing:
        return existing
    return "ambiguous_prediction_match" if reason == "scoring_skipped" else ""


def _missing_prediction_reason(row: dict[str, Any], reason: str) -> str:
    existing = _clean(row.get("missingPredictionReason"))
    if existing:
        return existing
    if reason == "missing_prediction":
        return "prediction_join_no_match"
    return ""


def _unsupported_market_reason(row: dict[str, Any], reason: str) -> str:
    existing = _clean(row.get("unsupportedMarketReason"))
    if existing:
        return existing
    if reason == "unsupported_market":
        market = _clean(row.get("market")) or "unknown_market"
        return f"unsupported_market:{market}"
    return ""


def _attribution_block_reason(row: dict[str, Any], reason: str) -> str:
    existing = _clean(row.get("attributionBlockReason"))
    if existing:
        return existing
    if reason == "invalid_attribution":
        return _clean(row.get("attributionStatus")) or "invalid_attribution"
    return ""


def _line_missing_or_invalid(row: dict[str, Any]) -> bool:
    line = _first(row, "line", "sportsbook_line", "prop_line")
    text = _clean(line)
    if not text:
        return True
    try:
        float(text)
    except (TypeError, ValueError):
        return True
    return False


def _missing_book(row: dict[str, Any]) -> bool:
    return not _clean(_first(row, "bookKey", "book_key", "sportsbookKey", "sportsbook_key", "book", "sportsbook", "bestBook", "selectedBook"))


def _missing_odds(row: dict[str, Any]) -> bool:
    return not _clean(_first(row, "americanOdds", "american_odds", "odds", "price", "bestAmericanOdds", "selectedBookAmericanOdds"))


def _unique_list(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _clean(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _list_value(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    raw = _clean(value)
    if not raw:
        return []
    return [part.strip() for part in re.split(r"[|;]", raw) if part.strip()]


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
    return _split_warnings(raw)


def _split_warnings(value: Any) -> list[str]:
    raw = _clean(value)
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
