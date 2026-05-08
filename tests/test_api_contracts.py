from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from typing import Iterator
from urllib.request import Request, urlopen

from mlb_app.server import AppRequestHandler


@contextmanager
def modular_server() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), AppRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def get_json(base_url: str, path: str) -> tuple[int, dict[str, object], str]:
    request = Request(base_url + path, method="GET")
    try:
        with urlopen(request, timeout=5) as response:  # noqa: S310 - local test server only
            return response.status, json.loads(response.read().decode("utf-8")), response.headers.get("Content-Type", "")
    except Exception as error:  # urllib raises for 404; preserve response payload for contract assertions.
        response = getattr(error, "fp", None)
        code = int(getattr(error, "code", 0))
        if response is None or code == 0:
            raise
        return code, json.loads(response.read().decode("utf-8")), getattr(error, "headers", {}).get("Content-Type", "")


def test_app_status_contract() -> None:
    with modular_server() as base_url:
        status, payload, content_type = get_json(base_url, "/api/app/status")

    assert status == 200
    assert content_type.startswith("application/json")
    assert payload["status"] == "ok"
    assert payload["productState"] == "research_mode"
    assert payload["productStateDetail"]["label"] == "Research Mode"
    assert "latestFullyGradedDate" in payload
    assert isinstance(payload["trainedMarkets"], list)
    assert isinstance(payload["productionEligibleMarkets"], list)


def test_prop_ml_status_contract() -> None:
    with modular_server() as base_url:
        status, payload, _content_type = get_json(base_url, "/api/prop-ml/status")

    assert status == 200
    assert payload["status"] in {"ok", "partial", "not_ready"}
    assert "markets" in payload
    assert "policy" in payload


def test_model_cards_contract() -> None:
    with modular_server() as base_url:
        status, payload, content_type = get_json(base_url, "/api/model-cards")

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
    with modular_server() as base_url:
        status, payload, content_type = get_json(base_url, "/api/model-card?market=batter_hits")

    assert status == 200
    assert content_type.startswith("application/json")
    assert payload["status"] == "ok"
    assert payload["modelCard"]["market"] == "batter_hits"
    assert "canShowConfidentPick" in payload["modelCard"]



def test_edge_board_contract() -> None:
    with modular_server() as base_url:
        status, payload, content_type = get_json(base_url, "/api/edge-board?season=2026&limit=5")

    assert status == 200
    assert content_type.startswith("application/json")
    assert payload["status"] == "ok"
    assert "rows" in payload
    assert isinstance(payload["rows"], list)
    assert "summary" in payload
    assert "filters" in payload
    assert "trust" in payload


def test_prop_detail_contract() -> None:
    with modular_server() as base_url:
        status, payload, content_type = get_json(base_url, "/api/prop-detail?market=batter_hits&player=Contract%20Player&team=NYY&opponent=BAL&line=0.5&americanOdds=-110")

    assert status == 200
    assert content_type.startswith("application/json")
    assert payload["status"] == "ok"
    assert payload["detail"]["overview"]["player"] == "Contract Player"
    assert "priceComparison" in payload["detail"]
    assert "modelExplanation" in payload["detail"]
    assert "riskContext" in payload["detail"]
    assert payload["detail"]["tracking"]["separateFromModelBacktests"] is True



def test_data_health_dashboard_contract() -> None:
    with modular_server() as base_url:
        status, payload, content_type = get_json(base_url, "/api/data-health/dashboard?season=2026&date=2026-05-07")

    assert status == 200
    assert content_type.startswith("application/json")
    assert payload["status"] == "ok"
    assert payload["version"] == "data-health-dashboard-v1"
    assert isinstance(payload["cards"], list)
    assert isinstance(payload["workflowPhases"], list)
    assert payload["productState"]["state"] == "research_mode"


def test_workflow_health_contract() -> None:
    with modular_server() as base_url:
        status, payload, content_type = get_json(base_url, "/api/workflows/health")

    assert status == 200
    assert content_type.startswith("application/json")
    assert "summaries" in payload
    assert "dailyHealth" in payload["summaries"]

def test_unknown_api_contract_is_safe_json() -> None:
    with modular_server() as base_url:
        status, payload, content_type = get_json(base_url, "/api/not-real")

    assert status == 404
    assert content_type.startswith("application/json")
    assert payload == {"status": "error", "code": "not_found", "error": "Not found"}


def test_playerboard_health_contract() -> None:
    with modular_server() as base_url:
        status, payload, content_type = get_json(base_url, "/api/playerboard/health")

    assert status == 200
    assert content_type.startswith("application/json")
    assert "rowsLoaded" in payload
    assert "latestFullyGradedDate" in payload
    assert payload["trust"]["mode"] == "research_mode"


def test_grading_health_contract() -> None:
    with modular_server() as base_url:
        status, payload, content_type = get_json(base_url, "/api/grading/health")

    assert status == 200
    assert content_type.startswith("application/json")
    assert payload["state"] in {"not_started", "waiting_for_finals", "graded", "partial", "failed"}
    assert "latestFullyGradedDate" in payload


def post_json(base_url: str, path: str, body: dict[str, object], *, action_header: bool = True) -> tuple[int, dict[str, object], str]:
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if action_header:
        headers["X-Baseball-Prop-Action"] = "1"
    request = Request(base_url + path, data=data, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=5) as response:  # noqa: S310 - local test server only
            return response.status, json.loads(response.read().decode("utf-8")), response.headers.get("Content-Type", "")
    except Exception as error:
        response = getattr(error, "fp", None)
        code = int(getattr(error, "code", 0))
        if response is None or code == 0:
            raise
        return code, json.loads(response.read().decode("utf-8")), getattr(error, "headers", {}).get("Content-Type", "")


def test_my_picks_contract_and_action_header() -> None:
    with modular_server() as base_url:
        status, payload, content_type = get_json(base_url, "/api/my-picks")
        assert status == 200
        assert content_type.startswith("application/json")
        assert payload["status"] == "ok"
        assert "exposure" in payload
        assert payload["policy"]["separateFromModelBacktests"] is True

        denied_status, denied_payload, _ = post_json(base_url, "/api/my-picks", {"player": "Denied", "team": "NYY", "opponent": "BAL", "market": "batter_hits"}, action_header=False)
        assert denied_status == 403
        assert denied_payload["code"] == "action_header_required"

        created_status, created_payload, _ = post_json(base_url, "/api/my-picks", {"date": "2026-05-07", "player": "Aaron Judge", "team": "NYY", "opponent": "BAL", "market": "batter_hits", "line": "0.5", "americanOdds": "-110", "decisionLabel": "Watchlist", "readinessLabel": "Research only", "suggestedStake": "Research only", "stakeUnits": 1})
        assert created_status == 200
        assert created_payload["status"] == "ok"
        assert created_payload["pick"]["stakeUnits"] == 0.0


def test_bankroll_settings_contract() -> None:
    with modular_server() as base_url:
        status, payload, _ = get_json(base_url, "/api/bankroll/settings")
        assert status == 200
        assert payload["status"] == "ok"
        assert payload["settings"]["stakingMethod"] in payload["allowedStakingMethods"]

        update_status, update_payload, _ = post_json(base_url, "/api/bankroll/settings", {"bankroll": 1500, "defaultUnitSize": 15, "maxUnitsPerBet": 0.25})
        assert update_status == 200
        assert update_payload["settings"]["bankroll"] == 1500
        assert update_payload["settings"]["maxUnitsPerBet"] == 0.25
