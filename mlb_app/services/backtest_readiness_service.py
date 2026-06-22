from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from mlb_app.services.backtest_dataset_builder_service import BacktestDatasetBuilderService
from mlb_app.services.ml_feature_export_service import DEFAULT_SOURCE, MLFeatureExportService
from mlb_app.services.ml_feature_schema import FEATURE_SCHEMA_VERSION, assert_no_leakage_fields, safe_feature_names

MIN_EXPORT_ROWS = 50
MIN_TRAINING_ROWS = 250
MIN_CLASS_ROWS = 25


class BacktestReadinessService:
    """Score market-level readiness without training or promoting a model."""

    def __init__(
        self,
        *,
        feature_export_service: MLFeatureExportService,
        training_builder_service: BacktestDatasetBuilderService | None = None,
    ) -> None:
        self.feature_export_service = feature_export_service
        self.training_builder_service = training_builder_service

    def evaluate(
        self,
        *,
        date_label: str,
        season: int | None = None,
        source: str = DEFAULT_SOURCE,
    ) -> dict[str, Any]:
        build = self.feature_export_service.build_features(date_label=date_label, season=season, source=source)
        rows_by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
        raw_by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
        warnings: list[str] = list(build.manifest.get("warnings") or [])

        leakage_check_passed = True
        for row in build.rows:
            market = _market(row)
            rows_by_market[market].append(row)
            try:
                assert_no_leakage_fields(row)
            except ValueError as error:
                leakage_check_passed = False
                warnings.append(str(error))

        for row in build.raw_rows:
            raw_by_market[_market(row)].append(row)

        training_by_market, training_warnings = self._training_label_summary(
            date_label=str(build.manifest.get("date") or date_label),
            season=season,
            source=source,
        )
        warnings.extend(training_warnings)

        markets: list[dict[str, Any]] = []
        for market in sorted(set(rows_by_market) | set(raw_by_market)):
            feature_rows = rows_by_market.get(market, [])
            raw_rows = raw_by_market.get(market, [])
            training_summary = training_by_market.get(market, {})
            labels = [_label_from_row(row) for row in raw_rows]
            raw_label_available = any(label is not None for label in labels)
            positive = sum(1 for label in labels if label is True)
            negative = sum(1 for label in labels if label is False)
            if training_summary:
                positive = int(training_summary.get("positive", 0))
                negative = int(training_summary.get("negative", 0))
            row_count = len(feature_rows)
            if training_summary:
                row_count = max(row_count, int(training_summary.get("row_count", 0)))
            two_class_ready = positive > 0 and negative > 0
            coverage = _game_market_coverage_pct(feature_rows)
            completeness = _feature_completeness_pct(feature_rows)
            market_leakage_passed = leakage_check_passed and bool(training_summary.get("leakage_check_passed", True))
            readiness, action, market_warnings = _readiness_for_market(
                row_count=row_count,
                positive=positive,
                negative=negative,
                two_class_ready=two_class_ready,
                game_market_coverage_pct=coverage,
                feature_completeness_pct=completeness,
                leakage_check_passed=market_leakage_passed,
                labels_exist=bool(training_summary) or raw_label_available,
            )
            markets.append(
                {
                    "market": market,
                    "row_count": row_count,
                    "positive_label_count": positive,
                    "negative_label_count": negative,
                    "two_class_ready": two_class_ready,
                    "game_market_coverage_pct": coverage,
                    "feature_completeness_pct": completeness,
                    "leakage_check_passed": market_leakage_passed,
                    "label_row_count": int(training_summary.get("row_count", 0)),
                    "recommended_action": action,
                    "readiness": readiness,
                    "warnings": market_warnings,
                }
            )

        readiness_counts = Counter(row["readiness"] for row in markets)
        return {
            "status": "ok",
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "date": build.manifest.get("date") or date_label,
            "source": build.manifest.get("source") or source,
            "market_count": len(markets),
            "markets": markets,
            "summary": {
                "row_count": len(build.rows),
                "readiness_counts": dict(sorted(readiness_counts.items())),
                "training_candidate_markets": [row["market"] for row in markets if row["readiness"] == "training_candidate"],
                "backtest_ready_markets": [row["market"] for row in markets if row["readiness"] in {"backtest_ready", "training_candidate"}],
            },
            "warnings": _dedupe(warnings)[:25],
        }

    def _training_label_summary(
        self,
        *,
        date_label: str,
        season: int | None,
        source: str,
    ) -> tuple[dict[str, dict[str, Any]], list[str]]:
        if self.training_builder_service is None:
            return {}, []
        try:
            build = self.training_builder_service.build_training_rows(
                date_label=date_label,
                season=season,
                source=source,
                include_ungraded=True,
                dry_run=True,
            )
        except Exception as error:
            return {}, [f"Sprint 13D training labels unavailable for readiness: {type(error).__name__}: {error}"]
        by_market: dict[str, dict[str, Any]] = defaultdict(lambda: {"row_count": 0, "positive": 0, "negative": 0, "leakage_check_passed": True})
        leakage_check_passed = bool(build.manifest.get("leakage_check_passed"))
        for row in build.rows:
            if str(row.get("target_label_status") or "").strip() != "graded":
                continue
            market = _market(row)
            summary = by_market[market]
            summary["row_count"] += 1
            summary["leakage_check_passed"] = leakage_check_passed
            result = str(row.get("target_result") or "").strip().lower()
            hit = _boolish(row.get("target_hit"))
            if result == "win" or hit is True:
                summary["positive"] += 1
            elif result == "loss" or hit is False:
                summary["negative"] += 1
        warnings = [str(item) for item in build.manifest.get("warnings", []) if str(item).strip()]
        return dict(by_market), warnings


def _readiness_for_market(
    *,
    row_count: int,
    positive: int,
    negative: int,
    two_class_ready: bool,
    game_market_coverage_pct: float,
    feature_completeness_pct: float,
    leakage_check_passed: bool,
    labels_exist: bool = False,
) -> tuple[str, str, list[str]]:
    warnings: list[str] = []
    if not leakage_check_passed:
        warnings.append("Leakage check failed; do not backtest or train this market.")
        return "not_ready", "fix_leakage_before_export", warnings
    if row_count < MIN_EXPORT_ROWS:
        warnings.append(f"Only {row_count} feature rows are available; collect at least {MIN_EXPORT_ROWS}.")
        return "not_ready", "collect_more_rows", warnings
    if not labels_exist:
        warnings.append("Feature rows exist, but Sprint 13D labels are not available yet.")
        return "export_ready", "build_player_prop_labels", warnings
    if not two_class_ready:
        warnings.append("Two-class grade labels are not available for this market.")
        return "not_ready", "add_two_class_grade_labels", warnings
    if feature_completeness_pct < 50.0:
        warnings.append("Feature completeness is below the backtest threshold.")
        return "export_ready", "fill_feature_gaps_before_backtest", warnings
    if (
        row_count >= MIN_TRAINING_ROWS
        and positive >= MIN_CLASS_ROWS
        and negative >= MIN_CLASS_ROWS
        and feature_completeness_pct >= 60.0
    ):
        return "training_candidate", "prepare_sprint13d_training_candidate", warnings
    return "backtest_ready", "run_backtest_before_training", warnings


def _feature_completeness_pct(rows: Sequence[Mapping[str, Any]]) -> float:
    if not rows:
        return 0.0
    fields = [field for field in safe_feature_names() if field not in {"feature_schema_version", "exported_at", "source"}]
    total = len(rows) * len(fields)
    if total <= 0:
        return 0.0
    present = 0
    for row in rows:
        for field in fields:
            value = row.get(field)
            if value is not None and value != "" and value != "null":
                present += 1
    return round((present / total) * 100.0, 2)


def _game_market_coverage_pct(rows: Sequence[Mapping[str, Any]]) -> float:
    if not rows:
        return 0.0
    matched = sum(
        1
        for row in rows
        if bool(row.get("game_market_available")) or str(row.get("game_market_enrichment_status") or "").strip() == "matched"
    )
    return round((matched / len(rows)) * 100.0, 2)


def _label_from_row(row: Mapping[str, Any]) -> bool | None:
    profit = _float_or_none(row.get("profit_1u"))
    if profit is not None:
        if profit > 0:
            return True
        if profit < 0:
            return False
    for key in ("result", "grade"):
        text = str(row.get(key) or "").strip().lower()
        if text in {"win", "won", "hit", "cash", "positive", "success", "true", "1"}:
            return True
        if text in {"loss", "lost", "miss", "negative", "failed", "false", "0"}:
            return False
        if text in {"push", "void", "cancelled", "canceled"}:
            return None
    return None


def _float_or_none(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(str(value).replace("+", ""))
    except (TypeError, ValueError):
        return None


def _boolish(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "win"}:
        return True
    if text in {"0", "false", "no", "n", "loss"}:
        return False
    return None


def _market(row: Mapping[str, Any]) -> str:
    return (
        str(
            row.get("feature_market")
            or row.get("meta_market")
            or row.get("market")
            or row.get("market_key")
            or row.get("marketKey")
            or "unknown"
        ).strip()
        or "unknown"
    )


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
