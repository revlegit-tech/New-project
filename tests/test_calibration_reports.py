from __future__ import annotations

from mlb_app.ml.evaluation.calibration import calibration_report


def test_calibration_buckets_are_generated() -> None:
    report = calibration_report([0, 1, 1, 0], [0.1, 0.55, 0.85, 0.35], bucket_count=4)

    assert report["bucketCount"] == 4
    assert len(report["buckets"]) == 4
    assert report["expectedCalibrationError"] is not None
