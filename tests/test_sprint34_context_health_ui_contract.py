from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from mlb_app.api.app import create_app
from mlb_app.config import Settings
from mlb_app.container import AppContainer


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_CONTEXT_FIELDS = {
    "status",
    "configuredForCurrentModel",
    "usedByCurrentModel",
    "artifactExists",
    "artifactRows",
    "rowsLoaded",
    "rowsJoinedToScoring",
    "populatedFeatureFields",
    "missingFeatureFields",
    "populatedPercent",
    "modelFeatureFields",
    "reason",
    "warnings",
}


def make_settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    return Settings(
        root_dir=tmp_path,
        public_dir=tmp_path / "public",
        data_dir=data_dir,
        model_dir=data_dir / "models",
        model_registry_path=data_dir / "models" / "model_registry.json",
        db_path=data_dir / "state.sqlite3",
        current_season=2026,
        db_enabled=False,
    )


def context_entry(
    *,
    status: str,
    configured: bool,
    used: bool,
    artifact_exists: bool,
    artifact_rows: int,
    rows_loaded: int,
    rows_joined: int,
    populated_fields: list[str],
    missing_fields: list[str],
    model_fields: list[str],
    reason: str,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "configuredForCurrentModel": configured,
        "usedByCurrentModel": used,
        "artifactExists": artifact_exists,
        "artifactRows": artifact_rows,
        "rowsLoaded": rows_loaded,
        "rowsJoinedToScoring": rows_joined,
        "populatedFeatureFields": populated_fields,
        "missingFeatureFields": missing_fields,
        "populatedPercent": 100.0 if populated_fields and not missing_fields else 0.0,
        "modelFeatureFields": model_fields,
        "reason": reason,
        "warnings": warnings or [],
    }


def write_prediction_summary(settings: Settings) -> None:
    summary_path = settings.data_dir / "predictions" / "prop_predictions_2026-07-03_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "contextConsumption": {
                    "player_recent_form": context_entry(
                        status="used",
                        configured=True,
                        used=True,
                        artifact_exists=True,
                        artifact_rows=10,
                        rows_loaded=10,
                        rows_joined=8,
                        populated_fields=["recent_hits_rate"],
                        missing_fields=[],
                        model_fields=["recent_hits_rate"],
                        reason="Rows joined to scoring and configured model fields are populated.",
                    ),
                    "game_markets": context_entry(
                        status="artifact_only",
                        configured=True,
                        used=False,
                        artifact_exists=True,
                        artifact_rows=6,
                        rows_loaded=6,
                        rows_joined=0,
                        populated_fields=[],
                        missing_fields=["game_market_consensus_current_total"],
                        model_fields=["game_market_consensus_current_total"],
                        reason="Artifact exists, but join into scoring/model features is pending.",
                    ),
                    "statcast": context_entry(
                        status="no_safe_rows",
                        configured=True,
                        used=False,
                        artifact_exists=True,
                        artifact_rows=0,
                        rows_loaded=0,
                        rows_joined=0,
                        populated_fields=[],
                        missing_fields=["barrel_rate"],
                        model_fields=["barrel_rate"],
                        reason="No safe local rows are available for pregame scoring.",
                    ),
                    "weather": context_entry(
                        status="available_not_used",
                        configured=False,
                        used=False,
                        artifact_exists=True,
                        artifact_rows=3,
                        rows_loaded=3,
                        rows_joined=0,
                        populated_fields=[],
                        missing_fields=[],
                        model_fields=[],
                        reason="Artifact is available, but current model metadata does not consume this group.",
                    ),
                    "umpire": context_entry(
                        status="unavailable",
                        configured=False,
                        used=False,
                        artifact_exists=False,
                        artifact_rows=0,
                        rows_loaded=0,
                        rows_joined=0,
                        populated_fields=[],
                        missing_fields=[],
                        model_fields=[],
                        reason="Unavailable for the current slate.",
                    ),
                },
                "contextFeatureArtifacts": {
                    "player_recent_form": {"exists": True, "rows": 10},
                    "game_markets": {"exists": True, "rows": 6},
                    "statcast": {"exists": True, "rows": 0},
                    "weather": {"exists": True, "rows": 3},
                    "umpire": {"exists": False, "rows": 0},
                },
                "contextJoinCounts": {"player_recent_form": 8, "game_markets": 0, "statcast": 0},
                "featureCompleteness": {
                    "recent_hits_rate": {"populated": 8, "missing": 0},
                    "game_market_consensus_current_total": {"populated": 0, "missing": 8},
                },
                "featureGroupsReady": ["player_recent_form"],
                "featureGroupsMissing": ["game_markets", "statcast"],
            }
        ),
        encoding="utf-8",
    )


def test_data_status_context_consumption_contract_is_preserved(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_prediction_summary(settings)
    client = TestClient(create_app(container=AppContainer(settings=settings)), client=("127.0.0.1", 50000))

    response = client.get("/api/data/status?season=2026")

    assert response.status_code == 200
    payload = response.json()
    assert "playerboard_build_health" in payload
    health = payload["playerboard_build_health"]
    context = health["contextConsumption"]
    assert set(context) >= {"player_recent_form", "game_markets", "statcast", "weather", "umpire"}
    for entry in context.values():
        assert REQUIRED_CONTEXT_FIELDS.issubset(entry)

    assert context["player_recent_form"]["status"] == "used"
    assert context["player_recent_form"]["usedByCurrentModel"] is True
    assert context["game_markets"]["status"] == "artifact_only"
    assert context["game_markets"]["artifactExists"] is True
    assert context["game_markets"]["usedByCurrentModel"] is False
    assert context["statcast"]["status"] == "no_safe_rows"
    assert context["statcast"]["usedByCurrentModel"] is False
    assert context["umpire"]["status"] == "unavailable"
    assert context["umpire"]["usedByCurrentModel"] is False


def test_context_group_rollups_match_consumption_semantics(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_prediction_summary(settings)
    client = TestClient(create_app(container=AppContainer(settings=settings)), client=("127.0.0.1", 50000))
    health = client.get("/api/data/status?season=2026").json()["playerboard_build_health"]
    context = health["contextConsumption"]

    used_groups = sorted(group for group, entry in context.items() if entry["usedByCurrentModel"])
    assert sorted(health["featureGroupsReady"]) == used_groups
    assert "game_markets" in health["featureGroupsMissing"]
    assert context["game_markets"]["artifactExists"] is True
    assert "statcast" in health["featureGroupsMissing"]
    assert context["statcast"]["artifactExists"] is True

    inactive_statuses = {
        "artifact_only",
        "joined_not_populated",
        "unavailable",
        "no_safe_rows",
        "not_configured",
        "available_not_used",
    }
    assert [
        group
        for group, entry in context.items()
        if entry["status"] in inactive_statuses and entry["usedByCurrentModel"] is True
    ] == []


def test_frontend_context_health_surface_uses_datastatus_and_safe_labels() -> None:
    main = (ROOT / "frontend" / "src" / "outlier" / "main.ts").read_text(encoding="utf-8")
    data_health = (ROOT / "frontend" / "src" / "outlier" / "data-health" / "index.ts").read_text(encoding="utf-8")

    assert 'optionalJson("/api/data/status")' in main
    assert "renderContextHealth" in main
    assert "getPlayerboardContextConsumption" in data_health
    assert 'artifact_only: "Artifact only"' in data_health
    assert 'no_safe_rows: "No safe local rows"' in data_health
    assert 'used: "Used by model"' in data_health
    assert "Neutral fallback" in main

    forbidden = ["Bet now", "Recommended bet", "guaranteed", "must bet"]
    combined = f"{main}\n{data_health}"
    assert [copy for copy in forbidden if copy.lower() in combined.lower()] == []
