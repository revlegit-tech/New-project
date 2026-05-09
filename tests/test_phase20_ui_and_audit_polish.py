from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_phase20_ui_contract_present_after_rail_refresh():
    source = (ROOT / "frontend" / "src" / "outlier" / "detail-rail" / "DetailRail.ts").read_text(encoding="utf-8")
    assert "DetailRailController" in source
    assert "detailQuery" in source
    assert "/api/prop-detail" in source
    assert "Server drilldown" in source


def test_phase20_audit_policy_marker_present_after_apply():
    source = (ROOT / "tools" / "phase16_common.py").read_text(encoding="utf-8")
    assert "PHASE20_AUDIT_POLICY_START" in source
    assert "STRING_LIVE_FEATURES" in source
    assert "ADVISORY_LIVE_FEATURES" in source


def test_phase20_qa_tool_exists():
    assert (ROOT / "tools" / "phase20_audit_cleanup_qa.py").exists()
