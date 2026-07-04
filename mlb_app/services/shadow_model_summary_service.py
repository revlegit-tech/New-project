from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.repositories.model_store import normalize_market_key
from mlb_app.services.model_registry_service import ModelRegistryService

SHADOW_MODEL_STAGE = "shadow"
SHADOW_MODEL_KEY = "calibrated_logistic"
SHADOW_MARKETS: tuple[str, ...] = (
    "batter_hits",
    "batter_home_runs",
    "batter_rbis",
    "batter_total_bases",
)


class ShadowModelSummaryService:
    """Read-only audit surface for Sprint 19 shadow model artifacts."""

    def __init__(
        self,
        settings: Settings = default_settings,
        *,
        registry_service: ModelRegistryService | None = None,
    ) -> None:
        self.settings = settings
        self.registry_service = registry_service or ModelRegistryService(settings=settings)

    def payload(self, *, market: str | None = None) -> dict[str, Any]:
        requested = [normalize_market_key(market)] if market else list(SHADOW_MARKETS)
        registry = self.registry_service.load_registry()
        summaries = [self.summary_for_market(selected, registry=registry) for selected in requested]
        return {
            "status": "ok",
            "modelStage": SHADOW_MODEL_STAGE,
            "modelKey": SHADOW_MODEL_KEY,
            "markets": summaries,
            "marketCount": len(summaries),
            "readyMarketCount": sum(1 for row in summaries if row.get("artifactStatus") == "ready"),
            "warnings": _dedupe([warning for row in summaries for warning in row.get("warnings", [])]),
            "policy": {
                "researchOnly": True,
                "productionPromotion": False,
                "action": "Research",
                "readinessLabel": "Experimental",
                "stakeUnits": 0,
                "betActionAllowed": False,
            },
        }

    def summary_for_market(self, market: str, *, registry: dict[str, Any] | None = None) -> dict[str, Any]:
        key = normalize_market_key(market)
        registry = registry if registry is not None else self.registry_service.load_registry()
        artifact_dir = self.artifact_dir(key)
        backtest_path = artifact_dir / "backtest_metrics.json"
        calibration_path = artifact_dir / "calibration.json"
        manifest_path = artifact_dir / "shadow_manifest.json"
        backtest = _read_json(backtest_path)
        calibration = _read_json(calibration_path)
        manifest = _read_json(manifest_path)
        registry_shadow = _registry_shadow_entry(registry, key)
        warnings: list[str] = []

        if backtest_path.is_file() or calibration_path.is_file() or manifest_path.is_file():
            warnings.append("Using Sprint 19 shadow calibrated_logistic artifacts.")
        else:
            warnings.append("Sprint 19 shadow calibrated_logistic artifacts are missing for this market.")
        if not backtest_path.is_file():
            warnings.append("Shadow backtest artifact is missing; metrics are not fabricated.")
        if not calibration_path.is_file():
            warnings.append("Shadow calibration artifact is missing; calibration metrics are not fabricated.")
        if not manifest_path.is_file():
            warnings.append("Shadow manifest artifact is missing.")
        if registry_shadow:
            warnings.append("Registry contains a shadow calibrated_logistic pointer for this market.")
        else:
            warnings.append("Registry shadow pointer is missing; artifact summary is file-based only.")
        warnings.extend(_strings(backtest.get("warnings")))
        warnings.extend(_strings(calibration.get("warnings")))
        warnings.extend(_strings(manifest.get("warnings")))

        artifact_status = "ready" if backtest_path.is_file() and calibration_path.is_file() else "missing"
        if artifact_status == "missing" and (backtest_path.is_file() or calibration_path.is_file() or manifest_path.is_file()):
            artifact_status = "partial"

        generated_at = _first_text(backtest, calibration, manifest, "generatedAt")
        return {
            "market": key,
            "modelStage": SHADOW_MODEL_STAGE,
            "modelKey": SHADOW_MODEL_KEY,
            "version": str(registry_shadow.get("version") or manifest.get("version") or ""),
            "artifactStatus": artifact_status,
            "artifactPath": _public_path(self.settings.root_dir, Path(str(registry_shadow.get("artifact") or ""))) if registry_shadow.get("artifact") else "",
            "artifactDir": _public_path(self.settings.root_dir, artifact_dir),
            "backtestPath": _public_path(self.settings.root_dir, backtest_path),
            "calibrationPath": _public_path(self.settings.root_dir, calibration_path),
            "manifestPath": _public_path(self.settings.root_dir, manifest_path),
            "evaluatedRows": _int(backtest.get("evaluatedRows")),
            "positiveRows": _int(backtest.get("positiveRows") or registry_shadow.get("positive_rows") or registry_shadow.get("positiveRows")),
            "negativeRows": _int(backtest.get("negativeRows") or registry_shadow.get("negative_rows") or registry_shadow.get("negativeRows")),
            "auc": _float(backtest.get("auc")),
            "brierScore": _float(backtest.get("brierScore") or calibration.get("brierScore")),
            "logLoss": _float(backtest.get("logLoss") or calibration.get("logLoss")),
            "expectedCalibrationError": _float(calibration.get("expectedCalibrationError")),
            "validationDates": [str(value) for value in backtest.get("validationDates", [])] if isinstance(backtest.get("validationDates"), list) else [],
            "generatedAt": generated_at,
            "readinessLabel": "Experimental",
            "action": "Research",
            "stakeUnits": 0,
            "betActionAllowed": False,
            "backtestStatus": str(manifest.get("backtestStatus") or ("ready" if backtest_path.is_file() else "missing")),
            "calibrationStatus": str(manifest.get("calibrationStatus") or ("ready" if calibration_path.is_file() else "missing")),
            "sourcePath": _public_source_path(backtest.get("sourcePath") or calibration.get("sourcePath") or manifest.get("sourcePath")),
            "provenance": {
                "artifactFamily": "sprint19_shadow",
                "artifactModelKey": SHADOW_MODEL_KEY,
                "prefersSprint19ShadowArtifacts": True,
                "fallbackUsed": False,
                "registryShadowPointerPresent": bool(registry_shadow),
            },
            "warnings": _dedupe(warnings),
        }

    def artifact_dir(self, market: str) -> Path:
        return self.settings.data_dir / "models" / "artifacts" / "sprint19_shadow" / SHADOW_MODEL_KEY / normalize_market_key(market)


def _registry_shadow_entry(registry: dict[str, Any], market: str) -> dict[str, Any]:
    raw_market = registry.get(normalize_market_key(market))
    if not isinstance(raw_market, dict):
        return {}
    shadow = raw_market.get(SHADOW_MODEL_STAGE)
    if not isinstance(shadow, dict):
        return {}
    models = shadow.get("models")
    if isinstance(models, dict) and isinstance(models.get(SHADOW_MODEL_KEY), dict):
        merged = dict(shadow)
        merged.update(models[SHADOW_MODEL_KEY])
        return merged
    selected = str(shadow.get("selected_model") or shadow.get("model_key") or shadow.get("modelKey") or "")
    if selected and selected != SHADOW_MODEL_KEY:
        return {}
    return dict(shadow) if str(shadow.get("model_key") or shadow.get("modelKey") or SHADOW_MODEL_KEY) == SHADOW_MODEL_KEY else {}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _first_text(*payloads_and_key: Any) -> str:
    *payloads, key = payloads_and_key
    for payload in payloads:
        if isinstance(payload, dict) and payload.get(key):
            return str(payload[key])
    return ""


def _public_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return path.name


def _public_source_path(value: Any) -> str:
    return str(value or "").replace("\\", "/")


def _int(value: Any) -> int | None:
    try:
        if value in {None, ""}:
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out
