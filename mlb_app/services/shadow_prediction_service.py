from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.ml.datasets.leakage_guard import assert_feature_columns_safe, is_feature_column
from mlb_app.ml.inference.prediction_service import PredictionService
from mlb_app.repositories.shadow_prediction_repository import ShadowPredictionRepository


PROTECTED_BOARD_FIELDS = ("finalProbabilityPercent", "finalEdgePercent", "rank")


class ShadowPredictionService:
    def __init__(
        self,
        *,
        settings: Settings = default_settings,
        prediction_service: PredictionService | None = None,
        repository: ShadowPredictionRepository | None = None,
    ) -> None:
        self.settings = settings
        self.prediction_service = prediction_service or PredictionService(settings=settings)
        self.repository = repository or ShadowPredictionRepository(settings=settings)

    def score_rows(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        model_stage: str = "shadow",
        model_key: str | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        scored_rows: list[dict[str, Any]] = []
        shadow_rows: list[dict[str, Any]] = []
        warnings: list[str] = []
        for source in rows:
            before = {field: source.get(field) for field in PROTECTED_BOARD_FIELDS}
            features = _features_from_row(source)
            assert_feature_columns_safe(features.keys())
            request = {
                "market": source.get("market") or source.get("propKey") or source.get("meta_market") or "",
                "player": source.get("player") or "",
                "line": source.get("line"),
                "side": source.get("side") or "",
                "marketProbability": source.get("marketProbability") or source.get("impliedProbabilityPercent"),
                "contextProbability": source.get("contextProbability") or source.get("modelProbabilityPercent"),
                "finalProbabilityPercent": source.get("finalProbabilityPercent"),
                "modelStage": model_stage,
                "modelKey": model_key or "",
                "features": features,
            }
            result = self.prediction_service.predict(request)
            payload = result.as_dict() if hasattr(result, "as_dict") else dict(result)
            output = dict(source)
            output["shadowPrediction"] = payload
            for field, value in before.items():
                output[field] = value
            scored_rows.append(output)
            shadow_rows.append(_shadow_storage_row(source, payload))
            warnings.extend(str(warning) for warning in payload.get("warnings") or [])
        storage = self.repository.append_many(shadow_rows) if persist and shadow_rows else {"backend": "none", "rowCount": 0}
        return {
            "status": "ok",
            "rowCount": len(scored_rows),
            "rows": scored_rows,
            "storage": storage,
            "warnings": _dedupe(warnings),
        }

    def evaluate_after_grading(self, graded_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        updated = 0
        for row in graded_rows:
            prediction_id = str(row.get("prediction_id") or row.get("shadow_prediction_id") or "")
            if not prediction_id:
                continue
            result = self.repository.mark_evaluated(
                prediction_id,
                {
                    "target_actual_value": row.get("target_actual_value") or row.get("actual_value"),
                    "target_hit": row.get("target_hit") or row.get("hit"),
                    "target_push": row.get("target_push") or row.get("push"),
                    "target_result": row.get("target_result") or row.get("result"),
                    "target_profit_1u": row.get("target_profit_1u") or row.get("profit_1u"),
                },
            )
            updated += int(result.get("updated") or 0)
        return {"status": "ok", "updated": updated}


def _features_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in row.items() if is_feature_column(str(key))}


def _shadow_storage_row(row: Mapping[str, Any], prediction: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "model_name": prediction.get("modelName") or "",
        "model_version": prediction.get("modelVersion") or "",
        "model_status": prediction.get("modelStatus") or "shadow",
        "market": prediction.get("market") or row.get("market") or "",
        "game_date": row.get("date") or row.get("game_date") or row.get("meta_game_date") or "",
        "game_id": row.get("gameId") or row.get("game_id") or row.get("meta_game_id") or "",
        "player": prediction.get("player") or row.get("player") or "",
        "team": row.get("team") or "",
        "opponent": row.get("opponent") or "",
        "line": prediction.get("line") if prediction.get("line") is not None else row.get("line"),
        "side": prediction.get("side") or row.get("side") or "",
        "sportsbook": row.get("book") or row.get("sportsbook") or "",
        "market_probability": prediction.get("marketProbability"),
        "model_probability": prediction.get("modelProbability"),
        "context_probability": prediction.get("contextProbability"),
        "blended_shadow_probability": prediction.get("blendedProbability"),
        "edge": prediction.get("edge"),
        "feature_coverage": prediction.get("featureCoverage"),
        "warnings": prediction.get("warnings") or [],
    }
    payload["prediction_id"] = _prediction_id(payload)
    return payload


def _prediction_id(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _dedupe(items: Sequence[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            out.append(text)
            seen.add(text)
    return out
