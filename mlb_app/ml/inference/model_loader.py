from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.ml.datasets.leakage_guard import assert_feature_columns_safe
from mlb_app.repositories.model_artifact_repository import (
    FeatureSchema,
    ModelArtifactRepository,
)
from mlb_app.repositories.model_store import normalize_market_key
from mlb_app.services.model_registry_service import ModelRegistryService

PREDICTABLE_STATUSES = {"candidate", "shadow", "production"}


@dataclass(frozen=True)
class LoadedModel:
    market: str
    model: Any | None = None
    feature_schema: FeatureSchema | None = None
    model_name: str = ""
    model_version: str = ""
    model_status: str = "unavailable"
    calibrated: bool = False
    production_eligible: bool = False
    available: bool = False
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def feature_names(self) -> tuple[str, ...]:
        if self.feature_schema is None:
            return ()
        return tuple(self.feature_schema.feature_names or self.feature_schema.required_features)

    @property
    def required_features(self) -> tuple[str, ...]:
        if self.feature_schema is None:
            return ()
        return tuple(self.feature_schema.required_features or self.feature_schema.feature_names)

    def public_metadata(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "modelName": self.model_name,
            "modelVersion": self.model_version,
            "modelStatus": self.model_status,
            "calibrated": self.calibrated,
            "productionEligible": self.production_eligible,
            "available": self.available,
            "featureCount": len(self.feature_names),
            "warnings": list(self.warnings),
        }


class ModelLoader:
    def __init__(
        self,
        *,
        settings: Settings = default_settings,
        registry_service: ModelRegistryService | None = None,
        artifact_repository: ModelArtifactRepository | None = None,
    ) -> None:
        self.settings = settings
        self.registry_service = registry_service or ModelRegistryService(settings=settings)
        self.artifact_repository = artifact_repository or self.registry_service.artifact_repository

    def load(self, market: str, *, stage: str = "shadow", model_key: str | None = None) -> LoadedModel:
        market_key = normalize_market_key(market)
        selected_stage = _normalize_stage(stage)
        warnings: list[str] = []
        entry = self._registry_entry(market_key, selected_stage, model_key=model_key)
        if not entry:
            return self._unavailable(
                market_key,
                selected_stage,
                warnings=[f"no {selected_stage} model is registered for {market_key}"],
            )

        status = str(entry.get("status") or selected_stage).strip().lower()
        model_name = str(entry.get("model_key") or entry.get("modelKey") or entry.get("model_type") or entry.get("modelType") or "").strip()
        version = str(entry.get("version") or entry.get("model_version") or entry.get("modelVersion") or "").strip()
        calibrated = bool(entry.get("calibrated"))

        if status not in PREDICTABLE_STATUSES:
            return self._unavailable(
                market_key,
                status,
                model_name=model_name,
                version=version,
                calibrated=calibrated,
                warnings=[f"model status {status!r} is not scoreable"],
            )
        if selected_stage == "production":
            status_payload = self.registry_service.market_status(market_key)
            warnings.extend(str(warning) for warning in status_payload.get("warnings") or [])
            if not bool(status_payload.get("productionEligible")):
                warnings.append("production model is blocked by registry validation gates")
                return self._unavailable(
                    market_key,
                    status,
                    model_name=model_name,
                    version=version,
                    calibrated=calibrated,
                    warnings=warnings,
                )

        verification = self.artifact_repository.verify_entry(market_key, stage=selected_stage, entry=entry)
        if not verification.get("ok"):
            warnings.extend(str(error) for error in verification.get("errors") or [])
            return self._unavailable(
                market_key,
                status,
                model_name=model_name,
                version=version,
                calibrated=calibrated,
                production_eligible=selected_stage == "production",
                warnings=warnings,
            )

        try:
            schema = self.artifact_repository.load_feature_schema(market_key, stage=selected_stage, entry=entry)
            feature_names = tuple(schema.feature_names or schema.required_features)
            if not feature_names:
                warnings.append("feature schema does not contain scoreable feature names")
                return self._unavailable(
                    market_key,
                    status,
                    model_name=model_name,
                    version=version,
                    calibrated=calibrated,
                    production_eligible=selected_stage == "production",
                    warnings=warnings,
                )
            assert_feature_columns_safe(feature_names)
            raw_model = self.artifact_repository.load_model(market_key, stage=selected_stage, entry=entry)
            model = _extract_predictor(raw_model)
        except Exception as error:  # noqa: BLE001 - model artifacts are external and must fail closed
            warnings.append(str(error))
            return self._unavailable(
                market_key,
                status,
                model_name=model_name,
                version=version,
                calibrated=calibrated,
                production_eligible=selected_stage == "production",
                warnings=warnings,
            )

        if not hasattr(model, "predict_proba"):
            warnings.append("model artifact does not expose predict_proba")
            return self._unavailable(
                market_key,
                status,
                model_name=model_name,
                version=version,
                calibrated=calibrated,
                production_eligible=selected_stage == "production",
                warnings=warnings,
            )

        return LoadedModel(
            market=market_key,
            model=model,
            feature_schema=schema,
            model_name=model_name,
            model_version=version,
            model_status=status,
            calibrated=calibrated,
            production_eligible=selected_stage == "production",
            available=True,
            warnings=tuple(_dedupe(warnings)),
        )

    def _registry_entry(self, market: str, stage: str, *, model_key: str | None = None) -> dict[str, Any]:
        registry = self.registry_service.load_registry()
        raw_market = registry.get(market)
        if not isinstance(raw_market, dict):
            return {}
        if stage == "production" and any(
            key in raw_market for key in ("artifact", "artifact_sha256", "artifactSha256", "status", "version")
        ):
            return dict(raw_market)
        stage_entry = raw_market.get(stage)
        if not isinstance(stage_entry, dict):
            return {}
        models = stage_entry.get("models")
        selected_key = str(model_key or stage_entry.get("selected_model") or stage_entry.get("model_key") or "").strip()
        if selected_key and isinstance(models, dict) and isinstance(models.get(selected_key), dict):
            selected = dict(stage_entry)
            selected.update(dict(models[selected_key]))
            selected["selected_model"] = selected_key
            return selected
        return dict(stage_entry)

    def _unavailable(
        self,
        market: str,
        status: str,
        *,
        model_name: str = "",
        version: str = "",
        calibrated: bool = False,
        production_eligible: bool = False,
        warnings: list[str] | tuple[str, ...],
    ) -> LoadedModel:
        return LoadedModel(
            market=market,
            model_name=model_name,
            model_version=version,
            model_status=status or "unavailable",
            calibrated=calibrated,
            production_eligible=production_eligible,
            available=False,
            warnings=tuple(_dedupe([str(warning) for warning in warnings])),
        )


def _extract_predictor(raw_model: Any) -> Any:
    if isinstance(raw_model, dict) and "model" in raw_model:
        return raw_model["model"]
    return raw_model


def _normalize_stage(value: str) -> str:
    stage = str(value or "shadow").strip().lower()
    return stage if stage in PREDICTABLE_STATUSES else "shadow"


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            out.append(text)
            seen.add(text)
    return out
