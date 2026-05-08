from __future__ import annotations

from pathlib import Path

from tools.phase14_common import infer_binary_target, production_gate_status, stable_row_key, write_csv_rows, read_csv_rows
from tools.phase14_promote_market_models import promote


def test_infer_binary_target_from_common_result_fields():
    assert infer_binary_target({"target": "1"}) == 1
    assert infer_binary_target({"target": "0"}) == 0
    assert infer_binary_target({"result": "win"}) == 1
    assert infer_binary_target({"grade": "loss"}) == 0
    assert infer_binary_target({"status": "pending"}) is None


def test_production_gate_requires_rows_calibration_and_metrics():
    entry = {
        "artifact": "data/models/prop_model_batter_hits.joblib",
        "features": "data/models/prop_model_batter_hits_features.json",
        "calibrated": True,
        "backtest": {"graded": 100, "brierScore": 0.1, "logLoss": 0.2},
    }
    gate = production_gate_status(entry)
    assert gate["ok"] is True
    weak = {**entry, "backtest": {"graded": 38, "brierScore": 0.1, "logLoss": 0.2}}
    gate = production_gate_status(weak)
    assert gate["ok"] is False
    assert "minimumBacktestRows" in gate["missing"]


def test_csv_round_trip_atomic_helper(tmp_path: Path):
    path = tmp_path / "rows.csv"
    rows = [{"market": "batter_hits", "target": 1}, {"market": "batter_hits", "target": 0}]
    write_csv_rows(path, rows)
    loaded = read_csv_rows(path)
    assert len(loaded) == 2
    assert loaded[0]["market"] == "batter_hits"
