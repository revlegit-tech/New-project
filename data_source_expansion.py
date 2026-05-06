from __future__ import annotations

"""Expanded free-data source sync for Baseball Prop Predictor.

Adds:
- pybaseball / Baseball Savant Statcast summaries
- Chadwick Register player ID crosswalk
- Retrosheet/Lahman status hooks and folders

This is intentionally cache-first. It stores local files and summaries so the
app can later use them in the All Data Prop Predictor without repeated manual CSV uploads.
"""

import argparse
import csv
import gzip
import io
import json
import urllib.request
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
WAREHOUSE_DIR = ROOT / "data" / "warehouse"
EXTERNAL_DIR = WAREHOUSE_DIR / "external"
SAVANT_DIR = EXTERNAL_DIR / "savant"
CHADWICK_DIR = EXTERNAL_DIR / "chadwick"
RETROSHEET_DIR = EXTERNAL_DIR / "retrosheet"
LAHMAN_DIR = EXTERNAL_DIR / "lahman"
SUMMARY_DIR = WAREHOUSE_DIR / "summaries"

CHADWICK_PEOPLE_URLS = [
    f"https://raw.githubusercontent.com/chadwickbureau/register/master/data/people-{suffix}.csv"
    for suffix in "0123456789abcdef"
]

RETROSHEET_DOWNLOAD_PAGE = "https://www.retrosheet.org/downloads/csvdownloads.html"
LAHMAN_INFO_PAGE = "https://sabr.org/lahman-database/"


def ensure_dirs() -> None:
    for path in [EXTERNAL_DIR, SAVANT_DIR, CHADWICK_DIR, RETROSHEET_DIR, LAHMAN_DIR, SUMMARY_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def read_csv_text_url(url: str, timeout: int = 60) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "baseball-prop-predictor"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8-sig", errors="replace")


def sync_chadwick_register(limit_rows: int = 0) -> dict[str, Any]:
    """Download Chadwick people CSV shards and build a compact MLBAM crosswalk."""
    ensure_dirs()

    rows_written = 0
    files_saved = []
    crosswalk_path = CHADWICK_DIR / "mlbam_crosswalk.csv"

    with crosswalk_path.open("w", encoding="utf-8", newline="") as out_handle:
        fieldnames = [
            "name_first",
            "name_last",
            "name_given",
            "key_mlbam",
            "key_retro",
            "key_bbref",
            "key_fangraphs",
            "key_uuid",
        ]
        writer = csv.DictWriter(out_handle, fieldnames=fieldnames)
        writer.writeheader()

        for url in CHADWICK_PEOPLE_URLS:
            filename = url.rsplit("/", 1)[-1]
            raw = read_csv_text_url(url)
            file_path = CHADWICK_DIR / filename
            file_path.write_text(raw, encoding="utf-8")
            files_saved.append(str(file_path))

            reader = csv.DictReader(io.StringIO(raw))
            for row in reader:
                if not str(row.get("key_mlbam", "")).strip():
                    continue

                writer.writerow({
                    "name_first": row.get("name_first", ""),
                    "name_last": row.get("name_last", ""),
                    "name_given": row.get("name_given", ""),
                    "key_mlbam": row.get("key_mlbam", ""),
                    "key_retro": row.get("key_retro", ""),
                    "key_bbref": row.get("key_bbref", ""),
                    "key_fangraphs": row.get("key_fangraphs", ""),
                    "key_uuid": row.get("key_uuid", ""),
                })
                rows_written += 1

                if limit_rows and rows_written >= limit_rows:
                    break

            if limit_rows and rows_written >= limit_rows:
                break

    summary = {
        "source": "chadwick_register",
        "filesSaved": len(files_saved),
        "crosswalkRows": rows_written,
        "crosswalkPath": str(crosswalk_path),
        "updatedAt": datetime.utcnow().isoformat() + "Z",
    }

    write_json(SUMMARY_DIR / "chadwick_status.json", summary)
    return summary


def sync_savant_statcast(start_date: str, end_date: str, team: str = "") -> dict[str, Any]:
    """Use pybaseball Statcast data for advanced batted-ball/pitch quality.

    Saves raw pitch-level CSV plus compact batter/pitcher summaries.
    """
    ensure_dirs()

    try:
        import pandas as pd
        from pybaseball import cache, statcast
    except ImportError as error:
        return {
            "source": "pybaseball_savant",
            "available": False,
            "error": "Missing dependency. Run: python -m pip install pybaseball pandas",
        }

    try:
        cache.enable()
    except Exception:
        pass

    df = statcast(start_dt=start_date, end_dt=end_date, team=team or None)

    raw_path = SAVANT_DIR / f"statcast_{start_date}_{end_date}{'_' + team if team else ''}.csv"
    df.to_csv(raw_path, index=False)

    batter_summary_path = SAVANT_DIR / f"batter_quality_{start_date}_{end_date}{'_' + team if team else ''}.csv"
    pitcher_summary_path = SAVANT_DIR / f"pitcher_quality_{start_date}_{end_date}{'_' + team if team else ''}.csv"

    summary: dict[str, Any] = {
        "source": "pybaseball_savant",
        "available": True,
        "startDate": start_date,
        "endDate": end_date,
        "team": team,
        "rows": int(len(df)),
        "rawPath": str(raw_path),
        "batterSummaryPath": str(batter_summary_path),
        "pitcherSummaryPath": str(pitcher_summary_path),
        "updatedAt": datetime.utcnow().isoformat() + "Z",
    }

    if len(df) == 0:
        write_json(SUMMARY_DIR / "savant_status.json", summary)
        return summary

    # Normalize optional columns.
    for col in ["launch_speed", "launch_angle", "estimated_woba_using_speedangle", "estimated_ba_using_speedangle", "estimated_slg_using_speedangle"]:
        if col not in df.columns:
            df[col] = None

    if "events" not in df.columns:
        df["events"] = ""

    if "description" not in df.columns:
        df["description"] = ""

    if "player_name" not in df.columns:
        df["player_name"] = ""

    # Batter quality.
    batter_rows = []
    grouped = df.groupby(["batter"], dropna=True)
    for batter_id, group in grouped:
        batted = group[group["launch_speed"].notna()]
        hard_hit = batted[batted["launch_speed"] >= 95] if len(batted) else batted
        barrels = group[group["events"].astype(str).str.contains("home_run|double|triple", case=False, na=False)]

        batter_rows.append({
            "batter_id": batter_id,
            "pitches": len(group),
            "batted_balls": len(batted),
            "avg_ev": round(float(batted["launch_speed"].mean()), 3) if len(batted) else "",
            "avg_launch_angle": round(float(batted["launch_angle"].mean()), 3) if len(batted) else "",
            "hard_hit_rate": round(len(hard_hit) / len(batted), 4) if len(batted) else "",
            "extra_base_event_rate": round(len(barrels) / len(group), 4) if len(group) else "",
            "xwoba": round(float(group["estimated_woba_using_speedangle"].dropna().mean()), 4) if group["estimated_woba_using_speedangle"].notna().any() else "",
            "xba": round(float(group["estimated_ba_using_speedangle"].dropna().mean()), 4) if group["estimated_ba_using_speedangle"].notna().any() else "",
            "xslg": round(float(group["estimated_slg_using_speedangle"].dropna().mean()), 4) if group["estimated_slg_using_speedangle"].notna().any() else "",
        })

    with batter_summary_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = ["batter_id", "pitches", "batted_balls", "avg_ev", "avg_launch_angle", "hard_hit_rate", "extra_base_event_rate", "xwoba", "xba", "xslg"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(batter_rows)

    # Pitcher quality.
    pitcher_rows = []
    grouped_pitchers = df.groupby(["pitcher"], dropna=True)
    for pitcher_id, group in grouped_pitchers:
        swinging = group[group["description"].astype(str).str.contains("swinging_strike|swinging_strike_blocked", case=False, na=False)]
        called_or_swing_k = group[group["events"].astype(str).str.contains("strikeout", case=False, na=False)]
        batted = group[group["launch_speed"].notna()]

        pitcher_rows.append({
            "pitcher_id": pitcher_id,
            "pitches": len(group),
            "whiff_rate_proxy": round(len(swinging) / len(group), 4) if len(group) else "",
            "strikeout_event_rate": round(len(called_or_swing_k) / len(group), 4) if len(group) else "",
            "avg_ev_allowed": round(float(batted["launch_speed"].mean()), 3) if len(batted) else "",
            "hard_hit_allowed_rate": round(len(batted[batted["launch_speed"] >= 95]) / len(batted), 4) if len(batted) else "",
        })

    with pitcher_summary_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = ["pitcher_id", "pitches", "whiff_rate_proxy", "strikeout_event_rate", "avg_ev_allowed", "hard_hit_allowed_rate"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(pitcher_rows)

    summary["batterSummaryRows"] = len(batter_rows)
    summary["pitcherSummaryRows"] = len(pitcher_rows)

    write_json(SUMMARY_DIR / "savant_status.json", summary)
    return summary


def historical_sources_status() -> dict[str, Any]:
    """Register Retrosheet/Lahman folders and document next steps.

    We do not auto-download huge historical archives by default because Retrosheet
    play-by-play is very large. This hook keeps the UI aware and ready.
    """
    ensure_dirs()

    payload = {
        "retrosheet": {
            "enabled": False,
            "folder": str(RETROSHEET_DIR),
            "infoPage": RETROSHEET_DOWNLOAD_PAGE,
            "note": "Historical CSV/play-by-play source. Use later for backtesting; not auto-downloaded by default because files are large.",
        },
        "lahman": {
            "enabled": False,
            "folder": str(LAHMAN_DIR),
            "infoPage": LAHMAN_INFO_PAGE,
            "note": "Historical season-level database. Use later for baselines and long-term priors.",
        },
        "updatedAt": datetime.utcnow().isoformat() + "Z",
    }

    write_json(SUMMARY_DIR / "historical_sources_status.json", payload)
    return payload


def status() -> dict[str, Any]:
    ensure_dirs()

    def load(name: str) -> dict[str, Any]:
        path = SUMMARY_DIR / name
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    return {
        "savant": load("savant_status.json"),
        "chadwick": load("chadwick_status.json"),
        "historical": load("historical_sources_status.json"),
    }


def sync_all(
    start_date: str,
    end_date: str,
    team: str = "",
    skip_savant: bool = False,
    include_chadwick: bool = False,
    include_historical: bool = False,
) -> dict[str, Any]:
    ensure_dirs()

    result = {
        "savant": None,
        "chadwick": None,
        "historical": None,
    }

    if skip_savant:
        result["savant"] = {"skipped": True, "reason": "skip_savant requested"}
    else:
        result["savant"] = sync_savant_statcast(start_date, end_date, team)

    # Chadwick is useful for ID crosswalks, but it downloads 16 CSV shards.
    # Do not run it during normal scheduled collectors.
    if include_chadwick:
        result["chadwick"] = sync_chadwick_register()
    else:
        result["chadwick"] = {
            "skipped": True,
            "reason": "include_chadwick not requested",
        }

    if include_historical:
        result["historical"] = historical_sources_status()
    else:
        result["historical"] = {
            "skipped": True,
            "reason": "include_historical not requested",
        }

    write_json(SUMMARY_DIR / "external_sources_status.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync expanded free data sources.")
    sub = parser.add_subparsers(dest="command", required=True)

    savant = sub.add_parser("savant")
    savant.add_argument("--start-date", required=True)
    savant.add_argument("--end-date", required=True)
    savant.add_argument("--team", default="")

    sub.add_parser("chadwick")
    sub.add_parser("historical-status")
    sub.add_parser("status")

    sync = sub.add_parser("sync-all")
    sync.add_argument("--start-date", required=True)
    sync.add_argument("--end-date", required=True)
    sync.add_argument("--team", default="")
    sync.add_argument("--skip-savant", action="store_true")
    sync.add_argument("--include-chadwick", action="store_true")
    sync.add_argument("--include-historical", action="store_true")

    args = parser.parse_args()

    if args.command == "savant":
        print(json.dumps(sync_savant_statcast(args.start_date, args.end_date, args.team), indent=2))
    elif args.command == "chadwick":
        print(json.dumps(sync_chadwick_register(), indent=2))
    elif args.command == "historical-status":
        print(json.dumps(historical_sources_status(), indent=2))
    elif args.command == "status":
        print(json.dumps(status(), indent=2))
    elif args.command == "sync-all":
        print(json.dumps(
            sync_all(
                args.start_date,
                args.end_date,
                args.team,
                args.skip_savant,
                include_chadwick=args.include_chadwick,
                include_historical=args.include_historical,
            ),
            indent=2,
        ))


if __name__ == "__main__":
    main()
