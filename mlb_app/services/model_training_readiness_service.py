from __future__ import annotations

import csv
import importlib.util
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.contracts.feature_store_schema import postgame_label_names
from mlb_app.services.data_source_capability_service import (
    DEFAULT_BASELINE_LABEL_ROWS,
    DEFAULT_PRODUCTION_LABEL_ROWS_PER_MARKET,
    DataSourceCapabilityService,
    resolve_date_mode,
)
from mlb_app.services.feature_store_materializer import FeatureStoreMaterializer
from mlb_app.services.runtime_status_service import safe_relpath

SCHEMA_VERSION = "model-training-readiness.v1"
ALLOWED_MODEL_STATES = (
    "unavailable",
    "research_only",
    "baseline_ready",
    "baseline_trained",
    "calibration_needed",
    "backtest_needed",
    "production_eligible",
)


class ModelTrainingReadinessService:
    """Read-only training gate evaluator. It never trains models."""

    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings
        self.baseline_min_rows = _int_from_env("MLB_BASELINE_LABEL_MIN_ROWS", DEFAULT_BASELINE_LABEL_ROWS)
        self.production_min_rows_per_market = _int_from_env(
            "MLB_PRODUCTION_LABEL_MIN_ROWS_PER_MARKET",
            DEFAULT_PRODUCTION_LABEL_ROWS_PER_MARKET,
        )
        self.capabilities = DataSourceCapabilityService(settings)
        self.materializer = FeatureStoreMaterializer(settings)

    def payload(self, *, date_label: str | None = None, season: int | None = None, market: str | None = None) -> dict[str, Any]:
        target_date, mode = resolve_date_mode(date_label)
        selected_season = int(season or self.settings.current_season)
        feature_path = self.materializer.feature_path(target_date)
        leakage = self._leakage_check(feature_path)
        capability_audit = self.capabilities.audit_feature_availability(target_date, selected_season)
        missing_critical = list(capability_audit.get("missingCriticalFeatureGroups") or [])
        calibration_available = self._has_artifacts("calibration")
        backtest_available = self._has_artifacts("backtests")
        label_files = self._label_files(selected_season, target_date)
        market_rows = self._market_rows(label_files)
        selected_market = str(market or "").strip()
        if selected_market:
            market_rows = {key: value for key, value in market_rows.items() if key == selected_market}

        markets = [
            self._market_payload(
                market_name=name,
                counts=counts,
                feature_matrix_exists=feature_path.is_file(),
                leakage_ok=leakage["ok"],
                calibration_available=calibration_available,
                backtest_available=backtest_available,
                missing_critical=missing_critical,
            )
            for name, counts in sorted(market_rows.items())
        ]
        ready_baseline = any(item["baselineEligible"] for item in markets)
        ready_production = any(item["productionEligible"] for item in markets)
        model_state = self._model_state(
            xgboost_available=_xgboost_available(),
            ready_baseline=ready_baseline,
            ready_production=ready_production,
            calibration_available=calibration_available,
            backtest_available=backtest_available,
        )
        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": "ok",
            "date": target_date,
            "season": selected_season,
            "resolvedDateMode": mode,
            "readyForBaselineTraining": ready_baseline,
            "readyForProductionTraining": ready_production,
            "eligibleBaselineMarkets": [item["market"] for item in markets if item["baselineEligible"]],
            "eligibleProductionMarkets": [item["market"] for item in markets if item["productionEligible"]],
            "modelTrainingTriggered": False,
            "externalApiCallsMade": False,
            "xgboostAvailable": _xgboost_available(),
            "modelState": model_state,
            "allowedModelStates": list(ALLOWED_MODEL_STATES),
            "featureMatrix": {
                "exists": feature_path.is_file(),
                "path": safe_relpath(feature_path, self.settings.root_dir),
                "leakagePolicyOk": leakage["ok"],
                "blockedFieldsFound": leakage["blockedFieldsFound"],
            },
            "validation": {
                "baselineMinRows": self.baseline_min_rows,
                "productionMinRowsPerMarket": self.production_min_rows_per_market,
                "calibrationArtifactsAvailable": calibration_available,
                "backtestArtifactsAvailable": backtest_available,
                "missingCriticalFeatureGroups": missing_critical,
            },
            "labelArtifacts": [safe_relpath(path, self.settings.root_dir) for path in label_files],
            "markets": markets,
            "warnings": self._warnings(markets, feature_path, leakage, calibration_available, backtest_available, missing_critical),
        }

    def _market_payload(
        self,
        *,
        market_name: str,
        counts: dict[str, int],
        feature_matrix_exists: bool,
        leakage_ok: bool,
        calibration_available: bool,
        backtest_available: bool,
        missing_critical: list[str],
    ) -> dict[str, Any]:
        label_rows = counts["labelRows"]
        two_class = counts["hitRows"] > 0 and counts["missRows"] > 0
        reasons: list[str] = []
        if label_rows < self.baseline_min_rows:
            reasons.append(f"Label rows below baseline threshold: {label_rows} < {self.baseline_min_rows}.")
        if not two_class:
            reasons.append("Two-class target validation is not satisfied for this market.")
        if not feature_matrix_exists:
            reasons.append("Pregame feature matrix is missing.")
        if not leakage_ok and feature_matrix_exists:
            reasons.append("Feature matrix contains postgame label/outcome fields.")
        elif not leakage_ok:
            reasons.append("Leakage policy cannot be verified until the feature matrix exists.")
        baseline = bool(label_rows >= self.baseline_min_rows and two_class and feature_matrix_exists and leakage_ok)
        if label_rows < self.production_min_rows_per_market:
            reasons.append(f"Label rows below production market threshold: {label_rows} < {self.production_min_rows_per_market}.")
        if not calibration_available:
            reasons.append("Calibration artifacts are missing.")
        if not backtest_available:
            reasons.append("Backtest artifacts are missing.")
        if missing_critical:
            reasons.append(f"Critical feature groups are missing: {', '.join(missing_critical)}.")
        production = bool(
            baseline
            and label_rows >= self.production_min_rows_per_market
            and calibration_available
            and backtest_available
            and not missing_critical
        )
        return {
            "market": market_name,
            "labelRows": label_rows,
            "hitRows": counts["hitRows"],
            "missRows": counts["missRows"],
            "pushRows": counts["pushRows"],
            "voidRows": counts["voidRows"],
            "twoClassTarget": two_class,
            "baselineEligible": baseline,
            "productionEligible": production,
            "reasons": reasons,
        }

    def _label_files(self, season: int, date_label: str) -> list[Path]:
        patterns = [
            self.settings.data_dir / "labels" / f"*{season}*.csv",
            self.settings.data_dir / "training" / f"*{season}*.csv",
            self.settings.data_dir / "warehouse" / "normalized" / "actionnetwork" / f"*labels*{date_label}*.csv",
        ]
        files: list[Path] = []
        for pattern in patterns:
            if pattern.parent.exists():
                files.extend(path for path in pattern.parent.glob(pattern.name) if path.is_file())
        return sorted(set(files))

    def _market_rows(self, label_files: list[Path]) -> dict[str, dict[str, int]]:
        counts: dict[str, dict[str, int]] = defaultdict(lambda: {"labelRows": 0, "hitRows": 0, "missRows": 0, "pushRows": 0, "voidRows": 0})
        for path in label_files:
            try:
                with path.open("r", encoding="utf-8-sig", newline="") as handle:
                    for row in csv.DictReader(handle):
                        market = _clean(row.get("market") or row.get("baseMarket") or row.get("prop_market")) or "unknown"
                        bucket = counts[market]
                        bucket["labelRows"] += 1
                        status = _label_status(row)
                        if status == "hit":
                            bucket["hitRows"] += 1
                        elif status == "miss":
                            bucket["missRows"] += 1
                        elif status == "push":
                            bucket["pushRows"] += 1
                        elif status == "void":
                            bucket["voidRows"] += 1
            except Exception:
                continue
        return dict(counts)

    def _leakage_check(self, feature_path: Path) -> dict[str, Any]:
        if not feature_path.is_file():
            return {"ok": False, "blockedFieldsFound": []}
        try:
            with feature_path.open("r", encoding="utf-8-sig", newline="") as handle:
                header = next(csv.reader(handle), [])
        except Exception:
            return {"ok": False, "blockedFieldsFound": []}
        blocked = sorted(set(header).intersection(postgame_label_names()))
        return {"ok": not blocked, "blockedFieldsFound": blocked}

    def _has_artifacts(self, kind: str) -> bool:
        directories = [self.settings.data_dir / kind]
        if kind == "calibration":
            directories.extend([self.settings.model_dir, self.settings.data_dir / "models"])
        patterns = ("*.json", "*.csv")
        return any(path.is_file() for directory in directories if directory.exists() for pattern in patterns for path in directory.glob(pattern))

    def _warnings(
        self,
        markets: list[dict[str, Any]],
        feature_path: Path,
        leakage: dict[str, Any],
        calibration_available: bool,
        backtest_available: bool,
        missing_critical: list[str],
    ) -> list[str]:
        warnings: list[str] = []
        if not feature_path.is_file():
            warnings.append("Pregame feature matrix is missing; baseline training remains disabled.")
        if not leakage.get("ok"):
            warnings.append("Leakage policy is not satisfied for the feature matrix.")
        if not any(item["baselineEligible"] for item in markets):
            warnings.append("No market currently satisfies baseline training gates.")
        if not calibration_available:
            warnings.append("Production training requires calibration artifacts.")
        if not backtest_available:
            warnings.append("Production training requires backtest artifacts.")
        if missing_critical:
            warnings.append(f"Production training blocked by missing critical feature groups: {', '.join(missing_critical)}.")
        return warnings

    @staticmethod
    def _model_state(
        *,
        xgboost_available: bool,
        ready_baseline: bool,
        ready_production: bool,
        calibration_available: bool,
        backtest_available: bool,
    ) -> str:
        if not xgboost_available:
            return "unavailable"
        if ready_production:
            return "production_eligible"
        if ready_baseline and not calibration_available:
            return "calibration_needed"
        if ready_baseline and not backtest_available:
            return "backtest_needed"
        if ready_baseline:
            return "baseline_ready"
        return "research_only"


def _label_status(row: dict[str, Any]) -> str:
    hit = _clean(row.get("hit") or row.get("target") or row.get("is_hit")).lower()
    result = _clean(row.get("result") or row.get("outcome") or row.get("status") or row.get("label")).lower()
    if hit in {"1", "true", "yes", "hit", "win", "won"} or result in {"hit", "win", "won", "over"}:
        return "hit"
    if hit in {"0", "false", "no", "miss", "loss", "lost"} or result in {"miss", "loss", "lost", "under"}:
        return "miss"
    if result == "push":
        return "push"
    if result in {"void", "cancelled", "canceled", "no_action"}:
        return "void"
    return "void"


def _xgboost_available() -> bool:
    return importlib.util.find_spec("xgboost") is not None


def _int_from_env(name: str, fallback: int) -> int:
    raw = os.environ.get(name, "")
    try:
        return int(str(raw).strip()) if str(raw).strip() else fallback
    except (TypeError, ValueError):
        return fallback


def _clean(value: Any) -> str:
    return str(value or "").strip()
