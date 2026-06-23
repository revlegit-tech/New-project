from __future__ import annotations

from mlb_app.ml.evaluation.metrics import binary_classification_metrics


def test_metrics_compute_expected_values_on_deterministic_fixture() -> None:
    metrics = binary_classification_metrics([1, 0, 1, 0], [0.9, 0.2, 0.7, 0.4])

    assert metrics["rows"] == 4
    assert metrics["brierScore"] == 0.075
    assert metrics["auc"] == 1.0
    assert metrics["logLoss"] > 0


def test_single_class_window_returns_clear_warning() -> None:
    metrics = binary_classification_metrics([1, 1], [0.7, 0.8])

    assert metrics["auc"] is None
    assert "single-class window; AUC is unavailable" in metrics["warnings"]
