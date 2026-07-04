from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path

from mlb_app.config import Settings
from mlb_app.ml.evaluation.reports import evaluate_csv
from mlb_app.ml.evaluation.walk_forward import date_ordered_splits
from mlb_app.services.model_backtest_service import ModelBacktestService
from mlb_app.services.model_calibration_service import ModelCalibrationService


def make_settings(tmp_path: Path) -> Settings:
    return replace(Settings.from_env(tmp_path), data_dir=tmp_path / "data", current_season=2026)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def training_rows(markets: tuple[str, ...] = ("batter_hits", "batter_home_runs")) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for market_index, market in enumerate(markets):
        for day in range(1, 81):
            for player_index in range(4):
                signal = (day + player_index + market_index) % 5
                target = 1 if signal in {0, 1} else 0
                rows.append(
                    {
                        "meta_game_date": f"2026-05-{day:02d}",
                        "meta_market": market,
                        "meta_player_id": f"player-{player_index}",
                        "feature_recent_form": float(signal),
                        "feature_line": 0.5 + player_index,
                        "target_hit": target,
                    }
                )
    return rows


def test_normalized_training_rows_fit_walk_forward_predictions_and_write_shadow_artifacts(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    training_path = tmp_path / "training.csv"
    write_csv(training_path, training_rows(("batter_hits",)))

    report = evaluate_csv(
        training_path,
        markets=["batter_hits"],
        min_train_rows=40,
        validation_window=5,
        artifact_root=settings.data_dir / "models" / "artifacts" / "sprint19_shadow" / "calibrated_logistic",
        write_artifacts=True,
    )

    metrics = report["markets"]["batter_hits"]["metrics"]
    assert report["status"] == "ok"
    assert metrics["evaluatedRows"] > 0
    assert metrics["brierScore"] is not None
    assert metrics["logLoss"] is not None
    assert "no valid predictions" not in metrics["warnings"]
    artifact_dir = settings.data_dir / "models" / "artifacts" / "sprint19_shadow" / "calibrated_logistic" / "batter_hits"
    assert (artifact_dir / "backtest_metrics.json").is_file()
    assert (artifact_dir / "calibration.json").is_file()


def test_walk_forward_splits_never_mix_same_game_date_between_train_and_validation() -> None:
    rows = training_rows(("batter_hits",))

    splits = date_ordered_splits(rows, min_train_rows=40, validation_window=3)

    assert splits
    for split in splits:
        train_dates = {row["meta_game_date"] for row in split.train_rows}
        validation_dates = {row["meta_game_date"] for row in split.validation_rows}
        assert train_dates.isdisjoint(validation_dates)
        assert max(train_dates) < min(validation_dates)


def test_shadow_artifact_status_services_return_ready_without_production_promotion(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    training_path = tmp_path / "training.csv"
    write_csv(training_path, training_rows(("batter_hits",)))
    evaluate_csv(
        training_path,
        markets=["batter_hits"],
        min_train_rows=40,
        validation_window=5,
        artifact_root=settings.data_dir / "models" / "artifacts" / "sprint19_shadow" / "calibrated_logistic",
        write_artifacts=True,
    )

    backtest = ModelBacktestService(settings).status(date_label="2026-06-24", season=2026, market="batter_hits")
    calibration = ModelCalibrationService(settings).status(date_label="2026-06-24", season=2026, market="batter_hits")

    assert backtest["backtestStatus"] == "ready"
    assert calibration["calibrationStatus"] == "ready"
    assert backtest["metrics"]["modelStage"] == "shadow"
    assert calibration["metrics"]["modelKey"] == "calibrated_logistic"
    assert backtest["metrics"]["betActionAllowed"] is False
    assert calibration["metrics"]["readinessLabel"] == "Experimental"
