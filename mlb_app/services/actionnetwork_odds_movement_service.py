from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _float(value: Any) -> float | None:
    try:
        text = _clean(value)
        return float(text) if text else None
    except ValueError:
        return None


def _time(value: Any) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _prop_key(row: dict[str, str]) -> tuple[str, ...]:
    entity = _clean(row.get("player_id")) or _clean(row.get("team_id"))
    return (
        _clean(row.get("source") or "actionnetwork"),
        _clean(row.get("game_date")),
        _clean(row.get("event_id")),
        entity,
        _clean(row.get("market_group")),
        _clean(row.get("market_type")),
        _clean(row.get("line")),
        _clean(row.get("bet_side")),
        _clean(row.get("book")),
    )


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_timestamped_snapshots(odds_dir: Path, game_date: str) -> list[Path]:
    return sorted(odds_dir.glob(f"actionnetwork_all_markets_{game_date}_*.csv"))


class ActionNetworkOddsMovementService:
    def build_feature_rows(self, rows: list[dict[str, str]]) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            if _clean(row.get("event_id")):
                grouped[_prop_key(row)].append(row)

        features: list[dict[str, Any]] = []
        for key, group in sorted(grouped.items()):
            group.sort(key=lambda item: _clean(item.get("snapshot_time")))
            first = group[0]
            latest = group[-1]
            odds = [_float(row.get("american_odds")) for row in group]
            probs = [_float(row.get("implied_probability")) for row in group]
            lines = [_float(row.get("line")) for row in group]
            odds_vals = [value for value in odds if value is not None]
            first_time = _time(first.get("snapshot_time"))
            latest_time = _time(latest.get("snapshot_time"))
            minutes = (
                (latest_time - first_time).total_seconds() / 60.0
                if first_time and latest_time
                else None
            )
            latest_snapshot = _clean(latest.get("snapshot_time"))
            latest_rows = [row for row in group if _clean(row.get("snapshot_time")) == latest_snapshot]
            latest_probs = [_float(row.get("implied_probability")) for row in latest_rows]
            latest_probs = [value for value in latest_probs if value is not None]
            best_price = max(odds_vals) if odds_vals else None

            features.append(
                {
                    "meta_source": key[0],
                    "meta_game_date": key[1],
                    "meta_event_id": key[2],
                    "meta_player_id": _clean(first.get("player_id")),
                    "meta_player_name": _clean(first.get("player_name")),
                    "meta_team_id": _clean(first.get("team_id")),
                    "meta_market_group": key[4],
                    "meta_market_type": key[5],
                    "meta_line": key[6],
                    "meta_bet_side": key[7],
                    "meta_book": key[8],
                    "meta_snapshot_first_time": _clean(first.get("snapshot_time")),
                    "meta_snapshot_latest_time": _clean(latest.get("snapshot_time")),
                    "feature_snapshot_count": len({_clean(row.get("snapshot_time")) for row in group}),
                    "feature_book_count": len({_clean(row.get("book")) for row in group if _clean(row.get("book"))}),
                    "feature_first_american_odds": _float(first.get("american_odds")),
                    "feature_latest_american_odds": _float(latest.get("american_odds")),
                    "feature_min_american_odds": min(odds_vals) if odds_vals else None,
                    "feature_max_american_odds": max(odds_vals) if odds_vals else None,
                    "feature_odds_delta_first_to_latest": (
                        _float(latest.get("american_odds")) - _float(first.get("american_odds"))
                        if _float(latest.get("american_odds")) is not None
                        and _float(first.get("american_odds")) is not None
                        else None
                    ),
                    "feature_implied_prob_first": _float(first.get("implied_probability")),
                    "feature_implied_prob_latest": _float(latest.get("implied_probability")),
                    "feature_implied_prob_delta": (
                        _float(latest.get("implied_probability")) - _float(first.get("implied_probability"))
                        if _float(latest.get("implied_probability")) is not None
                        and _float(first.get("implied_probability")) is not None
                        else None
                    ),
                    "feature_line_first": _float(first.get("line")),
                    "feature_line_latest": _float(latest.get("line")),
                    "feature_line_delta": (
                        _float(latest.get("line")) - _float(first.get("line"))
                        if _float(latest.get("line")) is not None and _float(first.get("line")) is not None
                        else None
                    ),
                    "feature_minutes_between_first_latest": minutes,
                    "feature_market_available_early": 1 if len(group) > 1 else 0,
                    "feature_market_removed_or_missing_latest": 0,
                    "feature_books_disagreeing_count": len(set(odds_vals)),
                    "feature_best_price_book_count": odds_vals.count(best_price) if best_price is not None else 0,
                    "feature_consensus_implied_prob_latest": (
                        sum(latest_probs) / len(latest_probs) if latest_probs else None
                    ),
                }
            )
        return features


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
