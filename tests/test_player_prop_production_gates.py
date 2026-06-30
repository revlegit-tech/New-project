from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.services.player_prop_production_gate_service import PlayerPropProductionGateService


def make_settings(tmp_path: Path, *, enable_bet_actions: bool = False) -> Settings:
    return Settings(
        root_dir=tmp_path,
        public_dir=tmp_path / "public",
        data_dir=tmp_path / "data",
        model_dir=tmp_path / "data" / "models",
        model_registry_path=tmp_path / "data" / "models" / "model_registry.json",
        current_season=2026,
        enable_bet_actions=enable_bet_actions,
        db_enabled=False,
    )


def write_backtest(settings: Settings, *, market: str = "batter_hits", sample_size: int = 250) -> None:
    path = settings.data_dir / "backtests" / "player_prop_model_backtest_summary_2026.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "markets": {
                    market: {
                        "sampleSize": sample_size,
                        "brierScore": 0.18,
                        "calibrationError": 0.03,
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def strong_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "date": "2026-06-29",
        "market": "batter_hits",
        "side": "Over",
        "americanOdds": "-110",
        "rawModelProbability": "0.60",
        "calibratedProbability": "0.61",
        "calibrationStatus": "applied",
        "edgePercent": "8.62",
        "identityConfidence": "strong",
        "predictionMatched": True,
    }
    row.update(overrides)
    return row


def test_default_config_blocks_bet_even_when_production_eligible(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_backtest(settings)

    gate = PlayerPropProductionGateService(settings=settings).evaluate(strong_row(), season=2026, date_label="2026-06-29")

    assert gate.productionEligible is True
    assert gate.productionGateStatus == "eligible_not_enabled"
    assert gate.betActionAllowed is False
    assert gate.productionGateReasons == []


def test_missing_calibration_blocks_production_eligibility(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_backtest(settings)

    gate = PlayerPropProductionGateService(settings=settings).evaluate(
        strong_row(calibrationStatus="not_available", calibratedProbability=""),
        season=2026,
        date_label="2026-06-29",
    )

    assert gate.productionEligible is False
    assert gate.productionGateStatus == "blocked"
    assert "calibration_not_available" in gate.productionGateReasons


def test_weak_identity_blocks_production_eligibility(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_backtest(settings)

    gate = PlayerPropProductionGateService(settings=settings).evaluate(
        strong_row(identityConfidence="weak"),
        season=2026,
        date_label="2026-06-29",
    )

    assert gate.productionEligible is False
    assert "identity_confidence_weak" in gate.productionGateReasons


def test_stale_prediction_blocks_production_eligibility(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_backtest(settings)

    gate = PlayerPropProductionGateService(settings=settings).evaluate(
        strong_row(date="2026-06-28"),
        season=2026,
        date_label="2026-06-29",
    )

    assert gate.productionEligible is False
    assert "prediction_stale" in gate.productionGateReasons


def test_missing_side_blocks_production_eligibility(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_backtest(settings)

    gate = PlayerPropProductionGateService(settings=settings).evaluate(
        strong_row(side="", rawLabel="Aaron Judge 0.5 Hits"),
        season=2026,
        date_label="2026-06-29",
    )

    assert gate.productionEligible is False
    assert "missing_side" in gate.productionGateReasons


def test_backtest_sample_size_below_threshold_blocks_production_eligibility(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_backtest(settings, sample_size=25)

    gate = PlayerPropProductionGateService(settings=settings).evaluate(strong_row(), season=2026, date_label="2026-06-29")

    assert gate.productionEligible is False
    assert "backtest_sample_size_below_threshold" in gate.productionGateReasons


def test_enabled_config_allows_bet_action_only_after_gates_pass(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, enable_bet_actions=True)
    write_backtest(settings)

    gate = PlayerPropProductionGateService(settings=settings).evaluate(strong_row(), season=2026, date_label="2026-06-29")

    assert gate.productionEligible is True
    assert gate.productionGateStatus == "closed"
    assert gate.betActionAllowed is True
