from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from mlb_app.ml.datasets.leakage_guard import assert_feature_columns_safe

FEATURE_SCHEMA_VERSION = "mlb-feature-schema.sprint19.v1"
ARTIFACT_METADATA_SCHEMA_VERSION = "mlb-model-metadata.sprint19.v1"
PROMOTION_GATE_SCHEMA_VERSION = "mlb-model-promotion-gates.sprint20.v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_feature_schema(
    *,
    market: str,
    feature_names: Iterable[str],
    required_features: Iterable[str] | None = None,
    optional_features: Iterable[str] | None = None,
) -> dict[str, Any]:
    names = [str(name) for name in feature_names]
    required = [str(name) for name in (required_features if required_features is not None else names)]
    optional = [str(name) for name in (optional_features or [])]
    assert_feature_columns_safe(names)
    assert_feature_columns_safe(required)
    assert_feature_columns_safe(optional)
    return {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "market": str(market),
        "feature_count": len(names),
        "feature_names": names,
        "required_features": required,
        "optional_features": optional,
    }


def build_training_metadata(
    *,
    market: str,
    model_key: str,
    trainer_metadata: Mapping[str, Any],
    feature_schema: Mapping[str, Any],
    training_rows: int,
    positive_rows: int,
    negative_rows: int,
    target_column: str,
    model_version: str,
    status: str,
    metrics: Mapping[str, Any] | None = None,
    source_dataset: str = "",
    trained_at: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": ARTIFACT_METADATA_SCHEMA_VERSION,
        "market": str(market),
        "model_key": str(model_key),
        "model_version": str(model_version),
        "status": str(status),
        "trained_at": trained_at or utc_now_iso(),
        "training_rows": int(training_rows),
        "positive_rows": int(positive_rows),
        "negative_rows": int(negative_rows),
        "target_column": str(target_column),
        "source_dataset": str(source_dataset),
        "feature_schema_version": str(feature_schema.get("schema_version") or ""),
        "feature_count": int(feature_schema.get("feature_count") or 0),
        "trainer": dict(trainer_metadata),
        "metrics": dict(metrics or {}),
        "production_gated": True,
        "live_probability_wiring": "not_enabled",
    }
