from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from incremental_stats_collector import (  # noqa: E402
    BATTER_FIELDS,
    PITCHER_FIELDS,
    clean,
    extract_boxscore_logs,
    fetch_json,
    game_is_final,
    mlb_get,
    season_phase_for_date,
    team_code,
)

WAREHOUSE_SEASON_LOG_DIR = ROOT / "data" / "warehouse" / "season_logs"
MLB_BASE = "https://statsapi.mlb.com/api/v1"

KEY_PRIORITY: tuple[tuple[str, ...], ...] = (
    ("game_pk", "player_id", "date"),
    ("gamePk", "playerId", "date"),
    ("game_date", "player_name", "team"),
    ("date", "player", "team"),
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill verified MLB batter/pitcher game logs from MLB StatsAPI boxscores."
    )
    parser.add_argument("--start-date", required=True, help="First slate date in YYYY-MM-DD format.")
    parser.add_argument("--end-date", required=True, help="Last slate date in YYYY-MM-DD format.")
    parser.add_argument("--season", type=int, required=True, help="MLB season, for example 2026.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and summarize without writing CSV files.")
    return parser.parse_args(argv)


def date_range(start_date: str, end_date: str) -> list[str]:
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    if end < start:
        raise ValueError("--end-date must be on or after --start-date")

    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv_rows(path: Path, fieldnames: list[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: clean(row.get(field, "")) for field in fieldnames})


def field_order(base_fields: list[str], existing_rows: list[dict[str, str]], new_rows: list[dict[str, Any]]) -> list[str]:
    fields = list(base_fields)
    seen = set(fields)
    for row in [*existing_rows, *new_rows]:
        for field in row:
            if field not in seen:
                fields.append(field)
                seen.add(field)
    return fields


def stable_key(row: Mapping[str, Any]) -> tuple[str, ...]:
    for fields in KEY_PRIORITY:
        values = tuple(clean(row.get(field)) for field in fields)
        if all(values):
            return (fields[0], *values)
    return ("row", json.dumps({str(k): clean(v) for k, v in sorted(row.items())}, sort_keys=True))


def dedupe_existing(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, ...]] = set()
    deduped = []
    for row in rows:
        key = stable_key(row)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def merge_rows(existing_rows: list[dict[str, str]], new_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()

    for row in existing_rows:
        key = stable_key(row)
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)

    before = len(merged)
    for row in new_rows:
        key = stable_key(row)
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)

    return merged, len(merged) - before


def dates_present(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    return sorted({clean(row.get("date") or row.get("game_date"))[:10] for row in rows if clean(row.get("date") or row.get("game_date"))})


def schedule_games(date_label: str, season: int) -> list[dict[str, Any]]:
    payload = mlb_get(
        "schedule",
        {
            "sportId": 1,
            "startDate": date_label,
            "endDate": date_label,
            "hydrate": "probablePitcher,team",
        },
    )
    games: list[dict[str, Any]] = []
    for day in payload.get("dates", []):
        for game in day.get("games", []):
            teams = game.get("teams", {})
            away_team = teams.get("away", {}).get("team", {})
            home_team = teams.get("home", {}).get("team", {})
            games.append(
                {
                    "season": season,
                    "seasonPhase": season_phase_for_date(date_label, season),
                    "date": date_label,
                    "gamePk": game.get("gamePk"),
                    "gameDate": game.get("gameDate"),
                    "status": game.get("status", {}).get("detailedState", ""),
                    "codedGameState": game.get("status", {}).get("codedGameState", ""),
                    "away": team_code(away_team),
                    "home": team_code(home_team),
                    "awayName": away_team.get("name", ""),
                    "homeName": home_team.get("name", ""),
                    "awayScore": teams.get("away", {}).get("score"),
                    "homeScore": teams.get("home", {}).get("score"),
                    "awayProbablePitcher": teams.get("away", {}).get("probablePitcher", {}).get("fullName", ""),
                    "homeProbablePitcher": teams.get("home", {}).get("probablePitcher", {}).get("fullName", ""),
                    "venue": game.get("venue", {}).get("name", ""),
                    "final": game_is_final(game),
                }
            )
    return games


def boxscore_for_game(game_pk: Any) -> dict[str, Any]:
    return fetch_json(f"{MLB_BASE}/game/{clean(game_pk)}/boxscore")


def collect_logs(start_date: str, end_date: str, season: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    batter_rows: list[dict[str, Any]] = []
    pitcher_rows: list[dict[str, Any]] = []
    warnings: list[str] = []

    for date_label in date_range(start_date, end_date):
        try:
            games = schedule_games(date_label, season)
        except Exception as error:
            warnings.append(f"{date_label}: schedule fetch failed: {type(error).__name__}: {error}")
            continue

        for game in games:
            game_pk = clean(game.get("gamePk"))
            if not game_pk:
                warnings.append(f"{date_label}: skipped scheduled game with no gamePk")
                continue
            if not bool(game.get("final")):
                warnings.append(f"{date_label} gamePk={game_pk}: skipped non-final game")
                continue
            try:
                extracted = extract_boxscore_logs(date_label, game, boxscore_for_game(game_pk))
            except Exception as error:
                warnings.append(f"{date_label} gamePk={game_pk}: boxscore fetch/extract failed: {type(error).__name__}: {error}")
                continue
            batter_rows.extend(extracted.get("batters", []))
            pitcher_rows.extend(extracted.get("pitchers", []))

    return batter_rows, pitcher_rows, warnings


def build_summary(
    *,
    start_date: str,
    end_date: str,
    season: int,
    dry_run: bool,
    batter_path: Path,
    pitcher_path: Path,
    existing_batters: list[dict[str, str]],
    existing_pitchers: list[dict[str, str]],
    final_batters: list[dict[str, Any]],
    final_pitchers: list[dict[str, Any]],
    added_batters: int,
    added_pitchers: int,
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "requestedDateRange": {"startDate": start_date, "endDate": end_date, "season": season},
        "dryRun": dry_run,
        "paths": {"batter": str(batter_path), "pitcher": str(pitcher_path)},
        "existingRowCounts": {"batter": len(existing_batters), "pitcher": len(existing_pitchers)},
        "addedRows": {"batter": added_batters, "pitcher": added_pitchers},
        "finalRowCounts": {"batter": len(final_batters), "pitcher": len(final_pitchers)},
        "datesPresent": {"batter": dates_present(final_batters), "pitcher": dates_present(final_pitchers)},
        "warnings": warnings,
    }


def run(
    *,
    start_date: str,
    end_date: str,
    season: int,
    dry_run: bool = False,
    season_log_dir: Path = WAREHOUSE_SEASON_LOG_DIR,
) -> dict[str, Any]:
    batter_path = season_log_dir / f"batter_game_logs_{season}.csv"
    pitcher_path = season_log_dir / f"pitcher_game_logs_{season}.csv"
    existing_batters = read_csv_rows(batter_path)
    existing_pitchers = read_csv_rows(pitcher_path)

    fetched_batters, fetched_pitchers, warnings = collect_logs(start_date, end_date, season)
    final_batters, added_batters = merge_rows(existing_batters, fetched_batters)
    final_pitchers, added_pitchers = merge_rows(existing_pitchers, fetched_pitchers)

    if not dry_run:
        write_csv_rows(batter_path, field_order(BATTER_FIELDS, existing_batters, fetched_batters), final_batters)
        write_csv_rows(pitcher_path, field_order(PITCHER_FIELDS, existing_pitchers, fetched_pitchers), final_pitchers)

    return build_summary(
        start_date=start_date,
        end_date=end_date,
        season=season,
        dry_run=dry_run,
        batter_path=batter_path,
        pitcher_path=pitcher_path,
        existing_batters=existing_batters,
        existing_pitchers=existing_pitchers,
        final_batters=final_batters,
        final_pitchers=final_pitchers,
        added_batters=added_batters,
        added_pitchers=added_pitchers,
        warnings=warnings,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = run(
        start_date=args.start_date,
        end_date=args.end_date,
        season=args.season,
        dry_run=args.dry_run,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
