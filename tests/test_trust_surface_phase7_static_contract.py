from __future__ import annotations
from pathlib import Path
SOURCE = Path("public/trust-surface.js").read_text(encoding="utf-8")
def test_trust_surface_declares_and_validates_app_status_schema() -> None:
    assert 'APP_STATUS_SCHEMA = "app-status-v1"' in SOURCE
    assert "meta.schema must be" in SOURCE
    assert "Trust surface contract violation" in SOURCE
    assert "renderSafeFailure" in SOURCE
def test_trust_surface_keeps_research_only_safe_failure_copy() -> None:
    assert 'label: "Research Only"' in SOURCE
    assert "Treat this slate as research-only" in SOURCE
    assert "Malformed status payload" in SOURCE
def test_trust_surface_exports_test_hooks_without_unsafe_html() -> None:
    assert "window.__MLBTrustSurfaceTestHooks" in SOURCE
    assert ".textContent" in SOURCE
    assert ".innerHTML" not in SOURCE
    assert "insertAdjacentHTML" not in SOURCE
