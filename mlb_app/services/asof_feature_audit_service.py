from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.contracts.feature_store_schema import postgame_label_names
from mlb_app.services.data_source_capability_service import DataSourceCapabilityService, resolve_date_mode
from mlb_app.services.feature_store_materializer import FeatureStoreMaterializer
from mlb_app.services.runtime_status_service import safe_relpath

SCHEMA_VERSION = "asof-feature-audit.v1"


class AsofFeatureAuditService:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings
        self.capabilities = DataSourceCapabilityService(settings)
        self.feature_store = FeatureStoreMaterializer(settings)

    def payload(self, *, date_label: str | None = None, season: int | None = None) -> dict[str, Any]:
        target_date, mode = resolve_date_mode(date_label)
        selected_season = int(season or self.settings.current_season)
        feature_path = self.feature_store.feature_path(target_date)
        header = _csv_header(feature_path)
        blocked = sorted(set(header).intersection(postgame_label_names() + _blocked_postgame_aliases()))
        capability_audit = self.capabilities.audit_feature_availability(target_date, selected_season)
        missing_groups = list(capability_audit.get("missingFeatureGroups") or [])
        warnings: list[str] = []
        recommendations: list[str] = []
        timestamp_warnings = self._timestamp_warnings(feature_path, target_date)
        warnings.extend(timestamp_warnings)
        if not feature_path.is_file():
            warnings.append("Feature matrix artifact is missing; audit inspected available metadata only.")
            recommendations.append("Materialize the pregame feature matrix from cached artifacts before modeling.")
        if blocked:
            warnings.append("Blocked postgame label fields were found in the feature matrix.")
            recommendations.append("Remove postgame labels/outcomes from prediction features.")
        pregame_safe = not blocked
        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": "ok",
            "date": target_date,
            "season": selected_season,
            "resolvedDateMode": mode,
            "pregameSafe": pregame_safe,
            "labelsSeparated": not blocked,
            "blockedFieldsFound": blocked,
            "missingFeatureGroups": missing_groups,
            "warnings": warnings,
            "recommendations": recommendations,
            "featureMatrix": {
                "path": safe_relpath(feature_path, self.settings.root_dir),
                "exists": feature_path.is_file(),
                "fieldCount": len(header),
                "rowsInspected": _count_rows(feature_path, limit=100),
            },
            "sourceTimestampAudit": {
                "status": "warning" if timestamp_warnings else "ok",
                "warnings": timestamp_warnings,
            },
            "externalApiCallsMade": False,
            "modelTrainingTriggered": False,
        }

    def _timestamp_warnings(self, path: Path, date_label: str) -> list[str]:
        warnings: list[str] = []
        if not path.is_file():
            return warnings
        for index, row in enumerate(_read_rows(path, limit=100), start=1):
            raw = str(row.get("source_snapshot_at") or "").strip()
            if not raw:
                continue
            try:
                timestamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                warnings.append(f"Row {index} has an unparsable source_snapshot_at value.")
                continue
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            if timestamp.date().isoformat() > date_label:
                warnings.append(f"Row {index} source_snapshot_at is after the target date.")
        return warnings


def _blocked_postgame_aliases() -> list[str]:
    return ["outcome", "settled_result", "final_score", "runs_scored", "postgame_result"]


def _csv_header(path: Path) -> list[str]:
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return next(csv.reader(handle), [])
    except Exception:
        return []


def _read_rows(path: Path, *, limit: int) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = []
            for index, row in enumerate(csv.DictReader(handle)):
                if index >= limit:
                    break
                rows.append(dict(row))
            return rows
    except Exception:
        return []


def _count_rows(path: Path, *, limit: int) -> int:
    return len(_read_rows(path, limit=limit))
