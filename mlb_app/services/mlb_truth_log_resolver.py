from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


TRUTH_CANDIDATE_DIRS: tuple[Path, ...] = (
    Path("data/cloud/season_logs"),
    Path("data/warehouse/season_logs"),
    Path("data/cache/incremental_stats"),
)


@dataclass(frozen=True)
class TruthLogs:
    source_dir: Path | None
    batter_rows: list[dict[str, str]]
    pitcher_rows: list[dict[str, str]]
    team_rows: list[dict[str, str]]
    first_date: str
    last_date: str
    date_count: int
    missing_reason: str = ""

    def covers(self, game_date: str | None) -> bool:
        if not game_date or not self.first_date or not self.last_date:
            return False
        return self.first_date <= game_date <= self.last_date

    def summary(self, requested_date: str | None = None) -> dict[str, object]:
        return {
            "truth_source_dir": str(self.source_dir) if self.source_dir else "",
            "truth_rows_batter": len(self.batter_rows),
            "truth_rows_pitcher": len(self.pitcher_rows),
            "truth_rows_team": len(self.team_rows),
            "truth_first_date": self.first_date,
            "truth_last_date": self.last_date,
            "truth_date_count": self.date_count,
            "requested_date_covered": self.covers(requested_date) if requested_date else False,
            "truth_missing_reason": self.missing_reason,
        }


def read_non_empty_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return []
        rows = list(reader)
    return rows


def _date_values(rows_by_kind: Iterable[list[dict[str, str]]]) -> list[str]:
    dates: set[str] = set()
    for rows in rows_by_kind:
        for row in rows:
            value = str(row.get("date") or row.get("game_date") or "")[:10]
            if value:
                dates.add(value)
    return sorted(dates)


def load_truth_logs(season: str, *, truth_dir: str | Path | None = None) -> TruthLogs:
    candidates = [Path(truth_dir)] if truth_dir else list(TRUTH_CANDIDATE_DIRS)
    missing: list[str] = []

    for base in candidates:
        batter = read_non_empty_csv(base / f"batter_game_logs_{season}.csv")
        pitcher = read_non_empty_csv(base / f"pitcher_game_logs_{season}.csv")
        team = read_non_empty_csv(base / f"team_game_logs_{season}.csv")
        if batter and pitcher and team:
            dates = _date_values((batter, pitcher, team))
            return TruthLogs(
                source_dir=base,
                batter_rows=batter,
                pitcher_rows=pitcher,
                team_rows=team,
                first_date=dates[0] if dates else "",
                last_date=dates[-1] if dates else "",
                date_count=len(dates),
            )
        missing.append(str(base))

    return TruthLogs(
        source_dir=None,
        batter_rows=[],
        pitcher_rows=[],
        team_rows=[],
        first_date="",
        last_date="",
        date_count=0,
        missing_reason="No candidate truth directory had non-empty batter, pitcher, and team logs: "
        + ", ".join(missing),
    )
