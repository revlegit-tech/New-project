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
    american_from_probability,
    expected_value_per_unit,
    first_value,
    implied_probability_from_american,
    model_market_key,
    score_exact_market_model,
    to_float,
)

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
    "warnings",
    "source_row_id",
    "prop_key",
    "game_pk",
    "american_odds",
    "implied_probability_percent",
]


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

        predictions: list[dict[str, Any]] = []
        skipped_by_reason: Counter[str] = Counter()
        scored_by_market: Counter[str] = Counter()
        missing_model_markets: set[str] = set()
        errors: list[str] = []

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
                "warnings": "|".join(sorted(set(warnings))),
                "source_row_id": str(first_value(row, ["source_row_id"], "")).strip(),
                "prop_key": str(first_value(row, ["prop_key"], "")).strip(),
                "game_pk": str(first_value(row, ["game_pk", "gamePk"], "")).strip(),
                "american_odds": _format_number(odds, 4),
                "implied_probability_percent": _format_number(implied * 100.0, 2),
            }
            predictions.append(output)
            scored_by_market[market] += 1

        blank_team_opponent_rows = sum(1 for row in predictions if not row.get("team") or not row.get("opponent"))
        unsafe_join_key_rows = sum(1 for row in predictions if row.get("joinKeyStrength") == "unsafe")
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
    side = str(first_value(row, ["side"], "")).strip()
    if side:
        return _clean_side(side)
    raw_label = str(first_value(row, ["rawLabel", "raw_label"], "")).strip()
    tokens = [token.strip(" :/-_()[]{}").lower() for token in raw_label.split()]
    if "under" in tokens:
        return "Under"
    if "over" in tokens:
        return "Over"
    return "Over"


def _clean_side(value: Any) -> str:
    text = str(value or "").strip()
    return text[:1].upper() + text[1:].lower() if text else "Over"


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
