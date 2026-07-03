from __future__ import annotations

from collections import Counter
from typing import Any


UNSCORED_REASON_TRUST_TIERS = {"unscored", "blocked", "unsupported"}


def compose_player_prop_explainability(row: dict[str, Any]) -> dict[str, Any]:
    """Build a compact, read-only explanation envelope for a playerboard row."""
    trust_tier = _clean(row.get("trustTier")) or "unscored"
    include_unscored_reasons = trust_tier.lower() in UNSCORED_REASON_TRUST_TIERS
    trust_score = _coerce_int(row.get("trustScore"))
    reasons = _list_value(row.get("trustReasons"))
    warnings = _dedupe([*_list_value(row.get("trustWarnings")), *_list_value(row.get("predictionWarnings"))])
    if not include_unscored_reasons:
        reasons = [reason for reason in reasons if reason not in {"missing_prediction", "prediction_join_no_match"}]
        warnings = [warning for warning in warnings if warning not in {"missing_prediction", "prediction_join_no_match", "skipped_by_model_scoring"}]
    blocks = _blocks(row, include_unscored_reasons=include_unscored_reasons)
    has_probability = _has_value(row.get("modelProbabilityPercent"))
    has_edge = _has_value(row.get("edgePercent"))
    has_implied = _has_value(row.get("impliedProbabilityPercent")) or _has_value(row.get("selectedBookImpliedProbability")) or _has_value(row.get("bestImpliedProbability"))
    unscored_reason = _clean(row.get("unscoredReason")) if include_unscored_reasons else ""
    unscored_reason_detail = _clean(row.get("unscoredReasonDetail")) if include_unscored_reasons else ""
    scoring_skip_reason = _clean(row.get("scoringSkipReason")) if include_unscored_reasons else ""
    missing_prediction_reason = _clean(row.get("missingPredictionReason")) if include_unscored_reasons else ""
    unsupported_market_reason = _clean(row.get("unsupportedMarketReason")) if include_unscored_reasons else ""
    guardrail_reasons = _list_value(row.get("probabilityGuardrailReasons"))
    if not include_unscored_reasons:
        guardrail_reasons = [
            reason
            for reason in guardrail_reasons
            if reason not in {"missing_prediction", "prediction_join_no_match", "unsupported_or_unscored_row"}
        ]

    model = {
        "modelFamily": _clean(row.get("modelFamily")),
        "modelVersion": _clean(row.get("modelVersion")),
        "modelProbabilitySource": _clean(row.get("modelProbabilitySource")) or "none",
        "hasModelProbability": has_probability,
        "explanation": _model_explanation(
            row,
            has_probability=has_probability,
            has_edge=has_edge,
            include_unscored_reasons=include_unscored_reasons,
        ),
    }
    if has_probability:
        model["modelProbabilityPercent"] = row.get("modelProbabilityPercent")
    if has_edge:
        model["edgePercent"] = row.get("edgePercent")
    if has_implied:
        model["hasImpliedProbability"] = True
        implied = _first(row, "impliedProbabilityPercent", "selectedBookImpliedProbability", "bestImpliedProbability")
        if _has_value(implied):
            model["impliedProbability"] = implied
    else:
        model["hasImpliedProbability"] = False

    calibration_status = _clean(row.get("calibrationStatus")) or "not_applicable"
    context_status = _clean(row.get("contextReadinessStatus")) or "unknown"
    guardrail_status = _clean(row.get("probabilityGuardrailStatus")) or "not_applicable"

    return {
        "summary": _summary(
            trust_tier=trust_tier,
            calibration_status=calibration_status,
            context_status=context_status,
            guardrail_status=guardrail_status,
            unscored_reason=unscored_reason,
        ),
        "trustTier": trust_tier,
        "trustScore": trust_score,
        "primaryReasons": reasons[:6],
        "warnings": warnings[:6],
        "blocks": blocks,
        "propIdentity": _prop_identity(row),
        "attribution": _attribution(row),
        "model": model,
        "calibration": {
            "calibrationStatus": calibration_status,
            "calibrationBucket": _clean(row.get("calibrationBucket")),
            "calibrationSampleSize": row.get("calibrationSampleSize"),
            "calibrationWarning": _clean(row.get("calibrationWarning")),
            "explanation": _calibration_explanation(calibration_status),
        },
        "guardrails": {
            "probabilityGuardrailStatus": guardrail_status,
            "probabilityGuardrailReasons": guardrail_reasons,
            "unsupportedMarketReason": unsupported_market_reason,
            "unscoredReason": unscored_reason,
            "unscoredReasonDetail": unscored_reason_detail,
            "scoringSkipReason": scoring_skip_reason,
            "missingPredictionReason": missing_prediction_reason,
            "explanation": _guardrail_explanation(row, guardrail_status, include_unscored_reasons=include_unscored_reasons),
        },
        "context": {
            "contextReadinessStatus": context_status,
            "readyFeatureGroups": _list_value(row.get("readyFeatureGroups")),
            "partialFeatureGroups": _list_value(row.get("partialFeatureGroups")),
            "fallbackFeatureGroups": _list_value(row.get("fallbackFeatureGroups")),
            "missingFeatureGroups": _list_value(row.get("missingFeatureGroups")),
            "staleFeatureGroups": _list_value(row.get("staleFeatureGroups")),
            "explanation": _context_explanation(context_status),
        },
        "dataFreshness": _data_freshness(row),
        "researchOnly": {
            "action": _clean(row.get("action")) or "Research",
            "readinessLabel": _clean(row.get("readinessLabel")) or "Experimental",
            "stakeUnits": _stake_units(row.get("stakeUnits")),
            "betActionAllowed": bool(row.get("betActionAllowed")) if row.get("betActionAllowed") is not None else False,
            "researchOnlyReason": _clean(row.get("researchOnlyReason")) or "research_only_lock",
            "explanation": "This row is research-only; bet actions and staking remain disabled.",
        },
        "nextChecks": _next_checks(row),
    }


def attach_player_prop_explainability(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) | {"explainability": compose_player_prop_explainability(row)} for row in rows]


def explainability_coverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    prepared = [dict(row) if isinstance(row.get("explainability"), dict) else dict(row) | {"explainability": compose_player_prop_explainability(row)} for row in rows]
    missing = [row for row in prepared if not isinstance(row.get("explainability"), dict) or not row.get("explainability")]
    tier_counts = dict(sorted(Counter(_clean((row.get("explainability") or {}).get("trustTier")) or _clean(row.get("trustTier")) or "unknown" for row in prepared).items()))
    return {
        "explainabilityCoverage": {
            "totalBoardRows": len(prepared),
            "rowsWithExplainability": len(prepared) - len(missing),
            "rowsMissingExplainability": len(missing),
            "explainabilityTierCounts": tier_counts,
        },
        "rowsWithExplainability": len(prepared) - len(missing),
        "rowsMissingExplainability": len(missing),
        "explainabilityTierCounts": tier_counts,
        "sampleMissingExplainabilityRows": _sample_rows(missing),
        "sampleExplainabilityRowsByTier": _sample_by_tier(prepared),
    }


def _prop_identity(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "player": _clean(_first(row, "player", "playerName", "name")),
        "team": _clean(row.get("team")),
        "opponent": _clean(row.get("opponent")),
        "market": _clean(row.get("market")),
        "side": _clean(row.get("side")),
        "line": row.get("line"),
        "book": _clean(_first(row, "selectedBook", "book", "bestBook", "bookKey")),
        "subjectRole": _subject_role(row.get("market")),
        "eventDate": _clean(row.get("date")),
    }


def _attribution(row: dict[str, Any]) -> dict[str, Any]:
    status = _clean(row.get("attributionStatus")) or "unknown"
    block_reason = _clean(row.get("attributionBlockReason"))
    invalid = status == "invalid_player_label" or block_reason == "invalid_player_label" or bool(row.get("invalidPlayerLabel"))
    return {
        "attributionStatus": status,
        "attributionConfidence": _clean(row.get("attributionConfidence") or row.get("identityConfidence")),
        "attributionBlockReason": block_reason,
        "invalidPlayerLabel": invalid,
        "explanation": _attribution_explanation(status, block_reason, invalid),
    }


def _data_freshness(row: dict[str, Any]) -> dict[str, Any]:
    freshness = row.get("freshness") if isinstance(row.get("freshness"), dict) else {}
    result = {
        "dataFreshnessStatus": _clean(row.get("dataFreshnessStatus") or freshness.get("status")) or "unknown",
        "explanation": "Freshness is reported only from existing row/source timestamps.",
    }
    for key in ("lastUpdate", "bestBookLastUpdate", "selectedBookLastUpdate", "snapshotAt", "predictionSource", "predictionGeneratedAt"):
        value = row.get(key)
        if _has_value(value):
            result[key] = value
    return result


def _blocks(row: dict[str, Any], *, include_unscored_reasons: bool) -> list[str]:
    values = [
        _clean(row.get("attributionBlockReason")),
    ]
    if include_unscored_reasons:
        values.extend(
            [
                _clean(row.get("unsupportedMarketReason")),
                _clean(row.get("scoringSkipReason")),
                _clean(row.get("missingPredictionReason")),
            ]
        )
    if _clean(row.get("probabilityGuardrailStatus")) == "blocked":
        values.extend(_list_value(row.get("probabilityGuardrailReasons")))
    if not include_unscored_reasons:
        values = [value for value in values if _clean(value) not in {"missing_prediction", "prediction_join_no_match", "unsupported_or_unscored_row"}]
    return _dedupe(values)[:8]


def _summary(*, trust_tier: str, calibration_status: str, context_status: str, guardrail_status: str, unscored_reason: str) -> str:
    parts = [f"{trust_tier.title()} trust"]
    if unscored_reason:
        parts.append(f"unscored reason is {unscored_reason}")
    if calibration_status not in {"", "applied", "ready"}:
        parts.append(f"calibration is {calibration_status}")
    if context_status not in {"", "ready"}:
        parts.append(f"context is {context_status}")
    if guardrail_status == "blocked":
        parts.append("guardrails blocked model output")
    return f"{parts[0]}: {', '.join(parts[1:])}." if len(parts) > 1 else parts[0] + "."


def _model_explanation(row: dict[str, Any], *, has_probability: bool, has_edge: bool, include_unscored_reasons: bool) -> str:
    if has_probability:
        if has_edge:
            return "Model probability and edge are existing scored outputs for this row."
        return "Model probability exists; edge was not emitted on this row."
    if not include_unscored_reasons:
        return "Model probability was not emitted on this scored research row."
    reason = _clean(row.get("unscoredReason") or row.get("missingPredictionReason") or row.get("unsupportedMarketReason")) or "no_model_prediction_available"
    return f"Model probability was withheld because {reason}."


def _calibration_explanation(status: str) -> str:
    if status == "applied":
        return "Calibration metadata was applied by the scoring output."
    if status in {"not_available", "missing"}:
        return "Calibration is not available for this row."
    if status == "not_applicable":
        return "Calibration is not applicable because no model probability was emitted."
    return f"Calibration status is {status or 'unknown'}."


def _guardrail_explanation(row: dict[str, Any], status: str, *, include_unscored_reasons: bool) -> str:
    if status == "ok":
        return "Probability guardrails passed for the emitted model output."
    reason = _clean(row.get("unscoredReason") or row.get("unsupportedMarketReason") or row.get("missingPredictionReason")) if include_unscored_reasons else ""
    if reason:
        return f"Guardrails withheld model actionability because {reason}."
    return f"Probability guardrail status is {status or 'unknown'}."


def _context_explanation(status: str) -> str:
    if status == "ready":
        return "Required context feature groups are reported ready."
    if status == "limited":
        return "Context is limited; inspect partial, fallback, missing, or stale feature groups."
    if status == "blocked":
        return "Context use is blocked for this row."
    return "Context readiness is unknown or not applicable."


def _attribution_explanation(status: str, block_reason: str, invalid: bool) -> str:
    if invalid:
        return "Attribution is blocked because the player label is invalid."
    if block_reason:
        return f"Attribution is blocked because {block_reason}."
    if status == "verified":
        return "Player, team, and opponent attribution is verified."
    if status:
        return f"Attribution status is {status}."
    return "Attribution status is unknown."


def _next_checks(row: dict[str, Any]) -> list[str]:
    checks: list[str] = []
    if _clean(row.get("attributionBlockReason")) or _clean(row.get("attributionStatus")) in {"invalid_player_label", "inferred_low_confidence", "ambiguous", "conflict"}:
        checks.append("Check attribution before trusting this row.")
    if _clean(row.get("calibrationStatus")) in {"not_available", "missing", "not_applicable"}:
        checks.append("Review calibration availability.")
    if _list_value(row.get("missingFeatureGroups")) or _list_value(row.get("staleFeatureGroups")):
        checks.append("Review missing or stale context features.")
    if _list_value(row.get("fallbackFeatureGroups")):
        checks.append("Review fallback context features.")
    if not _has_value(row.get("modelProbabilityPercent")):
        checks.append("Review why model output was withheld.")
    checks.append("Check lineup confirmation.")
    checks.append("Check book/odds freshness.")
    return _dedupe(checks)[:6]


def _sample_rows(rows: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    return [
        {
            "player": _clean(row.get("player")),
            "market": _clean(row.get("market")),
            "side": _clean(row.get("side")),
            "line": row.get("line"),
            "book": _clean(_first(row, "selectedBook", "book", "bestBook", "bookKey")),
            "trustTier": _clean(row.get("trustTier")),
            "unscoredReason": _clean(row.get("unscoredReason")),
        }
        for row in rows[:limit]
    ]


def _sample_by_tier(rows: list[dict[str, Any]], *, per_tier_limit: int = 5) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        explainability = row.get("explainability") if isinstance(row.get("explainability"), dict) else {}
        tier = _clean(explainability.get("trustTier")) or _clean(row.get("trustTier")) or "unknown"
        bucket = grouped.setdefault(tier, [])
        if len(bucket) < per_tier_limit:
            bucket.append(
                {
                    **_sample_rows([row], limit=1)[0],
                    "summary": _clean(explainability.get("summary")),
                    "primaryReasons": list(explainability.get("primaryReasons") or [])[:4],
                }
            )
    return dict(sorted(grouped.items()))


def _subject_role(market: Any) -> str:
    text = _clean(market)
    if text.startswith("pitcher_"):
        return "pitcher"
    if text.startswith("team_") or text in {"moneyline", "run_line", "game_total_runs"}:
        return "team"
    return "batter"


def _list_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    raw = _clean(value)
    if not raw:
        return []
    return [part.strip() for part in raw.replace(";", "|").split("|") if part.strip()]


def _dedupe(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _clean(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if _has_value(value):
            return value
    return ""


def _stake_units(value: Any) -> int | float:
    if not _has_value(value):
        return 0
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0
    return int(parsed) if parsed.is_integer() else parsed


def _coerce_int(value: Any) -> int | None:
    if not _has_value(value):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _has_value(value: Any) -> bool:
    return value not in {None, ""} and _clean(value).lower() not in {"nan", "none", "null"}


def _clean(value: Any) -> str:
    return str(value or "").strip()
