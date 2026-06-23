from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.ml.inference.model_loader import LoadedModel, ModelLoader
from mlb_app.ml.inference.probability_blender import BlendInputs, ProbabilityBlender


@dataclass(frozen=True)
class ModelPredictionRequest:
    market: str
    player: str = ""
    line: float | None = None
    side: str = ""
    features: Mapping[str, Any] = field(default_factory=dict)
    market_probability: float | None = None
    context_probability: float | None = None
    engine_probability: float | None = None
    steam_probability: float | None = None
    existing_final_probability_percent: float | None = None
    model_stage: str = "shadow"
    model_key: str | None = None


@dataclass(frozen=True)
class ModelPredictionResult:
    market: str
    player: str = ""
    line: float | None = None
    side: str = ""
    model_probability: float | None = None
    market_probability: float | None = None
    context_probability: float | None = None
    blended_probability: float | None = None
    edge: float | None = None
    model_name: str = ""
    model_version: str = ""
    model_status: str = "unavailable"
    calibrated: bool = False
    feature_coverage: float = 0.0
    available: bool = False
    model_contributed: bool = False
    final_probability_percent: float | None = None
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "player": self.player,
            "line": self.line,
            "side": self.side,
            "modelProbability": self.model_probability,
            "marketProbability": self.market_probability,
            "contextProbability": self.context_probability,
            "blendedProbability": self.blended_probability,
            "edge": self.edge,
            "modelName": self.model_name,
            "modelVersion": self.model_version,
            "modelStatus": self.model_status,
            "calibrated": self.calibrated,
            "featureCoverage": self.feature_coverage,
            "available": self.available,
            "modelContributed": self.model_contributed,
            "finalProbabilityPercent": self.final_probability_percent,
            "warnings": list(self.warnings),
        }


class PredictionService:
    def __init__(
        self,
        *,
        settings: Settings = default_settings,
        model_loader: ModelLoader | None = None,
        probability_blender: ProbabilityBlender | None = None,
    ) -> None:
        self.settings = settings
        self.model_loader = model_loader or ModelLoader(settings=settings)
        self.probability_blender = probability_blender or ProbabilityBlender()

    def predict(self, request: ModelPredictionRequest | Mapping[str, Any]) -> ModelPredictionResult:
        prediction_request = _coerce_request(request)
        loaded = self.model_loader.load(
            prediction_request.market,
            stage=prediction_request.model_stage,
            model_key=prediction_request.model_key,
        )
        warnings = list(loaded.warnings)
        feature_coverage = _feature_coverage(loaded, prediction_request.features)
        if loaded.available and feature_coverage < 1.0:
            warnings.append(f"feature coverage is {feature_coverage:.2f}; missing features were scored as null")

        model_probability: float | None = None
        if loaded.available:
            try:
                frame = _feature_frame(loaded, prediction_request.features)
                model_probability = _predict_probability(loaded.model, frame)
            except Exception as error:  # noqa: BLE001 - inference must fail closed
                warnings.append(f"model scoring unavailable: {error}")

        blend = self.probability_blender.blend(
            BlendInputs(
                model_probability=model_probability,
                market_probability=prediction_request.market_probability,
                context_probability=prediction_request.context_probability,
                engine_probability=prediction_request.engine_probability,
                steam_probability=prediction_request.steam_probability,
                model_status=loaded.model_status,
                production_eligible=loaded.production_eligible,
            ),
            existing_final_probability_percent=prediction_request.existing_final_probability_percent,
        )
        warnings.extend(blend.warnings)
        return ModelPredictionResult(
            market=loaded.market or prediction_request.market,
            player=prediction_request.player,
            line=prediction_request.line,
            side=prediction_request.side,
            model_probability=_round_probability(model_probability),
            market_probability=_round_probability(prediction_request.market_probability),
            context_probability=_round_probability(prediction_request.context_probability),
            blended_probability=blend.blended_probability,
            edge=blend.edge,
            model_name=loaded.model_name,
            model_version=loaded.model_version,
            model_status=loaded.model_status,
            calibrated=loaded.calibrated,
            feature_coverage=feature_coverage,
            available=bool(loaded.available and model_probability is not None),
            model_contributed=blend.model_contributed,
            final_probability_percent=blend.final_probability_percent,
            warnings=tuple(_dedupe(warnings)),
        )


def _coerce_request(request: ModelPredictionRequest | Mapping[str, Any]) -> ModelPredictionRequest:
    if isinstance(request, ModelPredictionRequest):
        return request
    payload = dict(request)
    return ModelPredictionRequest(
        market=str(payload.get("market") or ""),
        player=str(payload.get("player") or ""),
        line=_float(payload.get("line")),
        side=str(payload.get("side") or ""),
        features=dict(payload.get("features") or {}),
        market_probability=_float(_first(payload, "market_probability", "marketProbability")),
        context_probability=_float(_first(payload, "context_probability", "contextProbability")),
        engine_probability=_float(_first(payload, "engine_probability", "engineProbability", "allDataProbability")),
        steam_probability=_float(_first(payload, "steam_probability", "steamProbability", "oddsMovementProbability")),
        existing_final_probability_percent=_float(_first(payload, "existing_final_probability_percent", "finalProbabilityPercent")),
        model_stage=str(_first(payload, "model_stage", "modelStage", "modelStatus", default="shadow") or "shadow"),
        model_key=str(_first(payload, "model_key", "modelKey", default="") or "") or None,
    )


def _feature_coverage(loaded: LoadedModel, features: Mapping[str, Any]) -> float:
    required = loaded.required_features
    if not required:
        return 0.0
    present = 0
    for name in required:
        if name in features and features.get(name) not in {None, ""}:
            present += 1
    return round(present / len(required), 6)


def _feature_frame(loaded: LoadedModel, features: Mapping[str, Any]) -> Any:
    try:
        import pandas as pd
    except ImportError as error:
        raise RuntimeError("pandas is required for model inference") from error
    row = {name: features.get(name) for name in loaded.feature_names}
    return pd.DataFrame([row], columns=list(loaded.feature_names)).apply(pd.to_numeric, errors="coerce")


def _predict_probability(model: Any, frame: Any) -> float:
    probabilities = model.predict_proba(frame)
    row = probabilities[0]
    if hasattr(row, "tolist"):
        row = row.tolist()
    if isinstance(row, (list, tuple)) and len(row) >= 2:
        return _clamp(float(row[1]))
    return _clamp(float(row))


def _round_probability(value: Any) -> float | None:
    number = _float(value)
    if number is None:
        return None
    if number > 1.0 and number <= 100.0:
        number = number / 100.0
    if number < 0.0 or number > 1.0:
        return None
    return round(number, 6)


def _clamp(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)


def _float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first(mapping: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in {None, ""}:
            return mapping[key]
    return default


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            out.append(text)
            seen.add(text)
    return out
