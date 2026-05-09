from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from mlb_app.asgi import app as asgi_app


def _client() -> TestClient:
    return TestClient(asgi_app, client=("127.0.0.1", 50000))


def get_json(path: str) -> tuple[int, dict[str, Any], str]:
    with _client() as client:
        response = client.get(path)
    return response.status_code, response.json(), response.headers.get("Content-Type", "")


def post_json(path: str, body: dict[str, object], *, action_header: bool = True) -> tuple[int, dict[str, Any], str]:
    headers = {"Content-Type": "application/json"}
    if action_header:
        headers["X-Baseball-Prop-Action"] = "1"
    with _client() as client:
        response = client.post(path, json=body, headers=headers)
    return response.status_code, response.json(), response.headers.get("Content-Type", "")


def test_app_status_contract() -> None:
    status, payload, content_type = get_json("/api/app/status")

    assert status == 200
    assert content_type.startswith("application/json")
    assert payload["status"] == "ok"
    assert payload["productState"] == "research_mode"
    assert payload["productStateDetail"]["label"] == "Research Mode"
    assert "latestFullyGradedDate" in payload
    assert isinstance(payload["trainedMarkets"], list)
    assert isinstance(payload["productionEligibleMarkets"], list)


def test_prop_ml_status_contract_remains_explicit_legacy_fallback() -> None:
    status, payload, _content_type = get_json("/api/prop-ml/status")

    assert status == 200
    assert payload["status"] in {"ok", "partial", "not_ready"}
    assert "markets" in payload
    assert "policy" in payload


def test_model_cards_contract() -> None:
    status, payload, content_type = get_json("/api/model-cards")

    assert status == 200
    assert content_type.startswith("application/json")
    assert payload["status"] == "ok"
    assert isinstance(payload["markets"], list)
    assert payload["markets"]
    first = payload["markets"][0]
    assert "decisionPolicy" in first
    assert "trustWarnings" in first
    assert "backtest" in first


def test_single_model_card_contract() -> None:
    status, payload, content_type = get_json("/api/model-card?market=batter_hits")

    assert status == 200
    assert content_type.startswith("application/json")
    assert payload["status"] == "ok"
    assert payload["markets"]
    first = payload["markets"][0]
    assert first["market"] == "batter_hits"
    assert "canShowConfidentPick" in first


def test_edge_board_contract() -> None:
    status, payload, content_type = get_json("/api/edge-board?season=2026&limit=5")

    assert status == 200
    assert content_type.startswith("application/json")
    assert payload["status"] == "ok"
    assert "rows" in payload
    assert isinstance(payload["rows"], list)
    assert "summary" in payload
    assert "filters" in payload
    assert "trust" in payload


def test_prop_detail_contract() -> None:
    status, payload, content_type = get_json("/api/prop-detail?market=batter_hits&player=Contract%20Player&team=NYY&opponent=BAL&line=0.5&americanOdds=-110")

    assert status == 200
    assert content_type.startswith("application/json")
    assert payload["status"] == "ok"
    assert payload["detail"]["overview"]["player"] == "Contract Player"
    assert "priceComparison" in payload["detail"]
    assert "modelExplanation" in payload["detail"]
    assert "riskContext" in payload["detail"]
    assert payload["detail"]["tracking"]["separateFromModelBacktests"] is True


def test_data_health_dashboard_contract() -> None:
    status, payload, content_type = get_json("/api/data-health/dashboard?season=2026&date=2026-05-07")

    assert status == 200
    assert content_type.startswith("application/json")
    assert payload["status"] == "ok"
    assert payload["version"] == "data-health-dashboard-v1"
    assert isinstance(payload["cards"], list)
    assert isinstance(payload["workflowPhases"], list)
    assert payload["productState"]["state"] == "research_mode"


def test_workflow_health_contract() -> None:
    status, payload, content_type = get_json("/api/workflows/health")

    assert status == 200
    assert content_type.startswith("application/json")
    assert "summaries" in payload
    assert "dailyHealth" in payload["summaries"]


def test_unknown_api_contract_is_safe_json() -> None:
    status, payload, content_type = get_json("/api/not-real")

    assert status == 404
    assert content_type.startswith("application/json")
    assert payload == {"status": "error", "code": "not_found", "error": "Not found"}


def test_playerboard_health_contract() -> None:
    status, payload, content_type = get_json("/api/playerboard/health")

    assert status == 200
    assert content_type.startswith("application/json")
    assert "rowsLoaded" in payload
    assert "latestFullyGradedDate" in payload
    assert payload["trust"]["mode"] == "research_mode"


def test_grading_health_contract() -> None:
    status, payload, content_type = get_json("/api/grading/health")

    assert status == 200
    assert content_type.startswith("application/json")
    assert payload["state"] in {"not_started", "waiting_for_finals", "graded", "partial", "failed"}
    assert "latestFullyGradedDate" in payload


def test_my_picks_contract_and_action_header() -> None:
    status, payload, content_type = get_json("/api/my-picks")
    assert status == 200
    assert content_type.startswith("application/json")
    assert payload["status"] == "ok"
    assert "exposure" in payload
    assert payload["policy"]["separateFromModelBacktests"] is True

    denied_status, denied_payload, _ = post_json("/api/my-picks", {"player": "Denied", "team": "NYY", "opponent": "BAL", "market": "batter_hits"}, action_header=False)
    assert denied_status == 403
    assert denied_payload["code"] == "action_header_required"

    created_status, created_payload, _ = post_json("/api/my-picks", {"date": "2026-05-07", "player": "Aaron Judge", "team": "NYY", "opponent": "BAL", "market": "batter_hits", "line": "0.5", "americanOdds": "-110", "decisionLabel": "Watchlist", "readinessLabel": "Research only", "suggestedStake": "Research only", "stakeUnits": 1})
    assert created_status == 200
    assert created_payload["status"] == "ok"
    assert created_payload["pick"]["stakeUnits"] == 0.0


def test_bankroll_settings_contract() -> None:
    status, payload, _ = get_json("/api/bankroll/settings")
    assert status == 200
    assert payload["status"] == "ok"
    assert payload["settings"]["stakingMethod"] in payload["allowedStakingMethods"]

    update_status, update_payload, _ = post_json("/api/bankroll/settings", {"bankroll": 1500, "defaultUnitSize": 15, "maxUnitsPerBet": 0.25})
    assert update_status == 200
    assert update_payload["settings"]["bankroll"] == 1500
    assert update_payload["settings"]["maxUnitsPerBet"] == 0.25
