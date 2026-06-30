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
from mlb_app.services.player_prop_identity_confidence import (
    identity_confidence_for_row,
    serialize_identity_warnings,
)
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
    "pitcher",
    "book",
    "bookKey",
    "line",
    "side",
    "rawLabel",
    "americanOdds",
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
    "source_row_id",
    "prop_key",
    "game_pk",
    "american_odds",
    "implied_probability_percent",
    "book_implied_probability",
    "vig_pct",
    "odds_move",
    "line_move",
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

        predictions: list[dict[str, Any]] = []
        skipped_by_reason: Counter[str] = Counter()
        scored_by_market: Counter[str] = Counter()
        missing_model_markets: set[str] = set()
        errors: list[str] = []
        score_feature_columns: set[str] = set()
        model_feature_warning_counts: Counter[str] = Counter()

        for row in rows:
            market = model_market_key(first_value(row, ["market"], ""))
            if not market:
                skipped_by_reason["missing_market"] += 1
                continue

            model_path = self.settings.model_dir / f"prop_model_{market}.joblib"
            if not model_path.is_file():
                skipped_by_reason["missing_model"] += 1
                missing_model_markets.add(market)
                continue
            score_feature_columns.update(_model_feature_columns(model_path))

            odds = _american_odds(row)
            if odds is None:
                skipped_by_reason["bad_or_blank_odds"] += 1
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
                continue
            for warning in prediction.warnings or []:
                model_feature_warning_counts[_summarize_model_warning(warning)] += 1

            side = _derive_side(row)
            probability = float(prediction.probability)
            if side.lower().startswith("under"):
                probability = 1.0 - probability
            probability = min(max(probability, 0.0), 1.0)
            implied = _implied_probability(row, odds)
            edge_percent = (probability - implied) * 100.0
            model_probability_percent = probability * 100.0
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

            output = {
                "date": selected_date,
                "season": int(season),
                "market": market,
                "baseMarket": str(first_value(row, ["baseMarket", "base_market"], "")).strip(),
                "isAltMarket": str(first_value(row, ["isAltMarket", "is_alt_market"], "")).strip(),
                "player": str(first_value(row, ["player"], "")).strip(),
                "team": str(first_value(row, ["team"], "")).strip(),
                "opponent": str(first_value(row, ["opponent"], "")).strip(),
                "pitcher": str(first_value(row, ["pitcher"], "")).strip(),
                "book": str(first_value(row, ["book", "sportsbook"], "")).strip(),
                "bookKey": str(first_value(row, ["bookKey", "book_key", "sportsbookKey", "sportsbook_key"], "")).strip(),
                "line": _number_or_blank(first_value(row, ["line", "sportsbook_line", "prop_line"], "")),
                "side": side,
                "rawLabel": str(first_value(row, ["rawLabel", "raw_label"], "")).strip(),
                "americanOdds": _format_number(odds, 4),
                "modelProbabilityPercent": _format_number(model_probability_percent, 2),
                "impliedProbabilityPercent": _format_number(implied * 100.0, 2),
                "edgePercent": _format_number(edge_percent, 2),
                "fairOdds": american_from_probability(probability),
                "expectedValue": _format_number(expected_value_per_unit(probability, odds), 4),
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
                "source_row_id": str(first_value(row, ["source_row_id"], "")).strip(),
                "prop_key": str(first_value(row, ["prop_key"], "")).strip(),
                "game_pk": str(first_value(row, ["game_pk", "gamePk"], "")).strip(),
                "american_odds": _format_number(odds, 4),
                "implied_probability_percent": _format_number(implied * 100.0, 2),
                "book_implied_probability": _format_number(implied, 6),
                "vig_pct": _number_or_blank(first_value(row, ["vig_pct", "vig", "vigPercent"], "")),
                "odds_move": _number_or_blank(first_value(row, ["odds_move", "oddsMove"], "")),
                "line_move": _number_or_blank(first_value(row, ["line_move", "lineMove"], "")),
            }
            predictions.append(output)
            scored_by_market[market] += 1

        feature_columns = sorted(score_feature_columns or set(DEFAULT_FEATURE_COLUMNS))
        feature_completeness = _feature_completeness(rows, feature_columns)
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
        identity_confidence_counts = Counter(str(row.get("identityConfidence") or "unknown") for row in predictions)
        identity_warning_counts: Counter[str] = Counter()
        for row in predictions:
            for warning in str(row.get("identityWarnings") or "").split("|"):
                if warning:
                    identity_warning_counts[warning] += 1
        extreme_probability_rows = sum(1 for row in predictions if to_float(row.get("modelProbabilityPercent"), 0.0) >= 80.0)
        extreme_edge_rows = sum(1 for row in predictions if to_float(row.get("edgePercent"), 0.0) >= 40.0)
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
            "featureGroupsReady": feature_groups_ready,
            "featureGroupsMissing": feature_groups_missing,
            "modelFeatureWarnings": [
                {"message": message, "count": count} for message, count in sorted(model_feature_warning_counts.items())
            ],
            "extremeProbabilityRows": extreme_probability_rows,
            "extremeEdgeRows": extreme_edge_rows,
            "rows_skipped": len(rows) - len(predictions),
            "rowsSkipped": len(rows) - len(predictions),
            "skipped_by_reason": dict(sorted(skipped_by_reason.items())),
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
    enriched = [dict(row) for row in rows]
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


def _feature_completeness(rows: list[dict[str, Any]], feature_columns: list[str]) -> dict[str, Any]:
    model_features = set(feature_columns)
    report: dict[str, Any] = {}
    row_count = len(rows)
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
        report[group] = {
            "availableFields": available,
            "missingFields": missing,
            "populatedPercent": round((populated / denominator) * 100.0, 2),
            "staleFields": [],
            "warnings": warnings,
        }
    return report


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


def _row_field_names(rows: list[dict[str, Any]]) -> set[str]:
    return {str(key) for row in rows for key in row}


def _field_populated_count(rows: list[dict[str, Any]], field: str) -> int:
    aliases = [field, _camel(field)]
    count = 0
    for row in rows:
        value = first_value(row, aliases, "")
        if _is_populated_feature_value(value):
            count += 1
    return count


def _is_populated_feature_value(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return False
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
