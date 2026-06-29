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
    "market",
    "player",
    "team",
    "opponent",
    "line",
    "side",
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

            side = _clean_side(first_value(row, ["side", "rawLabel"], "Over"))
            probability = float(prediction.probability)
            if side.lower().startswith("under"):
                probability = 1.0 - probability
            probability = min(max(probability, 0.0), 1.0)
            implied = implied_probability_from_american(odds)

            output = {
                "date": selected_date,
                "market": market,
                "player": str(first_value(row, ["player"], "")).strip(),
                "team": str(first_value(row, ["team"], "")).strip(),
                "opponent": str(first_value(row, ["opponent"], "")).strip(),
                "line": _number_or_blank(first_value(row, ["line", "sportsbook_line", "prop_line"], "")),
                "side": side,
                "americanOdds": _format_number(odds, 4),
                "modelProbabilityPercent": _format_number(probability * 100.0, 2),
                "impliedProbabilityPercent": _format_number(implied * 100.0, 2),
                "edgePercent": _format_number((probability - implied) * 100.0, 2),
                "fairOdds": american_from_probability(probability),
                "expectedValue": _format_number(expected_value_per_unit(probability, odds), 4),
                "modelPath": _safe_model_id(model_path, self.settings),
                "readinessLabel": "Experimental",
                "action": "Research",
                "stake": 0,
                "stakeUnits": 0,
            }
            predictions.append(output)
            scored_by_market[market] += 1

        summary = {
            "date": selected_date,
            "season": int(season),
            "source": source,
            "input_source": paths.input_source,
            "input_path": str(paths.input_path),
            "output_path": str(paths.out_path),
            "summary_output_path": str(paths.summary_out_path),
            "dry_run": bool(dry_run),
            "rows_loaded": len(rows),
            "rows_scored": len(predictions),
            "rows_skipped": len(rows) - len(predictions),
            "skipped_by_reason": dict(sorted(skipped_by_reason.items())),
            "scored_by_market": dict(sorted(scored_by_market.items())),
            "missing_model_markets": sorted(missing_model_markets),
            "errors": errors,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
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
        features_path: Path | None,
        playerboard_path: Path | None,
        out_path: Path | None,
        summary_out_path: Path | None,
    ) -> ScorePaths:
        feature_candidates = [
            self.settings.data_dir / "features" / f"prop_features_{date_label}.csv",
            self.settings.data_dir / "warehouse" / "ml_features" / f"player_prop_features_{date_label}.csv",
        ]
        explicit_features = features_path is not None
        selected_features = features_path if explicit_features else next((path for path in feature_candidates if path.is_file()), None)
        selected_playerboard = playerboard_path or (self.settings.data_dir / "playerboard" / f"playerboard_{season}.csv")

        if selected_features is not None and selected_features.is_file():
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


def _clean_side(value: Any) -> str:
    text = str(value or "").strip()
    return text[:1].upper() + text[1:].lower() if text else "Over"


def _number_or_blank(value: Any) -> float | str:
    parsed = to_float(value, math.nan)
    return "" if math.isnan(parsed) else _format_number(parsed, 4)


def _format_number(value: float, places: int) -> float:
    rounded = round(float(value), places)
    return int(rounded) if rounded.is_integer() else rounded


def _safe_model_id(model_path: Path, settings: Settings) -> str:
    try:
        return str(model_path.resolve().relative_to(settings.root_dir.resolve()))
    except ValueError:
        return model_path.name
