from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.player_prop_model_calibration_service import calibration_rows
from mlb_app.services.player_prop_model_runtime import (
    expected_value_per_unit,
    first_value,
    implied_probability_from_american,
    model_market_key,
    to_float,
)

SCHEMA_VERSION = "player-prop-model-backtest.v1"
EDGE_BUCKETS = [(-1.0, -0.05), (-0.05, 0.0), (0.0, 0.05), (0.05, 0.10), (0.10, 1.0)]


class PlayerPropModelBacktestService:
    """Evaluation-only backtests for player prop model probabilities."""

    def __init__(self, *, settings: Settings = default_settings) -> None:
        self.settings = settings

    def backtest(
        self,
        *,
        season: int,
        input_path: Path | str | None = None,
        output_path: Path | str | None = None,
        summary_path: Path | str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        source_path = Path(input_path) if input_path else self.settings.data_dir / "training" / "historical_props_from_ml_labels_joined.csv"
        out_path = Path(output_path) if output_path else self.settings.data_dir / "backtests" / f"player_prop_model_backtest_{season}.csv"
        summary_out = Path(summary_path) if summary_path else self.settings.data_dir / "backtests" / f"player_prop_model_backtest_summary_{season}.json"
        raw_rows = _read_csv_rows(source_path)
        rows = backtest_rows(raw_rows)
        generated_at = datetime.now(timezone.utc).isoformat()
        market_rows = _market_summaries(rows, generated_at=generated_at)
        summary = {
            "schemaVersion": SCHEMA_VERSION,
            "season": int(season),
            "inputPath": str(source_path),
            "outputPath": str(out_path),
            "summaryPath": str(summary_out),
            "generatedAt": generated_at,
            "rowsLoaded": len(raw_rows),
            "rowsEvaluated": len(rows),
            "markets": {row["market"]: row for row in market_rows},
            "warnings": _warnings(raw_rows, rows, source_path),
            "dryRun": bool(dry_run),
        }
        if not dry_run:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            summary_out.parent.mkdir(parents=True, exist_ok=True)
            _write_csv(out_path, _flatten_rows(market_rows))
            summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {"summary": summary, "rows": market_rows}


def backtest_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, float | str | None]]:
    out: list[dict[str, float | str | None]] = []
    for row in rows:
        market = model_market_key(first_value(row, ["market", "baseMarket"], ""))
        if not market:
            continue
        normalized_rows = calibration_rows([row], market=market)
        if not normalized_rows:
            continue
        normalized = normalized_rows[0]
        implied = _implied(row)
        probability = float(normalized["probability"])
        target = float(normalized["target"])
        edge = probability - implied if implied is not None else math.nan
        odds = _odds(row)
        roi = _roi(target, odds) if odds is not None else None
        out.append(
            {
                "market": market,
                "modelProbability": probability,
                "target": target,
                "impliedProbability": implied,
                "edge": edge,
                "edgeBucket": edge_bucket(edge),
                "roi": roi,
            }
        )
    return out


def edge_bucket(edge: float) -> str:
    if math.isnan(edge):
        return "no_implied_probability"
    for low, high in EDGE_BUCKETS:
        if low <= edge < high or (high == 1.0 and edge <= high):
            return f"{low * 100:.0f}% to {high * 100:.0f}%"
    return "out_of_range"


def _market_summaries(rows: list[dict[str, Any]], *, generated_at: str) -> list[dict[str, Any]]:
    markets = sorted({str(row["market"]) for row in rows})
    summaries: list[dict[str, Any]] = []
    for market in markets:
        market_rows = [row for row in rows if row["market"] == market]
        bucket_rows = []
        for bucket in sorted({str(row["edgeBucket"]) for row in market_rows}):
            selected = [row for row in market_rows if row["edgeBucket"] == bucket]
            bucket_rows.append(_summary_row(market, selected, generated_at=generated_at, edge_bucket=bucket))
        summary = _summary_row(market, market_rows, generated_at=generated_at, edge_bucket="all")
        summary["edgeBuckets"] = bucket_rows
        summaries.append(summary)
    return summaries


def _summary_row(market: str, rows: list[dict[str, Any]], *, generated_at: str, edge_bucket: str) -> dict[str, Any]:
    count = len(rows)
    probabilities = [float(row["modelProbability"]) for row in rows]
    targets = [float(row["target"]) for row in rows]
    implied_values = [float(row["impliedProbability"]) for row in rows if row.get("impliedProbability") is not None and not math.isnan(float(row["impliedProbability"]))]
    edge_values = [float(row["edge"]) for row in rows if not math.isnan(float(row["edge"]))]
    roi_values = [float(row["roi"]) for row in rows if row.get("roi") is not None]
    return {
        "market": market,
        "edgeBucket": edge_bucket,
        "sampleSize": count,
        "hitRate": _average(targets),
        "averageModelProbability": _average(probabilities),
        "averageImpliedProbability": _average(implied_values) if implied_values else None,
        "averageEdge": _average(edge_values) if edge_values else None,
        "brierScore": _brier(probabilities, targets),
        "calibrationError": abs(_average(probabilities) - _average(targets)) if rows else None,
        "roi": _average(roi_values) if roi_values else None,
        "generatedAt": generated_at,
        "warnings": [] if count else ["No evaluated rows."],
    }


def _flatten_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for row in rows:
        buckets = row.get("edgeBuckets") if isinstance(row.get("edgeBuckets"), list) else []
        flattened.append({key: value for key, value in row.items() if key != "edgeBuckets"})
        for bucket in buckets:
            flattened.append(bucket)
    return flattened


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "market",
        "edgeBucket",
        "sampleSize",
        "hitRate",
        "averageModelProbability",
        "averageImpliedProbability",
        "averageEdge",
        "brierScore",
        "calibrationError",
        "roi",
        "generatedAt",
        "warnings",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "warnings": "|".join(row.get("warnings") or [])})


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _implied(row: dict[str, Any]) -> float | None:
    value = first_value(row, ["implied_probability", "book_implied_probability", "implied_probability_percent", "sportsbookImpliedPercent"], "")
    parsed = to_float(value, math.nan)
    if not math.isnan(parsed):
        return parsed / 100.0 if parsed > 1.0 else parsed
    odds = _odds(row)
    return implied_probability_from_american(odds) if odds is not None else None


def _odds(row: dict[str, Any]) -> float | None:
    value = first_value(row, ["american_odds", "americanOdds", "odds", "price"], "")
    parsed = to_float(value, math.nan)
    return None if math.isnan(parsed) or parsed == 0 else parsed


def _roi(target: float, odds: float) -> float:
    if target >= 1.0:
        return 100.0 / abs(odds) if odds < 0 else odds / 100.0
    return -1.0


def _average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _brier(probabilities: list[float], targets: list[float]) -> float | None:
    if not probabilities:
        return None
    return sum((p - y) ** 2 for p, y in zip(probabilities, targets, strict=False)) / len(probabilities)


def _warnings(raw_rows: list[dict[str, Any]], rows: list[dict[str, Any]], source_path: Path) -> list[str]:
    warnings: list[str] = []
    if not source_path.is_file():
        warnings.append(f"Backtest input file not found: {source_path}")
    elif raw_rows and not rows:
        warnings.append("No labeled rows with model probabilities were available for backtesting.")
    if rows and not any(row.get("roi") is not None for row in rows):
        warnings.append("No odds were available; ROI was not computed.")
    return warnings
