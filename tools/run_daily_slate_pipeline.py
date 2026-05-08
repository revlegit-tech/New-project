from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass
class StepResult:
    name: str
    command: list[str]
    required: bool
    ok: bool
    returncode: int = 0
    durationSeconds: float = 0.0
    stdoutTail: str = ""
    stderrTail: str = ""
    parsedJson: dict[str, Any] | list[Any] | None = None
    skipped: bool = False
    reason: str = ""


@dataclass
class PipelineResult:
    status: str
    ok: bool
    date: str
    season: int
    generatedAt: str
    steps: list[StepResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    dataHealth: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)
    outputPath: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["steps"] = [asdict(step) for step in self.steps]
        return payload


def _tail(text: str, limit: int = 4000) -> str:
    text = text or ""
    return text[-limit:]


def _parse_json_from_stdout(stdout: str) -> dict[str, Any] | list[Any] | None:
    text = (stdout or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Many legacy scripts emit progress lines before a final JSON object. Parse the last object/array.
    candidates = [idx for idx in (text.rfind("\n{"), text.rfind("\n["), text.find("{"), text.find("[")) if idx >= 0]
    for idx in sorted(set(candidates), reverse=True):
        candidate = text[idx:].strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _run_step(name: str, command: list[str], *, required: bool, timeout: int, dry_run: bool) -> StepResult:
    if dry_run:
        return StepResult(name=name, command=command, required=required, ok=True, skipped=True, reason="dry-run")
    started = datetime.now(timezone.utc)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    try:
        proc = subprocess.run(
            command,
            cwd=str(ROOT),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        duration = (datetime.now(timezone.utc) - started).total_seconds()
        return StepResult(
            name=name,
            command=command,
            required=required,
            ok=proc.returncode == 0,
            returncode=proc.returncode,
            durationSeconds=round(duration, 3),
            stdoutTail=_tail(proc.stdout),
            stderrTail=_tail(proc.stderr),
            parsedJson=_parse_json_from_stdout(proc.stdout),
        )
    except subprocess.TimeoutExpired as error:
        duration = (datetime.now(timezone.utc) - started).total_seconds()
        return StepResult(
            name=name,
            command=command,
            required=required,
            ok=False,
            returncode=124,
            durationSeconds=round(duration, 3),
            stdoutTail=_tail(error.stdout or ""),
            stderrTail=f"Timed out after {timeout}s\n{_tail(error.stderr or '')}",
        )


def _python_script(script: str, *args: str) -> list[str]:
    return [sys.executable, str(ROOT / script), *args]


def _health_payload(date_label: str, season: int) -> dict[str, Any]:
    from mlb_app.services.data_health_dashboard_service import DataHealthDashboardService

    try:
        return DataHealthDashboardService().payload({"date": [date_label], "season": [str(season)]})
    except Exception as error:  # keep pipeline reporting honest instead of hiding status
        return {"status": "error", "ok": False, "warnings": [f"Data health dashboard failed: {error}"]}


def _validate_payload(date_label: str, season: int) -> dict[str, Any]:
    from tools.validate_daily_slate import validate_slate

    try:
        return validate_slate(date_label, season)
    except Exception as error:
        return {"status": "error", "ok": False, "warnings": [f"Slate validator failed: {error}"]}


def run_pipeline(args: argparse.Namespace) -> PipelineResult:
    date_label = args.date or datetime.now().strftime("%Y-%m-%d")
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    result = PipelineResult(
        status="ok",
        ok=True,
        date=date_label,
        season=args.season,
        generatedAt=generated_at,
    )

    if not args.skip_schedule:
        result.steps.append(
            _run_step(
                "schedule_snapshot",
                _python_script("season_auto_collector.py", "snapshot", "--date", date_label, "--run-type", args.run_type),
                required=False,
                timeout=args.schedule_timeout_seconds,
                dry_run=args.dry_run,
            )
        )

    if not args.skip_weather:
        weather_cmd = _python_script("weather_collector.py", "sync", "--season", str(args.season), "--phase", args.season_phase)
        if args.force_weather:
            weather_cmd.append("--force")
        result.steps.append(
            _run_step(
                "weather_sync",
                weather_cmd,
                required=False,
                timeout=args.weather_timeout_seconds,
                dry_run=args.dry_run,
            )
        )

    if args.include_stats_catchup:
        start_date = args.stats_start_date or (datetime.strptime(date_label, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
        end_date = args.stats_end_date or (datetime.strptime(date_label, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        stats_cmd = _python_script(
            "incremental_stats_collector.py",
            "catchup",
            "--season",
            str(args.season),
            "--start-date",
            start_date,
            "--end-date",
            end_date,
            "--season-phase",
            args.season_phase,
        )
        if args.force_stats:
            stats_cmd.append("--force")
        if args.max_stats_dates:
            stats_cmd.extend(["--max-dates", str(args.max_stats_dates)])
        result.steps.append(
            _run_step(
                "stats_catchup",
                stats_cmd,
                required=False,
                timeout=args.stats_timeout_seconds,
                dry_run=args.dry_run,
            )
        )

    if not args.skip_odds_movement:
        result.steps.append(
            _run_step(
                "odds_movement_sync",
                _python_script("odds_movement.py", "sync", "--season", str(args.season), "--date", date_label),
                required=False,
                timeout=args.odds_timeout_seconds,
                dry_run=args.dry_run,
            )
        )

    refresh_cmd = _python_script(
        "tools/refresh_outlier_slate.py",
        "--date",
        date_label,
        "--season",
        str(args.season),
        "--limit",
        str(args.limit),
        "--source-mode",
        args.source_mode,
    )
    if args.max_events:
        refresh_cmd.extend(["--max-events", str(args.max_events)])
    if args.skip_fetch:
        refresh_cmd.append("--skip-fetch")
    if args.market:
        refresh_cmd.extend(["--market", args.market])
    result.steps.append(
        _run_step(
            "propline_and_playerboard_refresh",
            refresh_cmd,
            required=True,
            timeout=args.refresh_timeout_seconds,
            dry_run=args.dry_run,
        )
    )

    if args.include_grading:
        result.steps.append(
            _run_step(
                "propline_grading",
                _python_script("grade_propline_props.py", "--date", date_label),
                required=False,
                timeout=args.grading_timeout_seconds,
                dry_run=args.dry_run,
            )
        )

    result.dataHealth = {} if args.dry_run else _health_payload(date_label, args.season)
    result.validation = {} if args.dry_run else _validate_payload(date_label, args.season)

    failed_required = [step for step in result.steps if step.required and not step.ok]
    failed_optional = [step for step in result.steps if not step.required and not step.ok]
    if failed_required:
        result.status = "failed"
        result.ok = False
        result.warnings.extend(f"Required step failed: {step.name}" for step in failed_required)
    elif failed_optional:
        result.status = "partial"
        result.ok = True
        result.warnings.extend(f"Optional enrichment step failed: {step.name}" for step in failed_optional)

    for source in (result.dataHealth, result.validation):
        for warning in source.get("warnings", []) if isinstance(source, dict) else []:
            if warning not in result.warnings:
                result.warnings.append(str(warning))

    if args.strict:
        validation_ok = bool(result.validation.get("ok", False)) if isinstance(result.validation, dict) else False
        health_ok = bool(result.dataHealth.get("ok", False)) if isinstance(result.dataHealth, dict) else False
        if not validation_ok or not health_ok:
            result.ok = False
            result.status = "failed"
            if not validation_ok:
                result.warnings.append("Strict mode failed: slate validation is not ok.")
            if not health_ok:
                result.warnings.append("Strict mode failed: data health is not ok.")

    out_dir = ROOT / "data" / "health" / "pipeline_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"daily_slate_{date_label}.json"
    result.outputPath = str(out_path)
    if not args.dry_run:
        out_path.write_text(json.dumps(result.as_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the production daily slate refresh pipeline for the Outlier UI.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="Slate date, e.g. 2026-05-07")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--market", default="", help="Optional market-only rebuild.")
    parser.add_argument("--source-mode", choices=["auto", "canonical", "legacy"], default="canonical")
    parser.add_argument("--max-events", type=int, default=0, help="Optional PropLine event cap. 0 means all events.")
    parser.add_argument("--skip-fetch", action="store_true", help="Use existing PropLine CSV and only rebuild board.")
    parser.add_argument("--skip-schedule", action="store_true")
    parser.add_argument("--skip-weather", action="store_true")
    parser.add_argument("--skip-odds-movement", action="store_true")
    parser.add_argument("--include-stats-catchup", action="store_true")
    parser.add_argument("--include-grading", action="store_true")
    parser.add_argument("--run-type", default="manual", choices=["morning", "midday", "midnight", "manual", "grading"])
    parser.add_argument("--season-phase", default="regular", choices=["regular", "practice", "all"])
    parser.add_argument("--stats-start-date", default="")
    parser.add_argument("--stats-end-date", default="")
    parser.add_argument("--force-stats", action="store_true")
    parser.add_argument("--force-weather", action="store_true")
    parser.add_argument("--max-stats-dates", type=int, default=0)
    parser.add_argument("--schedule-timeout-seconds", type=int, default=240)
    parser.add_argument("--weather-timeout-seconds", type=int, default=300)
    parser.add_argument("--odds-timeout-seconds", type=int, default=180)
    parser.add_argument("--stats-timeout-seconds", type=int, default=900)
    parser.add_argument("--refresh-timeout-seconds", type=int, default=900)
    parser.add_argument("--grading-timeout-seconds", type=int, default=300)
    parser.add_argument("--strict", action="store_true", help="Return non-zero when post-run validation/data health is not OK.")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = run_pipeline(args)
    print(json.dumps(result.as_dict(), indent=2, ensure_ascii=False))
    raise SystemExit(0 if result.ok else 1)


if __name__ == "__main__":
    main()
