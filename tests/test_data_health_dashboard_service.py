from __future__ import annotations

from mlb_app.services.data_health_dashboard_service import DataHealthDashboardService


def test_data_health_dashboard_contract_defaults_to_product_grade_shape() -> None:
    payload = DataHealthDashboardService().payload({"season": ["2026"], "date": ["2026-05-07"]})

    assert payload["status"] == "ok"
    assert payload["version"] == "data-health-dashboard-v1"
    assert payload["overallStatus"] in {"Good", "Partial", "Stale", "Missing", "Failed"}
    assert payload["dataConfidence"] in {"Good", "Partial", "Stale", "Missing", "Failed"}
    assert payload["productState"]["state"] == "research_mode"
    assert isinstance(payload["cards"], list)
    assert isinstance(payload["workflowPhases"], list)
    assert {card["key"] for card in payload["cards"]} >= {
        "odds_freshness",
        "playerboard_freshness",
        "schedule_coverage",
        "prop_coverage",
        "weather_coverage",
        "pitcher_coverage",
        "lineup_coverage",
        "bvp_coverage",
        "savant_coverage",
        "grading_status",
        "model_artifacts",
    }
    assert {phase["key"] for phase in payload["workflowPhases"]} == {"morning", "pre_lock", "postgame", "weekly"}


def test_data_health_dashboard_cards_use_limited_status_vocabulary() -> None:
    payload = DataHealthDashboardService().payload({"season": ["2026"], "date": ["2026-05-07"]})
    allowed = {"Good", "Partial", "Stale", "Missing", "Failed"}

    assert all(card["status"] in allowed for card in payload["cards"])
    assert all(phase["status"] in allowed for phase in payload["workflowPhases"])
