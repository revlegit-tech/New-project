from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DETAIL_RAIL = ROOT / "frontend" / "src" / "outlier" / "detail-rail" / "DetailRail.ts"
CLIENT = ROOT / "frontend" / "src" / "outlier" / "api" / "client.ts"
TYPES = ROOT / "frontend" / "src" / "outlier" / "types" / "modelAudit.ts"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shadow_audit_api_client_exposes_read_only_endpoints() -> None:
    source = read(CLIENT)

    assert "getMlModelsStatus" in source
    assert '"/api/ml-models/status"' in source
    assert "getShadowSummary" in source
    assert "/api/ml-models/shadow-summary" in source
    assert "getShadowReadiness" in source
    assert "/api/ml-models/shadow-readiness" in source
    assert "getProductionGates" in source
    assert "/api/ml-models/production-gates" in source
    assert "/api/admin/ml-models/promote" not in source


def test_shadow_audit_types_preserve_gate_and_research_lock_fields() -> None:
    source = read(TYPES)

    for field in [
        "ShadowSummaryResponse",
        "ShadowReadinessResponse",
        "ProductionGatesResponse",
        "GateCheck",
        "GateSummary",
        "ShadowMarketSummary",
        "ShadowReadinessMarket",
        "productionEligible",
        "manualGovernanceRequired",
        "promotionCommandPreview",
        "betActionAllowed",
        "stakeUnits",
    ]:
        assert field in source


def test_shadow_audit_panel_renders_research_only_safety_labels() -> None:
    source = read(DETAIL_RAIL)

    for label in [
        "Experimental Shadow Model",
        "Experimental",
        "Shadow",
        "Research only",
        "Not actionable",
        "Not production eligible",
        "Manual governance required",
        "Production eligible",
        "No",
        "manual_governance_review_required",
    ]:
        assert label in source


def test_shadow_audit_panel_has_safe_empty_error_and_no_promotion_button() -> None:
    source = read(DETAIL_RAIL)

    assert "No Sprint 19 shadow model for this market yet." in source
    assert "Shadow audit unavailable" in source
    assert "Loading shadow model audit" in source
    assert "promotionCommandPreview" not in source
    assert "promote" not in source.lower()
    assert "data-action: \"promote" not in source


def test_shadow_audit_ui_does_not_mutate_board_actionability_fields() -> None:
    source = read(DETAIL_RAIL)

    assert "row.modelProbability" not in source
    assert "row.edge" not in source
    assert "row.trustTier =" not in source
    assert "row.readinessLabel =" not in source
    assert "row.betActionAllowed =" not in source
    assert "row.stakeUnits =" not in source
