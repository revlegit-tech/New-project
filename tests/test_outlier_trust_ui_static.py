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
    assert "Experimental model output. Research only. No staking recommendation." in row
    assert "Identity is inferred from board context. Research only." in trust
    assert "Identity inferred" in trust
    assert "Identity\", trustStatusLabel(identity.identityConfidence)" in rail
    assert "Identity is inferred from board context. Bet" not in trust
    assert "label: \"Bet\"" not in trust
