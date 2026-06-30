from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.player_prop_model_runtime import to_float
from mlb_app.services.prop_side_normalization import normalize_prop_side


MIN_BACKTEST_SAMPLE_SIZE = 200
MIN_FEATURE_COVERAGE = 0.70
MIN_EDGE_PERCENT = 1.0
MAX_ABS_EDGE_PERCENT = 35.0
MIN_PROBABILITY = 0.03
MAX_PROBABILITY = 0.97
MAX_PREDICTION_AGE_DAYS = 1
MAX_ODDS_AGE_SECONDS = 15 * 60
QUALITY_WARNING_KEYWORDS = (
    "critical",
    "all-null",
    "missing critical",
    "market mismatch",
    "sample size below minimum",
    "unsafe_prediction_join_key",
)


@dataclass(frozen=True)
class ProductionGateResult:
    productionGateStatus: str
    productionGateReasons: list[str]
    productionEligible: bool
    betActionAllowed: bool

    def to_row(self) -> dict[str, Any]:
        return {
            "productionGateStatus": self.productionGateStatus,
            "productionGateReasons": list(self.productionGateReasons),
            "productionEligible": self.productionEligible,
            "betActionAllowed": self.betActionAllowed,
        }


class PlayerPropProductionGateService:
    """Hard production gates for MLB player prop model outputs.

    This service only reports eligibility. Existing callers still keep action
    labels research-only and stakes at zero.
    """

    def __init__(self, *, settings: Settings = default_settings) -> None:
        self.settings = settings
        self._backtest_cache: dict[int, dict[str, Any]] = {}

    def evaluate(
        self,
        row: dict[str, Any],
        *,
        season: int | None = None,
        date_label: str | None = None,
        model_feature_warnings: list[str] | None = None,
    ) -> ProductionGateResult:
        reasons: list[str] = []
        if row.get("predictionMatched") is False:
            reasons.append("prediction_not_matched")

        identity = _clean(row.get("identityConfidence")).lower() or "unknown"
        if identity != "strong":
            reasons.append(f"identity_confidence_{identity}")

        side = normalize_prop_side(
            row.get("side"),
            row.get("rawLabel") or row.get("raw_label"),
            row.get("label") or row.get("title") or row.get("name"),
            row.get("outcome") or row.get("selection") or row.get("pickSide"),
        )
        if not side:
            reasons.append("missing_side")

        calibration_status = _clean(row.get("calibrationStatus")).lower()
        if calibration_status != "applied":
            reasons.append(f"calibration_{calibration_status or 'missing'}")

        feature_coverage = _feature_coverage(row)
        if feature_coverage is not None and feature_coverage < MIN_FEATURE_COVERAGE:
            reasons.append("feature_completeness_insufficient")
        if _truthy(row.get("hasCriticalMissingData")):
            reasons.append("critical_feature_data_missing")
        for group in _list_value(row.get("missingFeatureGroups")):
            if group:
                reasons.append(f"missing_feature_group_{group}")

        if _is_prediction_stale(row, date_label=date_label):
            reasons.append("prediction_stale")

        odds_reason = _odds_freshness_reason(row)
        if odds_reason:
            reasons.append(odds_reason)

        market = _clean(row.get("market"))
        backtest = _market_backtest(market, row, self._backtest_summary(season))
        sample_size = int(to_float(backtest.get("sampleSize"), 0.0) or 0)
        if sample_size < MIN_BACKTEST_SAMPLE_SIZE:
            reasons.append("backtest_sample_size_below_threshold")
        calibration_error = to_float(backtest.get("calibrationError"), None)
        if calibration_error is not None and calibration_error > 0.08:
            reasons.append("backtest_calibration_error_high")
        brier_score = to_float(backtest.get("brierScore"), None)
        if brier_score is not None and brier_score > 0.30:
            reasons.append("backtest_brier_score_high")

        probability = _probability_value(row)
        if probability is None or probability <= MIN_PROBABILITY or probability >= MAX_PROBABILITY:
            reasons.append("probability_outside_sanity_bounds")

        edge = to_float(row.get("edgePercent"), None)
        if edge is None or edge < MIN_EDGE_PERCENT:
            reasons.append("edge_below_threshold")
        elif abs(edge) > MAX_ABS_EDGE_PERCENT:
            reasons.append("edge_outside_sanity_bounds")

        for warning in [*_list_value(row.get("modelQualityWarnings")), *(model_feature_warnings or [])]:
            if _quality_warning_is_blocking(warning):
                reasons.append(f"blocking_model_warning:{warning}")

        deduped_reasons = _unique(reasons)
        eligible = not deduped_reasons
        enabled = bool(getattr(self.settings, "enable_bet_actions", False))
        return ProductionGateResult(
            productionGateStatus="closed" if eligible and enabled else "eligible_not_enabled" if eligible else "blocked",
            productionGateReasons=deduped_reasons,
            productionEligible=eligible,
            betActionAllowed=eligible and enabled,
        )

    @staticmethod
    def research_only(reason: str = "no_modeled_prediction") -> ProductionGateResult:
        return ProductionGateResult(
            productionGateStatus="research_only",
            productionGateReasons=[reason],
            productionEligible=False,
            betActionAllowed=False,
        )

    def _backtest_summary(self, season: int | None) -> dict[str, Any]:
        selected_season = int(season or self.settings.current_season)
        if selected_season not in self._backtest_cache:
            path = self.settings.data_dir / "backtests" / f"player_prop_model_backtest_summary_{selected_season}.json"
            self._backtest_cache[selected_season] = _read_json(path)
        return self._backtest_cache[selected_season]


def _market_backtest(market: str, row: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    direct = row.get("backtest") if isinstance(row.get("backtest"), dict) else {}
    if direct:
        return direct
    markets = summary.get("markets") if isinstance(summary.get("markets"), dict) else {}
    payload = markets.get(market) if isinstance(markets.get(market), dict) else {}
    return payload


def _feature_coverage(row: dict[str, Any]) -> float | None:
    for key in ("featureCoverage", "featureCompleteness", "modelFeatureCoverage"):
        value = to_float(row.get(key), None)
        if value is not None:
            return value if value <= 1 else value / 100.0
    return None


def _probability_value(row: dict[str, Any]) -> float | None:
    for key in ("calibratedProbability", "rawModelProbability"):
        value = to_float(row.get(key), None)
        if value is not None:
            return value if value <= 1 else value / 100.0
    percent = to_float(row.get("modelProbabilityPercent"), None)
    return None if percent is None else percent / 100.0


def _is_prediction_stale(row: dict[str, Any], *, date_label: str | None) -> bool:
    row_date = _clean(row.get("date") or row.get("predictionDate"))
    if date_label and row_date and row_date != date_label:
        return True
    generated_at = _parse_datetime(row.get("predictionGeneratedAt") or row.get("generatedAt"))
    if generated_at is None:
        return False
    reference = _parse_date(date_label) if date_label else date.today()
    return generated_at.date() < reference and (reference - generated_at.date()).days > MAX_PREDICTION_AGE_DAYS


def _odds_freshness_reason(row: dict[str, Any]) -> str:
    odds = _clean(row.get("americanOdds") or row.get("american_odds") or row.get("odds") or row.get("price"))
    if not odds:
        return "odds_missing"
    status = _clean(row.get("oddsFreshnessStatus") or row.get("actionnetworkStatus")).lower()
    if status and ("stale" in status or "missing" in status):
        return "odds_stale_or_missing"
    age = to_float(row.get("oddsAgeSeconds") or row.get("oddsSnapshotAgeSeconds"), None)
    if age is not None and age > MAX_ODDS_AGE_SECONDS:
        return "odds_stale_or_missing"
    return ""


def _quality_warning_is_blocking(warning: str) -> bool:
    raw = _clean(warning).lower()
    return bool(raw and any(keyword in raw for keyword in QUALITY_WARNING_KEYWORDS))


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _list_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    raw = _clean(value)
    if not raw:
        return []
    return [part.strip() for part in raw.replace(";", "|").split("|") if part.strip()]


def _parse_datetime(value: Any) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _parse_date(value: str | None) -> date:
    try:
        return date.fromisoformat(_clean(value))
    except ValueError:
        return date.today()


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
