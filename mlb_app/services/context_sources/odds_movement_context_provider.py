from __future__ import annotations

from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.context_sources.base import (
    ContextProviderResult,
    clean,
    context_path,
    first_value,
    key,
    read_csv_rows,
    to_float,
    write_csv_rows,
)


ODDS_MOVEMENT_FIELDS = [
    "date",
    "season",
    "player",
    "market",
    "side",
    "line",
    "book",
    "bookKey",
    "americanOdds",
    "previousAmericanOdds",
    "odds_move",
    "previousLine",
    "line_move",
    "currentSnapshotPath",
    "priorSnapshotPath",
]


class OddsMovementContextProvider:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def materialize(self, *, date_label: str, season: int) -> ContextProviderResult:
        output_path = context_path(self.settings, "odds_movement", f"odds_movement_{date_label}.csv")
        current_path = self.settings.data_dir / "odds" / f"propline_props_{date_label}.csv"
        warnings: list[str] = []
        if not current_path.is_file():
            warnings.append("Current odds snapshot not found.")
            write_csv_rows(output_path, [], ODDS_MOVEMENT_FIELDS)
            return self._result("missing", date_label, season, 0, output_path, warnings)

        prior_path = self._prior_snapshot(date_label)
        if prior_path is None:
            warnings.append("Prior odds snapshot not found; movement fields left null.")
        current_rows = read_csv_rows(current_path)
        prior_rows = read_csv_rows(prior_path) if prior_path else []
        prior_by_key = {_odds_key(row): row for row in prior_rows if _odds_key(row)}
        output = []
        for row in current_rows:
            row_key = _odds_key(row)
            if not row_key:
                continue
            prior = prior_by_key.get(row_key, {})
            current_odds = to_float(first_value(row, ["americanOdds", "american_odds", "odds"]), 0.0)
            previous_odds = to_float(first_value(prior, ["americanOdds", "american_odds", "odds"]), 0.0) if prior else 0.0
            current_line = to_float(first_value(row, ["line", "prop_line"]), 0.0)
            previous_line = to_float(first_value(prior, ["line", "prop_line"]), 0.0) if prior else 0.0
            output.append(
                {
                    "date": date_label,
                    "season": season,
                    "player": clean(first_value(row, ["player"])),
                    "market": clean(first_value(row, ["market"])),
                    "side": clean(first_value(row, ["side"])),
                    "line": clean(first_value(row, ["line"])),
                    "book": clean(first_value(row, ["book"])),
                    "bookKey": clean(first_value(row, ["bookKey", "book_key"])),
                    "americanOdds": clean(first_value(row, ["americanOdds", "american_odds", "odds"])),
                    "previousAmericanOdds": "" if not prior else clean(first_value(prior, ["americanOdds", "american_odds", "odds"])),
                    "odds_move": "" if not prior or current_odds == 0.0 or previous_odds == 0.0 else round(current_odds - previous_odds, 6),
                    "previousLine": "" if not prior else clean(first_value(prior, ["line", "prop_line"])),
                    "line_move": "" if not prior else round(current_line - previous_line, 6),
                    "currentSnapshotPath": str(current_path),
                    "priorSnapshotPath": str(prior_path or ""),
                }
            )
        if prior_path and not any(clean(row.get("previousAmericanOdds")) for row in output):
            warnings.append("Prior odds snapshot did not match current prop keys.")
        write_csv_rows(output_path, output, ODDS_MOVEMENT_FIELDS)
        status = _status_for_output(output, prior_path=prior_path)
        return self._result(status, date_label, season, len(output), output_path, warnings)

    def _prior_snapshot(self, date_label: str) -> Path | None:
        candidates = sorted(self.settings.data_dir.glob("odds/propline_props_*.csv"))
        prior = [path for path in candidates if path.stem.replace("propline_props_", "") < date_label]
        return prior[-1] if prior else None

    def _result(self, status: str, date_label: str, season: int, rows: int, path: Path, warnings: list[str]) -> ContextProviderResult:
        return ContextProviderResult(
            status=status,
            date=date_label,
            season=season,
            source="odds_movement",
            rows=rows,
            path=str(path),
            warnings=warnings,
        )


def _status_for_output(output: list[dict[str, Any]], *, prior_path: Path | None) -> str:
    if not output:
        return "missing"
    return "partial" if prior_path and not any(clean(row.get("previousAmericanOdds")) for row in output) else "ok"


def _odds_key(row: dict[str, Any]) -> str:
    parts = [
        key(first_value(row, ["player"])),
        key(first_value(row, ["market"])),
        key(first_value(row, ["side"])),
        key(first_value(row, ["bookKey", "book_key", "book"])),
        clean(first_value(row, ["line", "prop_line"])),
    ]
    if any(not part for part in parts[:4]):
        return ""
    return "|".join(parts)
