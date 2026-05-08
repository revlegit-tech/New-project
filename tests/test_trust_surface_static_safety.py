from __future__ import annotations

from pathlib import Path


def test_trust_surface_does_not_use_inner_html_for_api_payloads() -> None:
    source = Path("public/trust-surface.js").read_text(encoding="utf-8")
    assert ".innerHTML" not in source
    assert "insertAdjacentHTML" not in source
    assert "textContent" in source
    assert "document.createElement" in source


def test_trust_surface_contract_validation_is_present() -> None:
    source = Path("public/trust-surface.js").read_text(encoding="utf-8")
    required_checks = (
        "productState must be a string",
        "grading.state must be a string",
        "dataConfidence must be a string",
        "productionEligibleMarkets must be an array",
        "latestBoardDate or playerboard date must be present",
        "Research Only",
    )
    for check in required_checks:
        assert check in source
