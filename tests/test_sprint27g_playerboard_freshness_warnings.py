from __future__ import annotations

from mlb_app.services.data_health_dashboard_service import DataHealthDashboardService


def test_data_health_dashboard_surfaces_playerboard_freshness_diagnostics() -> None:
    warnings = DataHealthDashboardService._playerboard_warnings(
        {
            "exists": True,
            "schemaOk": True,
            "rowsLoaded": 3497,
            "dateRowsInFile": 17631,
            "snapshotGroupCount": 5,
            "latestRecentGameDate": "2026-05-06",
            "recentGamesAgeDays": 48,
            "rowsWithRecentGames": 12202,
            "staleRecentGameRows": 6500,
            "warnings": ["Multiple playerboard snapshot groups detected for this date (5)."],
        }
    )

    assert any("Multiple playerboard snapshot groups" in warning for warning in warnings)
    assert any("row count is unusually high" in warning for warning in warnings)
    assert any("recentGames context appears stale" in warning for warning in warnings)
