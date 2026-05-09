from __future__ import annotations

from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.repositories.model_artifact_repository import hash_payload
from mlb_app.repositories.model_store import normalize_market_key
from mlb_app.repositories.prediction_events_repository import PredictionEventsRepository
from mlb_app.services.model_registry_service import ModelRegistryService


class PredictionAuditService:
    """Records and reads append-only prediction audit events."""

    def __init__(
        self,
        settings: Settings = default_settings,
        *,
        repository: PredictionEventsRepository | None = None,
        model_registry_service: ModelRegistryService | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository or PredictionEventsRepository(settings)
        self.model_registry_service = model_registry_service or ModelRegistryService(settings=settings)

    def record(self, body: dict[str, Any]) -> dict[str, Any]:
        market = normalize_market_key(body.get("market") or body.get("modelKey") or "")
        if not market:
            return {"status": "error", "code": "missing_market", "error": "market is required", "_status": 400}
        output_probability = _optional_float(body.get("outputProbability") or body.get("output_probability"))
        if output_probability is None:
            return {
                "status": "error",
                "code": "missing_output_probability",
                "error": "outputProbability is required",
                "_status": 400,
            }
        status = self.model_registry_service.market_status(market)
        model_version = str(body.get("modelVersion") or body.get("model_version") or status.get("version") or "")
        artifact_sha = str(body.get("artifactSha256") or body.get("artifact_sha256") or status.get("artifactSha256") or "")
        input_payload = body.get("input") or body.get("features") or body.get("metadata") or {}
        event = {
            **body,
            "modelKey": str(body.get("modelKey") or body.get("model_key") or market),
            "modelVersion": model_version,
            "market": market,
            "inputHash": str(body.get("inputHash") or body.get("input_hash") or hash_payload(input_payload)),
            "outputProbability": output_probability,
            "outputEdge": _optional_float(body.get("outputEdge") or body.get("output_edge")),
            "artifactSha256": artifact_sha,
            "modelStatus": status.get("status"),
            "modelArtifactHashVerified": status.get("hashVerified"),
        }
        saved = self.repository.append_if_absent(event)
        return {"status": "ok", "event": saved, "storage": {"sourceOfTruth": "sqlite", "path": str(self.repository.path)}}

    def payload(self, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
        query = query or {}
        market = _query(query, "market")
        model_key = _query(query, "modelKey") or _query(query, "model_key")
        limit = _int(_query(query, "limit"), 100)
        events = self.repository.list_events(market=market, model_key=model_key, limit=limit)
        return {
            "status": "ok",
            "events": events,
            "eventCount": len(events),
            "storage": {"sourceOfTruth": "sqlite", "path": str(self.repository.path)},
            "filters": {"market": market, "modelKey": model_key, "limit": limit},
        }


def _query(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key) or []
    return str(values[0]).strip() if values else ""


def _int(value: Any, default: int) -> int:
    try:
        return max(1, min(int(value), 1000)) if str(value).strip() else default
    except (TypeError, ValueError):
        return default


def _optional_float(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
