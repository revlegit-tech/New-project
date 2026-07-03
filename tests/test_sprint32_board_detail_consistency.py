from __future__ import annotations

from pathlib import Path

from mlb_app.services.data_status_service import _sample_trust_rows


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_board_and_detail_share_trust_surface_and_reason_labels() -> None:
    board_row = read("frontend/src/outlier/board/BoardRow.ts")
    detail = read("frontend/src/outlier/detail-rail/DetailRail.ts")
    trust = read("frontend/src/outlier/trust/rowTrust.ts")

    assert "rowBoardTrustSurface(row)" in board_row
    assert "rowBoardTrustSurface(row)" in detail
    assert "rowTrustReasonLabel(row)" in detail
    assert "const trustChip = boardTrust.chips[0]" in detail
    assert "badgeToneClass(trustChip.tone)" in detail
    assert "stat(\"Reason\", rowTrustReasonLabel(row))" in detail
    assert "stat(\"Capability\", trustStatusLabel(boardTrust.marketCapabilityStatus))" in detail
    assert "visibleUnscoredReasonDetail" in trust


def test_shared_trust_surface_defines_safe_labels_for_all_row_classes() -> None:
    trust = read("frontend/src/outlier/trust/rowTrust.ts")

    for expected in (
        'status === "standard"',
        'status === "low" || status === "limited"',
        'status === "unscored"',
        'status === "blocked"',
        'status === "unsupported"',
        'label: "Research only"',
        'label: "Model Unavailable"',
        'label: "Calibration unavailable"',
        'label: "Context limited"',
        'label: "Unsupported market"',
        'label: "Blocked"',
        'label: "Unscored"',
        'label: "Unknown"',
        'label: "Not available"',
    ):
        assert expected in trust


def test_scored_rows_suppress_stale_unscored_reason_in_ui_helpers() -> None:
    trust = read("frontend/src/outlier/trust/rowTrust.ts")

    assert 'trustTier === "standard" || trustTier === "low" || trustTier === "limited"' in trust
    assert 'return guardrailStatus === "blocked" ? raw : "none";' in trust
    assert 'if (!unscoredReason || unscoredReason === "none") return "";' in trust
    assert "missingPredictionReason" not in trust
    assert "scoringSkipReason" not in trust


def test_data_status_samples_normalize_reason_taxonomy() -> None:
    samples = _sample_trust_rows(
        [
            {
                "player": "Scored",
                "market": "batter_hits",
                "predictionMatched": True,
                "trustTier": "standard",
                "probabilityGuardrailStatus": "ok",
                "calibrationStatus": "applied",
                "contextReadinessStatus": "ready",
                "unscoredReason": "missing_prediction",
                "missingPredictionReason": "prediction_join_no_match",
                "scoringSkipReason": "stale_skip",
                "marketCapabilityStatus": "model_supported",
            },
            {
                "player": "Unscored",
                "market": "batter_hits",
                "trustTier": "unscored",
                "probabilityGuardrailStatus": "blocked",
                "calibrationStatus": "not_available",
                "contextReadinessStatus": "unknown",
                "unscoredReason": "missing_prediction",
                "unscoredReasonDetail": "No matching model prediction row was found.",
                "missingPredictionReason": "prediction_join_no_match",
            },
            {
                "player": "Blocked",
                "market": "batter_hits",
                "trustTier": "blocked",
                "probabilityGuardrailStatus": "blocked",
                "calibrationStatus": "not_available",
                "contextReadinessStatus": "blocked",
                "unscoredReason": "invalid_attribution",
                "attributionBlockReason": "invalid_player_label",
            },
            {
                "player": "Unsupported",
                "market": "batter_stolen_bases",
                "trustTier": "unsupported",
                "probabilityGuardrailStatus": "blocked",
                "calibrationStatus": "not_available",
                "contextReadinessStatus": "unknown",
                "unscoredReason": "unsupported_market",
                "unsupportedMarketReason": "unsupported_market:batter_stolen_bases",
            },
        ],
        limit=10,
    )

    scored, unscored, blocked, unsupported = samples
    assert scored["unscoredReason"] == ""
    assert scored["unscoredReasonDetail"] == ""
    assert scored["missingPredictionReason"] == ""
    assert scored["scoringSkipReason"] == ""
    assert scored["reasonDisplayLabel"] == "Not available"
    assert scored["reasonTaxonomy"] == "not_available"

    assert unscored["unscoredReason"] == "missing_prediction"
    assert unscored["unscoredReasonDetail"] == "No matching model prediction row was found."
    assert unscored["missingPredictionReason"] == "prediction_join_no_match"
    assert unscored["reasonTaxonomy"] == "unscored"
    assert unscored["reasonDisplayLabel"] == "Unscored"

    assert blocked["unscoredReason"] == "invalid_attribution"
    assert blocked["reasonTaxonomy"] == "blocked"
    assert blocked["reasonDisplayLabel"] == "Blocked"
    assert blocked["attributionBlockReason"] == "invalid_player_label"

    assert unsupported["unscoredReason"] == "unsupported_market"
    assert unsupported["reasonTaxonomy"] == "unsupported"
    assert unsupported["reasonDisplayLabel"] == "Unsupported market"
    assert unsupported["marketCapabilityStatus"] == "unsupported"


def test_legacy_fallback_rows_render_unknown_or_not_available_safely() -> None:
    trust = read("frontend/src/outlier/trust/rowTrust.ts")
    detail = read("frontend/src/outlier/detail-rail/DetailRail.ts")

    assert 'normalizedStatus(row.trustTier ?? explainability.trustTier) || "unknown"' in trust
    assert 'normalizedStatus(row.calibrationStatus ?? calibration.calibrationStatus) || "unknown"' in trust
    assert 'normalizedStatus(row.probabilityGuardrailStatus ?? guardrails.probabilityGuardrailStatus) || "unknown"' in trust
    assert 'normalizedStatus(row.contextReadinessStatus ?? context.contextReadinessStatus) || "unknown"' in trust
    assert 'const explainability = objectValue(row.explainability);' in detail
    assert 'return value && typeof value === "object" && !Array.isArray(value)' in detail


def test_detail_rail_opens_from_selected_board_row_static_contract() -> None:
    main = read("frontend/src/outlier/main.ts")
    row = read("frontend/src/outlier/board/BoardRow.ts")

    assert 'dataset: { rowIndex: String(options.index)' in row
    assert 'target.closest("[data-row-index]")' in main
    assert "selectRow(Number(row.getAttribute(\"data-row-index\")))" in main
    assert "detailRail.open(appState.filteredRows[appState.selectedIndex]" in main


def test_sprint32_touched_frontend_copy_avoids_forbidden_action_language() -> None:
    touched = "\n".join(
        read(path)
        for path in (
            "frontend/src/outlier/board/BoardRow.ts",
            "frontend/src/outlier/detail-rail/DetailRail.ts",
            "frontend/src/outlier/trust/rowTrust.ts",
        )
    )

    for forbidden in ("Bet now", "Recommended bet", "Guaranteed", "Must bet", "No staking recommendation"):
        assert forbidden.lower() not in touched.lower()
