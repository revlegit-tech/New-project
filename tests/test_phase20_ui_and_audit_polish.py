from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_phase20_ui_contract_present_after_rail_refresh():
    source = (ROOT / "public" / "outlier-detail.js").read_text(encoding="utf-8")
    assert "function gameContextCard(row)" in source
    assert "function movement(value)" in source
    assert "function weatherSummary(row)" in source
    assert "Game Context" in source
    assert "ML Move" in source
    assert "__testHooks" in source


def test_phase20_audit_policy_marker_present_after_apply():
    source = (ROOT / "tools" / "phase16_common.py").read_text(encoding="utf-8")
    assert "PHASE20_AUDIT_POLICY_START" in source
    assert "STRING_LIVE_FEATURES" in source
    assert "ADVISORY_LIVE_FEATURES" in source


def test_phase20_qa_tool_exists():
    assert (ROOT / "tools" / "phase20_audit_cleanup_qa.py").exists()
