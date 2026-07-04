from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response

from mlb_app.api.dependencies import (
    get_blocking_work_limiter,
    get_model_registry_service,
    get_model_training_service,
    get_prediction_service,
    get_shadow_model_readiness_service,
    get_shadow_model_summary_service,
)
from mlb_app.api.models import (
    MLModelsAdminActionResponse,
    MLModelsFeatureCoverageResponse,
    MLModelsMetricsResponse,
    MLModelsPredictionPreviewResponse,
    MLModelsRegistryResponse,
    MLModelsShadowReadinessResponse,
    MLModelsShadowSummaryResponse,
    MLModelsStatusResponse,
)
from mlb_app.api.routes._utils import enforce_native_mutation, with_schema_version
from mlb_app.ml.evaluation.reports import evaluate_csv
from mlb_app.ml.inference.prediction_service import PredictionService
from mlb_app.repositories.model_store import normalize_market_key
from mlb_app.services.blocking_work import BlockingWorkLimiter
from mlb_app.services.model_registry_service import ModelRegistryService
from mlb_app.services.model_training_service import ModelTrainingService
from mlb_app.services.shadow_model_readiness_service import ShadowModelReadinessService
from mlb_app.services.shadow_model_summary_service import ShadowModelSummaryService

router = APIRouter(prefix="/api", tags=["ml-models"])

SCHEMA_VERSION = "ml-models.v1"
SCOREABLE_STAGES = ("candidate", "shadow", "production")
REGISTRY_STAGES = ("candidate", "shadow", "production", "deprecated", "disabled")


@router.get("/ml-models/status", response_model=MLModelsStatusResponse, name="native_ml_models_status")
async def ml_models_status(
    service: Annotated[ModelRegistryService, Depends(get_model_registry_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict[str, Any]:
    registry = await limiter.run(service.load_registry, route_name="/api/ml-models/status")
    payload = _status_payload(registry, service)
    return with_schema_version(payload, SCHEMA_VERSION)


@router.get("/ml-models/registry", response_model=MLModelsRegistryResponse, name="native_ml_models_registry")
async def ml_models_registry(
    service: Annotated[ModelRegistryService, Depends(get_model_registry_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict[str, Any]:
    registry = await limiter.run(service.load_registry, route_name="/api/ml-models/registry")
    entries = _safe_registry_entries(registry)
    return with_schema_version(
        {
            "status": "ok",
            "entries": entries,
            "entryCount": len(entries),
            "markets": _market_keys(registry),
            "warnings": [],
        },
        SCHEMA_VERSION,
    )


@router.get("/ml-models/metrics", response_model=MLModelsMetricsResponse, name="native_ml_models_metrics")
async def ml_models_metrics(
    service: Annotated[ModelRegistryService, Depends(get_model_registry_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict[str, Any]:
    registry = await limiter.run(service.load_registry, route_name="/api/ml-models/metrics")
    metrics = _metrics_entries(registry)
    return with_schema_version(
        {"status": "ok", "metrics": metrics, "metricCount": len(metrics), "warnings": []},
        SCHEMA_VERSION,
    )


@router.get(
    "/ml-models/feature-coverage",
    response_model=MLModelsFeatureCoverageResponse,
    name="native_ml_models_feature_coverage",
)
async def ml_models_feature_coverage(
    request: Request,
    service: Annotated[ModelRegistryService, Depends(get_model_registry_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict[str, Any]:
    registry = await limiter.run(service.load_registry, route_name="/api/ml-models/feature-coverage")
    received_features = _feature_query(request)
    coverage = await limiter.run(
        _feature_coverage_entries,
        registry,
        service,
        received_features,
        route_name="/api/ml-models/feature-coverage",
    )
    return with_schema_version(
        {
            "status": "ok",
            "coverage": coverage,
            "entryCount": len(coverage),
            "receivedFeatureCount": len(received_features),
            "warnings": _dedupe([warning for entry in coverage for warning in entry.get("warnings", [])]),
        },
        SCHEMA_VERSION,
    )


@router.get(
    "/ml-models/predictions/preview",
    response_model=MLModelsPredictionPreviewResponse,
    name="native_ml_models_predictions_preview",
)
async def ml_models_prediction_preview(
    request: Request,
    service: Annotated[PredictionService, Depends(get_prediction_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict[str, Any]:
    prediction_request = _prediction_request_from_query(request)
    result = await limiter.run(service.predict, prediction_request, route_name="/api/ml-models/predictions/preview")
    preview = result.as_dict() if hasattr(result, "as_dict") else dict(result)
    preview.update(
        {
            "modelStage": prediction_request["modelStage"] or "shadow",
            "modelKey": prediction_request["modelKey"] or ("calibrated_logistic" if prediction_request["modelStage"] == "shadow" else ""),
            "previewLabel": "Experimental/Shadow" if prediction_request["modelStage"] == "shadow" else "Experimental",
            "readinessLabel": "Experimental",
            "action": "Research",
            "stakeUnits": 0,
            "betActionAllowed": False,
        }
    )
    return with_schema_version(
        {
            "status": "ok",
            "preview": _sanitize_public_payload(preview, _root_dir(service)),
            "warnings": list(preview.get("warnings", [])) if isinstance(preview, dict) else [],
        },
        SCHEMA_VERSION,
    )


@router.get(
    "/ml-models/shadow-summary",
    response_model=MLModelsShadowSummaryResponse,
    name="native_ml_models_shadow_summary",
)
async def ml_models_shadow_summary(
    request: Request,
    service: Annotated[ShadowModelSummaryService, Depends(get_shadow_model_summary_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict[str, Any]:
    market = str(request.query_params.get("market") or "").strip() or None
    payload = await limiter.run(service.payload, market=market, route_name="/api/ml-models/shadow-summary")
    return with_schema_version(payload, SCHEMA_VERSION)


@router.get(
    "/ml-models/shadow-readiness",
    response_model=MLModelsShadowReadinessResponse,
    name="native_ml_models_shadow_readiness",
)
async def ml_models_shadow_readiness(
    request: Request,
    service: Annotated[ShadowModelReadinessService, Depends(get_shadow_model_readiness_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict[str, Any]:
    market = str(request.query_params.get("market") or "").strip() or None
    return await limiter.run(service.payload, market=market, route_name="/api/ml-models/shadow-readiness")


@router.post("/admin/ml-models/train", response_model=MLModelsAdminActionResponse, name="native_admin_ml_models_train")
async def admin_ml_models_train(
    request: Request,
    response: Response,
    service: Annotated[ModelTrainingService, Depends(get_model_training_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    enforce_native_mutation(request, owner="ml_ops", risk="high", kind="ml_model_train")
    payload = body or {}
    training_path = _body_text(payload, "trainingPath", "training_path")
    if not training_path:
        response.status_code = 202
        return with_schema_version(
            {
                "status": "skipped",
                "action": "train",
                "result": {},
                "warnings": ["trainingPath is required; no training job was started"],
            },
            SCHEMA_VERSION,
        )
    result = await limiter.run(
        service.train_from_dataset,
        training_path=_resolve_input_path(training_path, service.settings.root_dir),
        markets=_body_list(payload, "markets"),
        model_keys=_body_list(payload, "models", "modelKeys", "model_keys"),
        model_version=_body_text(payload, "modelVersion", "model_version") or None,
        registry_status=_body_text(payload, "registryStatus", "registry_status", "status") or "candidate",
        registry_path=_resolve_input_path(
            _body_text(payload, "registryPath", "registry_path"),
            service.settings.root_dir,
        )
        if _body_text(payload, "registryPath", "registry_path")
        else None,
        dry_run=_body_bool(payload, "dryRun", "dry_run", default=True),
        test_mode=_body_bool(payload, "testMode", "test_mode", default=False),
        minimum_rows=_body_int(payload, "minimumRows", "minimum_rows"),
        minimum_positive_rows=_body_int(payload, "minimumPositiveRows", "minimum_positive_rows"),
        timeout_seconds=180.0,
        route_name="POST /api/admin/ml-models/train",
    )
    result_payload = result.as_dict() if hasattr(result, "as_dict") else dict(result)
    return with_schema_version(
        {
            "status": str(result_payload.get("status") or "ok"),
            "action": "train",
            "result": _sanitize_public_payload(result_payload, service.settings.root_dir),
            "warnings": list(result_payload.get("warnings", [])),
        },
        SCHEMA_VERSION,
    )


@router.post(
    "/admin/ml-models/evaluate",
    response_model=MLModelsAdminActionResponse,
    name="native_admin_ml_models_evaluate",
)
async def admin_ml_models_evaluate(
    request: Request,
    response: Response,
    service: Annotated[ModelRegistryService, Depends(get_model_registry_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    enforce_native_mutation(request, owner="ml_ops", risk="high", kind="ml_model_evaluate")
    payload = body or {}
    evaluation_path = _body_text(payload, "evaluationPath", "evaluation_path", "trainingPath", "training_path")
    if evaluation_path:
        report = await limiter.run(
            evaluate_csv,
            _resolve_input_path(evaluation_path, service.settings.root_dir),
            min_train_rows=_body_int(payload, "minTrainRows", "min_train_rows") or 20,
            validation_window=_body_int(payload, "validationWindow", "validation_window") or 20,
            markets=_body_list(payload, "markets"),
            artifact_root=service.settings.data_dir / "models" / "artifacts" / "sprint19_shadow" / "calibrated_logistic",
            write_artifacts=_body_bool(payload, "writeArtifacts", "write_artifacts", default=True),
            route_name="POST /api/admin/ml-models/evaluate",
        )
        return with_schema_version(
            {
                "status": str(report.get("status") or "ok"),
                "action": "evaluate",
                "result": _sanitize_public_payload(report, service.settings.root_dir),
                "warnings": list(report.get("warnings", [])),
            },
            SCHEMA_VERSION,
        )
    market = normalize_market_key(_body_text(payload, "market"))
    if not market:
        response.status_code = 202
        return with_schema_version(
            {
                "status": "skipped",
                "action": "evaluate",
                "result": {},
                "warnings": ["market is required; no model evaluation was started"],
            },
            SCHEMA_VERSION,
        )
    result = await limiter.run(
        service.validate_promotion,
        market,
        _body_text(payload, "targetStatus", "target_status") or "production",
        source_status=_body_text(payload, "sourceStatus", "source_status") or None,
        model_key=_body_text(payload, "modelKey", "model_key") or None,
        route_name="POST /api/admin/ml-models/evaluate",
    )
    return with_schema_version(
        {
            "status": "ok",
            "action": "evaluate",
            "market": market,
            "result": _sanitize_public_payload(result, service.settings.root_dir),
            "warnings": list(result.get("warnings", [])) if isinstance(result, dict) else [],
        },
        SCHEMA_VERSION,
    )


@router.post(
    "/admin/ml-models/promote",
    response_model=MLModelsAdminActionResponse,
    name="native_admin_ml_models_promote",
)
async def admin_ml_models_promote(
    request: Request,
    response: Response,
    service: Annotated[ModelRegistryService, Depends(get_model_registry_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    enforce_native_mutation(request, owner="ml_ops", risk="critical", kind="ml_model_promote")
    payload = body or {}
    market = normalize_market_key(_body_text(payload, "market"))
    if not market:
        response.status_code = 400
        return with_schema_version(
            {
                "status": "error",
                "action": "promote",
                "result": {"code": "market_required"},
                "warnings": ["market is required"],
            },
            SCHEMA_VERSION,
        )
    result = await limiter.run(
        service.transition_model_status,
        market,
        _body_text(payload, "targetStatus", "target_status") or "production",
        source_status=_body_text(payload, "sourceStatus", "source_status") or None,
        model_key=_body_text(payload, "modelKey", "model_key") or None,
        route_name="POST /api/admin/ml-models/promote",
    )
    if isinstance(result, dict) and result.get("status") == "rejected":
        response.status_code = 409
    return with_schema_version(
        {
            "status": str(result.get("status") or "ok") if isinstance(result, dict) else "ok",
            "action": "promote",
            "market": market,
            "result": _sanitize_public_payload(result, service.settings.root_dir),
            "warnings": [],
        },
        SCHEMA_VERSION,
    )


def _status_payload(registry: dict[str, Any], service: ModelRegistryService) -> dict[str, Any]:
    entries = _safe_registry_entries(registry)
    counts: dict[str, int] = {}
    for entry in entries:
        status = str(entry.get("status") or entry.get("stage") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    policy = service.status_payload(())["policy"]
    return {
        "status": "ok",
        "registry": {
            "present": bool(registry),
            "entryCount": len(entries),
            "path": _public_path(service.settings.root_dir, service.settings.model_registry_path),
        },
        "modelCounts": counts,
        "markets": _market_keys(registry),
        "productionMarkets": sorted({entry["market"] for entry in entries if entry.get("stage") == "production"}),
        "shadowMarkets": sorted({entry["market"] for entry in entries if entry.get("stage") == "shadow"}),
        "candidateMarkets": sorted({entry["market"] for entry in entries if entry.get("stage") == "candidate"}),
        "policy": policy,
        "warnings": [],
    }


def _safe_registry_entries(registry: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for market in _market_keys(registry):
        raw_market = registry.get(market)
        if not isinstance(raw_market, dict):
            continue
        if any(key in raw_market for key in ("artifact", "artifact_sha256", "artifactSha256", "status", "version")):
            entries.append(_safe_entry(market, "production", raw_market))
            # Do not continue here: legacy root production entries can coexist
            # with nested candidate/shadow stages in the Sprint 19 registry.

        for stage in REGISTRY_STAGES:
            stage_entry = raw_market.get(stage)
            if not isinstance(stage_entry, dict):
                continue
            models = stage_entry.get("models")
            if isinstance(models, dict) and models:
                for model_key, model_entry in sorted(models.items()):
                    if isinstance(model_entry, dict):
                        merged = dict(stage_entry)
                        merged.update(model_entry)
                        merged["selected_model"] = str(model_key)
                        entries.append(_safe_entry(market, stage, merged))
            else:
                entries.append(_safe_entry(market, stage, stage_entry))
    return entries


def _safe_entry(market: str, stage: str, entry: dict[str, Any]) -> dict[str, Any]:
    artifact_sha = _text(_first(entry, "artifact_sha256", "artifactSha256", "sha256"))
    features_sha = _text(_first(entry, "features_sha256", "featuresSha256", "feature_schema_sha256", "featureSchemaSha256"))
    metrics_sha = _text(_first(entry, "metrics_sha256", "metricsSha256"))
    return {
        "market": normalize_market_key(market),
        "stage": stage,
        "status": _text(_first(entry, "status", "modelStatus"), stage),
        "modelKey": _text(_first(entry, "model_key", "modelKey", "selected_model", "selectedModel")),
        "selectedModel": _text(_first(entry, "selected_model", "selectedModel", "model_key", "modelKey")),
        "version": _text(_first(entry, "version", "model_version", "modelVersion")),
        "trainedAt": _text(_first(entry, "trained_at", "trainedAt")),
        "lastPromotedAt": _text(_first(entry, "last_promoted_at", "lastPromotedAt")),
        "trainingRows": _int(_first(entry, "training_rows", "trainingRows")),
        "positiveRows": _int(_first(entry, "positive_rows", "positiveRows")),
        "negativeRows": _int(_first(entry, "negative_rows", "negativeRows")),
        "featureCount": _int(_first(entry, "feature_count", "featureCount")),
        "calibrated": bool(entry.get("calibrated")),
        "productionGated": bool(entry.get("production_gated") or entry.get("productionGated")),
        "artifactHashPrefix": artifact_sha[:12],
        "featuresHashPrefix": features_sha[:12],
        "metricsHashPrefix": metrics_sha[:12],
        "metrics": _dict(_first(entry, "metrics", "evaluation_metrics", "evaluationMetrics")),
        "backtest": _dict(_first(entry, "backtest", "backtestMetrics")),
        "knownLimitations": _strings(_first(entry, "known_limitations", "knownLimitations", "limitations")),
    }


def _metrics_entries(registry: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in _safe_registry_entries(registry):
        metric_values = _dict(entry.get("metrics"))
        backtest = _dict(entry.get("backtest"))
        rows.append(
            {
                "market": entry["market"],
                "stage": entry["stage"],
                "modelKey": entry.get("modelKey", ""),
                "version": entry.get("version", ""),
                "metrics": metric_values,
                "backtest": backtest,
                "hasMetrics": bool(metric_values or backtest),
            }
        )
    return rows


def _feature_coverage_entries(
    registry: dict[str, Any],
    service: ModelRegistryService,
    received_features: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for market in _market_keys(registry):
        raw_market = registry.get(market)
        if not isinstance(raw_market, dict):
            continue
        for stage in SCOREABLE_STAGES:
            stage_entry = raw_market.get(stage)
            if not isinstance(stage_entry, dict):
                continue
            selected_entries = _stage_model_entries(stage_entry)
            for model_key, entry in selected_entries:
                warnings: list[str] = []
                try:
                    schema = service.artifact_repository.load_feature_schema(market, stage=stage, entry=entry)
                    required = tuple(schema.required_features or schema.feature_names)
                    feature_names = tuple(schema.feature_names or required)
                except Exception as error:  # noqa: BLE001 - registry artifacts must fail closed
                    required = ()
                    feature_names = ()
                    warnings.append(str(error))
                present = [name for name in required if name in received_features and received_features.get(name) not in {None, ""}]
                missing = [name for name in required if name not in present]
                coverage = round(len(present) / len(required), 6) if required and received_features else None
                rows.append(
                    {
                        "market": normalize_market_key(market),
                        "stage": stage,
                        "modelKey": model_key,
                        "schemaVersion": getattr(schema, "version", "missing") if "schema" in locals() else "missing",
                        "featureCount": len(feature_names),
                        "requiredFeatureCount": len(required),
                        "optionalFeatureCount": max(len(feature_names) - len(required), 0),
                        "receivedFeatureCount": len(received_features),
                        "featureCoverage": coverage,
                        "presentFeatureCount": len(present),
                        "missingFeatureCount": len(missing),
                        "missingFeatures": missing[:50],
                        "warnings": warnings,
                    }
                )
                if "schema" in locals():
                    del schema
    return rows


def _stage_model_entries(stage_entry: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    models = stage_entry.get("models")
    if not isinstance(models, dict) or not models:
        return [(_text(_first(stage_entry, "model_key", "modelKey", "selected_model", "selectedModel")), dict(stage_entry))]
    out: list[tuple[str, dict[str, Any]]] = []
    for model_key, model_entry in sorted(models.items()):
        if not isinstance(model_entry, dict):
            continue
        merged = dict(stage_entry)
        merged.update(model_entry)
        merged["selected_model"] = str(model_key)
        out.append((str(model_key), merged))
    return out


def _prediction_request_from_query(request: Request) -> dict[str, Any]:
    query = request.query_params
    return {
        "market": str(query.get("market") or ""),
        "player": str(query.get("player") or ""),
        "line": _float(query.get("line")),
        "side": str(query.get("side") or ""),
        "marketProbability": _float(query.get("marketProbability") or query.get("market_probability")),
        "contextProbability": _float(query.get("contextProbability") or query.get("context_probability")),
        "engineProbability": _float(query.get("engineProbability") or query.get("engine_probability")),
        "steamProbability": _float(query.get("steamProbability") or query.get("steam_probability")),
        "finalProbabilityPercent": _float(query.get("finalProbabilityPercent") or query.get("existingFinalProbabilityPercent")),
        "modelStage": str(query.get("modelStage") or query.get("model_stage") or "shadow"),
        "modelKey": str(query.get("modelKey") or query.get("model_key") or ""),
        "features": _feature_query(request),
    }


def _feature_query(request: Request) -> dict[str, Any]:
    features: dict[str, Any] = {}
    raw_features = request.query_params.get("features")
    if raw_features:
        try:
            payload = json.loads(raw_features)
            if isinstance(payload, dict):
                features.update(payload)
        except json.JSONDecodeError:
            pass
    for key, value in request.query_params.multi_items():
        if str(key).startswith("feature_"):
            features[str(key)] = _float(value) if _float(value) is not None else value
    return features


def _sanitize_public_payload(value: Any, root: Path) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize_public_payload(_sanitize_path_value(key, item, root), root) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_public_payload(item, root) for item in value]
    return value


def _sanitize_path_value(key: str, value: Any, root: Path) -> Any:
    if not isinstance(value, str):
        return value
    if "path" not in key.lower() and key not in {"artifact", "features", "metadata", "registry", "artifactRoot"}:
        return value
    return _public_path(root, Path(value))


def _public_path(root: Path, path: Path | str) -> str:
    target = Path(path)
    if not str(target):
        return ""
    try:
        return target.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return target.name


def _resolve_input_path(value: str, root: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (root / path).resolve()


def _root_dir(service: PredictionService) -> Path:
    return getattr(getattr(service, "settings", None), "root_dir", Path(".")).resolve()


def _market_keys(registry: dict[str, Any]) -> list[str]:
    return sorted(normalize_market_key(str(key)) for key in registry if str(key).strip())


def _body_text(payload: dict[str, Any], *keys: str) -> str:
    value = _first(payload, *keys)
    return str(value or "").strip()


def _body_list(payload: dict[str, Any], *keys: str) -> list[str] | None:
    value = _first(payload, *keys, default=None)
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return [part.strip() for part in value.replace("\n", ",").split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(part).strip() for part in value if str(part).strip()]
    return None


def _body_bool(payload: dict[str, Any], *keys: str, default: bool) -> bool:
    value = _first(payload, *keys, default=None)
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _body_int(payload: dict[str, Any], *keys: str) -> int | None:
    return _int(_first(payload, *keys, default=None), default=None)


def _first(mapping: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key not in mapping:
            continue
        value = mapping[key]
        if value is not None and value != "":
            return value
    return default


def _text(value: Any, default: str = "") -> str:
    text = str(value if value is not None else "").strip()
    return text or default


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _int(value: Any, default: int | None = 0) -> int | None:
    try:
        if value in {None, ""}:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            out.append(text)
            seen.add(text)
    return out
