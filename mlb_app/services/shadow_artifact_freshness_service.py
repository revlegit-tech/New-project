from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.repositories.model_store import normalize_market_key
from mlb_app.services.model_registry_service import ModelRegistryService
from mlb_app.services.shadow_model_summary_service import SHADOW_MARKETS, SHADOW_MODEL_KEY, SHADOW_MODEL_STAGE

FRESHNESS_SCHEMA_VERSION = "shadow-artifact-freshness.v1"
DEFAULT_MAX_ALLOWED_AGE_HOURS = 36.0


class ShadowArtifactFreshnessService:
    """Read-only freshness policy for Sprint 19 shadow artifacts."""

    def __init__(
        self,
        settings: Settings = default_settings,
        *,
        registry_service: ModelRegistryService | None = None,
        max_allowed_age_hours: float = DEFAULT_MAX_ALLOWED_AGE_HOURS,
    ) -> None:
        self.settings = settings
        self.registry_service = registry_service or ModelRegistryService(settings=settings)
        self.max_allowed_age_hours = float(max_allowed_age_hours)

    def payload(self, *, market: str | None = None) -> dict[str, Any]:
        requested = [normalize_market_key(market)] if market else list(SHADOW_MARKETS)
        registry = self.registry_service.load_registry()
        rows = [self.freshness_for_market(selected, registry=registry) for selected in requested]
        return {
            "status": "ok",
            "schemaVersion": FRESHNESS_SCHEMA_VERSION,
            "marketCount": len(rows),
            "freshMarketCount": sum(1 for row in rows if row.get("freshnessStatus") == "fresh"),
            "staleMarketCount": sum(1 for row in rows if row.get("freshnessStatus") == "stale"),
            "missingMarketCount": sum(1 for row in rows if row.get("freshnessStatus") == "missing"),
            "unknownMarketCount": sum(1 for row in rows if row.get("freshnessStatus") == "unknown"),
            "markets": rows,
            "warnings": _dedupe([warning for row in rows for warning in row.get("warnings", [])]),
            "policy": _policy(self.max_allowed_age_hours),
        }

    def freshness_for_market(self, market: str, *, registry: dict[str, Any] | None = None) -> dict[str, Any]:
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
        blockers: list[str] = []
        existing_paths = [path for path in (backtest_path, calibration_path, manifest_path) if path.is_file()]
        missing_paths = [name for name, path in (("backtest", backtest_path), ("calibration", calibration_path), ("manifest", manifest_path)) if not path.is_file()]

        if missing_paths:
            blockers.extend(f"missing_shadow_{name}" for name in missing_paths)
            warnings.append("One or more Sprint 19 shadow artifacts are missing; freshness is not inferred from absent files.")
        if not registry_shadow:
            blockers.append("missing_registry_shadow_pointer")
            warnings.append("Registry shadow pointer is missing; freshness remains research-only.")

        generated_at = _first_text(backtest, calibration, manifest, ("generatedAt", "generated_at"))
        generated_dt = _parse_datetime(generated_at)
        artifact_age_hours = _age_hours(generated_dt)
        if not generated_at:
            warnings.append("generatedAt is missing; freshness timestamp is not fabricated.")
        elif generated_dt is None:
            warnings.append("generatedAt could not be parsed; freshness is unknown.")

        latest_validation_date = _latest_validation_date(backtest, calibration, manifest)
        if not latest_validation_date:
            warnings.append("validationDates are missing; latestValidationDate is not fabricated.")

        fallback_used = _first_bool(backtest, calibration, manifest, ("fallbackUsed", "fallback_used"))
        provenance = manifest.get("provenance")
        if fallback_used is None and isinstance(provenance, dict):
            fallback_used = _bool_value(provenance.get("fallbackUsed"))
        if fallback_used is True:
            blockers.append("fallback_used")
            warnings.append("Fallback provenance is true; artifacts cannot be treated as promotion-ready.")

        artifact_status = "ready" if backtest_path.is_file() and calibration_path.is_file() and manifest_path.is_file() else "missing"
        if artifact_status == "missing" and existing_paths:
            artifact_status = "partial"

        freshness_status = "missing" if blockers and any(blocker.startswith("missing_shadow_") for blocker in blockers) else "unknown"
        if artifact_status in {"ready", "partial"} and generated_dt is not None and artifact_age_hours is not None:
            freshness_status = "fresh" if artifact_age_hours <= self.max_allowed_age_hours else "stale"
            if freshness_status == "stale":
                warnings.append("Artifact generatedAt is older than the configured freshness policy.")
        elif artifact_status in {"ready", "partial"} and existing_paths and not generated_at:
            mtime_age = _mtime_age_hours(existing_paths)
            artifact_age_hours = mtime_age
            freshness_status = "unknown"
            warnings.append("File modified time was used only as secondary age fallback; generatedAt remains missing.")

        source_path = _public_source_path(backtest.get("sourcePath") or calibration.get("sourcePath") or manifest.get("sourcePath"))
        if not source_path:
            warnings.append("sourcePath is missing; source provenance is not fabricated.")

        return {
            "market": key,
            "modelStage": SHADOW_MODEL_STAGE,
            "modelKey": SHADOW_MODEL_KEY,
            "artifactStatus": artifact_status,
            "freshnessStatus": freshness_status,
            "generatedAt": generated_at,
            "artifactAgeHours": round(artifact_age_hours, 3) if artifact_age_hours is not None else None,
            "maxAllowedAgeHours": self.max_allowed_age_hours,
            "latestValidationDate": latest_validation_date,
            "sourcePath": source_path,
            "backtestPath": _public_path(self.settings.root_dir, backtest_path),
            "calibrationPath": _public_path(self.settings.root_dir, calibration_path),
            "manifestPath": _public_path(self.settings.root_dir, manifest_path),
            "fallbackUsed": bool(fallback_used) if fallback_used is not None else False,
            "registryShadowPointerPresent": bool(registry_shadow),
            "warnings": _dedupe(warnings),
            "blockers": _dedupe(blockers),
            "recommendedNextStep": _recommended_next_step(freshness_status, blockers),
            "readinessLabel": "Experimental",
            "action": "Research",
            "stakeUnits": 0,
            "betActionAllowed": False,
        }

    def compact_for_market(self, market: str, *, registry: dict[str, Any] | None = None) -> dict[str, Any]:
        row = self.freshness_for_market(market, registry=registry)
        return {
            "artifactStatus": row["artifactStatus"],
            "freshnessStatus": row["freshnessStatus"],
            "generatedAt": row["generatedAt"],
            "artifactAgeHours": row["artifactAgeHours"],
            "maxAllowedAgeHours": row["maxAllowedAgeHours"],
            "latestValidationDate": row["latestValidationDate"],
            "fallbackUsed": row["fallbackUsed"],
            "registryShadowPointerPresent": row["registryShadowPointerPresent"],
            "warnings": row["warnings"],
            "blockers": row["blockers"],
            "recommendedNextStep": row["recommendedNextStep"],
        }

    def artifact_dir(self, market: str) -> Path:
        return self.settings.data_dir / "models" / "artifacts" / "sprint19_shadow" / SHADOW_MODEL_KEY / normalize_market_key(market)


def _policy(max_allowed_age_hours: float) -> dict[str, Any]:
    return {
        "researchOnly": True,
        "productionPromotion": False,
        "action": "Research",
        "readinessLabel": "Experimental",
        "stakeUnits": 0,
        "betActionAllowed": False,
        "maxAllowedAgeHours": max_allowed_age_hours,
        "missingFallbackUsedTreatedAsFalse": True,
    }


def _recommended_next_step(status: str, blockers: list[str]) -> str:
    if "fallback_used" in blockers:
        return "Regenerate market-specific shadow artifacts without fallback provenance, then rerun the audit."
    if any(blocker.startswith("missing_shadow_") for blocker in blockers):
        return "Generate missing Sprint 19 shadow backtest, calibration, and manifest artifacts, then rerun freshness."
    if "missing_registry_shadow_pointer" in blockers:
        return "Repair the registry shadow calibrated_logistic pointer before considering artifact freshness complete."
    if status == "stale":
        return "Rerun the daily shadow evaluation workflow to refresh artifact metadata."
    if status == "fresh":
        return "Keep research-only locks in place and continue manual governance review separately."
    return "Add generatedAt, sourcePath, and validationDates provenance to the shadow artifacts, then rerun freshness."


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
    selected = str(shadow.get("selected_model") or shadow.get("selectedModel") or shadow.get("model_key") or shadow.get("modelKey") or "")
    if selected and selected != SHADOW_MODEL_KEY:
        return {}
    return dict(shadow)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _first_text(*payloads_and_keys: Any) -> str:
    *payloads, keys = payloads_and_keys
    key_list = keys if isinstance(keys, tuple) else (keys,)
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for key in key_list:
            if payload.get(key) not in {None, ""}:
                return str(payload[key])
    return ""


def _first_bool(*payloads_and_keys: Any) -> bool | None:
    *payloads, keys = payloads_and_keys
    key_list = keys if isinstance(keys, tuple) else (keys,)
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for key in key_list:
            parsed = _bool_value(payload.get(key))
            if parsed is not None:
                return parsed
    return None


def _bool_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in {None, ""}:
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def _latest_validation_date(*payloads: dict[str, Any]) -> str:
    values: list[str] = []
    for payload in payloads:
        raw = payload.get("validationDates") if isinstance(payload, dict) else None
        if isinstance(raw, list):
            values.extend(str(item) for item in raw if str(item).strip())
    return max(values) if values else ""


def _parse_datetime(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _age_hours(generated_at: datetime | None) -> float | None:
    if generated_at is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - generated_at).total_seconds() / 3600.0)


def _mtime_age_hours(paths: list[Path]) -> float | None:
    mtimes: list[float] = []
    for path in paths:
        try:
            mtimes.append(path.stat().st_mtime)
        except OSError:
            continue
    if not mtimes:
        return None
    return max(0.0, (datetime.now(timezone.utc).timestamp() - max(mtimes)) / 3600.0)


def _public_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return path.name


def _public_source_path(value: Any) -> str:
    return str(value or "").replace("\\", "/")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out
