from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_board_source_exposes_trust_chips_and_filters() -> None:
    main = read("frontend/src/outlier/main.ts")
    row_trust = read("frontend/src/outlier/trust/rowTrust.ts")
    board_row = read("frontend/src/outlier/board/BoardRow.ts")

    assert "actionLabelFilter" in main
    assert "marketCapabilityFilter" in main
    assert "productionEligibleFilter" in main
    assert "calibrationStatusFilter" in main
    assert "backtestStatusFilter" in main
    assert "freshnessStatusFilter" in main
    assert "missingDataOnlyFilter" in main
    assert "trustedMarketsOnlyFilter" in main
    assert "No rows are currently production eligible." in main
    assert "rowIsTrustedMarket" in main

    assert "actionLabelChip" in row_trust
    assert "marketCapabilityChip" in row_trust
    assert "productionEligibilityChip" in row_trust
    assert "calibrationChip" in row_trust
    assert "backtestChip" in row_trust
    assert "gameMarketChip" in row_trust
    assert "missingDataChip" in row_trust
    assert ".slice(0, 6)" in board_row


def test_detail_rail_and_report_show_sprint34_explanations() -> None:
    detail = read("frontend/src/outlier/detail-rail/DetailRail.ts")
    report = read("frontend/src/outlier/research-report/index.ts")

    assert "Why it appears" in detail
    assert "Market readiness" in detail
    assert "Missing groups" in detail
    assert "Umpire" in detail
    assert "As-of audit" in detail

    assert "Readiness summary" in report
    assert "No markets are production eligible yet." in report
    assert "Production eligible" in report
    assert "Missing data" in report
    assert "Cal " in report
    assert "BT " in report
