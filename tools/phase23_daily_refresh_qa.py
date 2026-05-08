from __future__ import annotations

"""Phase 23 daily refresh QA report.

Operator-facing QA for the MLB daily data pipeline. This report consolidates the
most important checks from PropLine, game context, weather, Phase 19 movement,
OddsPapi Phase 22, fixture metadata fallback, and Playerboard.

It is intentionally read-only except for writing an audit JSON when --write is
provided. It does not fetch provider data and does not fabricate CLV, opening
lines, moneyline movement, totals, or implied runs.
"""

import argparse
import csv
import glob
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
AUDIT_DIR = DATA / "warehouse" / "audits"

CRITICAL_CONTEXT_FIELDS = [
    "team_moneyline",
    "opponent_moneyline",
    "game_total",
    "moneyline_implied_probability",
    "team_implied_runs",
    "opponent_implied_runs",
    "weather_temperature_f",
    "weather_wind_mph",
    "weather_humidity",
    "weather_wind_direction",
    "roof_status",
]

PHASE19_FIELDS = [
    "open_team_moneyline",
    "close_team_moneyline",
    "moneyline_move",
    "open_game_total",
    "close_game_total",
    "total_move",
    "line_movement_source",
    "line_movement_status",
]

PHASE22_FIELDS = [
    "oddspapi_fixture_id",
    "oddspapi_provider_status",
    "oddspapi_bookmakers",
]

PLAYERBOARD_CORE_FIELDS = [
    "player",
    "market",
    "team",
    "opponent",
    "americanOdds",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean(value: Any) -> str:
    return str(value or "").strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:  # noqa: BLE001 - operator QA should capture parse errors.
        return {"status": "warning", "error": f"Could not parse JSON: {error}", "path": str(path)}


def newest(pattern: str) -> Path | None:
    matches = sorted(
        glob.glob(pattern),
        key=lambda name: Path(name).stat().st_mtime if Path(name).exists() else 0,
        reverse=True,
    )
    return Path(matches[0]) if matches else None


def file_info(path: Path, *, required: bool = True) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "required": required,
            "status": "missing" if required else "optional_missing",
        }
    stat = path.stat()
    modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    return {
        "path": str(path),
        "exists": True,
        "required": required,
        "status": "ok",
        "sizeBytes": stat.st_size,
        "modifiedAt": modified.isoformat().replace("+00:00", "Z"),
    }


def coverage(rows: list[dict[str, Any]], fields: list[str]) -> list[dict[str, Any]]:
    total = len(rows)
    out: list[dict[str, Any]] = []
    for field in fields:
        present = sum(1 for row in rows if clean(row.get(field)))
        out.append({
            "field": field,
            "presentRows": present,
            "coverage": round(present / max(1, total), 4),
        })
    return out


def coverage_map(items: list[dict[str, Any]]) -> dict[str, float]:
    return {str(item.get("field")): float(item.get("coverage") or 0) for item in items}


def rows_for_date(rows: list[dict[str, str]], date_label: str) -> list[dict[str, str]]:
    return [row for row in rows if clean(row.get("date")) == date_label]


def check_artifacts(date_label: str, season: int) -> dict[str, Any]:
    propline_path = DATA / "odds" / f"propline_props_{date_label}.csv"
    context_path = DATA / "warehouse" / "game_context" / f"game_context_{date_label}.csv"
    markets_path = DATA / "warehouse" / "game_context" / f"game_context_markets_{date_label}.csv"
    playerboard_path = DATA / "playerboard" / f"playerboard_{season}.csv"
    phase22_audit_path = AUDIT_DIR / f"phase22_oddspapi_clv_{date_label}.json"
    phase22_fallback_audit_path = AUDIT_DIR / f"phase22_v3_fixture_metadata_fallback_{date_label}.json"
    phase21_daily_path = newest(str(AUDIT_DIR / f"phase21_daily_refresh_{date_label}_*.json"))

    files = {
        "proplineProps": file_info(propline_path),
        "gameContext": file_info(context_path),
        "gameContextMarkets": file_info(markets_path),
        "playerboard": file_info(playerboard_path),
        "phase22Audit": file_info(phase22_audit_path, required=False),
        "phase22FixtureFallbackAudit": file_info(phase22_fallback_audit_path, required=False),
        "phase21DailyRefresh": file_info(phase21_daily_path, required=False) if phase21_daily_path else {
            "path": str(AUDIT_DIR / f"phase21_daily_refresh_{date_label}_*.json"),
            "exists": False,
            "required": False,
            "status": "optional_missing",
        },
    }

    propline_rows = read_csv(propline_path)
    context_rows = read_csv(context_path)
    markets_rows = read_csv(markets_path)
    playerboard_rows = rows_for_date(read_csv(playerboard_path), date_label)

    context_cov = coverage(context_rows, CRITICAL_CONTEXT_FIELDS)
    phase19_cov = coverage(context_rows, PHASE19_FIELDS)
    phase22_cov = coverage(context_rows, PHASE22_FIELDS)
    playerboard_cov = coverage(playerboard_rows, PLAYERBOARD_CORE_FIELDS)

    context_cov_map = coverage_map(context_cov)
    phase19_cov_map = coverage_map(phase19_cov)
    phase22_cov_map = coverage_map(phase22_cov)
    playerboard_cov_map = coverage_map(playerboard_cov)

    phase22_audit = read_json(phase22_audit_path, {"status": "missing"})
    phase22_fallback_audit = read_json(phase22_fallback_audit_path, {"status": "missing"})
    phase21_daily = read_json(phase21_daily_path, {"status": "missing"}) if phase21_daily_path else {"status": "missing"}

    checks: list[dict[str, Any]] = []

    def add_check(name: str, status: str, **extra: Any) -> None:
        checks.append({"name": name, "status": status, **extra})

    add_check(
        "propline_props_present",
        "ok" if propline_rows else "warning",
        rows=len(propline_rows),
        path=str(propline_path),
    )
    add_check(
        "game_context_present",
        "ok" if context_rows else "warning",
        rows=len(context_rows),
        path=str(context_path),
    )
    add_check(
        "game_context_markets_present",
        "ok" if markets_rows else "warning",
        rows=len(markets_rows),
        path=str(markets_path),
    )
    add_check(
        "playerboard_current_date_rows",
        "ok" if playerboard_rows else "warning",
        rows=len(playerboard_rows),
        path=str(playerboard_path),
    )

    low_context = [field for field, pct in context_cov_map.items() if pct < 0.80]
    add_check(
        "critical_context_coverage_80pct",
        "ok" if not low_context else "warning",
        threshold=0.80,
        lowFields=low_context,
    )

    low_playerboard = [field for field, pct in playerboard_cov_map.items() if pct < 0.95]
    add_check(
        "playerboard_core_coverage_95pct",
        "ok" if not low_playerboard else "warning",
        threshold=0.95,
        lowFields=low_playerboard,
    )

    # Phase 19 movement can be pending early in a slate, but once context rows exist,
    # >= 80% coverage is the operator-safe target for normal same-day QA.
    low_movement = [field for field, pct in phase19_cov_map.items() if pct < 0.80]
    add_check(
        "phase19_movement_coverage_80pct",
        "ok" if context_rows and not low_movement else "warning",
        threshold=0.80,
        lowFields=low_movement,
    )

    phase22_status = clean(phase22_audit.get("status")) or "missing"
    add_check(
        "phase22_oddspapi_fetch_audit",
        "ok" if phase22_status in {"ok", "warning", "skipped"} else "warning",
        auditStatus=phase22_status,
        fixtureCount=phase22_audit.get("fixtureCount", 0),
        providerClvReadyRows=phase22_audit.get("providerClvReadyRows", 0),
        providerErrors=phase22_audit.get("providerErrors", []),
        note="warning/skipped is acceptable here because Phase 19 remains the movement source until true CLV is available.",
    )

    fixture_fallback_status = clean(phase22_fallback_audit.get("status")) or "missing"
    add_check(
        "phase22_fixture_metadata_fallback",
        "ok" if fixture_fallback_status == "ok" else "warning",
        auditStatus=fixture_fallback_status,
        fixtureCount=phase22_fallback_audit.get("fixtureCount", 0),
        contextRows=phase22_fallback_audit.get("contextRows", 0),
        matchedRows=phase22_fallback_audit.get("matchedRows", 0),
        unmatchedPairs=phase22_fallback_audit.get("unmatchedPairs", []),
    )

    low_fixture = [field for field, pct in phase22_cov_map.items() if pct < 0.80]
    add_check(
        "phase22_fixture_metadata_coverage_80pct",
        "ok" if context_rows and not low_fixture else "warning",
        threshold=0.80,
        lowFields=low_fixture,
    )

    collector_status = clean(phase21_daily.get("collector", {}).get("status")) if isinstance(phase21_daily, dict) else ""
    add_check(
        "phase21_collector_status",
        "ok" if collector_status in {"ok", "skipped"} else "warning",
        collectorStatus=collector_status or "missing",
    )

    warnings = [check for check in checks if check.get("status") != "ok"]
    return {
        "status": "ok" if not warnings else "warning",
        "phase": "23",
        "date": date_label,
        "season": season,
        "generatedAt": now_iso(),
        "files": files,
        "rowCounts": {
            "proplineProps": len(propline_rows),
            "gameContext": len(context_rows),
            "gameContextMarkets": len(markets_rows),
            "playerboardForDate": len(playerboard_rows),
        },
        "coverage": {
            "criticalContext": {"rows": len(context_rows), "fields": context_cov},
            "phase19Movement": {"rows": len(context_rows), "fields": phase19_cov},
            "phase22FixtureMetadata": {"rows": len(context_rows), "fields": phase22_cov},
            "playerboardCore": {"rows": len(playerboard_rows), "fields": playerboard_cov},
        },
        "providerAudits": {
            "phase22OddsPapiClv": {
                "path": str(phase22_audit_path),
                "status": phase22_status,
                "fixtureCount": phase22_audit.get("fixtureCount", 0),
                "matchedProviderRows": phase22_audit.get("matchedProviderRows", 0),
                "providerClvReadyRows": phase22_audit.get("providerClvReadyRows", 0),
                "providerErrors": phase22_audit.get("providerErrors", []),
            },
            "phase22FixtureMetadataFallback": {
                "path": str(phase22_fallback_audit_path),
                "status": fixture_fallback_status,
                "fixtureCount": phase22_fallback_audit.get("fixtureCount", 0),
                "fixtureIndexPairs": phase22_fallback_audit.get("fixtureIndexPairs", 0),
                "contextRows": phase22_fallback_audit.get("contextRows", 0),
                "matchedRows": phase22_fallback_audit.get("matchedRows", 0),
                "unmatchedPairs": phase22_fallback_audit.get("unmatchedPairs", []),
            },
        },
        "checks": checks,
        "warnings": warnings,
        "operatorSummary": {
            "readyForUi": not warnings,
            "movementSource": "phase19_observed_first_latest_snapshot",
            "fixtureMetadataSource": "oddspapi_fixture_metadata_fallback_when_clv_unavailable",
            "clvSource": "unavailable_unless_provider_audit_reports_providerClvReadyRows",
        },
        "notes": [
            "Phase 23 is read-only QA/reporting. It does not fetch provider data.",
            "Phase 22 fixture metadata is allowed to be ready while providerClvReadyRows remains 0.",
            "No CLV, opening lines, movement, totals, or implied runs are fabricated by this report.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Phase 23 daily refresh QA report.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    report = check_artifacts(args.date, args.season)
    if args.write:
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        path = AUDIT_DIR / f"phase23_daily_refresh_qa_{args.date}.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        report["outputPath"] = str(path)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
