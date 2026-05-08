from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_phase20_ui_marker_present_after_apply():
    source = (ROOT / "public" / "outlier-detail.js").read_text(encoding="utf-8")
    assert "PHASE20_GAME_CONTEXT_POLISH_START" in source
    assert "phase20Probability" in source
    assert "movement pending" in source


def test_phase20_audit_policy_marker_present_after_apply():
    source = (ROOT / "tools" / "phase16_common.py").read_text(encoding="utf-8")
    assert "PHASE20_AUDIT_POLICY_START" in source
    assert "STRING_LIVE_FEATURES" in source
    assert "ADVISORY_LIVE_FEATURES" in source


def test_phase20_qa_tool_exists():
    assert (ROOT / "tools" / "phase20_audit_cleanup_qa.py").exists()
