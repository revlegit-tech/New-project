from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from mlb_app.ml.registry.metadata import build_feature_schema, build_training_metadata
from mlb_app.ml.trainers.base import ModelTrainer
from mlb_app.repositories.model_artifact_repository import sha256_file


@dataclass(frozen=True)
class ArtifactWriteResult:
    market: str
    model_key: str
    status: str
    artifact_path: Path
    feature_schema_path: Path
    metadata_path: Path
    artifact_sha256: str
    feature_schema_sha256: str
    metadata_sha256: str
    registry_entry: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "modelKey": self.model_key,
            "status": self.status,
            "artifactPath": str(self.artifact_path),
            "featureSchemaPath": str(self.feature_schema_path),
            "metadataPath": str(self.metadata_path),
            "artifactSha256": self.artifact_sha256,
            "featureSchemaSha256": self.feature_schema_sha256,
            "metadataSha256": self.metadata_sha256,
            "registryEntry": dict(self.registry_entry),
        }


class ModelArtifactWriter:
    def __init__(self, artifact_root: str | Path) -> None:
        self.artifact_root = Path(artifact_root)

    def write(
        self,
        *,
        market: str,
        model_key: str,
        trainer: ModelTrainer,
        model_version: str,
        status: str,
        training_rows: int,
        positive_rows: int,
        negative_rows: int,
        target_column: str,
        metrics: Mapping[str, Any] | None = None,
        source_dataset: str = "",
    ) -> ArtifactWriteResult:
        target_dir = self.artifact_root / _safe_segment(market) / _safe_segment(model_key) / _safe_segment(model_version)
        target_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = target_dir / "model.joblib"
        feature_schema_path = target_dir / "feature_schema.json"
        metadata_path = target_dir / "metadata.json"

        trainer.save(artifact_path)
        feature_schema = build_feature_schema(market=market, feature_names=trainer.get_feature_names())
        _write_json(feature_schema_path, feature_schema)
        metadata = build_training_metadata(
            market=market,
            model_key=model_key,
            trainer_metadata=trainer.get_metadata(),
            feature_schema=feature_schema,
            training_rows=training_rows,
            positive_rows=positive_rows,
            negative_rows=negative_rows,
            target_column=target_column,
            model_version=model_version,
            status=status,
            metrics=metrics,
            source_dataset=source_dataset,
            trained_at=str(trainer.get_metadata().get("trained_at") or ""),
        )
        _write_json(metadata_path, metadata)

        artifact_sha = sha256_file(artifact_path)
        feature_sha = sha256_file(feature_schema_path)
        metadata_sha = sha256_file(metadata_path)
        registry_entry = {
            "status": status,
            "market": market,
            "model_key": model_key,
            "model_type": trainer.get_metadata().get("model_name") or model_key,
            "version": model_version,
            "artifact": str(artifact_path),
            "features": str(feature_schema_path),
            "metadata": str(metadata_path),
            "artifact_sha256": artifact_sha,
            "features_sha256": feature_sha,
            "metadata_sha256": metadata_sha,
            "trained_at": trainer.get_metadata().get("trained_at") or metadata["trained_at"],
            "training_rows": int(training_rows),
            "positive_rows": int(positive_rows),
            "negative_rows": int(negative_rows),
            "feature_count": len(trainer.get_feature_names()),
            "calibrated": bool(trainer.get_metadata().get("calibrated")),
            "metrics": dict(metrics or {}),
            "production_gated": True,
        }
        return ArtifactWriteResult(
            market=market,
            model_key=model_key,
            status=status,
            artifact_path=artifact_path,
            feature_schema_path=feature_schema_path,
            metadata_path=metadata_path,
            artifact_sha256=artifact_sha,
            feature_schema_sha256=feature_sha,
            metadata_sha256=metadata_sha,
            registry_entry=registry_entry,
        )


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def _safe_segment(value: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in text).strip("_") or "unknown"
