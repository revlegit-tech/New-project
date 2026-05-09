from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from mlb_app.config import Settings, settings as default_settings
from mlb_app.repositories.model_store import normalize_market_key


class ModelArtifactError(RuntimeError):
    """Base error for model governance failures."""


class ModelArtifactVerificationError(ModelArtifactError):
    """Raised when a content-addressed artifact does not match its registry hash."""


class FeatureSchemaMismatchError(ModelArtifactError):
    """Raised when inference input columns do not match a model feature schema."""


@dataclass(frozen=True)
class FileVerification:
    path: str
    expected_sha256: str = ""
    actual_sha256: str = ""
    exists: bool = False
    verified: bool = False
    error: str = ""

    @property
    def prefix(self) -> str:
        return (self.expected_sha256 or self.actual_sha256)[:12]

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "expectedSha256": self.expected_sha256,
            "actualSha256": self.actual_sha256,
            "hashPrefix": self.prefix,
            "exists": self.exists,
            "verified": self.verified,
            "error": self.error,
        }


@dataclass(frozen=True)
class FeatureSchema:
    version: str
    feature_names: tuple[str, ...]
    required_features: tuple[str, ...]
    optional_features: tuple[str, ...] = ()
    source_path: str = ""
    sha256: str = ""

    @property
    def count(self) -> int:
        return len(self.feature_names)

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "featureCount": self.count,
            "featureNames": list(self.feature_names),
            "requiredFeatures": list(self.required_features),
            "optionalFeatures": list(self.optional_features),
            "sourcePath": self.source_path,
            "sha256": self.sha256,
            "hashPrefix": self.sha256[:12],
        }


@dataclass(frozen=True)
class FeatureValidationResult:
    ok: bool
    schema_version: str
    expected_features: tuple[str, ...]
    received_columns: tuple[str, ...]
    missing_features: tuple[str, ...]
    extra_features: tuple[str, ...]
    order_mismatches: tuple[dict[str, Any], ...]
    input_hash: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schemaVersion": self.schema_version,
            "expectedFeatureCount": len(self.expected_features),
            "receivedColumnCount": len(self.received_columns),
            "missingFeatures": list(self.missing_features),
            "extraFeatures": list(self.extra_features),
            "orderMismatches": list(self.order_mismatches),
            "inputHash": self.input_hash,
        }


@dataclass(frozen=True)
class ModelRegistryEntry:
    market: str
    stage: str
    version: str = ""
    status: str = "research_only"
    artifact_sha256: str = ""
    features_sha256: str = ""
    metrics_sha256: str = ""
    training_data_sha256: str = ""
    trained_at: str = ""
    training_window: dict[str, Any] = field(default_factory=dict)
    last_promoted_at: str = ""
    artifact_path: Path | None = None
    features_path: Path | None = None
    metrics_path: Path | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    known_limitations: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def artifact_hash_prefix(self) -> str:
        return self.artifact_sha256[:12]

    @property
    def features_hash_prefix(self) -> str:
        return self.features_sha256[:12]

    @property
    def metrics_hash_prefix(self) -> str:
        return self.metrics_sha256[:12]

    def as_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "stage": self.stage,
            "version": self.version,
            "status": self.status,
            "artifactSha256": self.artifact_sha256,
            "artifactHashPrefix": self.artifact_hash_prefix,
            "featuresSha256": self.features_sha256,
            "featuresHashPrefix": self.features_hash_prefix,
            "metricsSha256": self.metrics_sha256,
            "metricsHashPrefix": self.metrics_hash_prefix,
            "trainingDataSha256": self.training_data_sha256,
            "trainedAt": self.trained_at,
            "trainingWindow": dict(self.training_window),
            "lastPromotedAt": self.last_promoted_at,
            "artifactPath": str(self.artifact_path or ""),
            "featuresPath": str(self.features_path or ""),
            "metricsPath": str(self.metrics_path or ""),
            "metrics": dict(self.metrics),
            "knownLimitations": list(self.known_limitations),
        }


class ModelArtifactRepository:
    """Content-addressed repository for model artifacts and feature schemas.

    Sprint 6 makes the registry the pointer to immutable artifacts. The service
    supports the new `data/models/artifacts/sha256/<hash>.*` layout while keeping
    legacy `artifact` / `features` paths readable during migration.
    """

    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings
        self.model_dir = settings.model_dir
        self.artifact_dir = self.model_dir / "artifacts" / "sha256"

    @property
    def registry_path(self) -> Path:
        if self.settings.model_registry_path.exists():
            return self.settings.model_registry_path
        return self.model_dir / "registry.json"

    def load_registry(self) -> dict[str, Any]:
        path = self.registry_path
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("Model registry must be a JSON object keyed by market")
        return payload

    def registry_entry(self, market: str, *, stage: str = "production") -> dict[str, Any]:
        registry = self.load_registry()
        raw_market = registry.get(normalize_market_key(market), {})
        if not isinstance(raw_market, dict):
            return {}
        return _select_stage(raw_market, stage)

    def resolve_entry(
        self,
        market: str,
        *,
        stage: str = "production",
        entry: dict[str, Any] | None = None,
    ) -> ModelRegistryEntry:
        key = normalize_market_key(market)
        raw = dict(entry if entry is not None else self.registry_entry(key, stage=stage))
        artifact_sha = _text(_first(raw, "artifact_sha256", "artifactSha256", "sha256"))
        features_sha = _text(_first(raw, "features_sha256", "featuresSha256", "feature_schema_sha256", "featureSchemaSha256"))
        metrics_sha = _text(_first(raw, "metrics_sha256", "metricsSha256"))
        artifact_path = self._resolve_artifact_path(raw, artifact_sha, key)
        features_path = self._resolve_features_path(raw, features_sha, artifact_path)
        metrics_path = self._resolve_metrics_path(raw, metrics_sha)
        return ModelRegistryEntry(
            market=key,
            stage=stage,
            version=_text(_first(raw, "version", "model_version", "modelVersion")),
            status=_text(_first(raw, "status", "modelStatus"), default="research_only").lower(),
            artifact_sha256=artifact_sha,
            features_sha256=features_sha,
            metrics_sha256=metrics_sha,
            training_data_sha256=_text(_first(raw, "training_data_sha256", "trainingDataSha256")),
            trained_at=_text(_first(raw, "trained_at", "trainedAt")),
            training_window=_dict(_first(raw, "training_window", "trainingWindow")),
            last_promoted_at=_text(_first(raw, "last_promoted_at", "lastPromotedAt", "promoted_at", "promotedAt")),
            artifact_path=artifact_path,
            features_path=features_path,
            metrics_path=metrics_path,
            metrics=_dict(_first(raw, "metrics", "evaluation_metrics", "evaluationMetrics")),
            known_limitations=tuple(_strings(_first(raw, "known_limitations", "knownLimitations", "limitations"))),
            raw=raw,
        )

    def verify_entry(self, market: str, *, stage: str = "production", entry: dict[str, Any] | None = None) -> dict[str, Any]:
        resolved = self.resolve_entry(market, stage=stage, entry=entry)
        artifact = self.verify_file(resolved.artifact_path, resolved.artifact_sha256).as_dict()
        features = self.verify_file(resolved.features_path, resolved.features_sha256).as_dict()
        metrics = self.verify_file(resolved.metrics_path, resolved.metrics_sha256).as_dict()
        required = [artifact]
        if resolved.features_sha256 or (resolved.features_path and resolved.features_path.exists()):
            required.append(features)
        if resolved.metrics_sha256:
            required.append(metrics)
        errors = [item["error"] for item in required if item.get("error")]
        return {
            "ok": not errors,
            "entry": resolved.as_dict(),
            "artifact": artifact,
            "features": features,
            "metrics": metrics,
            "errors": errors,
        }

    def verify_or_raise(self, market: str, *, stage: str = "production", entry: dict[str, Any] | None = None) -> dict[str, Any]:
        result = self.verify_entry(market, stage=stage, entry=entry)
        if not result["ok"]:
            raise ModelArtifactVerificationError("; ".join(result["errors"]))
        return result

    def verify_file(self, path: Path | None, expected_sha256: str = "") -> FileVerification:
        path_text = str(path or "")
        expected = _text(expected_sha256).lower()
        if path is None:
            return FileVerification(path=path_text, expected_sha256=expected, error="artifact path unavailable")
        if not path.exists():
            error = "file missing"
            if expected:
                error = f"file missing for expected sha256 {expected[:12]}"
            return FileVerification(path=path_text, expected_sha256=expected, error=error)
        actual = sha256_file(path)
        if expected and actual.lower() != expected:
            return FileVerification(
                path=path_text,
                expected_sha256=expected,
                actual_sha256=actual,
                exists=True,
                verified=False,
                error=f"sha256 mismatch: expected {expected[:12]}, got {actual[:12]}",
            )
        return FileVerification(
            path=path_text,
            expected_sha256=expected,
            actual_sha256=actual,
            exists=True,
            verified=bool(expected and actual.lower() == expected) or not expected,
        )


    def load_model(self, market: str, *, stage: str = "production", entry: dict[str, Any] | None = None) -> Any:
        """Load a model only after content-hash verification succeeds."""

        resolved = self.resolve_entry(market, stage=stage, entry=entry)
        verification = self.verify_file(resolved.artifact_path, resolved.artifact_sha256)
        if verification.error:
            raise ModelArtifactVerificationError(verification.error)
        if resolved.artifact_sha256 and not verification.verified:
            raise ModelArtifactVerificationError("model artifact hash verification failed")
        try:
            import joblib  # type: ignore[import-not-found]
        except Exception as error:  # pragma: no cover - environment dependent
            raise ModelArtifactError("joblib is required to load model artifacts") from error
        return joblib.load(str(resolved.artifact_path))

    def load_feature_schema(self, market: str, *, stage: str = "production", entry: dict[str, Any] | None = None) -> FeatureSchema:
        resolved = self.resolve_entry(market, stage=stage, entry=entry)
        path = resolved.features_path
        if path is None or not path.exists():
            return FeatureSchema(version="missing", feature_names=(), required_features=(), source_path=str(path or ""))
        payload = json.loads(path.read_text(encoding="utf-8"))
        actual_sha = sha256_file(path)
        if resolved.features_sha256 and actual_sha.lower() != resolved.features_sha256.lower():
            raise ModelArtifactVerificationError(
                f"feature schema sha256 mismatch: expected {resolved.features_sha256[:12]}, got {actual_sha[:12]}"
            )
        if isinstance(payload, list):
            feature_names = tuple(_strings(payload))
            required = feature_names
            version = "features.v1"
            optional: tuple[str, ...] = ()
        elif isinstance(payload, dict):
            feature_names = tuple(_strings(_first(payload, "feature_names", "featureNames", "features", "columns")))
            required = tuple(_strings(_first(payload, "required_features", "requiredFeatures", "required", default=feature_names)))
            optional = tuple(_strings(_first(payload, "optional_features", "optionalFeatures", "optional")))
            version = _text(_first(payload, "schema_version", "schemaVersion", "version"), default="features.v1")
        else:
            raise ValueError("Feature schema must be a JSON object or array")
        return FeatureSchema(
            version=version,
            feature_names=feature_names,
            required_features=required,
            optional_features=optional,
            source_path=str(path),
            sha256=actual_sha,
        )

    def validate_feature_columns(
        self,
        market: str,
        columns_or_frame: Iterable[str] | Any,
        *,
        stage: str = "production",
        entry: dict[str, Any] | None = None,
        strict_order: bool = True,
    ) -> FeatureValidationResult:
        schema = self.load_feature_schema(market, stage=stage, entry=entry)
        columns = _columns(columns_or_frame)
        expected = schema.feature_names or schema.required_features
        missing = tuple(name for name in schema.required_features if name not in columns)
        extra = tuple(name for name in columns if name not in expected and name not in schema.optional_features)
        mismatches: list[dict[str, Any]] = []
        if strict_order and expected:
            actual_expected = [name for name in columns if name in expected]
            for index, expected_name in enumerate(expected):
                actual_name = actual_expected[index] if index < len(actual_expected) else None
                if actual_name != expected_name:
                    mismatches.append({"position": index, "expected": expected_name, "actual": actual_name})
        ok = not missing and not mismatches
        return FeatureValidationResult(
            ok=ok,
            schema_version=schema.version,
            expected_features=expected,
            received_columns=columns,
            missing_features=missing,
            extra_features=extra,
            order_mismatches=tuple(mismatches),
            input_hash=hash_columns(columns),
        )

    def _resolve_artifact_path(self, entry: dict[str, Any], artifact_sha: str, market: str) -> Path:
        explicit = _text(_first(entry, "artifact", "artifact_path", "artifactPath", "model_path", "modelPath"))
        if explicit:
            return _resolve_path(self.settings.root_dir, explicit)
        if artifact_sha:
            return self.artifact_dir / f"{artifact_sha}.joblib"
        return self.model_dir / f"prop_model_{market}.joblib"

    def _resolve_features_path(self, entry: dict[str, Any], features_sha: str, artifact_path: Path) -> Path:
        explicit = _text(_first(entry, "features", "features_path", "featuresPath", "metadata", "metadata_path", "metadataPath"))
        if explicit:
            return _resolve_path(self.settings.root_dir, explicit)
        if features_sha:
            return self.artifact_dir / f"{features_sha}.features.json"
        return artifact_path.with_name(f"{artifact_path.stem}_features.json")

    def _resolve_metrics_path(self, entry: dict[str, Any], metrics_sha: str) -> Path | None:
        explicit = _text(_first(entry, "metrics_path", "metricsPath", "metrics_file", "metricsFile"))
        if explicit:
            return _resolve_path(self.settings.root_dir, explicit)
        if metrics_sha:
            return self.artifact_dir / f"{metrics_sha}.metrics.json"
        return None


def sha256_file(path: str | Path) -> str:
    hasher = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def hash_columns(columns: Iterable[str]) -> str:
    return hashlib.sha256(json.dumps(list(columns), separators=(",", ":")).encode("utf-8")).hexdigest()


def hash_payload(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")).hexdigest()


def _select_stage(raw_market: dict[str, Any], stage: str) -> dict[str, Any]:
    if stage in raw_market and isinstance(raw_market.get(stage), dict):
        return dict(raw_market[stage])
    if "production" in raw_market and isinstance(raw_market.get("production"), dict):
        return dict(raw_market["production"])
    # Legacy flat registry entries contain artifact/status fields directly.
    if any(key in raw_market for key in ("artifact", "artifact_sha256", "artifactSha256", "status", "version")):
        return dict(raw_market)
    for value in raw_market.values():
        if isinstance(value, dict):
            return dict(value)
    return {}


def _resolve_path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (root / path).resolve()


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


def _columns(value: Iterable[str] | Any) -> tuple[str, ...]:
    columns = getattr(value, "columns", value)
    return tuple(str(column).strip() for column in columns if str(column).strip())
