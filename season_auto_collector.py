from __future__ import annotations
from local_env import load_local_env
load_local_env()
import os

"""Final autonomous 2024-2026 MLB data collector.

Runs:
- MLB StatsAPI sync
- PropLine sync
- Open-Meteo weather sync
- PropLine odds snapshots
- warehouse summaries
- batter game logs
- pitcher game logs
- team game logs
- duplicate-safe upserts
- timestamped run logs
- compact cloud export
- Savant/pybaseball only when --include-savant is used

Recommended schedule:
- 06:00 ET: current-day snapshot, no Savant
- 12:00 ET: current-day snapshot, no Savant
- 00:00 ET: previous-day final snapshot with Savant
"""

import argparse
import csv
import json
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
WAREHOUSE_DIR = DATA_DIR / "warehouse"
RAW_DIR = WAREHOUSE_DIR / "raw"
SUMMARY_DIR = WAREHOUSE_DIR / "summaries"
LOG_DIR = WAREHOUSE_DIR / "logs"
SEASON_LOG_DIR = WAREHOUSE_DIR / "season_logs"

CLOUD_DIR = DATA_DIR / "cloud"
CLOUD_SEASON_DIR = CLOUD_DIR / "season_logs"
CLOUD_SUMMARY_DIR = CLOUD_DIR / "summaries"

RUN_INDEX = SEASON_LOG_DIR / "collector_runs.csv"

SUPPORTED_YEARS = {2024, 2025, 2026}


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def resolve_date(date_text: str | None, offset: int) -> str:
    base = datetime.strptime(date_text, "%Y-%m-%d") if date_text else datetime.now()
    return (base + timedelta(days=offset)).strftime("%Y-%m-%d")


def validate_year(date_label: str) -> None:
    year = int(str(date_label)[:4])
    if year not in SUPPORTED_YEARS:
        raise ValueError("Active autonomous collection only supports 2024, 2025, and 2026.")


def ensure_dirs() -> None:
    for path in [
        WAREHOUSE_DIR,
        RAW_DIR,
        SUMMARY_DIR,
        LOG_DIR,
        SEASON_LOG_DIR,
        CLOUD_DIR,
        CLOUD_SEASON_DIR,
        CLOUD_SUMMARY_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def clean(value: Any) -> str:
    return str(value or "").strip()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def stat(stats: dict[str, Any], key: str) -> str:
    value = stats.get(key, "")
    return "" if value is None else str(value)


def team_code(team: dict[str, Any]) -> str:
    value = (
        team.get("abbreviation")
        or team.get("teamCode")
        or team.get("fileCode")
        or team.get("name")
        or ""
    )
    aliases = {
        "KC": "KCR",
        "SD": "SDP",
        "SF": "SFG",
        "TB": "TBR",
        "WSH": "WSN",
        "CWS": "CHW",
        "OAK": "ATH",
    }
    value = clean(value).upper()
    return aliases.get(value, value)


def append_or_upsert_csv(
    path: Path,
    key_fields: list[str],
    fieldnames: list[str],
    new_rows: list[dict[str, Any]],
) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[tuple[str, ...], dict[str, Any]] = {}

    if path.exists():
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                key = tuple(clean(row.get(field)) for field in key_fields)
                existing[key] = row

    for row in new_rows:
        normalized = {field: clean(row.get(field, "")) for field in fieldnames}
        key = tuple(clean(normalized.get(field)) for field in key_fields)
        existing[key] = normalized

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in existing.values():
            writer.writerow({field: row.get(field, "") for field in fieldnames})

    return len(new_rows)


def extract_logs_from_boxscores(date_label: str) -> dict[str, Any]:
    year = int(date_label[:4])
    boxscore_path = RAW_DIR / f"boxscores_{date_label}.json"
    boxscores = load_json(boxscore_path, {})

    batter_rows: list[dict[str, Any]] = []
    pitcher_rows: list[dict[str, Any]] = []
    team_rows: list[dict[str, Any]] = []

    for game_pk, boxscore in boxscores.items():
        teams = boxscore.get("teams", {})

        for side in ["away", "home"]:
            team_obj = teams.get(side, {})
            team = team_obj.get("team", {})
            team_abbr = team_code(team)
            team_name = clean(team.get("name"))
            players = team_obj.get("players", {})
            team_stats = team_obj.get("teamStats", {})
            batting_team_stats = team_stats.get("batting", {})
            pitching_team_stats = team_stats.get("pitching", {})

            team_rows.append({
                "date": date_label,
                "season": year,
                "gamePk": game_pk,
                "side": side,
                "team": team_abbr,
                "teamName": team_name,
                "runs": stat(batting_team_stats, "runs"),
                "hits": stat(batting_team_stats, "hits"),
                "homeRuns": stat(batting_team_stats, "homeRuns"),
                "strikeOuts": stat(batting_team_stats, "strikeOuts"),
                "baseOnBalls": stat(batting_team_stats, "baseOnBalls"),
                "atBats": stat(batting_team_stats, "atBats"),
                "totalBases": stat(batting_team_stats, "totalBases"),
                "leftOnBase": stat(batting_team_stats, "leftOnBase"),
                "pitchingRuns": stat(pitching_team_stats, "runs"),
                "pitchingHits": stat(pitching_team_stats, "hits"),
                "pitchingStrikeOuts": stat(pitching_team_stats, "strikeOuts"),
                "pitchingBaseOnBalls": stat(pitching_team_stats, "baseOnBalls"),
                "pitchingHomeRuns": stat(pitching_team_stats, "homeRuns"),
            })

            for player_key, player in players.items():
                person = player.get("person", {})
                player_id = clean(person.get("id")) or clean(player_key).replace("ID", "")
                player_name = clean(person.get("fullName"))
                jersey = clean(player.get("jerseyNumber"))
                position = clean(player.get("position", {}).get("abbreviation"))

                batting = player.get("stats", {}).get("batting", {})
                pitching = player.get("stats", {}).get("pitching", {})

                if batting:
                    batter_rows.append({
                        "date": date_label,
                        "season": year,
                        "gamePk": game_pk,
                        "side": side,
                        "team": team_abbr,
                        "playerId": player_id,
                        "player": player_name,
                        "jersey": jersey,
                        "position": position,
                        "plateAppearances": stat(batting, "plateAppearances"),
                        "atBats": stat(batting, "atBats"),
                        "runs": stat(batting, "runs"),
                        "hits": stat(batting, "hits"),
                        "doubles": stat(batting, "doubles"),
                        "triples": stat(batting, "triples"),
                        "homeRuns": stat(batting, "homeRuns"),
                        "rbi": stat(batting, "rbi"),
                        "baseOnBalls": stat(batting, "baseOnBalls"),
                        "strikeOuts": stat(batting, "strikeOuts"),
                        "stolenBases": stat(batting, "stolenBases"),
                        "totalBases": stat(batting, "totalBases"),
                        "leftOnBase": stat(batting, "leftOnBase"),
                    })

                if pitching:
                    pitcher_rows.append({
                        "date": date_label,
                        "season": year,
                        "gamePk": game_pk,
                        "side": side,
                        "team": team_abbr,
                        "playerId": player_id,
                        "player": player_name,
                        "jersey": jersey,
                        "position": position,
                        "inningsPitched": stat(pitching, "inningsPitched"),
                        "runs": stat(pitching, "runs"),
                        "earnedRuns": stat(pitching, "earnedRuns"),
                        "hits": stat(pitching, "hits"),
                        "homeRuns": stat(pitching, "homeRuns"),
                        "baseOnBalls": stat(pitching, "baseOnBalls"),
                        "strikeOuts": stat(pitching, "strikeOuts"),
                        "battersFaced": stat(pitching, "battersFaced"),
                        "pitchesThrown": stat(pitching, "pitchesThrown"),
                        "strikes": stat(pitching, "strikes"),
                        "wins": stat(pitching, "wins"),
                        "losses": stat(pitching, "losses"),
                        "saves": stat(pitching, "saves"),
                    })

    batter_fields = [
        "date", "season", "gamePk", "side", "team", "playerId", "player", "jersey", "position",
        "plateAppearances", "atBats", "runs", "hits", "doubles", "triples", "homeRuns",
        "rbi", "baseOnBalls", "strikeOuts", "stolenBases", "totalBases", "leftOnBase",
    ]

    pitcher_fields = [
        "date", "season", "gamePk", "side", "team", "playerId", "player", "jersey", "position",
        "inningsPitched", "runs", "earnedRuns", "hits", "homeRuns", "baseOnBalls",
        "strikeOuts", "battersFaced", "pitchesThrown", "strikes", "wins", "losses", "saves",
    ]

    team_fields = [
        "date", "season", "gamePk", "side", "team", "teamName", "runs", "hits",
        "homeRuns", "strikeOuts", "baseOnBalls", "atBats", "totalBases", "leftOnBase",
        "pitchingRuns", "pitchingHits", "pitchingStrikeOuts", "pitchingBaseOnBalls", "pitchingHomeRuns",
    ]

    batter_file = SEASON_LOG_DIR / f"batter_game_logs_{year}.csv"
    pitcher_file = SEASON_LOG_DIR / f"pitcher_game_logs_{year}.csv"
    team_file = SEASON_LOG_DIR / f"team_game_logs_{year}.csv"

    batter_upserted = append_or_upsert_csv(
        batter_file,
        ["gamePk", "playerId"],
        batter_fields,
        batter_rows,
    )

    pitcher_upserted = append_or_upsert_csv(
        pitcher_file,
        ["gamePk", "playerId"],
        pitcher_fields,
        pitcher_rows,
    )

    team_upserted = append_or_upsert_csv(
        team_file,
        ["gamePk", "team"],
        team_fields,
        team_rows,
    )

    return {
        "date": date_label,
        "boxscorePath": str(boxscore_path),
        "boxscoresRead": len(boxscores),
        "batterRowsUpserted": batter_upserted,
        "pitcherRowsUpserted": pitcher_upserted,
        "teamRowsUpserted": team_upserted,
        "batterLog": str(batter_file),
        "pitcherLog": str(pitcher_file),
        "teamLog": str(team_file),
    }


def copy_if_exists(source: Path, dest: Path) -> bool:
    if not source.exists():
        return False

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(source.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
    return True


def export_compact_cloud_data(date_label: str, summary: dict[str, Any]) -> dict[str, Any]:
    year = int(date_label[:4])
    exported = []

    for filename in [
        f"batter_game_logs_{year}.csv",
        f"pitcher_game_logs_{year}.csv",
        f"team_game_logs_{year}.csv",
        "collector_runs.csv",
    ]:
        source = SEASON_LOG_DIR / filename
        dest = CLOUD_SEASON_DIR / filename
        if copy_if_exists(source, dest):
            exported.append(str(dest))

    for filename in [
        f"daily_summary_{date_label}.json",
        f"games_{date_label}.json",
        f"weather_summary_{date_label}.json",
    ]:
        source = SUMMARY_DIR / filename
        dest = CLOUD_SUMMARY_DIR / filename
        if copy_if_exists(source, dest):
            exported.append(str(dest))

    latest_path = CLOUD_SUMMARY_DIR / "latest_collector_run.json"
    write_json(latest_path, summary)
    exported.append(str(latest_path))

    return {
        "cloudDir": str(CLOUD_DIR),
        "exportedCount": len(exported),
        "exportedFiles": exported,
    }


def sync_all_sources(date_label: str, include_savant: bool) -> dict[str, Any]:
    from data_warehouse_sync import sync_date
    from data_source_expansion import sync_all
    from unified_prop_context import build_batter_pitcher_samples

    validate_year(date_label)

    result: dict[str, Any] = {
        "external": None,
        "dataHub": None,
        "bvp": None,
        "logs": None,
    }

    result["external"] = sync_all(
        start_date=date_label,
        end_date=date_label,
        team="",
        skip_savant=not include_savant,
    )

    result["dataHub"] = sync_date(date_label)

    try:
        result["bvp"] = build_batter_pitcher_samples() if include_savant else {
            "skipped": True,
            "reason": "Savant/BvP runs only when --include-savant is used.",
        }
    except Exception as error:
        result["bvp"] = {
            "available": False,
            "error": str(error),
        }

    result["logs"] = extract_logs_from_boxscores(date_label)

    return result


def append_run_index(summary: dict[str, Any]) -> None:
    RUN_INDEX.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "runId", "date", "runType", "startedAt", "finishedAt", "success",
        "includeSavant", "propCount", "mlbGames", "finalGames", "boxscoresSaved",
        "batterRowsUpserted", "pitcherRowsUpserted", "teamRowsUpserted",
        "cloudExportedCount", "logPath",
    ]

    exists = RUN_INDEX.exists()

    with RUN_INDEX.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)

        if not exists:
            writer.writeheader()

        result = summary.get("result") or {}
        hub = result.get("dataHub") or {}
        logs = result.get("logs") or {}
        cloud = summary.get("cloudExport") or {}

        writer.writerow({
            "runId": summary.get("runId", ""),
            "date": summary.get("date", ""),
            "runType": summary.get("runType", ""),
            "startedAt": summary.get("startedAt", ""),
            "finishedAt": summary.get("finishedAt", ""),
            "success": summary.get("success", False),
            "includeSavant": summary.get("includeSavant", False),
            "propCount": hub.get("propCount", ""),
            "mlbGames": hub.get("mlbGames", ""),
            "finalGames": hub.get("finalGames", ""),
            "boxscoresSaved": hub.get("boxscoresSaved", ""),
            "batterRowsUpserted": logs.get("batterRowsUpserted", ""),
            "pitcherRowsUpserted": logs.get("pitcherRowsUpserted", ""),
            "teamRowsUpserted": logs.get("teamRowsUpserted", ""),
            "cloudExportedCount": cloud.get("exportedCount", ""),
            "logPath": summary.get("logPath", ""),
        })


def snapshot(date_label: str, run_type: str, include_savant: bool) -> dict[str, Any]:
    ensure_dirs()
    validate_year(date_label)

    run_id = now_stamp()
    started_at = now_iso()
    log_path = LOG_DIR / f"season_collector_{run_type}_{date_label}_{run_id}.json"

    summary: dict[str, Any] = {
        "runId": run_id,
        "date": date_label,
        "runType": run_type,
        "startedAt": started_at,
        "finishedAt": "",
        "success": False,
        "includeSavant": include_savant,
        "result": None,
        "cloudExport": None,
        "error": "",
        "traceback": "",
        "logPath": str(log_path),
    }

    try:
        summary["result"] = sync_all_sources(date_label, include_savant=include_savant)

        try:
            from weather_collector import collect_and_build

            try:


                if os.environ.get("SKIP_WEATHER_FEATURES", "").strip().lower() in {"1", "true", "yes"}:
                    summary["weatherFeatures"] = {
                        "success": False,
                        "skipped": True,
                        "reason": "SKIP_WEATHER_FEATURES enabled",
                    }
                else:
                    try:
                        summary["weatherFeatures"] = collect_and_build(
                        season=int(date_label[:4]),
                        phase="regular",
                        force=False,
                        )
                    except BaseException as error:
                        summary["weatherFeatures"] = {
                            "success": False,
                            "skipped": True,
                            "reason": "Weather feature collection failed but collector will continue",
                            "error": str(error),
                        }


            except Exception as error:


                summary["weatherFeatures"] = {


                    "success": False,


                    "skipped": True,


                    "reason": "Weather feature collection failed but collector will continue",


                    "error": str(error),


                }
        except Exception as weather_error:
            summary["weatherFeatures"] = {"error": str(weather_error)}

        # Daily incremental stats warehouse:
        # - Runs only on true midnight/full-final snapshots.
        # - Skipped for grading/manual runs so daily grading stays date-only and fast.
        # - Safely upserts, so reruns do not create duplicates.
        # - Pulls only missing/new final games unless force is used manually.
        if run_type == "midnight":
            try:
                from incremental_stats_collector import catchup_stats

                season = int(date_label[:4])
                summary["incrementalStats"] = catchup_stats(
                    season=season,
                    start_date=f"{season}-03-01",
                    end_date=date_label,
                    force=False,
                    season_phase="regular",
                )
            except Exception as stats_error:
                summary["incrementalStats"] = {
                    "error": str(stats_error),
                }

        if include_savant:
            try:
                from savant_features import sync_savant

                # Savant is heavier than MLB StatsAPI/PropLine.
                # Run only when the collector is explicitly told to include it.
                summary["savantFeatures"] = sync_savant(
                    season=int(date_label[:4]),
                    start_date=f"{int(date_label[:4])}-03-25",
                    end_date=date_label,
                    force=False,
                )
            except Exception as savant_error:
                summary["savantFeatures"] = {"error": str(savant_error)}
        else:
            summary["savantFeatures"] = {
                "skipped": True,
                "reason": "Savant runs only when --include-savant is used.",
            }

        try:
            from odds_movement import snapshot_and_build

            summary["oddsMovement"] = snapshot_and_build(
                date_label=date_label,
                market="",
                season=int(date_label[:4]),
            )
        except Exception as odds_error:
            summary["oddsMovement"] = {"error": str(odds_error)}

        try:
            from mlb_app.services.playerboard_builder import build_playerboard

            # Automatically save the full ranked board for ML/backtesting.
            # This does not clutter prediction_history; it writes to data/playerboard.
            summary["playerboard"] = build_playerboard(
                season=int(date_label[:4]),
                date_label=date_label,
                market="",
                limit=5000,
                save=True,
            )
        except Exception as board_error:
            summary["playerboard"] = {"error": str(board_error)}


        # Phase 18 provider-backed context collector hook
        try:
            import subprocess
            import sys

            context_markets = [
                market.strip()
                for market in os.environ.get("PHASE18_MARKETS", "batter_hits,batter_total_bases").split(",")
                if market.strip()
            ]
            context_cmd = [
                sys.executable,
                str(ROOT / "tools" / "phase18_fill_missing_context.py"),
                "--date",
                date_label,
                "--season",
                str(int(date_label[:4])),
                "--line-source",
                os.environ.get("PHASE18_LINE_SOURCE", "propline"),
                "--markets",
                *context_markets,
            ]
            context_run = subprocess.run(
                context_cmd,
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=int(os.environ.get("PHASE18_COLLECTOR_TIMEOUT_SECONDS", "600")),
                check=False,
            )
            summary["phase18ProviderContext"] = {
                "status": "ok" if context_run.returncode == 0 else "warning",
                "returncode": context_run.returncode,
                "stdoutTail": context_run.stdout[-4000:],
                "stderrTail": context_run.stderr[-4000:],
            }
        except Exception as context_error:
            summary["phase18ProviderContext"] = {"error": str(context_error)}

        try:
            from playerboard_backtest import grade_playerboard

            summary["playerboardBacktest"] = grade_playerboard(
                season=int(date_label[:4]),
            )
        except Exception as backtest_error:
            summary["playerboardBacktest"] = {"error": str(backtest_error)}

        try:
            from model_audit import audit_model_math

            summary["modelAudit"] = audit_model_math(
                season=int(date_label[:4]),
            )
        except Exception as audit_error:
            summary["modelAudit"] = {"error": str(audit_error)}

        try:
            from ml_export import export_playerboard_training

            summary["mlExport"] = export_playerboard_training(
                season=int(date_label[:4]),
            )
        except Exception as ml_error:
            summary["mlExport"] = {"error": str(ml_error)}

        try:
            from prediction_history import grade_predictions

            summary["predictionGrades"] = grade_predictions(season=int(date_label[:4]))
        except Exception as grade_error:
            summary["predictionGrades"] = {"error": str(grade_error)}


        # PHASE19_LINE_MOVEMENT_HOOK_START
        try:
            from tools.phase19_line_movement import run_phase19

            summary["phase19LineMovement"] = run_phase19(
                date_label=date_label,
                season=int(date_label[:4]),
                source="season_auto_collector",
                patch_playerboard=False,
            )
        except Exception as line_movement_error:
            summary["phase19LineMovement"] = {
                "error": str(line_movement_error),
                "status": "warning",
            }
        # PHASE19_LINE_MOVEMENT_HOOK_END

        # PHASE22_ODDSPAPI_CLV_HOOK_START
        try:
            from tools.phase22_oddspapi_clv import run_phase22

            summary["phase22OddsPapiClv"] = run_phase22(
                date_label=date_label,
                season=int(date_label[:4]),
                apply=True,
            )
        except Exception as oddspapi_clv_error:
            summary["phase22OddsPapiClv"] = {
                "error": str(oddspapi_clv_error),
                "status": "warning",
            }
        # PHASE22_ODDSPAPI_CLV_HOOK_END

        # PHASE22_V3_FIXTURE_METADATA_FALLBACK_HOOK_START
        try:
            if os.environ.get("PHASE22_SKIP_FIXTURE_METADATA_FALLBACK", "").strip().lower() in {"1", "true", "yes"}:
                summary["phase22FixtureMetadataFallback"] = {
                    "status": "skipped",
                    "reason": "PHASE22_SKIP_FIXTURE_METADATA_FALLBACK enabled",
                }
            else:
                from tools.phase22_v3_fixture_metadata_fallback import apply_fixture_metadata

                summary["phase22FixtureMetadataFallback"] = apply_fixture_metadata(
                    date=date_label,
                    season=int(date_label[:4]),
                    dry_run=False,
                )
        except FileNotFoundError as fixture_metadata_missing:
            summary["phase22FixtureMetadataFallback"] = {
                "status": "skipped",
                "reason": str(fixture_metadata_missing),
            }
        except Exception as fixture_metadata_error:
            summary["phase22FixtureMetadataFallback"] = {
                "status": "warning",
                "error": str(fixture_metadata_error),
            }
        # PHASE22_V3_FIXTURE_METADATA_FALLBACK_HOOK_END


        summary["cloudExport"] = export_compact_cloud_data(date_label, summary)
        summary["success"] = True
    except Exception as error:
        summary["error"] = str(error)
        summary["traceback"] = traceback.format_exc()

    summary["finishedAt"] = now_iso()

    write_json(log_path, summary)
    append_run_index(summary)

    return summary


def status() -> dict[str, Any]:
    ensure_dirs()

    latest_runs = []

    if RUN_INDEX.exists():
        with RUN_INDEX.open("r", encoding="utf-8-sig", newline="") as handle:
            latest_runs = list(csv.DictReader(handle))[-15:]

    season_files = {
        "batter": sorted(str(path) for path in SEASON_LOG_DIR.glob("batter_game_logs_*.csv")),
        "pitcher": sorted(str(path) for path in SEASON_LOG_DIR.glob("pitcher_game_logs_*.csv")),
        "team": sorted(str(path) for path in SEASON_LOG_DIR.glob("team_game_logs_*.csv")),
    }

    cloud_files = {
        "seasonLogs": sorted(str(path) for path in CLOUD_SEASON_DIR.glob("*")),
        "summaries": sorted(str(path) for path in CLOUD_SUMMARY_DIR.glob("*")),
    }

    return {
        "warehouse": str(WAREHOUSE_DIR),
        "seasonLogDir": str(SEASON_LOG_DIR),
        "cloudDir": str(CLOUD_DIR),
        "runIndex": str(RUN_INDEX),
        "latestRuns": latest_runs,
        "seasonFiles": season_files,
        "cloudFiles": cloud_files,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Final autonomous MLB data collector.")
    sub = parser.add_subparsers(dest="command", required=True)

    snap = sub.add_parser("snapshot")
    snap.add_argument("--date", default="")
    snap.add_argument("--date-offset", type=int, default=0)
    snap.add_argument("--run-type", default="manual", choices=["morning", "midday", "midnight", "manual", "grading"])
    snap.add_argument("--include-savant", action="store_true")

    sub.add_parser("status")

    args = parser.parse_args()

    if args.command == "snapshot":
        date_label = resolve_date(args.date or None, args.date_offset)
        print(json.dumps(
            snapshot(date_label, args.run_type, include_savant=args.include_savant),
            indent=2,
            ensure_ascii=False,
        ))
    elif args.command == "status":
        print(json.dumps(status(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
