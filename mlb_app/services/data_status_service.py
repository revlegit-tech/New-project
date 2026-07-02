from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from mlb_app.config import Settings, settings as default_settings
from mlb_app.repositories.data_health_repository import DataHealthRepository
from mlb_app.repositories.historical_game_odds_repository import HistoricalGameOddsRepository
from mlb_app.repositories.warehouse_db import WarehouseDatabase
from mlb_app.services.collector_manifest_service import CollectorManifestService
from mlb_app.services.game_market_feature_lookup_service import GameMarketFeatureLookupService
from mlb_app.services.ml_feature_export_service import latest_ml_feature_export_status
from mlb_app.services.player_prop_label_builder_service import (
    latest_player_prop_label_status,
    latest_player_prop_training_status,
)

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
        historical_game_odds_repository: HistoricalGameOddsRepository | None = None,
        game_market_feature_lookup_service: GameMarketFeatureLookupService | None = None,
        now_provider: Callable[[], datetime] | None = None,
        stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
    ) -> None:
        self.settings = settings
        self.data_dir = settings.data_dir
        self._now_provider = now_provider
        self.stale_after_seconds = int(stale_after_seconds)
        self.manifests = CollectorManifestService(settings=settings)
        self.data_health_repository = data_health_repository or DataHealthRepository(WarehouseDatabase.from_settings(settings))
        self.historical_game_odds_repository = historical_game_odds_repository or HistoricalGameOddsRepository(
            WarehouseDatabase.from_settings(settings),
            settings=settings,
        )
        self.game_market_feature_lookup_service = game_market_feature_lookup_service

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
        historical_game_odds = self._historical_game_odds_status()
        game_market_enrichment = self._game_market_enrichment_status(
            database_status=database_status,
            historical_game_odds=historical_game_odds,
        )
        playerboard_build_health = self._playerboard_build_health(source_freshness.get("playerboard", {}))
        ml_feature_exports = self._ml_feature_exports_status(database_status)
        ml_label_exports = self._ml_label_exports_status(database_status)
        ml_training_datasets = self._ml_training_datasets_status(database_status)

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
            "historical_game_odds": historical_game_odds,
            "game_market_enrichment": game_market_enrichment,
            "playerboard_build_health": playerboard_build_health,
            "ml_feature_exports": ml_feature_exports,
            "ml_label_exports": ml_label_exports,
            "ml_training_datasets": ml_training_datasets,
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

    def _historical_game_odds_status(self) -> dict[str, Any]:
        try:
            status = self.historical_game_odds_repository.status()
        except Exception as error:
            status = {
                "enabled": self.settings.db_enabled,
                "reachable": False,
                "games": 0,
                "line_rows": 0,
                "feature_rows": 0,
                "grade_rows": 0,
                "latest_import_at": "",
                "source_file_present": (self.data_dir / "external" / "mlb_odds_dataset.json").exists(),
                "warnings": [f"Historical game odds status unavailable: {type(error).__name__}: {error}"],
            }
        return {
            "enabled": bool(status.get("enabled")),
            "reachable": bool(status.get("reachable")),
            "games": int(status.get("games") or 0),
            "line_rows": int(status.get("line_rows") or 0),
            "feature_rows": int(status.get("feature_rows") or 0),
            "grade_rows": int(status.get("grade_rows") or 0),
            "latest_import_at": str(status.get("latest_import_at") or ""),
            "source_file_present": bool(status.get("source_file_present")),
            "warnings": [str(item) for item in status.get("warnings", []) if str(item).strip()],
        }

    def _game_market_enrichment_status(
        self,
        *,
        database_status: dict[str, Any],
        historical_game_odds: dict[str, Any],
    ) -> dict[str, Any]:
        lookup_status = (
            self.game_market_feature_lookup_service.status_payload()
            if self.game_market_feature_lookup_service is not None
            else {}
        )
        fallback = database_status.get("csv_fallback") if isinstance(database_status.get("csv_fallback"), dict) else {}
        warnings = list(lookup_status.get("warnings") or [])
        if not bool(historical_game_odds.get("feature_rows")):
            warnings.append("No historical game-market feature rows are available for enrichment.")
        if not bool(database_status.get("enabled")) or not bool(database_status.get("reachable")):
            warnings.append("Game-market enrichment will fall back safely because the warehouse is unavailable.")
        return {
            "enabled": bool(getattr(self.settings, "game_market_enrichment_enabled", True)),
            "source": lookup_status.get("source") or "historical_game_market_features",
            "historical_game_odds_available": bool(
                historical_game_odds.get("enabled")
                and historical_game_odds.get("reachable")
                and int(historical_game_odds.get("feature_rows") or 0) > 0
            ),
            "feature_rows": int(historical_game_odds.get("feature_rows") or 0),
            "latest_feature_date": self._latest_feature_date(),
            "matched_rows_last_request": int(lookup_status.get("matched_rows_last_request") or 0),
            "fallback_mode": fallback.get("status") or ("active_db_unreachable" if not database_status.get("reachable") else "standby"),
            "warnings": _dedupe(warnings)[:10],
        }

    def _latest_feature_date(self) -> str:
        try:
            return self.historical_game_odds_repository.latest_feature_date()
        except Exception:
            return ""

    def _playerboard_build_health(self, playerboard_source: dict[str, Any]) -> dict[str, Any]:
        path = self.data_dir / "status" / "playerboard_build_status.json"
        try:
            latest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            latest = {}
        if not isinstance(latest, dict):
            latest = {}
        return {
            "rowsSaved": int(latest.get("rowsSaved") or playerboard_source.get("row_count") or 0),
            "unsupportedMarketCounts": dict(latest.get("unsupportedMarketCounts") or {}),
            "attributionStatusCounts": dict(latest.get("attributionStatusCounts") or {}),
            "rosterEvidenceAvailableRows": int(latest.get("rosterEvidenceAvailableRows") or 0),
            "rosterEvidenceUnavailableRows": int(latest.get("rosterEvidenceUnavailableRows") or 0),
            "lastSnapshotTimestamp": str(latest.get("snapshotAt") or playerboard_source.get("latest_timestamp") or ""),
            "sourceOfTruth": str(latest.get("sourceOfTruth") or "csv"),
            "sourceMode": str(latest.get("sourceMode") or ""),
            "inputSourceMode": str(latest.get("inputSourceMode") or ""),
            "snapshotId": str(latest.get("snapshotId") or ""),
            "buildTimingsMs": dict(latest.get("buildTimingsMs") or {}),
            "slowestBuildPhases": list(latest.get("slowestBuildPhases") or []),
            "generatedAt": str(latest.get("generatedAt") or ""),
        }

    def _ml_feature_exports_status(self, database_status: dict[str, Any]) -> dict[str, Any]:
        latest = latest_ml_feature_export_status(self.settings)
        fallback = database_status.get("csv_fallback") if isinstance(database_status.get("csv_fallback"), dict) else {}
        return {
            "enabled": True,
            "latest_export_date": latest.get("latest_export_date") or "",
            "latest_export_rows": int(latest.get("latest_export_rows") or 0),
            "latest_manifest_path": latest.get("latest_manifest_path") or "",
            "feature_schema_version": latest.get("feature_schema_version") or "",
            "leakage_check_passed": latest.get("leakage_check_passed"),
            "game_market_feature_coverage_pct": latest.get("game_market_feature_coverage_pct"),
            "fallback_mode": fallback.get("status") or latest.get("fallback_mode") or "",
            "warnings": [str(item) for item in latest.get("warnings", []) if str(item).strip()][:10],
        }

    def _ml_label_exports_status(self, database_status: dict[str, Any]) -> dict[str, Any]:
        latest = latest_player_prop_label_status(self.settings)
        fallback = database_status.get("csv_fallback") if isinstance(database_status.get("csv_fallback"), dict) else {}
        return {
            "enabled": True,
            "latest_label_date": latest.get("latest_label_date") or "",
            "latest_label_rows": int(latest.get("latest_label_rows") or 0),
            "latest_manifest_path": latest.get("latest_manifest_path") or "",
            "label_schema_version": latest.get("label_schema_version") or "",
            "graded_count": int(latest.get("graded_count") or 0),
            "ungraded_count": int(latest.get("ungraded_count") or 0),
            "fallback_mode": fallback.get("status") or latest.get("fallback_mode") or "",
            "warnings": [str(item) for item in latest.get("warnings", []) if str(item).strip()][:10],
        }

    def _ml_training_datasets_status(self, database_status: dict[str, Any]) -> dict[str, Any]:
        latest = latest_player_prop_training_status(self.settings)
        fallback = database_status.get("csv_fallback") if isinstance(database_status.get("csv_fallback"), dict) else {}
        return {
            "enabled": True,
            "latest_training_date": latest.get("latest_training_date") or "",
            "latest_training_rows": int(latest.get("latest_training_rows") or 0),
            "latest_manifest_path": latest.get("latest_manifest_path") or "",
            "training_schema_version": latest.get("training_schema_version") or "",
            "leakage_check_passed": latest.get("leakage_check_passed"),
            "fallback_mode": fallback.get("status") or latest.get("fallback_mode") or "",
            "warnings": [str(item) for item in latest.get("warnings", []) if str(item).strip()][:10],
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
