from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_playerboard_contract_declares_board_trust_fields() -> None:
    models = read("mlb_app/api/models.py")
    for field in (
        "trustTier",
        "trustScore",
        "calibrationStatus",
        "probabilityGuardrailStatus",
        "contextReadinessStatus",
        "unscoredReason",
        "marketCapabilityStatus",
    ):
        assert field in models


def test_board_renders_explicit_trust_scan_columns_and_filters() -> None:
    main = read("frontend/src/outlier/main.ts")
    board_row = read("frontend/src/outlier/board/BoardRow.ts")
    row_trust = read("frontend/src/outlier/trust/rowTrust.ts")

    for column in (
        '{ key: "trustTier", label: "Trust" }',
        '{ key: "calibrationStatus", label: "Cal" }',
        '{ key: "probabilityGuardrailStatus", label: "Guard" }',
        '{ key: "contextReadinessStatus", label: "Context" }',
        '{ key: "unscoredReason", label: "Reason" }',
        '{ key: "marketCapabilityStatus", label: "Capability" }',
    ):
        assert column in board_row

    for filter_id in (
        "trustTierFilter",
        "calibrationStatusFilter",
        "probabilityGuardrailStatusFilter",
        "contextReadinessStatusFilter",
        "unscoredReasonFilter",
        "marketCapabilityFilter",
    ):
        assert filter_id in main

    assert "rowBoardTrustSurface(row)" in board_row
    assert "uniqueBoardTrustValues" in main
    assert '|| "unknown"' in row_trust


def test_board_trust_surface_suppresses_unscored_reasons_for_scored_rows() -> None:
    row_trust = read("frontend/src/outlier/trust/rowTrust.ts")

    assert 'trustTier === "standard" || trustTier === "low" || trustTier === "limited"' in row_trust
    assert 'return guardrailStatus === "blocked" ? raw : "none";' in row_trust
    assert 'label: "Scored"' in row_trust
    assert "missingPredictionReason" not in row_trust
    assert "scoringSkipReason" not in row_trust
