from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from mlb_app.config import Settings, settings as default_settings
from mlb_app.repositories.data_health_repository import DataHealthRepository
from mlb_app.repositories.warehouse_db import WarehouseDatabase
from mlb_app.services.collector_manifest_service import CollectorManifestService

DEFAULT_STALE_AFTER_SECONDS = 36 * 60 * 60
MAX_ROW_COUNT_BYTES = 20 * 1024 * 1024
MAX_JSON_COUNT_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class SourceSpec:
    key: str
    relative_path: str
    patterns: tuple[str, ...]
    critical: bool = True
    count_rows: bool = True
    count_markets: bool = False


SOURCE_SPECS: tuple[SourceSpec, ...] = (
    SourceSpec("odds", "odds", ("propline_props_*.csv", "*.csv", "*.json"), count_markets=True),
    SourceSpec("warehouse_odds_snapshots", "warehouse/odds_snapshots", ("*.csv", "*.json"), count_markets=True),
    SourceSpec("warehouse_raw", "warehouse/raw", ("*.json", "*.csv"), count_rows=False),
    SourceSpec("playerboard", "playerboard", ("playerboard_*.csv", "*.csv"), count_markets=True),
    SourceSpec("edge_board", "edge_board", ("*.csv", "*.json"), critical=False, count_markets=True),
    SourceSpec("cloud_summaries", "cloud/summaries", ("latest_collector_run.json", "*.json"), count_rows=False),
    SourceSpec("odds_movement_cache", "cache/odds_movement", ("*.csv", "*.json"), critical=False, count_markets=True),
)


class DataStatusService:
    """Compact production data status and freshness summary."""

    def __init__(
        self,
        *,
        settings: Settings = default_settings,
        data_health_repository: DataHealthRepository | None = None,
        now_provider: Callable[[], datetime] | None = None,
        stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
    ) -> None:
        self.settings = settings
        self.data_dir = settings.data_dir
        self._now_provider = now_provider
        self.stale_after_seconds = int(stale_after_seconds)
        self.manifests = CollectorManifestService(settings=settings)
        self.data_health_repository = data_health_repository or DataHealthRepository(WarehouseDatabase.from_settings(settings))

    def payload(self, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
        query = query or {}
        generated_at = self._now()
        current_date = generated_at.date().isoformat()
        season = self.settings.season_from_query(query)
        latest_manifest = self.manifests.load_latest_manifest()

        source_freshness: dict[str, dict[str, Any]] = {}
        warnings: list[str] = []
        missing_files = self._missing_expected_files(season)
        expected_files = self._expected_files(season)

        for spec in SOURCE_SPECS:
            source = self._inspect_source(spec, generated_at=generated_at)
            source_freshness[spec.key] = source
            warnings.extend(source["warnings"])

        if latest_manifest is None:
            warnings.append("No collector manifest found.")
        elif latest_manifest.get("artifact_critical_files_missing"):
            missing = ", ".join(latest_manifest.get("artifact_critical_files_missing") or [])
            warnings.append(f"Latest collector manifest is missing artifact-critical paths: {missing}.")

        database_status = self._database_status(season)
        if database_status["enabled"] and not database_status["reachable"]:
            suffix = " CSV fallback is enabled." if database_status["csv_fallback"]["enabled"] else ""
            warnings.append(f"Warehouse database is enabled but unreachable.{suffix}")

        warnings.extend(f"Missing expected file: {path}" for path in missing_files)
        data_health_score = self._score(source_freshness, missing_files)
        status = self._overall_status(source_freshness, missing_files, warnings)

        return {
            "status": status,
            "current_date": current_date,
            "generated_at": generated_at.isoformat(),
            "latest_collector_manifest": latest_manifest,
            "source_freshness": source_freshness,
            "database": database_status,
            "expected_files": expected_files,
            "missing_files": missing_files,
            "warnings": _dedupe(warnings)[:40],
            "data_health_score": data_health_score,
        }

    def _database_status(self, season: int) -> dict[str, Any]:
        try:
            raw = self.data_health_repository.database_status(season=season)
        except Exception as error:
            raw = {
                "enabled": self.settings.db_enabled,
                "reachable": False,
                "dialect": "",
                "reason": "error",
                "error": f"{type(error).__name__}: {error}",
                "latestDbSnapshotDate": "",
                "rowCounts": {},
                "tables": {},
            }
        enabled = bool(raw.get("enabled"))
        reachable = bool(raw.get("reachable"))
        latest_date = str(raw.get("latestDbSnapshotDate") or "")
        fallback_enabled = bool(self.settings.db_fallback_to_csv)
        return {
            "enabled": enabled,
            "reachable": reachable,
            "dialect": str(raw.get("dialect") or ""),
            "reason": str(raw.get("reason") or ""),
            "error": str(raw.get("error") or ""),
            "latest_db_snapshot_date": latest_date,
            "row_counts": raw.get("rowCounts") if isinstance(raw.get("rowCounts"), dict) else {},
            "tables": raw.get("tables") if isinstance(raw.get("tables"), dict) else {},
            "csv_fallback": {
                "enabled": fallback_enabled,
                "active": bool((not enabled) or (not reachable) or (not latest_date)),
                "status": _csv_fallback_status(
                    enabled=enabled,
                    reachable=reachable,
                    latest_date=latest_date,
                    fallback_enabled=fallback_enabled,
                ),
            },
        }

    def _inspect_source(self, spec: SourceSpec, *, generated_at: datetime) -> dict[str, Any]:
        root = self.data_dir / spec.relative_path
        warnings: list[str] = []
        files = _matching_files(root, spec.patterns)
        latest = files[0] if files else None

        if latest is None:
            warnings.append(f"No files found for {spec.key}.")
            return {
                "status": "missing",
                "path": _relative_data_path(root, self.data_dir),
                "latest_file": None,
                "latest_timestamp": None,
                "age_seconds": None,
                "row_count": None,
                "file_count": 0,
                "market_counts": {},
                "warnings": warnings,
            }

        latest_timestamp = datetime.fromtimestamp(latest.stat().st_mtime, timezone.utc)
        age_seconds = max(0, int((generated_at - latest_timestamp).total_seconds()))
        row_count = _cheap_row_count(latest) if spec.count_rows else None
        market_counts = _market_counts(latest) if spec.count_markets else {}

        status = "fresh"
        if age_seconds > self.stale_after_seconds:
            status = "stale"
            warnings.append(f"{spec.key} latest file is stale.")
        if row_count == 0 and latest.suffix.lower() == ".csv":
            status = "warning" if status == "fresh" else status
            warnings.append(f"{spec.key} latest CSV has zero rows.")

        return {
            "status": status,
            "path": _relative_data_path(root, self.data_dir),
            "latest_file": _relative_data_path(latest, self.data_dir),
            "latest_timestamp": latest_timestamp.isoformat(),
            "age_seconds": age_seconds,
            "row_count": row_count,
            "file_count": len(files),
            "market_counts": market_counts,
            "warnings": warnings,
        }

    def _expected_files(self, season: int) -> list[str]:
        return [
            f"data/playerboard/playerboard_{season}.csv",
            "data/cloud/summaries/latest_collector_run.json",
            f"data/cache/odds_movement/status_{season}.json",
            f"data/cache/odds_movement/prop_movement_{season}.csv",
            f"data/cache/odds_movement/prop_snapshots_{season}.csv",
        ]

    def _missing_expected_files(self, season: int) -> list[str]:
        missing: list[str] = []
        for relative in self._expected_files(season):
            path = self.data_dir / relative.removeprefix("data/").lstrip("/")
            if not path.exists():
                missing.append(relative)
        return missing

    def _overall_status(
        self,
        source_freshness: dict[str, dict[str, Any]],
        missing_files: list[str],
        warnings: list[str],
    ) -> str:
        critical_statuses = [
            source["status"]
            for spec in SOURCE_SPECS
            if spec.critical
            for key, source in source_freshness.items()
            if key == spec.key
        ]
        if missing_files or any(status == "missing" for status in critical_statuses):
            return "missing"
        if any(status == "stale" for status in critical_statuses):
            return "stale"
        if warnings or any(source["status"] in {"warning", "stale", "missing"} for source in source_freshness.values()):
            return "warning"
        return "fresh"

    def _score(self, source_freshness: dict[str, dict[str, Any]], missing_files: list[str]) -> int:
        score = 100
        score -= min(45, len(missing_files) * 9)
        for spec in SOURCE_SPECS:
            source = source_freshness.get(spec.key, {})
            status = source.get("status")
            if status == "missing":
                score -= 12 if spec.critical else 4
            elif status == "stale":
                score -= 8 if spec.critical else 3
            elif status == "warning":
                score -= 5 if spec.critical else 2
        return max(0, min(100, score))

    def _now(self) -> datetime:
        if self._now_provider is not None:
            value = self._now_provider()
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc)


def _cheap_row_count(path: Path) -> int | None:
    try:
        if path.suffix.lower() == ".csv":
            if path.stat().st_size > MAX_ROW_COUNT_BYTES:
                return None
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                return sum(1 for _ in csv.DictReader(handle))
        if path.suffix.lower() == ".json":
            if path.stat().st_size > MAX_JSON_COUNT_BYTES:
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                return len(payload)
            if isinstance(payload, dict):
                for key in ("rows", "items", "data", "games", "props"):
                    value = payload.get(key)
                    if isinstance(value, list):
                        return len(value)
                return len(payload)
    except (OSError, json.JSONDecodeError):
        return None
    return None


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _market_counts(path: Path) -> dict[str, int]:
    try:
        counts: dict[str, int] = {}
        if path.suffix.lower() == ".csv":
            if path.stat().st_size > MAX_ROW_COUNT_BYTES:
                return {}
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    _increment_market_count(counts, row)
        elif path.suffix.lower() == ".json":
            if path.stat().st_size > MAX_JSON_COUNT_BYTES:
                return {}
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows = payload if isinstance(payload, list) else payload.get("rows") if isinstance(payload, dict) else []
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, dict):
                        _increment_market_count(counts, row)
        return dict(sorted(counts.items()))
    except (OSError, json.JSONDecodeError):
        return {}


def _increment_market_count(counts: dict[str, int], row: dict[str, Any]) -> None:
    market = str(row.get("market") or row.get("market_key") or row.get("marketKey") or "").strip()
    if market:
        counts[market] = counts.get(market, 0) + 1


def _csv_fallback_status(*, enabled: bool, reachable: bool, latest_date: str, fallback_enabled: bool) -> str:
    if not fallback_enabled:
        return "disabled"
    if not enabled:
        return "primary_csv"
    if not reachable:
        return "active_db_unreachable"
    if not latest_date:
        return "active_db_empty"
    return "standby"


def _matching_files(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    if not root.exists():
        return []
    files: dict[Path, None] = {}
    for pattern in patterns:
        for path in root.rglob(pattern):
            if path.is_file():
                files[path] = None
    return sorted(files, key=lambda path: _safe_mtime(path), reverse=True)


def _relative_data_path(path: Path, data_dir: Path) -> str:
    try:
        return str(Path("data") / path.resolve().relative_to(data_dir.resolve())).replace("\\", "/")
    except (OSError, ValueError):
        return str(path.name)


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0
