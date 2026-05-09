from __future__ import annotations

from typing import Any

from mlb_app.observability.metrics import MetricsRegistry, default_registry


class AlertService:
    """Evaluates operator-facing alert rules from app health and metrics."""

    def __init__(self, *, metrics: MetricsRegistry | None = None, p95_latency_threshold_ms: float = 750.0) -> None:
        self.metrics = metrics or default_registry()
        self.p95_latency_threshold_ms = float(p95_latency_threshold_ms)

    def evaluate(self, *, app_status: dict[str, Any], model_status: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        playerboard = app_status.get("playerboard") if isinstance(app_status.get("playerboard"), dict) else {}
        workflows = app_status.get("workflows") if isinstance(app_status.get("workflows"), dict) else {}
        model_status = model_status or {}

        confidence = str(app_status.get("dataConfidence") or playerboard.get("dataConfidence") or "").lower()
        if confidence in {"stale", "missing", "failed"}:
            alerts.append(_alert("playerboard_stale", "critical", f"Playerboard confidence is {confidence or 'unknown'}."))
        elif confidence == "partial":
            alerts.append(_alert("playerboard_partial", "warning", "Playerboard is partial; verify schema, grading, and row counts."))

        if not bool(playerboard.get("ok", True)):
            alerts.append(_alert("playerboard_unhealthy", "critical", "Playerboard health check is not OK."))
        if int(playerboard.get("badShiftedRows") or 0) > 0 or not bool(playerboard.get("schemaOk", True)):
            alerts.append(_alert("schema_mismatch", "critical", "Playerboard schema mismatch or shifted rows detected."))
        if not bool(workflows.get("ok", True)):
            alerts.append(_alert("collector_failed", "warning", "One or more collector workflow summaries need attention."))

        model_warnings = list(model_status.get("warnings") or []) if isinstance(model_status.get("warnings"), list) else []
        if any("hash" in str(warning).lower() or "artifact" in str(warning).lower() for warning in model_warnings):
            alerts.append(_alert("model_artifact_verification_failed", "critical", "Model artifact verification warning is active."))
        for market in model_status.get("markets") or []:
            if isinstance(market, dict) and market.get("hashVerified") is False and market.get("artifactSha256"):
                alerts.append(_alert("model_artifact_verification_failed", "critical", f"Artifact hash failed for {market.get('market')}"))

        for histogram in self.metrics.snapshot().get("histograms", []):
            if histogram.get("name") == "http_request_latency_ms" and (histogram.get("p95") or 0) > self.p95_latency_threshold_ms:
                alerts.append(
                    _alert(
                        "p95_latency_high",
                        "warning",
                        f"P95 latency {histogram.get('p95')}ms exceeds {self.p95_latency_threshold_ms:.0f}ms.",
                        labels=histogram.get("labels") or {},
                    )
                )
        return _dedupe_alerts(alerts)

    def payload(self, *, app_status: dict[str, Any], model_status: dict[str, Any] | None = None) -> dict[str, Any]:
        alerts = self.evaluate(app_status=app_status, model_status=model_status)
        return {
            "status": "ok",
            "alerts": alerts,
            "alertCount": len(alerts),
            "severityCounts": _severity_counts(alerts),
            "rules": [
                "collector_failed",
                "playerboard_stale",
                "schema_mismatch",
                "model_artifact_verification_failed",
                "p95_latency_high",
            ],
        }


def _alert(code: str, severity: str, message: str, *, labels: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message, "labels": labels or {}}


def _dedupe_alerts(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for alert in alerts:
        key = (str(alert.get("code")), str(alert.get("message")))
        if key not in seen:
            seen.add(key)
            out.append(alert)
    return out


def _severity_counts(alerts: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for alert in alerts:
        severity = str(alert.get("severity") or "unknown")
        counts[severity] = counts.get(severity, 0) + 1
    return counts
