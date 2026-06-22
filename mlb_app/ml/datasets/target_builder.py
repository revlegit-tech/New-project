from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping, Sequence
from typing import Any

from mlb_app.ml.market_config import MarketModelConfig, get_market_config, normalize_market
from mlb_app.ml.datasets.leakage_guard import TARGET_PREFIX

TARGET_CANDIDATES: tuple[str, ...] = (
    "target_hit",
    "target_result",
)

POSITIVE_VALUES = {"1", "true", "yes", "y", "over", "hit", "win", "won", "graded_win"}
NEGATIVE_VALUES = {"0", "false", "no", "n", "under", "miss", "loss", "lost", "graded_loss"}

_LINE_FIELDS: tuple[str, ...] = ("line", "target_line", "prop_line")
_SIDE_FIELDS: tuple[str, ...] = ("side", "target_side", "rawLabel", "raw_label", "selection", "outcome")


@dataclass(frozen=True)
class MarketTarget:
    market: str
    target_hit: int | None
    target_push: bool
    target_actual_value: float | None
    target_line: float | None
    target_side: str
    target_status: str
    target_reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "target_hit": self.target_hit,
            "target_push": self.target_push,
            "target_actual_value": self.target_actual_value,
            "target_line": self.target_line,
            "target_side": self.target_side,
            "target_status": self.target_status,
            "target_reason": self.target_reason,
        }


def build_binary_target(rows: Sequence[Mapping[str, Any]] | Any, *, target_column: str | None = None) -> Any:
    pd = _pandas()
    frame = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame([dict(row) for row in rows])
    selected = target_column or _first_existing_column(frame, TARGET_CANDIDATES)
    if not selected:
        raise ValueError(f"No binary target column found. Tried: {', '.join(TARGET_CANDIDATES)}")
    if not str(selected).startswith(TARGET_PREFIX):
        raise ValueError("Training targets must come from target_* columns.")

    target = frame[selected].map(normalize_binary_target)
    valid = target.notna()
    if not bool(valid.any()):
        raise ValueError(f"Target column {selected!r} has no usable binary labels.")
    return target.loc[valid].astype(int)


def build_market_target(row: Mapping[str, Any], *, market: str | None = None) -> MarketTarget:
    config = get_market_config(market or str(row.get("market") or ""))
    market_key = config.market
    side = _target_side(row, config)
    actual = _actual_value(row, config)
    line = _first_float(row, _LINE_FIELDS)

    if actual is None:
        return MarketTarget(
            market=market_key,
            target_hit=None,
            target_push=False,
            target_actual_value=None,
            target_line=line,
            target_side=side,
            target_status="invalid_actual",
            target_reason=f"Missing or invalid {config.actual_value_field}.",
        )

    if config.target_type == "event_or_line" and line is None:
        if side not in {"over", "under"}:
            return _invalid_side(market_key, actual, line, side)
        hit = actual >= 1.0 if side == "over" else actual < 1.0
        return MarketTarget(
            market=market_key,
            target_hit=int(hit),
            target_push=False,
            target_actual_value=actual,
            target_line=None,
            target_side=side,
            target_status="graded",
            target_reason="Home-run yes/no target built from actual_home_runs >= 1.",
        )

    if line is None:
        return MarketTarget(
            market=market_key,
            target_hit=None,
            target_push=False,
            target_actual_value=actual,
            target_line=None,
            target_side=side,
            target_status="invalid_line",
            target_reason="Missing or invalid prop line.",
        )
    if side not in {"over", "under"}:
        return _invalid_side(market_key, actual, line, side)
    if actual == line:
        return MarketTarget(
            market=market_key,
            target_hit=None,
            target_push=True,
            target_actual_value=actual,
            target_line=line,
            target_side=side,
            target_status="push",
            target_reason="Actual value equaled the prop line.",
        )

    hit = actual > line if side == "over" else actual < line
    return MarketTarget(
        market=market_key,
        target_hit=int(hit),
        target_push=False,
        target_actual_value=actual,
        target_line=line,
        target_side=side,
        target_status="graded",
        target_reason=f"{side.title()} target built from {config.actual_value_field} versus line.",
    )


def build_market_target_rows(
    rows: Sequence[Mapping[str, Any]] | Any,
    *,
    market: str | None = None,
) -> list[dict[str, Any]]:
    records, _ = _records_and_index(rows)
    return [build_market_target(row, market=market).as_dict() for row in records]


def build_market_binary_target(
    rows: Sequence[Mapping[str, Any]] | Any,
    *,
    market: str | None = None,
    include_pushes: bool = False,
) -> Any:
    pd = _pandas()
    records, index = _records_and_index(rows)
    targets = [build_market_target(row, market=market) for row in records]
    values = [0 if target.target_push and include_pushes else target.target_hit for target in targets]
    target = pd.Series(values, index=index)
    valid = target.notna()
    if not bool(valid.any()):
        market_label = normalize_market(market or (records[0].get("market") if records else ""))
        raise ValueError(f"No usable market target labels found for {market_label or 'unknown market'}.")
    return target.loc[valid].astype(int)


def normalize_binary_target(value: Any) -> int | None:
    text = str(value).strip().lower()
    if text in POSITIVE_VALUES:
        return 1
    if text in NEGATIVE_VALUES:
        return 0
    try:
        return 1 if float(text) >= 1.0 else 0
    except (TypeError, ValueError):
        return None


def _first_existing_column(frame: Any, candidates: Sequence[str]) -> str:
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
    return ""


def _records_and_index(rows: Sequence[Mapping[str, Any]] | Any) -> tuple[list[dict[str, Any]], Any]:
    pd = _pandas()
    if isinstance(rows, pd.DataFrame):
        return [dict(row) for row in rows.to_dict("records")], rows.index
    records = [dict(row) for row in rows]
    return records, None


def _actual_value(row: Mapping[str, Any], config: MarketModelConfig) -> float | None:
    candidates = (
        config.actual_value_field,
        f"target_{config.actual_value_field}",
        "target_actual_value",
        "actual_value",
    )
    return _first_float(row, candidates)


def _target_side(row: Mapping[str, Any], config: MarketModelConfig) -> str:
    raw = _first_text(row, _SIDE_FIELDS)
    if not raw and config.default_side_logic in {"home_run_yes_or_line", "over_under_push"}:
        return "over"
    text = raw.strip().lower().replace("_", " ").replace("-", " ")
    if text in {"o", "over", "more", "yes", "y", "hit", "true", "1", "hr", "home run"}:
        return "over"
    if text in {"u", "under", "less", "no", "n", "miss", "false", "0"}:
        return "under"
    if "over" in text:
        return "over"
    if "under" in text:
        return "under"
    if "yes" in text or "home run" in text or text == "hr":
        return "over"
    if "no" in text:
        return "under"
    return text


def _invalid_side(market: str, actual: float | None, line: float | None, side: str) -> MarketTarget:
    return MarketTarget(
        market=market,
        target_hit=None,
        target_push=False,
        target_actual_value=actual,
        target_line=line,
        target_side=side,
        target_status="invalid_side",
        target_reason="Side must resolve to Over/Yes or Under/No.",
    )


def _first_float(row: Mapping[str, Any], fields: Sequence[str]) -> float | None:
    for field in fields:
        if field not in row:
            continue
        value = _float_or_none(row.get(field))
        if value is not None:
            return value
    return None


def _first_text(row: Mapping[str, Any], fields: Sequence[str]) -> str:
    for field in fields:
        value = row.get(field)
        if value is not None and str(value).strip():
            return str(value)
    return ""


def _float_or_none(value: Any) -> float | None:
    try:
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def _pandas() -> Any:
    try:
        import pandas as pd
    except ImportError as error:
        raise RuntimeError("pandas is required to build MLB ML targets.") from error
    return pd
