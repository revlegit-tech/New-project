from __future__ import annotations
from datetime import datetime, timezone
from typing import Any

APP_STATUS_SCHEMA_VERSION = "app-status-v1"
APP_STATUS_ROUTE = "/api/app/status"
VALID_DATA_CONFIDENCE = {"Good", "Partial", "Stale", "Missing", "Failed"}
VALID_PRODUCT_STATES = {"research_mode", "experimental_model", "backtest_positive", "production_tracked"}
VALID_GRADING_STATES = {"not_started", "waiting_for_finals", "boxscores_loaded", "grading_running", "graded", "partial", "failed"}
REQUIRED_TOP_LEVEL_FIELDS = ("status", "ok", "season", "checkedAt", "generatedAt", "warnings", "productState", "productStateDetail", "researchMode", "latestBoardDate", "latestFullyGradedDate", "dataConfidence", "modelPolicy", "trainedMarkets", "productionEligibleMarkets", "playerboard", "grading", "workflows", "meta")

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def build_app_status_payload(*, season: int, playerboard: dict[str, Any], grading: dict[str, Any], workflows: dict[str, Any], model_status: dict[str, Any], product_state: dict[str, Any], request_id: str = "", generated_at: str | None = None) -> dict[str, Any]:
    """Build the canonical app-status-v1 response consumed by the trust surface."""
    generated_at = generated_at or utc_now_iso()
    board_date = _string(playerboard.get("latestAvailableDate") or playerboard.get("date"))
    grading_state = normalize_grading_state(grading.get("state"))
    grading_summary = grading.get("summary") if isinstance(grading.get("summary"), dict) else {}
    workflow_summaries = workflows.get("summaries") if isinstance(workflows.get("summaries"), dict) else {}
    production_markets = _string_list(model_status.get("productionEligibleMarkets"))
    trained_markets = _string_list(model_status.get("trainedMarkets"))
    confidence = normalize_data_confidence(playerboard.get("dataConfidence"))
    warnings: list[str] = []
    for source in (playerboard, grading, workflows, model_status):
        warnings.extend(_string_list(source.get("warnings")))
    if not _bool(playerboard.get("ok")):
        warnings.append("Playerboard needs attention.")
    if grading_state != "graded":
        warnings.append("Latest board date is not fully graded yet.")
    if not _bool(workflows.get("ok")):
        warnings.append("Workflow summaries need attention.")
    if not production_markets:
        warnings.append("No market is currently eligible for confident production picks.")
    product_detail = normalize_product_state(product_state)
    return {
        "status": "ok",
        "ok": not _dedupe(warnings),
        "season": int(season),
        "checkedAt": generated_at,
        "generatedAt": generated_at,
        "warnings": _dedupe(warnings),
        "productState": product_detail["state"],
        "productStateDetail": product_detail,
        "researchMode": bool(product_detail.get("researchMode", True)),
        "latestBoardDate": board_date,
        "latestFullyGradedDate": _string(grading.get("latestFullyGradedDate")),
        "dataConfidence": confidence,
        "modelPolicy": model_status.get("policy") if isinstance(model_status.get("policy"), dict) else {},
        "trainedMarkets": trained_markets,
        "productionEligibleMarkets": production_markets,
        "playerboard": {
            "ok": _bool(playerboard.get("ok")),
            "date": _string(playerboard.get("date") or playerboard.get("latestAvailableDate")),
            "latestAvailableDate": _string(playerboard.get("latestAvailableDate")),
            "rowsLoaded": _int(playerboard.get("rowsLoaded")),
            "totalRowsInFile": _int(playerboard.get("totalRowsInFile")),
            "badShiftedRows": _int(playerboard.get("badShiftedRows")),
            "missingMarketDisplayRows": _int(playerboard.get("missingMarketDisplayRows")),
            "latestSnapshotAt": _string(playerboard.get("latestSnapshotAt")),
            "dataConfidence": confidence,
        },
        "grading": {
            "ok": _bool(grading.get("ok")),
            "state": grading_state,
            "date": _string(grading.get("date")),
            "latestFullyGradedDate": _string(grading.get("latestFullyGradedDate")),
            "backtestRowsForDate": _int(grading_summary.get("backtestRowsForDate")),
            "gradedBacktestRowsForDate": _int(grading_summary.get("gradedBacktestRowsForDate")),
            "mlRowsForDate": _int(grading_summary.get("mlRowsForDate")),
            "gradedMlRowsForDate": _int(grading_summary.get("gradedMlRowsForDate")),
        },
        "workflows": {
            "ok": _bool(workflows.get("ok")),
            "dailyHealth": _trim_workflow_summary(_dict(workflow_summaries.get("dailyHealth"))),
            "dailyGrading": _trim_workflow_summary(_dict(workflow_summaries.get("dailyGrading"))),
            "weeklyRepair": _trim_workflow_summary(_dict(workflow_summaries.get("weeklyRepair"))),
        },
        "meta": {"schema": APP_STATUS_SCHEMA_VERSION, "route": APP_STATUS_ROUTE, "requestId": _string(request_id), "generatedAt": generated_at},
    }

def normalize_product_state(product_state: dict[str, Any] | None) -> dict[str, Any]:
    raw = product_state or {}
    state = _string(raw.get("state") or raw.get("productState"), "research_mode")
    if state not in VALID_PRODUCT_STATES:
        state = "research_mode"
    return {"state": state, "productState": state, "label": _string(raw.get("label"), "Research Mode"), "severity": _string(raw.get("severity"), "warning"), "message": _string(raw.get("message"), "Model outputs are experimental. Use this board for research, not blind tailing or automated betting."), "researchMode": _bool(raw.get("researchMode"), default=True), "allowedDecisionLabels": _string_list(raw.get("allowedDecisionLabels")) or ["No bet", "Watchlist", "Model lean"], "generatedAt": _string(raw.get("generatedAt")) or utc_now_iso()}

def normalize_data_confidence(value: Any) -> str:
    text = _string(value, "Missing")
    title = text[:1].upper() + text[1:] if text else "Missing"
    return title if title in VALID_DATA_CONFIDENCE else "Missing"

def normalize_grading_state(value: Any) -> str:
    text = _string(value, "not_started").lower()
    return text if text in VALID_GRADING_STATES else "failed"

def validate_app_status_payload(payload: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["payload must be an object"]
    for field in REQUIRED_TOP_LEVEL_FIELDS:
        if field not in payload:
            errors.append(f"missing top-level field: {field}")
    if payload.get("status") != "ok": errors.append("status must be 'ok'")
    if not isinstance(payload.get("ok"), bool): errors.append("ok must be a boolean")
    if not isinstance(payload.get("season"), int): errors.append("season must be an integer")
    if not isinstance(payload.get("warnings"), list): errors.append("warnings must be an array")
    if not isinstance(payload.get("productState"), str): errors.append("productState must be a string")
    elif payload["productState"] not in VALID_PRODUCT_STATES: errors.append("productState must be a known state")
    if not isinstance(payload.get("productStateDetail"), dict): errors.append("productStateDetail must be an object")
    if not isinstance(payload.get("researchMode"), bool): errors.append("researchMode must be a boolean")
    if not isinstance(payload.get("latestBoardDate"), str): errors.append("latestBoardDate must be a string")
    if not isinstance(payload.get("latestFullyGradedDate"), str): errors.append("latestFullyGradedDate must be a string")
    if payload.get("dataConfidence") not in VALID_DATA_CONFIDENCE: errors.append("dataConfidence must be Good, Partial, Stale, Missing, or Failed")
    if not isinstance(payload.get("modelPolicy"), dict): errors.append("modelPolicy must be an object")
    if not isinstance(payload.get("trainedMarkets"), list): errors.append("trainedMarkets must be an array")
    if not isinstance(payload.get("productionEligibleMarkets"), list): errors.append("productionEligibleMarkets must be an array")
    playerboard = payload.get("playerboard")
    if not isinstance(playerboard, dict): errors.append("playerboard must be an object")
    else:
        for key in ("ok", "date", "latestAvailableDate", "rowsLoaded", "totalRowsInFile", "dataConfidence"):
            if key not in playerboard: errors.append(f"playerboard.{key} is required")
        if not isinstance(playerboard.get("ok"), bool): errors.append("playerboard.ok must be a boolean")
        if playerboard.get("dataConfidence") not in VALID_DATA_CONFIDENCE: errors.append("playerboard.dataConfidence must be a known confidence value")
    grading = payload.get("grading")
    if not isinstance(grading, dict): errors.append("grading must be an object")
    else:
        for key in ("ok", "state", "date", "latestFullyGradedDate"):
            if key not in grading: errors.append(f"grading.{key} is required")
        if grading.get("state") not in VALID_GRADING_STATES: errors.append("grading.state must be a known grading state")
    workflows = payload.get("workflows")
    if not isinstance(workflows, dict): errors.append("workflows must be an object")
    else:
        for key in ("ok", "dailyHealth", "dailyGrading", "weeklyRepair"):
            if key not in workflows: errors.append(f"workflows.{key} is required")
    meta = payload.get("meta")
    if not isinstance(meta, dict): errors.append("meta must be an object")
    else:
        if meta.get("schema") != APP_STATUS_SCHEMA_VERSION: errors.append(f"meta.schema must be {APP_STATUS_SCHEMA_VERSION}")
        if meta.get("route") != APP_STATUS_ROUTE: errors.append(f"meta.route must be {APP_STATUS_ROUTE}")
        if not isinstance(meta.get("requestId"), str): errors.append("meta.requestId must be a string")
        if not isinstance(meta.get("generatedAt"), str): errors.append("meta.generatedAt must be a string")
    return errors

def _trim_workflow_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {"ok": _bool(summary.get("ok")), "date": _string(summary.get("date")), "checkedAt": _string(summary.get("checkedAt")), "exists": _bool(summary.get("exists"))}

def _dict(value: Any) -> dict[str, Any]: return value if isinstance(value, dict) else {}
def _string(value: Any, default: str = "") -> str: return default if value is None else str(value)
def _string_list(value: Any) -> list[str]: return [str(item) for item in value if str(item).strip()] if isinstance(value, (list, tuple, set)) else []
def _bool(value: Any, default: bool = False) -> bool:
    if value is None: return default
    if isinstance(value, bool): return value
    return str(value).strip().lower() not in {"0", "false", "no", "off", "", "none"}
def _int(value: Any, default: int = 0) -> int:
    try:
        if value in {None, ""}: return default
        return int(float(value))
    except (TypeError, ValueError): return default
def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set(); out: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            out.append(text); seen.add(text)
    return out
