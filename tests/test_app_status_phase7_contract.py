from __future__ import annotations
import json
from pathlib import Path
from mlb_app.schemas.app_status import APP_STATUS_SCHEMA_VERSION, validate_app_status_payload
from mlb_app.services.app_status_service import AppStatusService
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "app_status"
class FakePlayerboardService:
    def health_payload(self, query: dict[str, list[str]]) -> dict[str, object]: return {"ok": True, "date": "2026-05-07", "latestAvailableDate": "2026-05-07", "rowsLoaded": 25, "totalRowsInFile": 25, "badShiftedRows": 0, "missingMarketDisplayRows": 0, "latestSnapshotAt": "2026-05-07T16:00:00Z", "dataConfidence": "Good"}
class FakeGradingService:
    def payload(self, query: dict[str, list[str]]) -> dict[str, object]: return {"ok": True, "state": "graded", "date": "2026-05-07", "latestFullyGradedDate": "2026-05-07", "summary": {"backtestRowsForDate": 4, "gradedBacktestRowsForDate": 4, "mlRowsForDate": 3, "gradedMlRowsForDate": 3}}
class FakeWorkflowService:
    def payload(self) -> dict[str, object]: return {"ok": True, "summaries": {"dailyHealth": {"ok": True, "date": "2026-05-07", "checkedAt": "2026-05-07T16:10:00Z", "exists": True}, "dailyGrading": {"ok": True, "date": "2026-05-07", "checkedAt": "2026-05-07T16:20:00Z", "exists": True}, "weeklyRepair": {"ok": True, "date": "2026-05-04", "checkedAt": "2026-05-04T09:00:00Z", "exists": True}}}
class FakeModelRegistryService:
    def status_payload(self) -> dict[str, object]: return {"policy": {"requiresExactMarketArtifact": True, "genericFallbackAllowed": False, "minimumTrainingRows": 200}, "trainedMarkets": ["batter_hits"], "productionEligibleMarkets": ["batter_hits"]}
def load_fixture(name: str) -> dict[str, object]: return json.loads((FIXTURE_DIR / name).read_text())
def test_app_status_service_emits_v1_contract_with_request_id() -> None:
    payload = AppStatusService(playerboard_service=FakePlayerboardService(), grading_service=FakeGradingService(), workflow_service=FakeWorkflowService(), model_registry_service=FakeModelRegistryService()).payload({"season":["2026"]}, request_id="req-phase7")  # type: ignore[arg-type]
    assert payload["meta"]["schema"] == APP_STATUS_SCHEMA_VERSION
    assert payload["meta"]["requestId"] == "req-phase7"
    assert payload["meta"]["route"] == "/api/app/status"
    assert payload["productState"] == "research_mode"
    assert payload["grading"]["state"] == "graded"
    assert payload["playerboard"]["dataConfidence"] == "Good"
    assert validate_app_status_payload(payload) == []
def test_valid_contract_fixtures_pass_backend_validator() -> None:
    for name in ["ready.json", "research_only.json", "missing_model.json", "stale_board.json", "grading_delayed.json"]: assert validate_app_status_payload(load_fixture(name)) == [], name
def test_malformed_contract_fixture_fails_backend_validator() -> None:
    errors = validate_app_status_payload(load_fixture("malformed.json"))
    assert errors
    assert "productState must be a string" in errors
    assert "productionEligibleMarkets must be an array" in errors
    assert "meta.schema must be app-status-v1" in errors
