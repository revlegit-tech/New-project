from __future__ import annotations

import csv
import json
from collections import Counter
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
from mlb_app.services.player_prop_prediction_repository import PlayerPropPredictionRepository, apply_unscored_trust_defaults
from mlb_app.services.player_prop_explainability_service import (
    attach_player_prop_explainability,
    explainability_coverage,
)
from mlb_app.services.player_prop_label_builder_service import (
    latest_player_prop_label_status,
    latest_player_prop_training_status,
)
from mlb_app.services.playerboard_read_service import PlayerboardReadService

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
        playerboard_read_service: PlayerboardReadService | None = None,
        player_prop_prediction_repository: PlayerPropPredictionRepository | None = None,
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
        self.playerboard_read_service = playerboard_read_service
        self.player_prop_prediction_repository = player_prop_prediction_repository or PlayerPropPredictionRepository(settings=settings)

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
        playerboard_build_health = self._playerboard_build_health(source_freshness.get("playerboard", {}), season=season)
        ml_feature_exports = self._ml_feature_exports_status(database_status)
        ml_label_exports = self._ml_label_exports_status(database_status)
        ml_training_datasets = self._ml_training_datasets_status(database_status)
        context_health = self._context_health(current_date)

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
            "contextCoverageByGroup": context_health["contextCoverageByGroup"],
            "contextFeatureGroups": context_health["contextFeatureGroups"],
            "context_source_audit": context_health["context_source_audit"],
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

    def _playerboard_build_health(self, playerboard_source: dict[str, Any], *, season: int) -> dict[str, Any]:
        path = self.data_dir / "status" / "playerboard_build_status.json"
        try:
            latest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            latest = {}
        if not isinstance(latest, dict):
            latest = {}
        scoring_summary = self._latest_prediction_summary()
        scope = self._playerboard_trust_scope(playerboard_source, season=season)
        trust_coverage = _playerboard_trust_coverage(
            scope["active_rows"],
            scope_name="active_slate",
            active_date=scope["active_date"],
            source=scope["source"],
            generated_at=self._now().isoformat(),
            season_rows=len(scope["season_rows"]),
            active_slate_rows=len(scope["active_rows"]),
            rows_excluded_by_date_scope=scope["rows_excluded_by_date_scope"],
            rows_excluded_by_season_scope=scope["rows_excluded_by_season_scope"],
        )
        season_trust_coverage = _playerboard_trust_coverage(
            scope["season_rows"],
            scope_name="season_artifact",
            active_date=scope["active_date"],
            source=scope["season_source"],
            generated_at=self._now().isoformat(),
            season_rows=len(scope["season_rows"]),
            active_slate_rows=len(scope["active_rows"]),
            rows_excluded_by_date_scope=0,
            rows_excluded_by_season_scope=scope["rows_excluded_by_season_scope"],
            outside_active_date=scope["active_date"],
        )
        explainability = explainability_coverage(attach_player_prop_explainability(trust_coverage["enrichedRows"]))
        context_consumption = _normalized_context_consumption(scoring_summary.get("contextConsumption"))
        return {
            "rowsSaved": int(latest.get("rowsSaved") or playerboard_source.get("row_count") or 0),
            "unsupportedMarketCounts": dict(latest.get("unsupportedMarketCounts") or {}),
            "attributionStatusCounts": dict(latest.get("attributionStatusCounts") or {}),
            "calibrationCoverage": dict(scoring_summary.get("calibrationCoverage") or {}),
            "trustTierCounts": dict(scoring_summary.get("trustTierCounts") or {}),
            "guardrailStatusCounts": dict(scoring_summary.get("guardrailStatusCounts") or {}),
            "contextReadinessCounts": dict(scoring_summary.get("contextReadinessCounts") or {}),
            "contextConsumption": context_consumption,
            "contextFeatureArtifacts": dict(scoring_summary.get("contextFeatureArtifacts") or {}),
            "contextJoinCounts": dict(scoring_summary.get("contextJoinCounts") or {}),
            "featureCompleteness": dict(scoring_summary.get("featureCompleteness") or {}),
            "featureGroupsReady": list(scoring_summary.get("featureGroupsReady") or []),
            "featureGroupsMissing": list(scoring_summary.get("featureGroupsMissing") or []),
            "sampleGuardrailRows": list(scoring_summary.get("sampleGuardrailRows") or [])[:10],
            "sampleLowTrustRows": list(scoring_summary.get("sampleLowTrustRows") or [])[:10],
            "sampleHighTrustRows": list(scoring_summary.get("sampleHighTrustRows") or [])[:10],
            "sampleUncalibratedRows": list(scoring_summary.get("sampleUncalibratedRows") or [])[:10],
            "trustCoverage": trust_coverage["trustCoverage"],
            "explainabilityCoverage": explainability["explainabilityCoverage"],
            "rowsWithExplainability": explainability["rowsWithExplainability"],
            "rowsMissingExplainability": explainability["rowsMissingExplainability"],
            "explainabilityTierCounts": explainability["explainabilityTierCounts"],
            "sampleMissingExplainabilityRows": explainability["sampleMissingExplainabilityRows"],
            "sampleExplainabilityRowsByTier": explainability["sampleExplainabilityRowsByTier"],
            "seasonTrustCoverage": season_trust_coverage["trustCoverage"],
            "trustCoverageScope": trust_coverage["trustCoverage"]["trustCoverageScope"],
            "activeDate": scope["active_date"],
            "activeSlateRows": len(scope["active_rows"]),
            "seasonRows": len(scope["season_rows"]),
            "statusRowsEvaluated": len(scope["active_rows"]),
            "rowsExcludedByDateScope": scope["rows_excluded_by_date_scope"],
            "rowsExcludedBySeasonScope": scope["rows_excluded_by_season_scope"],
            "sourceOfTrustCoverage": scope["source"],
            "trustCoverageGeneratedAt": trust_coverage["trustCoverage"]["trustCoverageGeneratedAt"],
            "unscoredRowCounts": trust_coverage["unscoredRowCounts"],
            "unscoredReasonCounts": trust_coverage["unscoredReasonCounts"],
            "unscoredReasonCountsByScope": {
                "active_slate": trust_coverage["unscoredReasonCounts"],
                "season_artifact": season_trust_coverage["unscoredReasonCounts"],
            },
            "blankTrustFieldCounts": trust_coverage["blankTrustFieldCounts"],
            "sampleUnscoredRows": trust_coverage["sampleUnscoredRows"],
            "sampleUnscoredRowsByReason": trust_coverage["sampleUnscoredRowsByReason"],
            "sampleUnsupportedRows": trust_coverage["sampleUnsupportedRows"],
            "sampleBlankTrustRows": trust_coverage["sampleBlankTrustRows"],
            "sampleOutsideActiveSlateRows": season_trust_coverage["sampleOutsideActiveSlateRows"],
            "unknownUnscoredDiagnostics": trust_coverage["unknownUnscoredDiagnostics"],
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

    def _playerboard_trust_scope(self, playerboard_source: dict[str, Any], *, season: int) -> dict[str, Any]:
        season_rows = self._latest_playerboard_rows(playerboard_source)
        active_rows: list[dict[str, Any]] = []
        active_date = ""
        source = "csv_season_artifact"
        rows_excluded_by_season_scope = 0

        if self.playerboard_read_service is not None:
            try:
                snapshot = self.playerboard_read_service.get_snapshot(season=season, date_label="", market="")
                active_rows = [dict(row) for row in snapshot.rows]
                active_date = str(snapshot.date or "")
                source = f"{snapshot.source}_active_snapshot"
                if not season_rows:
                    season_rows = [dict(row) for row in snapshot.raw_rows]
            except Exception:
                active_rows = []

        if not active_rows:
            active_date = active_date or _latest_row_date(season_rows)
            active_rows = _active_rows_from_artifact(season_rows, active_date=active_date)
        if active_rows and active_date:
            active_rows = self.player_prop_prediction_repository.join_predictions(active_rows, date_label=active_date).rows

        rows_excluded_by_date_scope = max(0, len(season_rows) - len(active_rows))
        return {
            "active_rows": active_rows,
            "season_rows": season_rows,
            "active_date": active_date,
            "source": source,
            "season_source": str(playerboard_source.get("latest_file") or "data/playerboard/playerboard_<season>.csv"),
            "rows_excluded_by_date_scope": rows_excluded_by_date_scope,
            "rows_excluded_by_season_scope": rows_excluded_by_season_scope,
        }

    def _latest_playerboard_rows(self, playerboard_source: dict[str, Any]) -> list[dict[str, Any]]:
        latest_file = str(playerboard_source.get("latest_file") or "")
        if latest_file:
            path = self.data_dir / latest_file.removeprefix("data/").lstrip("/\\")
        else:
            candidates = sorted((self.data_dir / "playerboard").glob("playerboard_*.csv"), key=_safe_mtime, reverse=True)
            path = candidates[0] if candidates else self.data_dir / "playerboard" / "missing.csv"
        if not path.is_file() or path.suffix.lower() != ".csv":
            return []
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                return [dict(row) for row in csv.DictReader(handle)]
        except OSError:
            return []

    def _latest_prediction_summary(self) -> dict[str, Any]:
        predictions_dir = self.data_dir / "predictions"
        candidates = sorted(predictions_dir.glob("prop_predictions_*_summary.json"), key=_safe_mtime, reverse=True)
        for path in candidates:
            if not path.is_file():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                return payload
        return {}

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

    def _context_health(self, current_date: str) -> dict[str, Any]:
        audit = self._latest_context_audit(current_date)
        if audit:
            return {
                "contextCoverageByGroup": audit.get("contextCoverageByGroup") if isinstance(audit.get("contextCoverageByGroup"), dict) else {},
                "contextFeatureGroups": audit.get("contextFeatureGroups") if isinstance(audit.get("contextFeatureGroups"), dict) else {},
                "context_source_audit": {
                    "path": audit.get("path") or "",
                    "date": audit.get("date") or "",
                    "generatedAt": audit.get("generatedAt") or "",
                    "warnings": list(audit.get("warnings") or [])[:20],
                },
            }
        coverage: dict[str, Any] = {}
        groups = {
            "weather": self.data_dir / "context" / "weather" / f"weather_context_{current_date}.csv",
            "game_markets": self.data_dir / "context" / "game_markets" / f"game_markets_{current_date}.csv",
            "bullpen_context": self.data_dir / "context" / "bullpen" / f"bullpen_context_{current_date}.csv",
            "statcast": self.data_dir / "context" / "statcast" / f"statcast_context_{current_date}.csv",
            "umpire": self.data_dir / "context" / "umpire" / f"umpire_context_{current_date}.csv",
        }
        feature_groups = {"ready": [], "partial": [], "fallback": [], "missing": []}
        for group, path in groups.items():
            rows, fields, sample = _read_small_csv(path)
            status = "missing"
            fallback_rows = sum(1 for row in sample if "fallback" in json.dumps(row).lower())
            if rows > 0 and fallback_rows == rows:
                status = "fallback"
                feature_groups["fallback"].append(group)
            elif rows > 0:
                status = "partial"
                feature_groups["partial"].append(group)
            else:
                feature_groups["missing"].append(group)
            coverage[group] = {
                "rows": rows,
                "populatedRows": rows,
                "fallbackRows": fallback_rows,
                "missingRequiredFields": [],
                "populatedPercent": 100.0 if rows else 0.0,
                "source": str(path),
                "status": status,
                "warnings": [] if path.is_file() else [f"{group} context artifact missing."],
                "fields": fields,
            }
        return {"contextCoverageByGroup": coverage, "contextFeatureGroups": feature_groups, "context_source_audit": {}}

    def _latest_context_audit(self, current_date: str) -> dict[str, Any]:
        context_dir = self.data_dir / "context"
        candidates = [context_dir / f"context_source_audit_{current_date}.json"]
        candidates.extend(sorted(context_dir.glob("context_source_audit_*.json"), key=_safe_mtime, reverse=True))
        for path in candidates:
            if not path.is_file():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                payload.setdefault("path", _relative_data_path(path, self.data_dir))
                return payload
        return {}

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


TRUST_COVERAGE_FIELDS = (
    "trustTier",
    "probabilityGuardrailStatus",
    "calibrationStatus",
    "contextReadinessStatus",
)


def _playerboard_trust_coverage(
    rows: list[dict[str, Any]],
    *,
    scope_name: str = "active_slate",
    active_date: str = "",
    source: str = "",
    generated_at: str = "",
    season_rows: int = 0,
    active_slate_rows: int = 0,
    rows_excluded_by_date_scope: int = 0,
    rows_excluded_by_season_scope: int = 0,
    outside_active_date: str = "",
) -> dict[str, Any]:
    prepared_rows = [_annotate_scope(row, scope_name=scope_name, active_date=outside_active_date) for row in rows]
    enriched_rows = [apply_unscored_trust_defaults(row) for row in prepared_rows]
    blank_counts = {
        "totalRowsMissingTrustTier": _missing_field_count(enriched_rows, "trustTier"),
        "totalRowsMissingGuardrailStatus": _missing_field_count(enriched_rows, "probabilityGuardrailStatus"),
        "totalRowsMissingCalibrationStatus": _missing_field_count(enriched_rows, "calibrationStatus"),
        "totalRowsMissingContextReadinessStatus": _missing_field_count(enriched_rows, "contextReadinessStatus"),
    }
    unscored_rows = [row for row in enriched_rows if not _truthy(row.get("predictionMatched"))]
    unsupported_rows = [
        row
        for row in unscored_rows
        if str(row.get("unscoredReason") or "") == "unsupported_market" or str(row.get("trustTier") or "") == "unsupported"
    ]
    blank_rows = [row for row in enriched_rows if any(not _clean(row.get(field)) for field in TRUST_COVERAGE_FIELDS)]
    reason_counts = dict(sorted(Counter(str(row.get("unscoredReason") or "unknown_unscored") for row in unscored_rows).items()))
    outside_rows = [
        row
        for row in enriched_rows
        if str(row.get("unscoredReason") or "") in {"outside_active_slate", "season_row_not_active_slate"}
    ]
    return {
        "trustCoverage": {
            "trustCoverageScope": scope_name,
            "activeDate": active_date,
            "activeSlateRows": active_slate_rows or len(enriched_rows),
            "seasonRows": season_rows or len(enriched_rows),
            "statusRowsEvaluated": len(enriched_rows),
            "rowsExcludedByDateScope": rows_excluded_by_date_scope,
            "rowsExcludedBySeasonScope": rows_excluded_by_season_scope,
            "sourceOfTrustCoverage": source,
            "trustCoverageGeneratedAt": generated_at,
            "totalBoardRows": len(enriched_rows),
            "totalRowsWithTrustTier": len(enriched_rows) - blank_counts["totalRowsMissingTrustTier"],
            "totalRowsMissingTrustTier": blank_counts["totalRowsMissingTrustTier"],
            "totalRowsWithGuardrailStatus": len(enriched_rows) - blank_counts["totalRowsMissingGuardrailStatus"],
            "totalRowsMissingGuardrailStatus": blank_counts["totalRowsMissingGuardrailStatus"],
            "totalRowsWithCalibrationStatus": len(enriched_rows) - blank_counts["totalRowsMissingCalibrationStatus"],
            "totalRowsMissingCalibrationStatus": blank_counts["totalRowsMissingCalibrationStatus"],
            "totalRowsWithContextReadinessStatus": len(enriched_rows) - blank_counts["totalRowsMissingContextReadinessStatus"],
            "totalRowsMissingContextReadinessStatus": blank_counts["totalRowsMissingContextReadinessStatus"],
        },
        "unscoredRowCounts": {
            "totalUnscoredRows": len(unscored_rows),
            "totalUnsupportedRows": len(unsupported_rows),
            "totalScoredRows": len(enriched_rows) - len(unscored_rows),
        },
        "unscoredReasonCounts": reason_counts,
        "blankTrustFieldCounts": blank_counts,
        "sampleUnscoredRows": _sample_trust_rows(unscored_rows),
        "sampleUnscoredRowsByReason": _sample_trust_rows_by_reason(unscored_rows),
        "sampleUnsupportedRows": _sample_trust_rows(unsupported_rows),
        "sampleBlankTrustRows": _sample_trust_rows(blank_rows),
        "sampleOutsideActiveSlateRows": _sample_trust_rows(outside_rows),
        "unknownUnscoredDiagnostics": _unknown_unscored_diagnostics(unscored_rows, reason_counts),
        "enrichedRows": enriched_rows,
    }


def _normalized_context_consumption(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, Any] = {}
    for group, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        entry = dict(payload)
        model_fields = _list_field(entry.get("modelFeatureFields"))
        populated_fields = _list_field(entry.get("populatedFeatureFields"))
        configured_for_model = bool(model_fields)
        status = _normalize_status(entry.get("status"))
        rows_joined = _safe_int(entry.get("rowsJoinedToScoring"))
        entry["modelFeatureFields"] = model_fields
        entry["populatedFeatureFields"] = populated_fields
        entry["configuredForCurrentModel"] = configured_for_model
        entry["usedByCurrentModel"] = bool(status == "used" and rows_joined > 0 and populated_fields)
        normalized[str(group)] = entry
    return normalized


def _list_field(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return []


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _annotate_scope(row: dict[str, Any], *, scope_name: str, active_date: str) -> dict[str, Any]:
    if scope_name != "season_artifact" or not active_date:
        return dict(row)
    row_date = _clean(row.get("date"))[:10]
    if row_date and row_date != active_date:
        return dict(row) | {
            "trustCoverageScope": "season_row_not_active_slate",
            "outsideActiveSlate": True,
            "unscoredReason": _clean(row.get("unscoredReason")) or "season_row_not_active_slate",
        }
    return dict(row)


def _missing_field_count(rows: list[dict[str, Any]], field: str) -> int:
    return sum(1 for row in rows if not _clean(row.get(field)))


def _sample_trust_rows(rows: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for row in rows:
        trust_tier = _normalize_status(row.get("trustTier"))
        guardrail_status = _normalize_status(row.get("probabilityGuardrailStatus"))
        unscored_reason = _visible_unscored_reason(row, trust_tier=trust_tier, guardrail_status=guardrail_status)
        unscored_reason_detail = _visible_unscored_reason_detail(row, unscored_reason)
        market_capability_status = _sample_market_capability_status(row, unscored_reason)
        samples.append(
            {
                "player": _clean(row.get("player")),
                "market": _clean(row.get("market")),
                "side": _clean(row.get("side")),
                "line": _clean(row.get("line")),
                "book": _clean(row.get("book") or row.get("bookKey") or row.get("bestBook")),
                "attributionStatus": _clean(row.get("attributionStatus")),
                "unscoredReason": unscored_reason,
                "unscoredReasonDetail": unscored_reason_detail,
                "reasonDisplayLabel": _reason_display_label(unscored_reason),
                "reasonTaxonomy": _reason_taxonomy(row, unscored_reason),
                "scoringSkipReason": "" if _scored_tier(trust_tier) else _clean(row.get("scoringSkipReason")),
                "unsupportedMarketReason": _clean(row.get("unsupportedMarketReason")),
                "attributionBlockReason": _clean(row.get("attributionBlockReason")),
                "missingPredictionReason": "" if _scored_tier(trust_tier) else _clean(row.get("missingPredictionReason")),
                "trustTier": trust_tier or "unknown",
                "calibrationStatus": _normalize_status(row.get("calibrationStatus")) or "unknown",
                "probabilityGuardrailStatus": guardrail_status or "unknown",
                "contextReadinessStatus": _normalize_status(row.get("contextReadinessStatus")) or "unknown",
                "marketCapabilityStatus": market_capability_status,
            }
        )
        if len(samples) >= limit:
            break
    return samples


def _sample_trust_rows_by_reason(rows: list[dict[str, Any]], *, per_reason_limit: int = 5) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        reason = _clean(row.get("unscoredReason")) or "unknown_unscored"
        bucket = grouped.setdefault(reason, [])
        if len(bucket) < per_reason_limit:
            bucket.extend(_sample_trust_rows([row], limit=1))
    return dict(sorted(grouped.items()))


def _unknown_unscored_diagnostics(rows: list[dict[str, Any]], reason_counts: dict[str, int]) -> dict[str, Any]:
    unknown_rows = [row for row in rows if (_clean(row.get("unscoredReason")) or "unknown_unscored") == "unknown_unscored"]
    return {
        "unknownUnscoredRows": int(reason_counts.get("unknown_unscored", 0)),
        "knownUnscoredRows": max(0, len(rows) - int(reason_counts.get("unknown_unscored", 0))),
        "diagnostic": "unknown_unscored is used only when existing row metadata cannot identify a safe reason.",
        "sampleRows": _sample_trust_rows(unknown_rows, limit=10),
    }


def _normalize_status(value: Any) -> str:
    return _clean(value).lower().replace("-", "_").replace(" ", "_")


def _scored_tier(trust_tier: str) -> bool:
    return trust_tier in {"standard", "low", "limited"}


def _visible_unscored_reason(row: dict[str, Any], *, trust_tier: str, guardrail_status: str) -> str:
    raw = _normalize_status(row.get("unscoredReason"))
    if not raw or raw == "none":
        return ""
    if _scored_tier(trust_tier):
        return raw if guardrail_status == "blocked" else ""
    if trust_tier in {"blocked", "unsupported", "unscored"}:
        return raw
    return raw if guardrail_status == "blocked" else ""


def _visible_unscored_reason_detail(row: dict[str, Any], unscored_reason: str) -> str:
    if not unscored_reason:
        return ""
    return _clean(row.get("unscoredReasonDetail"))


def _sample_market_capability_status(row: dict[str, Any], unscored_reason: str) -> str:
    status = _normalize_status(row.get("marketCapabilityStatus"))
    if status:
        return status
    if unscored_reason == "unsupported_market" or _normalize_status(row.get("trustTier")) == "unsupported":
        return "unsupported"
    market = _clean(row.get("market"))
    return "unknown" if market else "not_available"


def _reason_taxonomy(row: dict[str, Any], unscored_reason: str) -> str:
    if not unscored_reason:
        return "not_available" if _scored_tier(_normalize_status(row.get("trustTier"))) else "unknown"
    if unscored_reason == "unsupported_market" or _normalize_status(row.get("trustTier")) == "unsupported":
        return "unsupported"
    if "invalid" in unscored_reason or "blocked" in unscored_reason or _normalize_status(row.get("trustTier")) == "blocked":
        return "blocked"
    return "unscored"


def _reason_display_label(unscored_reason: str) -> str:
    if not unscored_reason:
        return "Not available"
    if unscored_reason == "unsupported_market":
        return "Unsupported market"
    if "invalid" in unscored_reason or "blocked" in unscored_reason:
        return "Blocked"
    return "Unscored"


def _latest_row_date(rows: list[dict[str, Any]]) -> str:
    dates = sorted({_clean(row.get("date"))[:10] for row in rows if _clean(row.get("date"))})
    return dates[-1] if dates else ""


def _active_rows_from_artifact(rows: list[dict[str, Any]], *, active_date: str) -> list[dict[str, Any]]:
    if not active_date:
        return list(rows)
    date_rows = [row for row in rows if _clean(row.get("date"))[:10] == active_date]
    with_snapshot = [row for row in date_rows if _clean(row.get("snapshotAt"))]
    if not with_snapshot:
        return date_rows
    by_market: dict[str, list[dict[str, Any]]] = {}
    for row in with_snapshot:
        by_market.setdefault(_clean(row.get("market")) or "unknown", []).append(row)
    selected: list[dict[str, Any]] = []
    for market_rows in by_market.values():
        latest_snapshot = max(_clean(row.get("snapshotAt")) for row in market_rows)
        selected.extend(row for row in market_rows if _clean(row.get("snapshotAt")) == latest_snapshot)
    return selected


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "verified"}


def _clean(value: Any) -> str:
    return str(value or "").strip()


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


def _read_small_csv(path: Path) -> tuple[int, list[str], list[dict[str, Any]]]:
    if not path.is_file():
        return 0, [], []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = [dict(row) for row in reader]
            return len(rows), [field for field in (reader.fieldnames or []) if field], rows
    except OSError:
        return 0, [], []


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
