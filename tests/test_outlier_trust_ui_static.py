from __future__ import annotations

from pathlib import Path


def test_outlier_ui_loads_runtime_model_and_actionnetwork_trust() -> None:
    source = Path("frontend/src/outlier/main.ts").read_text(encoding="utf-8")

    assert "/api/actionnetwork/trust" in source
    assert "/api/runtime/status" in source
    assert "/api/workflow/status" in source
    assert "/api/ml-models/status" in source
    assert "Runtime Healthy" in source
    assert "Workflow Degraded" in source
    assert "modeledMarketCount" in source
    assert "Experimental / Research Mode" in source
    assert "MLB markets" in source


def test_outlier_ui_uses_dynamic_market_registry() -> None:
    source = Path("frontend/src/outlier/main.ts").read_text(encoding="utf-8")
    markets = Path("frontend/src/shared/markets/markets.ts").read_text(encoding="utf-8")

    assert "/api/mlb/market-registry" in source
    assert "renderMarketOptions" in source
    assert "Market Coverage" in source
    assert "marketCoveragePanel" in source
    assert "RegistryMarketGroup" in markets
    assert "fallbackMarketGroups" in markets


def test_outlier_rows_and_detail_rail_render_trust_chips() -> None:
    row = Path("frontend/src/outlier/board/BoardRow.ts").read_text(encoding="utf-8")
    rail = Path("frontend/src/outlier/detail-rail/DetailRail.ts").read_text(encoding="utf-8")
    trust = Path("frontend/src/outlier/trust/rowTrust.ts").read_text(encoding="utf-8")

    assert "rowTrustChips" in row
    assert "rowTrustChips" in rail
    assert "Model Shadow" in trust
    assert "Model Production" in trust
    assert "Snapshot Fresh" in trust
    assert "Not Trainable" in trust
    assert "Production gates closed" in trust
    assert "Research only. Production betting gates are closed." in trust
    assert "Gates pass, disabled" in trust
    assert "Experimental model output. Research only. No action recommendation." in row
    assert "Identity is inferred from board context. Research only." in trust
    assert "Identity inferred" in trust
    assert "Corrected" in trust
    assert "Ambiguous player" in trust
    assert "Source mismatch corrected by roster evidence." in trust
    assert "Identity\", trustStatusLabel(identity.identityConfidence)" in rail
    assert "Identity is inferred from board context. Bet" not in trust
    assert "label: \"Bet\"" not in trust


def test_outlier_board_controls_are_visibly_labeled() -> None:
    source = Path("frontend/src/outlier/main.ts").read_text(encoding="utf-8")
    styles = Path("frontend/src/shared/styles/layout.css").read_text(encoding="utf-8")

    assert "Board controls" in source
    assert "Filter by sportsbook, market, quote coverage, model status, and attribution trust." in source
    assert "filterField(\"Sportsbook\"" in source
    assert "filterField(\"Market\"" in source
    assert "filterField(\"Market group\"" in source
    assert "filterField(\"Book coverage\"" in source
    assert "filterField(\"Search\"" in source
    assert "filterField(\"Side\"" in source
    assert "filterField(\"Min quote count\"" in source
    assert "filterField(\"Date\"" in source
    assert "filterField(\"Action\"" in source
    assert "filterField(\"Capability\"" in source
    assert "filterField(\"Model state\"" in source
    assert "filterField(\"Calibration\"" in source
    assert "filterField(\"Backtest\"" in source
    assert "filterField(\"Freshness\"" in source
    assert "Best Available" in source
    assert "No quote" in source
    assert "UI bundle loaded" in source
    assert ".ob-filter-label" in styles


def test_outlier_attribution_chips_are_prioritized_and_safe() -> None:
    row = Path("frontend/src/outlier/board/BoardRow.ts").read_text(encoding="utf-8")
    trust = Path("frontend/src/outlier/trust/rowTrust.ts").read_text(encoding="utf-8")
    frontend_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("frontend/src/outlier").rglob("*.ts")
    )

    assert "rowAttributionChip" in row
    assert "rowAttributionChip" in trust
    assert "Corrected" in trust
    assert "Ambiguous player" in trust
    assert "Identity inferred" in trust
    assert "Possible team mismatch" in trust
    assert "Invalid player label" in trust
    assert "Context limited" in trust
    assert "Bet now" not in frontend_sources
