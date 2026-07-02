from __future__ import annotations

import csv
import json
import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.player_prop_model_runtime import (
    DEFAULT_FEATURE_COLUMNS,
    american_from_probability,
    expected_value_per_unit,
    first_value,
    implied_probability_from_american,
    metadata_path_for_model,
    model_market_key,
    score_exact_market_model,
    to_float,
)
from mlb_app.services.player_prop_model_calibration_service import PlayerPropModelCalibrationService
from mlb_app.services.player_prop_context_feature_join_service import PlayerPropContextFeatureJoinService
from mlb_app.services.player_attribution import apply_attribution
from mlb_app.services.player_prop_identity_confidence import (
    identity_confidence_for_row,
    serialize_identity_warnings,
)
from mlb_app.services.player_prop_production_gate_service import PlayerPropProductionGateService
from mlb_app.services.prop_side_normalization import normalize_prop_side

OUTPUT_FIELDS = [
    "date",
    "season",
    "market",
    "baseMarket",
    "isAltMarket",
    "player",
    "team",
    "opponent",
    "attributionStatus",
    "attributionConfidence",
    "attributionCorrectionApplied",
    "playerTeamEvidenceStatus",
    "attributionWarnings",
    "originalTeam",
    "originalOpponent",
    "resolvedTeam",
    "resolvedOpponent",
    "correctedTeam",
    "correctedOpponent",
    "pitcher",
    "subjectDisplayName",
    "subjectName",
    "normalizedSubjectName",
    "subjectRole",
    "subjectNameSource",
    "subjectTeam",
    "subjectOpponent",
    "normalizedSubjectTeam",
    "normalizedSubjectOpponent",
    "subjectIdentityWarnings",
    "book",
    "bookKey",
    "line",
    "side",
    "rawLabel",
    "americanOdds",
    "rawModelProbability",
    "calibratedProbability",
    "calibrationApplied",
    "calibrationMethod",
    "calibrationStatus",
    "calibrationArtifactGeneratedAt",
    "calibrationBucket",
    "calibrationSampleSize",
    "calibrationWarning",
    "modelVersion",
    "modelFamily",
    "modelProbabilitySource",
    "probabilityGuardrailStatus",
    "probabilityGuardrailReasons",
    "trustTier",
    "trustScore",
    "trustReasons",
    "contextReadinessStatus",
    "readyFeatureGroups",
    "partialFeatureGroups",
    "fallbackFeatureGroups",
    "missingFeatureGroups",
    "staleFeatureGroups",
    "unsupportedMarketReason",
    "attributionBlockReason",
    "dataFreshnessStatus",
    "researchOnlyReason",
    "modelProbabilityPercent",
    "impliedProbabilityPercent",
    "edgePercent",
    "fairOdds",
    "expectedValue",
    "modelPath",
    "readinessLabel",
    "action",
    "stake",
    "stakeUnits",
    "confidence",
    "recommendation",
    "missingData",
    "predictionKey",
    "joinKeyStrength",
    "identityConfidence",
    "identityWarnings",
    "playerTeamVerified",
    "opponentVerified",
    "warnings",
    "modelQualityWarnings",
    "productionGateStatus",
    "productionGateReasons",
    "productionEligible",
    "betActionAllowed",
    "predictionMatched",
    "source_row_id",
    "prop_key",
    "game_pk",
    "american_odds",
    "implied_probability_percent",
    "book_implied_probability",
    "vig_pct",
    "odds_move",
    "line_move",
    "recent_games",
    "recent_rate",
    "season_rate",
    "rolling_avg_5",
    "rolling_avg_10",
    "rolling_avg_15",
    "rolling_total_bases_10",
    "rolling_hr_rate_15",
    "rolling_k_rate_10",
    "pitcher_recent_games",
    "pitcher_k_rate",
    "pitcher_walk_rate",
    "pitcher_hr_rate",
    "pitcher_babip",
    "pitcher_days_rest",
    "pitcher_velo_delta",
    "barrel_rate",
    "hard_hit_rate",
    "xwoba",
    "xba",
    "xslg",
    "batter_babip",
    "batter_k_rate",
    "batter_walk_rate",
    "batter_ld_rate",
    "batter_gb_rate",
    "batter_sprint_speed",
    "batter_hand",
    "pitcher_hand",
    "batter_avg_vs_hand",
    "batter_k_rate_vs_hand",
    "batter_recent_hits_vs_lhp",
    "batter_recent_hits_vs_rhp",
    "pitcher_avg_allowed_vs_hand",
]

FEATURE_GROUPS = {
    "odds_movement": ["odds_move", "line_move"],
    "vig": ["vig_pct", "book_implied_probability", "implied_probability_percent"],
    "player_recent_form": [
        "recent_games",
        "recent_rate",
        "season_rate",
        "rolling_avg_5",
        "rolling_avg_10",
        "rolling_avg_15",
        "rolling_total_bases_10",
        "rolling_hr_rate_15",
        "rolling_k_rate_10",
    ],
    "statcast": [
        "batter_babip",
        "batter_k_rate",
        "batter_walk_rate",
        "barrel_rate",
        "hard_hit_rate",
        "xwoba",
        "xba",
        "xslg",
        "batter_ld_rate",
        "batter_gb_rate",
        "batter_sprint_speed",
    ],
    "weather": ["temperature", "wind_mph", "wind_out_score", "wind_out_flag", "turf_flag", "cold_game_flag"],
    "umpire": ["ump_k_rate", "ump_zone_size_zscore", "ump_favor_batter_score"],
    "handedness_platoon": [
        "batter_hand",
        "pitcher_hand",
        "batter_avg_vs_hand",
        "batter_k_rate_vs_hand",
        "batter_recent_hits_vs_lhp",
        "batter_recent_hits_vs_rhp",
        "pitcher_avg_allowed_vs_hand",
    ],
    "pitcher_context": [
        "pitcher_k_rate",
        "pitcher_walk_rate",
        "pitcher_hr_rate",
        "pitcher_babip",
        "pitcher_days_rest",
        "pitcher_velo_delta",
    ],
    "bullpen_context": ["opponent_bullpen_era_7d"],
    "game_markets": ["team_k_rate", "team_walk_rate", "opponent_rate", "park_factor", "hit_factor", "hr_factor", "k_factor"],
}


@dataclass(frozen=True)
class ScorePaths:
    input_path: Path
    input_source: str
    out_path: Path
    summary_out_path: Path


class PlayerPropModelScoringService:
    """Score current MLB player prop rows with exact market model artifacts."""

    def __init__(self, *, settings: Settings = default_settings) -> None:
        self.settings = settings
        self.calibration = PlayerPropModelCalibrationService(settings=settings)
        self.context_joins = PlayerPropContextFeatureJoinService(settings=settings)
        self.production_gates = PlayerPropProductionGateService(settings=settings)

    def score(
        self,
        *,
        date_label: str,
        season: int,
        source: str = "playerboard",
        features_path: Path | str | None = None,
        playerboard_path: Path | str | None = None,
        out_path: Path | str | None = None,
        summary_out_path: Path | str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        selected_date = str(date_label).strip()
        paths = self.resolve_paths(
            date_label=selected_date,
            season=season,
            source=source,
            features_path=Path(features_path) if features_path else None,
            playerboard_path=Path(playerboard_path) if playerboard_path else None,
            out_path=Path(out_path) if out_path else None,
            summary_out_path=Path(summary_out_path) if summary_out_path else None,
        )
        rows = _read_csv_rows(paths.input_path)
        rows = [row for row in rows if _row_matches_date(row, selected_date)]
        rows = _enrich_safe_feature_rows(rows, input_source=paths.input_source)
        context_join_result = self.context_joins.join(
            rows,
            date_label=selected_date,
            season=season,
            input_source=paths.input_source,
        )
        rows = context_join_result.rows

        predictions: list[dict[str, Any]] = []
        skipped_by_reason: Counter[str] = Counter()
        skipped_samples: list[dict[str, Any]] = []
        scored_by_market: Counter[str] = Counter()
        missing_model_markets: set[str] = set()
        errors: list[str] = []
        score_feature_columns: set[str] = set()
        model_feature_warning_counts: Counter[str] = Counter()

        for row in rows:
            market = model_market_key(first_value(row, ["market"], ""))
            if not market:
                skipped_by_reason["missing_market"] += 1
                _append_sample(skipped_samples, row, reason="missing_market")
                continue

            model_path = self.settings.model_dir / f"prop_model_{market}.joblib"
            if not model_path.is_file():
                skipped_by_reason["missing_model"] += 1
                missing_model_markets.add(market)
                _append_sample(skipped_samples, row, reason="missing_model", market=market)
                continue
            score_feature_columns.update(_model_feature_columns(model_path))

            odds = _american_odds(row)
            if odds is None:
                skipped_by_reason["bad_or_blank_odds"] += 1
                _append_sample(skipped_samples, row, reason="bad_or_blank_odds", market=market)
                continue

            try:
                prediction_row = dict(row)
                prediction_row.setdefault("american_odds", odds)
                prediction = score_exact_market_model(
                    prediction_row,
                    model_path=model_path,
                    market=market,
                    settings=self.settings,
                )
            except Exception as error:
                skipped_by_reason["prediction_error"] += 1
                errors.append(f"{market}: {type(error).__name__}: {error}")
                _append_sample(skipped_samples, row, reason="prediction_error", market=market)
                continue
            for warning in prediction.warnings or []:
                model_feature_warning_counts[_summarize_model_warning(warning)] += 1

            side = _derive_side(row)
            probability = float(prediction.probability)
            if side.lower().startswith("under"):
                probability = 1.0 - probability
            probability = min(max(probability, 0.0), 1.0)
            calibration = self.calibration.apply(market=market, probability=probability)
            display_probability = calibration.applied_probability
            implied = _implied_probability(row, odds)
            edge_percent = (display_probability - implied) * 100.0
            model_probability_percent = display_probability * 100.0
            warnings = _row_warnings(
                row,
                input_source=paths.input_source,
                model_probability_percent=model_probability_percent,
                edge_percent=edge_percent,
            )
            prediction_key = _prediction_key(row, selected_date=selected_date, market=market, side=side, odds=odds)
            join_key_strength = _join_key_strength(
                row,
                input_source=paths.input_source,
                prediction_key=prediction_key,
                market=market,
                side=side,
            )
            identity = identity_confidence_for_row(row, input_source=paths.input_source)
            if join_key_strength == "unsafe" and "unsafe_prediction_join_key" not in warnings:
                warnings.append("unsafe_prediction_join_key")
            output_line = _number_or_blank(first_value(row, ["line", "sportsbook_line", "prop_line"], ""))
            output_book = str(first_value(row, ["bookKey", "book_key", "sportsbookKey", "sportsbook_key", "book", "sportsbook"], "")).strip()
            context_readiness = _row_context_readiness(
                row,
                model_feature_columns=score_feature_columns or set(DEFAULT_FEATURE_COLUMNS),
                context_artifacts=context_join_result.artifacts,
            )
            guardrail = _probability_guardrail(
                row,
                odds=odds,
                calibration_status=calibration.status,
                model_probability_percent=model_probability_percent,
                edge_percent=edge_percent,
                market=market,
            )

            output = {
                "date": selected_date,
                "season": int(season),
                "market": market,
                "baseMarket": str(first_value(row, ["baseMarket", "base_market"], "")).strip(),
                "isAltMarket": str(first_value(row, ["isAltMarket", "is_alt_market"], "")).strip(),
                "player": str(first_value(row, ["player"], "")).strip(),
                "team": str(first_value(row, ["team"], "")).strip(),
                "opponent": str(first_value(row, ["opponent"], "")).strip(),
                "attributionStatus": str(first_value(row, ["attributionStatus", "attribution_status"], "")).strip(),
                "attributionConfidence": str(first_value(row, ["attributionConfidence", "attribution_confidence"], "")).strip(),
                "attributionCorrectionApplied": _bool_or_blank(
                    first_value(row, ["attributionCorrectionApplied", "attribution_correction_applied"], "")
                ),
                "playerTeamEvidenceStatus": str(
                    first_value(row, ["playerTeamEvidenceStatus", "player_team_evidence_status"], "")
                ).strip(),
                "attributionWarnings": _warning_value(
                    first_value(row, ["attributionWarnings", "attribution_warnings"], "")
                ),
                "originalTeam": str(first_value(row, ["originalTeam", "original_team"], "")).strip(),
                "originalOpponent": str(first_value(row, ["originalOpponent", "original_opponent"], "")).strip(),
                "resolvedTeam": str(first_value(row, ["resolvedTeam", "resolved_team", "correctedTeam", "corrected_team"], "")).strip(),
                "resolvedOpponent": str(
                    first_value(row, ["resolvedOpponent", "resolved_opponent", "correctedOpponent", "corrected_opponent"], "")
                ).strip(),
                "correctedTeam": str(first_value(row, ["correctedTeam", "corrected_team"], "")).strip(),
                "correctedOpponent": str(first_value(row, ["correctedOpponent", "corrected_opponent"], "")).strip(),
                "pitcher": str(first_value(row, ["pitcher"], "")).strip(),
                "subjectDisplayName": str(first_value(row, ["subjectDisplayName"], "")).strip(),
                "subjectName": str(first_value(row, ["subjectName"], "")).strip(),
                "normalizedSubjectName": str(first_value(row, ["normalizedSubjectName"], "")).strip(),
                "subjectRole": str(first_value(row, ["subjectRole"], "unknown")).strip() or "unknown",
                "subjectNameSource": str(first_value(row, ["subjectNameSource"], "")).strip(),
                "subjectTeam": str(first_value(row, ["subjectTeam"], "")).strip(),
                "subjectOpponent": str(first_value(row, ["subjectOpponent"], "")).strip(),
                "normalizedSubjectTeam": str(first_value(row, ["normalizedSubjectTeam"], "")).strip(),
                "normalizedSubjectOpponent": str(first_value(row, ["normalizedSubjectOpponent"], "")).strip(),
                "subjectIdentityWarnings": str(first_value(row, ["subjectIdentityWarnings"], "")).strip(),
                "book": str(first_value(row, ["book", "sportsbook"], "")).strip(),
                "bookKey": output_book,
                "line": output_line,
                "side": side,
                "rawLabel": str(first_value(row, ["rawLabel", "raw_label"], "")).strip(),
                "americanOdds": _format_number(odds, 4),
                "rawModelProbability": _format_number(calibration.raw_probability, 6),
                "calibratedProbability": ""
                if calibration.calibrated_probability is None
                else _format_number(calibration.calibrated_probability, 6),
                "calibrationApplied": calibration.applied,
                "calibrationMethod": calibration.method,
                "calibrationStatus": calibration.status,
                "calibrationArtifactGeneratedAt": calibration.artifact_generated_at,
                "calibrationBucket": _calibration_bucket(market=market, side=side, line=output_line, book=output_book),
                "calibrationSampleSize": _calibration_sample_size(self.settings, market),
                "calibrationWarning": "|".join(sorted(set(calibration.warnings))),
                "modelVersion": _clean_model_version(prediction.model_version),
                "modelFamily": "player_prop_exact_market",
                "modelProbabilitySource": "calibrated_model" if calibration.applied else "raw_model_uncalibrated",
                "probabilityGuardrailStatus": guardrail["status"],
                "probabilityGuardrailReasons": "|".join(guardrail["reasons"]),
                "modelProbabilityPercent": _format_number(model_probability_percent, 2),
                "impliedProbabilityPercent": _format_number(implied * 100.0, 2),
                "edgePercent": _format_number(edge_percent, 2),
                "fairOdds": american_from_probability(display_probability),
                "expectedValue": _format_number(expected_value_per_unit(display_probability, odds), 4),
                "modelPath": _safe_model_id(model_path, self.settings),
                "readinessLabel": "Experimental",
                "action": "Research",
                "stake": 0,
                "stakeUnits": 0,
                "confidence": str(first_value(row, ["confidence"], "")).strip(),
                "recommendation": str(first_value(row, ["recommendation"], "Research")).strip() or "Research",
                "missingData": str(first_value(row, ["missingData", "missing_data"], "")).strip(),
                "predictionKey": prediction_key,
                "joinKeyStrength": join_key_strength,
                "identityConfidence": identity["identityConfidence"],
                "identityWarnings": serialize_identity_warnings(identity["identityWarnings"]),
                "playerTeamVerified": identity["playerTeamVerified"],
                "opponentVerified": identity["opponentVerified"],
                "warnings": "|".join(sorted(set(warnings))),
                "modelQualityWarnings": "|".join(sorted(set(calibration.warnings))),
                "predictionMatched": True,
                "source_row_id": str(first_value(row, ["source_row_id"], "")).strip(),
                "prop_key": str(first_value(row, ["prop_key"], "")).strip(),
                "game_pk": str(first_value(row, ["game_pk", "gamePk"], "")).strip(),
                "american_odds": _format_number(odds, 4),
                "implied_probability_percent": _format_number(implied * 100.0, 2),
                "book_implied_probability": _format_number(implied, 6),
                "vig_pct": _number_or_blank(first_value(row, ["vig_pct", "vig", "vigPercent"], "")),
                "odds_move": _number_or_blank(first_value(row, ["odds_move", "oddsMove"], "")),
                "line_move": _number_or_blank(first_value(row, ["line_move", "lineMove"], "")),
                "recent_games": _number_or_blank(first_value(row, ["recent_games", "recentGames"], "")),
                "recent_rate": _number_or_blank(first_value(row, ["recent_rate", "recentRate"], "")),
                "season_rate": _number_or_blank(first_value(row, ["season_rate", "seasonRate"], "")),
                "rolling_avg_5": _number_or_blank(first_value(row, ["rolling_avg_5", "rollingAvg5"], "")),
                "rolling_avg_10": _number_or_blank(first_value(row, ["rolling_avg_10", "rollingAvg10"], "")),
                "rolling_avg_15": _number_or_blank(first_value(row, ["rolling_avg_15", "rollingAvg15"], "")),
                "rolling_total_bases_10": _number_or_blank(
                    first_value(row, ["rolling_total_bases_10", "rollingTotalBases10"], "")
                ),
                "rolling_hr_rate_15": _number_or_blank(first_value(row, ["rolling_hr_rate_15", "rollingHrRate15"], "")),
                "rolling_k_rate_10": _number_or_blank(first_value(row, ["rolling_k_rate_10", "rollingKRate10"], "")),
                "pitcher_recent_games": _number_or_blank(first_value(row, ["pitcher_recent_games", "pitcherRecentGames"], "")),
                "pitcher_k_rate": _number_or_blank(first_value(row, ["pitcher_k_rate", "pitcherKRate"], "")),
                "pitcher_walk_rate": _number_or_blank(first_value(row, ["pitcher_walk_rate", "pitcherWalkRate"], "")),
                "pitcher_hr_rate": _number_or_blank(first_value(row, ["pitcher_hr_rate", "pitcherHrRate"], "")),
                "pitcher_babip": _number_or_blank(first_value(row, ["pitcher_babip", "pitcherBabip"], "")),
                "pitcher_days_rest": _number_or_blank(first_value(row, ["pitcher_days_rest", "pitcherDaysRest"], "")),
                "pitcher_velo_delta": _number_or_blank(first_value(row, ["pitcher_velo_delta", "pitcherVeloDelta"], "")),
                "barrel_rate": _number_or_blank(first_value(row, ["barrel_rate", "barrelRate"], "")),
                "hard_hit_rate": _number_or_blank(first_value(row, ["hard_hit_rate", "hardHitRate"], "")),
                "xwoba": _number_or_blank(first_value(row, ["xwoba", "xwOBA"], "")),
                "xba": _number_or_blank(first_value(row, ["xba", "xBA"], "")),
                "xslg": _number_or_blank(first_value(row, ["xslg", "xSLG"], "")),
                "batter_babip": _number_or_blank(first_value(row, ["batter_babip", "batterBabip"], "")),
                "batter_k_rate": _number_or_blank(first_value(row, ["batter_k_rate", "batterKRate"], "")),
                "batter_walk_rate": _number_or_blank(first_value(row, ["batter_walk_rate", "batterWalkRate"], "")),
                "batter_ld_rate": _number_or_blank(first_value(row, ["batter_ld_rate", "batterLdRate"], "")),
                "batter_gb_rate": _number_or_blank(first_value(row, ["batter_gb_rate", "batterGbRate"], "")),
                "batter_sprint_speed": _number_or_blank(first_value(row, ["batter_sprint_speed", "batterSprintSpeed"], "")),
                "batter_hand": str(first_value(row, ["batter_hand", "batterHand"], "")).strip(),
                "pitcher_hand": str(first_value(row, ["pitcher_hand", "pitcherHand"], "")).strip(),
                "batter_avg_vs_hand": _number_or_blank(first_value(row, ["batter_avg_vs_hand", "batterAvgVsHand"], "")),
                "batter_k_rate_vs_hand": _number_or_blank(first_value(row, ["batter_k_rate_vs_hand", "batterKRateVsHand"], "")),
                "batter_recent_hits_vs_lhp": _number_or_blank(
                    first_value(row, ["batter_recent_hits_vs_lhp", "batterRecentHitsVsLhp"], "")
                ),
                "batter_recent_hits_vs_rhp": _number_or_blank(
                    first_value(row, ["batter_recent_hits_vs_rhp", "batterRecentHitsVsRhp"], "")
                ),
                "pitcher_avg_allowed_vs_hand": _number_or_blank(
                    first_value(row, ["pitcher_avg_allowed_vs_hand", "pitcherAvgAllowedVsHand"], "")
                ),
            }
            gate = self.production_gates.evaluate(output, season=season, date_label=selected_date)
            output.update(
                {
                    "productionGateStatus": gate.productionGateStatus,
                    "productionGateReasons": "|".join(gate.productionGateReasons),
                    "productionEligible": gate.productionEligible,
                    "betActionAllowed": gate.betActionAllowed,
                }
            )
            output.update(
                _row_trust(
                    output,
                    context_readiness=context_readiness,
                    guardrail=guardrail,
                    calibration_applied=calibration.applied,
                )
            )
            predictions.append(output)
            scored_by_market[market] += 1

        feature_columns = sorted(score_feature_columns or set(DEFAULT_FEATURE_COLUMNS))
        context_artifacts = context_join_result.artifacts
        feature_completeness = _feature_completeness(predictions, feature_columns, context_artifacts=context_artifacts)
        feature_groups_ready = sorted(
            group for group, payload in feature_completeness.items() if payload["populatedPercent"] > 0
        )
        feature_groups_missing = sorted(
            group for group, payload in feature_completeness.items() if payload["populatedPercent"] == 0
        )
        for warning in _feature_completeness_warnings(feature_completeness, rows, feature_columns):
            model_feature_warning_counts[warning] += 1
        blank_team_opponent_rows = sum(1 for row in predictions if not row.get("team") or not row.get("opponent"))
        unsafe_join_key_rows = sum(1 for row in predictions if row.get("joinKeyStrength") == "unsafe")
        calibration_status_counts = Counter(str(row.get("calibrationStatus") or "unknown") for row in predictions)
        calibration_applied_rows = sum(1 for row in predictions if row.get("calibrationApplied") is True)
        calibration_artifact_generated_at = _first_text(
            row.get("calibrationArtifactGeneratedAt") for row in predictions if row.get("calibrationStatus") == "applied"
        )
        model_quality_warning_counts: Counter[str] = Counter()
        for row in predictions:
            for warning in str(row.get("modelQualityWarnings") or "").split("|"):
                if warning:
                    model_quality_warning_counts[warning] += 1
        identity_confidence_counts = Counter(str(row.get("identityConfidence") or "unknown") for row in predictions)
        identity_warning_counts: Counter[str] = Counter()
        for row in predictions:
            for warning in str(row.get("identityWarnings") or "").split("|"):
                if warning:
                    identity_warning_counts[warning] += 1
        extreme_probability_rows = sum(1 for row in predictions if to_float(row.get("modelProbabilityPercent"), 0.0) >= 80.0)
        extreme_edge_rows = sum(1 for row in predictions if to_float(row.get("edgePercent"), 0.0) >= 40.0)
        trust_tier_counts = Counter(str(row.get("trustTier") or "unknown") for row in predictions)
        guardrail_status_counts = Counter(str(row.get("probabilityGuardrailStatus") or "unknown") for row in predictions)
        context_readiness_counts = Counter(str(row.get("contextReadinessStatus") or "unknown") for row in predictions)
        calibration_coverage = _calibration_coverage(predictions, skipped_by_reason, skipped_samples)
        summary = {
            "date": selected_date,
            "season": int(season),
            "source": source,
            "input_source": paths.input_source,
            "input_path": str(paths.input_path),
            "inputSource": paths.input_source,
            "inputPath": str(paths.input_path),
            "output_path": str(paths.out_path),
            "summary_output_path": str(paths.summary_out_path),
            "dry_run": bool(dry_run),
            "rows_loaded": len(rows),
            "rows_scored": len(predictions),
            "rowsLoaded": len(rows),
            "rowsScored": len(predictions),
            "blankTeamOpponentRows": blank_team_opponent_rows,
            "unsafeJoinKeyRows": unsafe_join_key_rows,
            "identityConfidenceCounts": dict(sorted(identity_confidence_counts.items())),
            "identityWarningCounts": dict(sorted(identity_warning_counts.items())),
            "featureCompleteness": feature_completeness,
            "contextFeatureArtifacts": context_artifacts,
            "contextJoinCounts": context_join_result.counts,
            "contextJoinWarnings": context_join_result.warnings,
            "contextIdentityDiagnostics": context_join_result.diagnostics,
            "boardContextAlignmentDiagnostics": context_join_result.board_alignment_diagnostics,
            "playerRecentFormProviderDiagnostics": _context_provider_diagnostics(
                self.settings, selected_date, "player_recent_form"
            ),
            "pitcherContextProviderDiagnostics": _context_provider_diagnostics(
                self.settings, selected_date, "pitcher_context"
            ),
            "handednessProviderDiagnostics": _context_provider_diagnostics(self.settings, selected_date, "handedness_platoon"),
            "oddsMovementRowsLoaded": context_join_result.counts.get("oddsMovementRowsLoaded", 0),
            "oddsMovementRowsJoined": context_join_result.counts.get("oddsMovementRowsJoined", 0),
            "oddsMovementRowsSkipped": context_join_result.counts.get("oddsMovementRowsSkipped", 0),
            "oddsMovementAmbiguousRows": context_join_result.counts.get("oddsMovementAmbiguousRows", 0),
            "statcastRowsLoaded": context_join_result.counts.get("statcastRowsLoaded", 0),
            "statcastRowsJoined": context_join_result.counts.get("statcastRowsJoined", 0),
            "statcastRowsSkipped": context_join_result.counts.get("statcastRowsSkipped", 0),
            "statcastAmbiguousRows": context_join_result.counts.get("statcastAmbiguousRows", 0),
            "handednessPlatoonRowsLoaded": context_join_result.counts.get("handednessPlatoonRowsLoaded", 0),
            "handednessPlatoonRowsJoined": context_join_result.counts.get("handednessPlatoonRowsJoined", 0),
            "handednessPlatoonRowsSkipped": context_join_result.counts.get("handednessPlatoonRowsSkipped", 0),
            "handednessPlatoonAmbiguousRows": context_join_result.counts.get("handednessPlatoonAmbiguousRows", 0),
            "featureGroupsReady": feature_groups_ready,
            "featureGroupsMissing": feature_groups_missing,
            "modelFeatureWarnings": [
                {"message": message, "count": count} for message, count in sorted(model_feature_warning_counts.items())
            ],
            "calibrationStatusCounts": dict(sorted(calibration_status_counts.items())),
            "calibrationCoverage": calibration_coverage,
            "calibrationAppliedRows": calibration_applied_rows,
            "calibrationSkippedRows": len(predictions) - calibration_applied_rows,
            "trustTierCounts": dict(sorted(trust_tier_counts.items())),
            "guardrailStatusCounts": dict(sorted(guardrail_status_counts.items())),
            "contextReadinessCounts": dict(sorted(context_readiness_counts.items())),
            "sampleGuardrailRows": _sample_rows(
                predictions,
                lambda item: str(item.get("probabilityGuardrailStatus") or "") != "ok",
                fields=("player", "market", "side", "line", "probabilityGuardrailStatus", "probabilityGuardrailReasons"),
            ),
            "sampleLowTrustRows": _sample_rows(
                predictions,
                lambda item: str(item.get("trustTier") or "") in {"blocked", "low", "limited"},
                fields=("player", "market", "attributionStatus", "trustTier", "trustReasons", "calibrationStatus"),
            ),
            "sampleHighTrustRows": _sample_rows(
                predictions,
                lambda item: str(item.get("trustTier") or "") == "standard",
                fields=("player", "market", "attributionStatus", "trustTier", "calibrationStatus", "calibrationBucket"),
            ),
            "sampleUncalibratedRows": _sample_rows(
                predictions,
                lambda item: str(item.get("calibrationStatus") or "") != "applied",
                fields=("player", "market", "side", "line", "calibrationStatus", "calibrationWarning"),
            ),
            "modelQualityWarnings": [
                {"message": message, "count": count} for message, count in sorted(model_quality_warning_counts.items())
            ],
            "backtestReference": _latest_backtest_reference(self.settings, season),
            "calibrationArtifactVersion": calibration_artifact_generated_at,
            "extremeProbabilityRows": extreme_probability_rows,
            "extremeEdgeRows": extreme_edge_rows,
            "rows_skipped": len(rows) - len(predictions),
            "rowsSkipped": len(rows) - len(predictions),
            "skipped_by_reason": dict(sorted(skipped_by_reason.items())),
            "sampleSkippedRows": skipped_samples[:10],
            "scored_by_market": dict(sorted(scored_by_market.items())),
            "missing_model_markets": sorted(missing_model_markets),
            "skippedByReason": dict(sorted(skipped_by_reason.items())),
            "scoredByMarket": dict(sorted(scored_by_market.items())),
            "missingModelMarkets": sorted(missing_model_markets),
            "errors": errors,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        summary["generatedAt"] = summary["generated_at"]
        report = {"summary": summary, "rows": predictions}

        if not dry_run:
            paths.out_path.parent.mkdir(parents=True, exist_ok=True)
            paths.summary_out_path.parent.mkdir(parents=True, exist_ok=True)
            _write_csv(paths.out_path, predictions)
            paths.summary_out_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        return report

    def resolve_paths(
        self,
        *,
        date_label: str,
        season: int,
        source: str,
        features_path: Path | None,
        playerboard_path: Path | None,
        out_path: Path | None,
        summary_out_path: Path | None,
    ) -> ScorePaths:
        normalized_source = str(source or "playerboard").strip().lower()
        if normalized_source not in {"playerboard", "features"}:
            raise ValueError(f"Unsupported scoring source: {source!r}. Use 'playerboard' or 'features'.")

        feature_candidates = [
            self.settings.data_dir / "features" / f"prop_features_{date_label}.csv",
            self.settings.data_dir / "warehouse" / "ml_features" / f"player_prop_features_{date_label}.csv",
        ]
        selected_playerboard = playerboard_path or (self.settings.data_dir / "playerboard" / f"playerboard_{season}.csv")

        if normalized_source == "features":
            selected_features = features_path or next((path for path in feature_candidates if path.is_file()), feature_candidates[0])
            input_path = selected_features
            input_source = "features"
        else:
            input_path = selected_playerboard
            input_source = "playerboard"

        return ScorePaths(
            input_path=input_path,
            input_source=input_source,
            out_path=out_path or (self.settings.data_dir / "predictions" / f"prop_predictions_{date_label}.csv"),
            summary_out_path=summary_out_path
            or (self.settings.data_dir / "predictions" / f"prop_predictions_{date_label}_summary.json"),
        )


def _enrich_safe_feature_rows(rows: list[dict[str, Any]], *, input_source: str) -> list[dict[str, Any]]:
    enriched = [apply_attribution(row) for row in rows]
    _fill_implied_probability(enriched)
    _fill_paired_vig(enriched, input_source=input_source)
    _fill_prior_snapshot_movement(enriched, input_source=input_source)
    return enriched


def _fill_implied_probability(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        odds = _american_odds(row)
        if odds is None:
            continue
        implied = implied_probability_from_american(odds)
        if not _has_numeric(row, "book_implied_probability"):
            row["book_implied_probability"] = implied
        if not _has_numeric(row, "implied_probability_percent"):
            row["implied_probability_percent"] = round(implied * 100.0, 6)


def _fill_paired_vig(rows: list[dict[str, Any]], *, input_source: str) -> None:
    by_key: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if _identity_confidence(row, input_source=input_source) not in {"strong", "medium"}:
            continue
        key = _safe_pair_key(row)
        if key:
            by_key.setdefault(key, []).append(row)

    for candidates in by_key.values():
        overs = [row for row in candidates if _derive_side(row).lower().startswith("over")]
        unders = [row for row in candidates if _derive_side(row).lower().startswith("under")]
        if len(overs) != 1 or len(unders) != 1:
            continue
        over_odds = _american_odds(overs[0])
        under_odds = _american_odds(unders[0])
        if over_odds is None or under_odds is None:
            continue
        vig = round((implied_probability_from_american(over_odds) + implied_probability_from_american(under_odds) - 1.0) * 100.0, 6)
        for row in (overs[0], unders[0]):
            if not _has_numeric(row, "vig_pct"):
                row["vig_pct"] = vig


def _fill_prior_snapshot_movement(rows: list[dict[str, Any]], *, input_source: str) -> None:
    for row in rows:
        if _identity_confidence(row, input_source=input_source) not in {"strong", "medium"}:
            continue
        current_odds = _american_odds(row)
        previous_odds = _previous_odds(row)
        if current_odds is not None and previous_odds is not None and not _has_numeric(row, "odds_move"):
            row["odds_move"] = round(current_odds - previous_odds, 6)

        current_line = to_float(first_value(row, ["line", "sportsbook_line", "prop_line"], ""), math.nan)
        previous_line = _previous_line(row)
        if not math.isnan(current_line) and previous_line is not None and not _has_numeric(row, "line_move"):
            row["line_move"] = round(current_line - previous_line, 6)


def _model_feature_columns(model_path: Path) -> list[str]:
    path = metadata_path_for_model(model_path)
    if not path.exists():
        return list(DEFAULT_FEATURE_COLUMNS)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return list(DEFAULT_FEATURE_COLUMNS)
    features = payload.get("numericFeatures")
    if isinstance(features, list) and features:
        return [str(feature) for feature in features if str(feature).strip()]
    return list(DEFAULT_FEATURE_COLUMNS)


def _feature_completeness(
    rows: list[dict[str, Any]],
    feature_columns: list[str],
    *,
    context_artifacts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    model_features = set(feature_columns)
    report: dict[str, Any] = {}
    row_count = len(rows)
    context_artifacts = context_artifacts or {}
    for group, fields in FEATURE_GROUPS.items():
        selected = [field for field in fields if field in model_features or field in _row_field_names(rows)]
        if not selected:
            selected = list(fields)
        available = [field for field in selected if _field_populated_count(rows, field) > 0]
        missing = [field for field in selected if field not in available]
        denominator = max(row_count * len(selected), 1)
        populated = sum(_field_populated_count(rows, field) for field in selected)
        warnings: list[str] = []
        if row_count == 0:
            warnings.append("No rows were loaded for feature completeness reporting.")
        elif not available:
            warnings.append(f"No populated {group} feature fields were available.")
        elif missing:
            warnings.append(f"{len(missing)} {group} feature fields were missing or all-null.")
        artifact = context_artifacts.get(group) or {}
        artifact_rows = int(artifact.get("rows") or 0)
        if artifact_rows > 0:
            artifact_fields = [field for field in selected if field in set(artifact.get("fields") or [])]
            if group == "odds_movement":
                populated_percent = round((populated / denominator) * 100.0, 2)
                if not available:
                    warnings = [warning for warning in warnings if not warning.startswith(f"No populated {group}")]
                    warnings.append(f"{group} context artifact available but no scoring rows joined safely.")
            elif group in {"player_recent_form", "pitcher_context", "statcast", "handedness_platoon"}:
                populated_percent = round((populated / denominator) * 100.0, 2)
                if not available:
                    warnings = [warning for warning in warnings if not warning.startswith(f"No populated {group}")]
                    warnings.append(f"{group} artifact has rows but no scoring rows joined safely.")
                elif artifact_fields and missing:
                    warnings.append(f"{len(missing)} {group} artifact fields were not populated in scoring rows.")
            elif artifact_fields:
                available = sorted(set(available).union(artifact_fields))
                missing = [field for field in selected if field not in available]
                populated_percent = max(
                    round((populated / denominator) * 100.0, 2),
                    round((len(artifact_fields) / max(len(selected), 1)) * 100.0, 2),
                )
                warnings = [warning for warning in warnings if not warning.startswith(f"No populated {group}")]
                warnings.append(f"{group} context artifact available with {artifact_rows} rows; join into scoring rows may still be pending.")
            else:
                populated_percent = round((populated / denominator) * 100.0, 2)
        else:
            populated_percent = round((populated / denominator) * 100.0, 2)
        report[group] = {
            "availableFields": available,
            "missingFields": missing,
            "populatedPercent": populated_percent,
            "staleFields": [],
            "warnings": warnings,
        }
    return report


def _context_feature_artifacts(settings: Settings, date_label: str) -> dict[str, Any]:
    paths = {
        "player_recent_form": settings.data_dir / "context" / "player_recent_form" / f"player_recent_form_{date_label}.csv",
        "pitcher_context": settings.data_dir / "context" / "pitcher_context" / f"pitcher_context_{date_label}.csv",
        "odds_movement": settings.data_dir / "context" / "odds_movement" / f"odds_movement_{date_label}.csv",
        "weather": settings.data_dir / "context" / "weather" / f"weather_context_{date_label}.csv",
        "statcast": settings.data_dir / "context" / "statcast" / f"statcast_context_{date_label}.csv",
        "bullpen_context": settings.data_dir / "context" / "bullpen" / f"bullpen_context_{date_label}.csv",
        "game_markets": settings.data_dir / "context" / "game_markets" / f"game_markets_{date_label}.csv",
        "umpire": settings.data_dir / "context" / "umpire" / f"umpire_context_{date_label}.csv",
    }
    artifacts: dict[str, Any] = {}
    for group, path in paths.items():
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                rows = sum(1 for _ in reader)
                fields = [field for field in (reader.fieldnames or []) if field]
        except Exception:
            continue
        artifacts[group] = {"path": str(path), "rows": rows, "fields": fields}
    return artifacts


def _context_provider_diagnostics(settings: Settings, date_label: str, provider: str) -> dict[str, Any]:
    audit_path = settings.data_dir / "context" / f"context_source_audit_{date_label}.json"
    if audit_path.is_file():
        try:
            payload = json.loads(audit_path.read_text(encoding="utf-8"))
            diagnostics = ((payload.get("providers") or {}).get(provider) or {}).get("diagnostics")
            if isinstance(diagnostics, dict):
                return diagnostics
        except Exception:
            pass
    if provider != "handedness_platoon":
        return {}
    path = settings.data_dir / "context" / "handedness_platoon" / f"handedness_platoon_{date_label}.csv"
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = [dict(row) for row in reader]
            fields = [field for field in (reader.fieldnames or []) if field]
    except Exception:
        return {"providerSourceMode": "unknown", "contextRowsGenerated": 0}
    board_seeded_rows = [row for row in rows if str(row.get("seedSource") or "").strip() == "playerboard"]
    return {
        "providerSourceMode": "playerboard" if board_seeded_rows else ("artifact" if rows else "none"),
        "contextRowsGenerated": len(rows),
        "contextRowsGeneratedFromBoard": len(board_seeded_rows),
        "contextRowsWithBatterHand": _artifact_populated_count(rows, "batter_hand"),
        "contextRowsWithPitcherHand": _artifact_populated_count(rows, "pitcher_hand"),
        "contextRowsWithSplitStats": sum(
            1
            for row in rows
            if any(
                _is_populated_feature_value(row.get(field))
                for field in (
                    "batter_avg_vs_hand",
                    "batter_k_rate_vs_hand",
                    "batter_recent_hits_vs_lhp",
                    "batter_recent_hits_vs_rhp",
                    "pitcher_avg_allowed_vs_hand",
                )
            )
        ),
        "fields": fields,
    }


def _artifact_populated_count(rows: list[dict[str, Any]], field: str) -> int:
    return sum(1 for row in rows if str(row.get(field) or "").strip())


def _feature_completeness_warnings(
    completeness: dict[str, Any],
    rows: list[dict[str, Any]],
    feature_columns: list[str],
) -> list[str]:
    warnings: list[str] = []
    for group, payload in completeness.items():
        if payload.get("populatedPercent") == 0:
            warnings.append(f"{group}: all configured fields are missing or all-null")
    all_null_model_fields = [
        field for field in feature_columns if field in _row_field_names(rows) and _field_populated_count(rows, field) == 0
    ]
    if all_null_model_fields:
        warnings.append("all-null model feature columns: " + ", ".join(sorted(all_null_model_fields)[:25]))
    return warnings


def _row_context_readiness(
    row: dict[str, Any],
    *,
    model_feature_columns: set[str],
    context_artifacts: dict[str, Any],
) -> dict[str, Any]:
    ready: list[str] = []
    partial: list[str] = []
    fallback: list[str] = []
    missing: list[str] = []
    stale: list[str] = []
    for group, fields in FEATURE_GROUPS.items():
        model_fields = [field for field in fields if field in model_feature_columns]
        selected = model_fields or fields
        populated = [field for field in selected if _is_populated_feature_value(first_value(row, [field, _camel(field)], ""), field=field)]
        artifact = context_artifacts.get(group) or {}
        artifact_rows = int(artifact.get("rows") or 0)
        fallback_only = _artifact_fallback_only(artifact)
        if populated and len(populated) == len(selected) and not fallback_only:
            ready.append(group)
        elif populated and not fallback_only:
            partial.append(group)
        elif fallback_only:
            fallback.append(group)
        elif artifact_rows > 0:
            partial.append(group)
        else:
            missing.append(group)
    status = "ready"
    if fallback and not ready and not partial:
        status = "fallback_only"
    elif fallback or partial or missing:
        status = "limited"
    if len(missing) == len(FEATURE_GROUPS):
        status = "missing"
    return {
        "status": status,
        "ready": sorted(set(ready)),
        "partial": sorted(set(partial)),
        "fallback": sorted(set(fallback)),
        "missing": sorted(set(missing)),
        "stale": stale,
    }


def _probability_guardrail(
    row: dict[str, Any],
    *,
    odds: float | None,
    calibration_status: str,
    model_probability_percent: float,
    edge_percent: float,
    market: str,
) -> dict[str, Any]:
    reasons: list[str] = []
    if odds is None:
        reasons.append("missing_or_invalid_odds")
    if not market:
        reasons.append("missing_market")
    if str(calibration_status or "") != "applied":
        reasons.append(f"calibration_{calibration_status or 'missing'}")
    if model_probability_percent >= 80.0 or model_probability_percent <= 20.0:
        reasons.append("extreme_probability_review_required")
    if abs(edge_percent) >= 40.0:
        reasons.append("extreme_edge_review_required")
    attribution = str(first_value(row, ["attributionStatus", "attribution_status"], "") or "").strip().lower()
    if attribution == "invalid_player_label":
        reasons.append("invalid_player_label")
    confidence = str(first_value(row, ["attributionConfidence", "attribution_confidence"], "") or "").strip().lower()
    if confidence == "inferred_low_confidence":
        reasons.append("inferred_low_confidence")
    status = "ok" if not reasons else ("blocked" if {"missing_or_invalid_odds", "missing_market", "invalid_player_label"} & set(reasons) else "warning")
    return {"status": status, "reasons": sorted(set(reasons))}


def _row_trust(
    row: dict[str, Any],
    *,
    context_readiness: dict[str, Any],
    guardrail: dict[str, Any],
    calibration_applied: bool,
) -> dict[str, Any]:
    reasons: list[str] = ["research_only_lock"]
    score = 50
    attribution = str(row.get("attributionStatus") or "").strip().lower()
    identity = str(row.get("identityConfidence") or "").strip().lower()
    if attribution == "invalid_player_label":
        score -= 50
        reasons.append("invalid_player_label")
    elif attribution in {"verified", "corrected"} or identity == "strong":
        score += 20
        reasons.append("verified_attribution")
    elif identity in {"unknown", "weak"}:
        score -= 20
        reasons.append("weak_identity")
    if calibration_applied:
        score += 15
        reasons.append("calibrated_probability")
    else:
        score -= 15
        reasons.append(f"calibration_{row.get('calibrationStatus') or 'missing'}")
    context_status = str(context_readiness.get("status") or "missing")
    if context_status == "ready":
        score += 10
        reasons.append("context_ready")
    elif context_status == "fallback_only":
        score -= 20
        reasons.append("fallback_only_context")
    elif context_status in {"limited", "missing"}:
        score -= 10
        reasons.append(f"context_{context_status}")
    if guardrail["status"] == "blocked":
        score = min(score, 20)
        reasons.extend(guardrail["reasons"])
    elif guardrail["status"] == "warning":
        score -= 10
        reasons.extend(guardrail["reasons"])
    if str(row.get("joinKeyStrength") or "") == "unsafe":
        score = min(score, 25)
        reasons.append("unsafe_prediction_join_key")
    score = max(0, min(100, score))
    if score < 25:
        tier = "blocked"
    elif score < 45:
        tier = "low"
    elif score < 70:
        tier = "limited"
    else:
        tier = "standard"
    attribution_block = "invalid_player_label" if attribution == "invalid_player_label" else ""
    unsupported_reason = "" if row.get("modelPath") else "missing_model"
    return {
        "trustTier": tier,
        "trustScore": score,
        "trustReasons": "|".join(sorted(set(reasons))),
        "contextReadinessStatus": context_status,
        "readyFeatureGroups": "|".join(context_readiness.get("ready") or []),
        "partialFeatureGroups": "|".join(context_readiness.get("partial") or []),
        "fallbackFeatureGroups": "|".join(context_readiness.get("fallback") or []),
        "missingFeatureGroups": "|".join(context_readiness.get("missing") or []),
        "staleFeatureGroups": "|".join(context_readiness.get("stale") or []),
        "unsupportedMarketReason": unsupported_reason,
        "attributionBlockReason": attribution_block,
        "dataFreshnessStatus": "current",
        "researchOnlyReason": "MLB_ENABLE_BET_ACTIONS=0; research lock keeps action=Research and stakeUnits=0",
    }


def _artifact_fallback_only(artifact: dict[str, Any]) -> bool:
    mode = " ".join(str(artifact.get(key) or "").lower() for key in ("status", "source", "sourceMode", "providerSourceMode"))
    if "fallback" in mode:
        return True
    fields = {str(field).lower() for field in artifact.get("fields") or []}
    return any("fallback" in field for field in fields)


def _row_field_names(rows: list[dict[str, Any]]) -> set[str]:
    return {str(key) for row in rows for key in row}


def _field_populated_count(rows: list[dict[str, Any]], field: str) -> int:
    aliases = [field, _camel(field)]
    count = 0
    for row in rows:
        value = first_value(row, aliases, "")
        if _is_populated_feature_value(value, field=field):
            count += 1
    return count


def _is_populated_feature_value(value: Any, *, field: str = "") -> bool:
    if value is None:
        return False
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return False
    if field in {"batter_hand", "pitcher_hand"}:
        return text.upper() in {"L", "R", "S"}
    parsed = to_float(value, math.nan)
    return not math.isnan(parsed)


def _has_numeric(row: dict[str, Any], field: str) -> bool:
    return _is_populated_feature_value(first_value(row, [field, _camel(field)], ""))


def _safe_pair_key(row: dict[str, Any]) -> str:
    date_value = str(first_value(row, ["date", "game_date", "gameDate", "event_date"], "")).strip()
    market = model_market_key(first_value(row, ["market"], ""))
    player = str(first_value(row, ["player"], "")).strip()
    team = str(first_value(row, ["team"], "")).strip()
    opponent = str(first_value(row, ["opponent"], "")).strip()
    book = str(first_value(row, ["bookKey", "book_key", "sportsbookKey", "sportsbook_key", "book", "sportsbook"], "")).strip()
    line = _number_or_blank(first_value(row, ["line", "sportsbook_line", "prop_line"], ""))
    side = _derive_side(row)
    if not all([date_value, market, player, team, opponent, book, str(line), side]):
        return ""
    return "|".join([date_value, market, _identity_key(player), _identity_key(team), _identity_key(opponent), _identity_key(book), str(line)])


def _identity_confidence(row: dict[str, Any], *, input_source: str) -> str:
    return str(identity_confidence_for_row(row, input_source=input_source).get("identityConfidence") or "unknown")


def _previous_odds(row: dict[str, Any]) -> float | None:
    value = first_value(
        row,
        [
            "previous_american_odds",
            "previousAmericanOdds",
            "prior_american_odds",
            "priorAmericanOdds",
            "firstAmericanOdds",
            "openingAmericanOdds",
        ],
        "",
    )
    parsed = to_float(value, math.nan)
    return None if math.isnan(parsed) or parsed == 0 else float(parsed)


def _previous_line(row: dict[str, Any]) -> float | None:
    value = first_value(row, ["previous_line", "previousLine", "prior_line", "priorLine", "firstLine", "openingLine"], "")
    parsed = to_float(value, math.nan)
    return None if math.isnan(parsed) else float(parsed)


def _summarize_model_warning(message: str) -> str:
    text = " ".join(str(message or "").split())
    if "Skipping features without any observed values" in text:
        return "sklearn skipped all-null feature columns during scoring"
    return text[:240]


def _camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _row_matches_date(row: dict[str, Any], date_label: str) -> bool:
    row_date = str(first_value(row, ["date", "game_date", "gameDate", "event_date"], "")).strip()
    return row_date == date_label


def _american_odds(row: dict[str, Any]) -> float | None:
    value = first_value(row, ["americanOdds", "american_odds", "odds", "price", "over_odds", "overOdds"], "")
    odds = to_float(value, math.nan)
    if math.isnan(odds) or odds == 0:
        return None
    return float(odds)


def _implied_probability(row: dict[str, Any], odds: float) -> float:
    value = first_value(row, ["sportsbookImpliedPercent", "implied_probability_percent"], "")
    parsed = to_float(value, math.nan)
    if not math.isnan(parsed):
        return parsed / 100.0 if parsed > 1.0 else parsed
    return implied_probability_from_american(odds)


def _derive_side(row: dict[str, Any]) -> str:
    return normalize_prop_side(
        first_value(row, ["side"], ""),
        first_value(row, ["rawLabel", "raw_label"], ""),
        first_value(row, ["label", "title", "name"], ""),
        first_value(row, ["outcome", "outcomeName", "outcome_name", "selection"], ""),
    )


def _number_or_blank(value: Any) -> float | str:
    parsed = to_float(value, math.nan)
    return "" if math.isnan(parsed) else _format_number(parsed, 4)


def _bool_or_blank(value: Any) -> bool | str:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return bool(value)


def _warning_value(value: Any) -> list[str] | str:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, (tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return ""
    return [part.strip() for part in text.split("|") if part.strip()] if "|" in text else text


def _format_number(value: float, places: int) -> float:
    rounded = round(float(value), places)
    return int(rounded) if rounded.is_integer() else rounded


def _prediction_key(row: dict[str, Any], *, selected_date: str, market: str, side: str, odds: float) -> str:
    player = str(first_value(row, ["player"], "")).strip()
    team = str(first_value(row, ["team"], "")).strip()
    opponent = str(first_value(row, ["opponent"], "")).strip()
    book = str(first_value(row, ["bookKey", "book_key", "sportsbookKey", "sportsbook_key", "book", "sportsbook"], "")).strip()
    line = _number_or_blank(first_value(row, ["line", "sportsbook_line", "prop_line"], ""))
    parts = [
        selected_date,
        market,
        _identity_key(player),
        _identity_key(team),
        _identity_key(opponent),
        _identity_key(book),
        str(line),
        _identity_key(side),
        str(_format_number(odds, 4)),
    ]
    if not selected_date or not market or not player or not book or not side:
        return ""
    return "|".join(parts)


def _join_key_strength(row: dict[str, Any], *, input_source: str, prediction_key: str, market: str, side: str) -> str:
    player = str(first_value(row, ["player"], "")).strip()
    team = str(first_value(row, ["team"], "")).strip()
    opponent = str(first_value(row, ["opponent"], "")).strip()
    book = str(first_value(row, ["bookKey", "book_key", "sportsbookKey", "sportsbook_key", "book", "sportsbook"], "")).strip()
    if input_source == "features":
        required = ["source_row_id", "prop_key", "game_pk", "team", "opponent"]
        if any(not _feature_identity_value(row, key) for key in required):
            return "unsafe"
    if prediction_key and team and opponent and book and player and market and side:
        return "strong"
    if prediction_key and (team or opponent):
        return "medium"
    return "unsafe"


def _row_warnings(
    row: dict[str, Any],
    *,
    input_source: str,
    model_probability_percent: float,
    edge_percent: float,
) -> list[str]:
    warnings: list[str] = []
    team = str(first_value(row, ["team"], "")).strip()
    opponent = str(first_value(row, ["opponent"], "")).strip()
    if not team or not opponent:
        warnings.append("missing_team_or_opponent")
    if input_source == "features":
        required = ["source_row_id", "prop_key", "game_pk", "team", "opponent"]
        if any(not _feature_identity_value(row, key) for key in required):
            warnings.append("unsafe_prediction_join_key")
    if model_probability_percent >= 80.0 or edge_percent >= 40.0:
        warnings.append("experimental_extreme_probability_review_required")
    return warnings


def _feature_identity_value(row: dict[str, Any], key: str) -> str:
    aliases = {
        "source_row_id": ["source_row_id", "sourceRowId"],
        "prop_key": ["prop_key", "propKey"],
        "game_pk": ["game_pk", "gamePk"],
        "team": ["team"],
        "opponent": ["opponent"],
    }
    return str(first_value(row, aliases.get(key, [key]), "")).strip()


def _identity_key(value: Any) -> str:
    return "_".join(str(value or "").strip().lower().split())


def _safe_model_id(model_path: Path, settings: Settings) -> str:
    try:
        return str(model_path.resolve().relative_to(settings.root_dir.resolve()))
    except ValueError:
        return model_path.name


def _first_text(values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _latest_backtest_reference(settings: Settings, season: int) -> dict[str, Any]:
    path = settings.data_dir / "backtests" / f"player_prop_model_backtest_summary_{season}.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"path": str(path), "status": "unreadable"}
    return {
        "path": str(path),
        "generatedAt": str(payload.get("generatedAt") or ""),
        "rowsEvaluated": payload.get("rowsEvaluated"),
    }


def _append_sample(samples: list[dict[str, Any]], row: dict[str, Any], *, reason: str, market: str = "") -> None:
    if len(samples) >= 10:
        return
    samples.append(
        {
            "reason": reason,
            "player": str(first_value(row, ["player"], "") or "").strip(),
            "market": market or model_market_key(first_value(row, ["market"], "")),
            "side": _derive_side(row),
            "line": _number_or_blank(first_value(row, ["line", "sportsbook_line", "prop_line"], "")),
            "book": str(first_value(row, ["bookKey", "book_key", "book", "sportsbook"], "") or "").strip(),
            "attributionStatus": str(first_value(row, ["attributionStatus", "attribution_status"], "") or "").strip(),
        }
    )


def _sample_rows(rows: list[dict[str, Any]], predicate: Any, *, fields: tuple[str, ...], limit: int = 10) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for row in rows:
        if not predicate(row):
            continue
        samples.append({field: row.get(field) for field in fields})
        if len(samples) >= limit:
            break
    return samples


def _calibration_coverage(
    predictions: list[dict[str, Any]],
    skipped_by_reason: Counter[str],
    skipped_samples: list[dict[str, Any]],
) -> dict[str, Any]:
    status_by_market: dict[str, Counter[str]] = {}
    calibrated_samples: list[dict[str, Any]] = []
    for row in predictions:
        market = str(row.get("market") or "unknown")
        status_by_market.setdefault(market, Counter())[str(row.get("calibrationStatus") or "unknown")] += 1
        if row.get("calibrationApplied") is True and len(calibrated_samples) < 10:
            calibrated_samples.append(
                {
                    "player": row.get("player"),
                    "market": market,
                    "side": row.get("side"),
                    "line": row.get("line"),
                    "book": row.get("bookKey") or row.get("book"),
                    "calibrationBucket": row.get("calibrationBucket"),
                    "calibrationSampleSize": row.get("calibrationSampleSize"),
                }
            )
    blocked = sum(1 for row in predictions if row.get("trustTier") == "blocked")
    unsupported = int(skipped_by_reason.get("missing_model") or 0) + sum(1 for row in predictions if row.get("unsupportedMarketReason"))
    invalid_attribution = sum(1 for row in predictions if row.get("attributionBlockReason"))
    return {
        "totalScoredRows": len(predictions),
        "calibratedRows": sum(1 for row in predictions if row.get("calibrationApplied") is True),
        "uncalibratedRows": sum(1 for row in predictions if row.get("calibrationApplied") is not True),
        "skippedRows": sum(skipped_by_reason.values()),
        "blockedRows": blocked,
        "unsupportedMarketRows": unsupported,
        "invalidAttributionRows": invalid_attribution,
        "calibrationStatusCountsByMarket": {market: dict(sorted(counter.items())) for market, counter in sorted(status_by_market.items())},
        "sampleSkippedRows": skipped_samples[:10],
        "sampleCalibratedRows": calibrated_samples,
    }


def _calibration_bucket(*, market: str, side: str, line: Any, book: str) -> str:
    parsed_line = to_float(line, math.nan)
    if math.isnan(parsed_line):
        line_bucket = "line:missing"
    elif parsed_line <= 0.5:
        line_bucket = "line:0-0.5"
    elif parsed_line <= 1.5:
        line_bucket = "line:1-1.5"
    elif parsed_line <= 3.5:
        line_bucket = "line:2-3.5"
    else:
        line_bucket = "line:4+"
    book_bucket = _identity_key(book) or "book:unknown"
    return "|".join([market or "unknown_market", _identity_key(side) or "unknown_side", line_bucket, book_bucket])


def _calibration_sample_size(settings: Settings, market: str) -> int | str:
    path = settings.model_dir / "calibration" / f"player_prop_calibration_{market}.joblib"
    if not path.is_file():
        return ""
    try:
        import joblib

        artifact = joblib.load(path)
    except Exception:
        return ""
    if not isinstance(artifact, dict):
        return ""
    try:
        return int(artifact.get("sampleSize") or artifact.get("sample_size"))
    except (TypeError, ValueError):
        return ""


def _clean_model_version(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text == "unknown" else text
