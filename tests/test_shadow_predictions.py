from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.repositories.shadow_prediction_repository import ShadowPredictionRepository
from mlb_app.services.shadow_prediction_service import ShadowPredictionService


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


class FakePrediction:
    def __init__(self, final_probability: float | None = 57.5) -> None:
        self.final_probability = final_probability

    def as_dict(self) -> dict[str, Any]:
        return {
            "market": "batter_hits",
            "player": "Aaron Judge",
            "line": 0.5,
            "side": "over",
            "modelProbability": 0.62,
            "marketProbability": 0.51,
            "contextProbability": 0.55,
            "blendedProbability": 0.58,
            "edge": 0.07,
            "modelName": "fake-shadow",
            "modelVersion": "v1",
            "modelStatus": "shadow",
            "featureCoverage": 1.0,
            "modelContributed": False,
            "finalProbabilityPercent": self.final_probability,
            "warnings": ["model probability is preview-only until production gates pass"],
        }


class FakePredictionService:
    def predict(self, request: dict[str, Any]) -> FakePrediction:
        return FakePrediction()


def test_shadow_model_scores_fixture_rows_and_persists_csv(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    csv_path = tmp_path / "data" / "predictions" / "shadow_predictions.csv"
    repository = ShadowPredictionRepository(settings, csv_path=csv_path)
    service = ShadowPredictionService(
        settings=settings,
        prediction_service=FakePredictionService(),  # type: ignore[arg-type]
        repository=repository,
    )

    result = service.score_rows(
        [
            {
                "date": "2026-05-01",
                "player": "Aaron Judge",
                "team": "NYY",
                "opponent": "BOS",
                "market": "batter_hits",
                "line": 0.5,
                "side": "over",
                "book": "FanDuel",
                "feature_line": 0.5,
                "feature_recent_rate": 0.61,
                "finalProbabilityPercent": 51.0,
                "finalEdgePercent": 2.0,
                "rank": 3,
            }
        ]
    )

    assert result["rowCount"] == 1
    assert csv_path.exists()
    stored = csv_path.read_text(encoding="utf-8")
    assert "fake-shadow" in stored
    assert result["rows"][0]["shadowPrediction"]["modelProbability"] == 0.62


def test_shadow_predictions_do_not_alter_final_board_probability(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = ShadowPredictionService(
        settings=settings,
        prediction_service=FakePredictionService(),  # type: ignore[arg-type]
        repository=ShadowPredictionRepository(settings, csv_path=tmp_path / "shadow.csv"),
    )
    row = {"market": "batter_hits", "feature_line": 0.5, "finalProbabilityPercent": 51.0, "finalEdgePercent": 2.0, "rank": 7}

    output = service.score_rows([row], persist=False)["rows"][0]

    assert output["finalProbabilityPercent"] == 51.0
    assert output["finalEdgePercent"] == 2.0
    assert output["rank"] == 7


def test_no_leakage_fields_enter_features_during_shadow_scoring(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = ShadowPredictionService(
        settings=settings,
        prediction_service=FakePredictionService(),  # type: ignore[arg-type]
        repository=ShadowPredictionRepository(settings, csv_path=tmp_path / "shadow.csv"),
    )

    try:
        service.score_rows([{"market": "batter_hits", "feature_actual_value": 1}], persist=False)
    except ValueError as error:
        assert "Blocked leakage fields" in str(error)
    else:  # pragma: no cover
        raise AssertionError("leakage field should be rejected")


def test_shadow_prediction_post_grading_evaluation(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    repository = ShadowPredictionRepository(settings, csv_path=tmp_path / "shadow.csv")
    repository.append_many([{"prediction_id": "p1", "market": "batter_hits", "model_name": "fake"}])
    service = ShadowPredictionService(
        settings=settings,
        prediction_service=FakePredictionService(),  # type: ignore[arg-type]
        repository=repository,
    )

    result = service.evaluate_after_grading([{"prediction_id": "p1", "target_hit": 1, "target_profit_1u": 0.91}])
    rows = repository.list_predictions()

    assert result["updated"] == 1
    assert rows[0]["target_hit"] == "1"
    assert rows[0]["target_profit_1u"] == "0.91"
    assert json.loads(rows[0]["warnings"] or "[]") == []
