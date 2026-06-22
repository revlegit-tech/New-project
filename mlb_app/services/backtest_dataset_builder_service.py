from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.ml.datasets.leakage_guard import (
    assert_training_row_contract,
    is_feature_column,
    is_prefixed_training_column,
    is_target_column,
    split_training_row,
)
from mlb_app.services.ml_feature_export_service import DEFAULT_SOURCE, MLFeatureExportService
from mlb_app.services.ml_feature_schema import (
    FEATURE_SCHEMA_VERSION,
    assert_no_leakage_fields,
    blocked_feature_names,
    safe_feature_names,
)
from mlb_app.services.player_prop_label_builder_service import (
    PlayerPropLabelBuilderService,
    read_existing_feature_rows,
    read_existing_label_rows,
)
from mlb_app.services.player_prop_label_schema import LABEL_SCHEMA_VERSION, assert_label_not_in_features

TRAINING_SCHEMA_VERSION = "player-prop-training.sprint18.v1"
TRAINING_API_SCHEMA_VERSION = "ml-training.v1"
DEFAULT_TRAINING_OUTPUT_RELATIVE_DIR = Path("warehouse") / "ml_training"
_META_SOURCE_FIELDS: frozenset[str] = frozenset(
    {
        "feature_schema_version",
        "exported_at",
        "source",
        "source_row_id",
        "prop_key",
        "date",
        "season",
        "player",
        "book",
    }
)
FEATURE_SOURCE_COLUMNS: tuple[str, ...] = tuple(name for name in safe_feature_names() if name not in _META_SOURCE_FIELDS)
FEATURE_COLUMNS: tuple[str, ...] = tuple(f"feature_{name}" for name in FEATURE_SOURCE_COLUMNS)
TARGET_COLUMNS: tuple[str, ...] = (
    "target_result",
    "target_hit",
    "target_push",
    "target_void",
    "target_actual_value",
    "target_grade",
    "target_profit_1u",
    "target_graded_at",
    "target_label_status",
    "target_label_reason",
)
METADATA_COLUMNS: tuple[str, ...] = (
    "meta_training_schema_version",
    "meta_training_join_key",
    "meta_feature_schema_version",
    "meta_label_schema_version",
    "meta_game_date",
    "meta_game_id",
    "meta_player",
    "meta_market",
    "meta_book",
    "meta_model_version",
    "meta_source",
    "meta_source_row_id",
    "meta_prop_key",
    "meta_team",
    "meta_opponent",
    "meta_season",
)


@dataclass(frozen=True)
class TrainingBuildResult:
    rows: list[dict[str, Any]]
    structured_rows: list[dict[str, Any]]
    feature_rows: list[dict[str, Any]]
    label_rows: list[dict[str, Any]]
    manifest: dict[str, Any]


class BacktestDatasetBuilderService:
    """Join safe pregame features to explicit postgame target columns."""

    def __init__(
        self,
        *,
        settings: Settings = default_settings,
        feature_export_service: MLFeatureExportService | None = None,
        label_builder_service: PlayerPropLabelBuilderService | None = None,
    ) -> None:
        self.settings = settings
        self.feature_export_service = feature_export_service or MLFeatureExportService(settings=settings)
        self.label_builder_service = label_builder_service or PlayerPropLabelBuilderService(
            settings=settings,
            feature_export_service=self.feature_export_service,
        )

    def build_training_dataset(
        self,
        *,
        date_label: str,
        season: int | None = None,
        source: str = DEFAULT_SOURCE,
        include_ungraded: bool = False,
        dry_run: bool = False,
        output_format: str = "both",
        output_dir: Path | str | None = None,
    ) -> dict[str, Any]:
        result = self.build_training_rows(
            date_label=date_label,
            season=season,
            source=source,
            include_ungraded=include_ungraded,
            dry_run=dry_run,
            output_format=output_format,
            output_dir=output_dir,
        )
        if dry_run:
            return result.manifest
        target_dir = Path(output_dir) if output_dir is not None else self.default_output_dir()
        paths = _planned_training_paths(target_dir, str(result.manifest["date"]), output_format)
        target_dir.mkdir(parents=True, exist_ok=True)
        result.manifest["written"] = True
        if "csv" in paths:
            _write_csv(paths["csv"], _csv_columns(result.manifest), result.rows)
        if "json" in paths:
            _write_json(
                paths["json"],
                {
                    "training_schema_version": TRAINING_SCHEMA_VERSION,
                    "manifest": result.manifest,
                    "rows": result.structured_rows,
                    "flat_rows": result.rows,
                },
            )
        _write_json(paths["manifest"], result.manifest)
        return result.manifest

    def build_training_rows(
        self,
        *,
        date_label: str,
        season: int | None = None,
        source: str = DEFAULT_SOURCE,
        include_ungraded: bool = False,
        dry_run: bool = True,
        output_format: str = "both",
        output_dir: Path | str | None = None,
    ) -> TrainingBuildResult:
        selected_date = _clean(date_label) or datetime.now(timezone.utc).date().isoformat()
        selected_season = int(season or self.settings.current_season)
        target_dir = Path(output_dir) if output_dir is not None else self.default_output_dir()
        feature_rows, feature_warnings = self._load_feature_rows(date_label=selected_date, season=selected_season, source=source)
        label_rows, label_warnings = self._load_label_rows(
            date_label=selected_date,
            season=selected_season,
            source=source,
            include_ungraded=True,
        )
        label_by_key = {_join_key(row): row for row in label_rows if _join_key(row)}
        warnings = feature_warnings + label_warnings

        flat_rows: list[dict[str, Any]] = []
        structured_rows: list[dict[str, Any]] = []
        blocked_found: set[str] = set()
        for feature in feature_rows:
            key = _join_key(feature)
            label = label_by_key.get(key)
            if not label:
                continue
            if not include_ungraded and _clean(label.get("label_status")) != "graded":
                continue
            try:
                assert_no_leakage_fields(feature)
                assert_label_not_in_features(feature)
            except ValueError as error:
                blocked_found.update(_blocked_fields(feature))
                warnings.append(str(error))
                continue
            metadata_payload = _metadata_payload(feature, label, join_key=key)
            feature_payload = _feature_payload(feature)
            target_payload = _target_payload(label)
            flat = {
                **metadata_payload,
                **feature_payload,
                **target_payload,
            }
            try:
                assert_training_row_contract(flat)
            except ValueError as error:
                blocked_found.update(_training_contract_leaks(flat))
                warnings.append(str(error))
                continue
            structured_rows.append(
                {
                    "metadata": metadata_payload,
                    "features": feature_payload,
                    "targets": target_payload,
                }
            )
            flat_rows.append(flat)

        manifest = self._manifest(
            rows=flat_rows,
            feature_rows=feature_rows,
            label_rows=label_rows,
            blocked_found=blocked_found,
            date_label=selected_date,
            season=selected_season,
            source=_normal_source(source),
            dry_run=dry_run,
            output_format=output_format,
            output_dir=target_dir,
            warnings=warnings,
        )
        return TrainingBuildResult(flat_rows, structured_rows, feature_rows, label_rows, manifest)

    def preview(self, *, date_label: str, limit: int = 25, season: int | None = None, source: str = DEFAULT_SOURCE) -> dict[str, Any]:
        selected_date = _clean(date_label) or datetime.now(timezone.utc).date().isoformat()
        rows, warnings = read_existing_training_rows(self.settings, selected_date)
        if not rows:
            built = self.build_training_rows(
                date_label=selected_date,
                season=season,
                source=source,
                include_ungraded=True,
                dry_run=True,
            )
            rows = built.rows
            warnings.extend(built.manifest.get("warnings") or [])
        structured_preview_rows = [_structure_training_row(row) for row in rows]
        return {
            "status": "ok",
            "training_schema_version": TRAINING_SCHEMA_VERSION,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "label_schema_version": LABEL_SCHEMA_VERSION,
            "date": selected_date,
            "row_count": len(rows),
            "feature_columns": list(FEATURE_COLUMNS),
            "target_columns": list(TARGET_COLUMNS),
            "metadata_columns": list(METADATA_COLUMNS),
            "rows": structured_preview_rows[: max(0, min(int(limit), 250))],
            "warnings": _dedupe(warnings)[:25],
        }

    def default_output_dir(self) -> Path:
        return self.settings.data_dir / DEFAULT_TRAINING_OUTPUT_RELATIVE_DIR

    def _load_feature_rows(self, *, date_label: str, season: int, source: str) -> tuple[list[dict[str, Any]], list[str]]:
        rows, warnings = read_existing_feature_rows(self.settings, date_label)
        if rows:
            return rows, warnings
        build = self.feature_export_service.build_features(date_label=date_label, season=season, source=source)
        return build.rows, list(build.manifest.get("warnings") or [])

    def _load_label_rows(
        self,
        *,
        date_label: str,
        season: int,
        source: str,
        include_ungraded: bool,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        rows, warnings = read_existing_label_rows(self.settings, date_label)
        if rows:
            return rows, warnings
        build = self.label_builder_service.build_label_rows(
            date_label=date_label,
            season=season,
            source=source,
            include_ungraded=include_ungraded,
            dry_run=True,
        )
        return build.rows, list(build.manifest.get("warnings") or [])

    def _manifest(
        self,
        *,
        rows: Sequence[Mapping[str, Any]],
        feature_rows: Sequence[Mapping[str, Any]],
        label_rows: Sequence[Mapping[str, Any]],
        blocked_found: set[str],
        date_label: str,
        season: int,
        source: str,
        dry_run: bool,
        output_format: str,
        output_dir: Path,
        warnings: list[str],
    ) -> dict[str, Any]:
        market_counts = Counter(_market_from_training_row(row) for row in rows)
        result_counts = Counter(_clean(row.get("target_result")) or "ungraded" for row in rows)
        status_counts = Counter(_clean(row.get("target_label_status")) or "unknown" for row in rows)
        planned = _planned_training_paths(output_dir, date_label, output_format)
        leakage_check_passed = not blocked_found
        return {
            "status": "ok",
            "schemaVersion": TRAINING_API_SCHEMA_VERSION,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "label_schema_version": LABEL_SCHEMA_VERSION,
            "training_schema_version": TRAINING_SCHEMA_VERSION,
            "date": date_label,
            "season": int(season),
            "source": source,
            "format": _normal_format(output_format),
            "dry_run": bool(dry_run),
            "feature_row_count": len(feature_rows),
            "label_row_count": len(label_rows),
            "joined_row_count": len(rows),
            "graded_training_row_count": int(status_counts.get("graded", 0)),
            "ungraded_training_row_count": sum(1 for row in rows if _clean(row.get("target_label_status")) != "graded"),
            "market_counts": dict(sorted(market_counts.items())),
            "result_counts": dict(sorted(result_counts.items())),
            "label_status_counts": dict(sorted(status_counts.items())),
            "feature_columns": list(FEATURE_COLUMNS),
            "target_columns": list(TARGET_COLUMNS),
            "metadata_columns": list(METADATA_COLUMNS),
            "leakage_check_passed": leakage_check_passed,
            "blocked_feature_fields_found": sorted(blocked_found),
            "output_paths": {key: _display_path(path, self.settings) for key, path in planned.items()},
            "written": False,
            "warnings": _dedupe(warnings)[:25],
        }


def read_existing_training_rows(settings: Settings, date_label: str) -> tuple[list[dict[str, Any]], list[str]]:
    root = settings.data_dir / DEFAULT_TRAINING_OUTPUT_RELATIVE_DIR
    json_path = root / f"player_prop_training_{date_label}.json"
    csv_path = root / f"player_prop_training_{date_label}.csv"
    warnings: list[str] = []
    if json_path.exists():
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            rows = payload.get("flat_rows") if isinstance(payload, dict) else payload
            if not rows and isinstance(payload, dict):
                rows = [_flatten_structured(row) for row in payload.get("rows", []) if isinstance(row, dict)]
            return _normalize_existing_training_rows(rows, warnings), warnings
        except (OSError, json.JSONDecodeError) as error:
            warnings.append(f"Existing training JSON unreadable: {type(error).__name__}: {error}")
    if csv_path.exists():
        try:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                return _normalize_existing_training_rows(list(csv.DictReader(handle)), warnings), warnings
        except OSError as error:
            warnings.append(f"Existing training CSV unreadable: {type(error).__name__}: {error}")
    return [], warnings


def _feature_payload(feature: Mapping[str, Any]) -> dict[str, Any]:
    return {f"feature_{name}": feature.get(name, "") for name in FEATURE_SOURCE_COLUMNS}


def _metadata_payload(feature: Mapping[str, Any], label: Mapping[str, Any], *, join_key: str) -> dict[str, Any]:
    return {
        "meta_training_schema_version": TRAINING_SCHEMA_VERSION,
        "meta_training_join_key": join_key,
        "meta_feature_schema_version": _clean(feature.get("feature_schema_version")) or FEATURE_SCHEMA_VERSION,
        "meta_label_schema_version": _clean(label.get("label_schema_version")) or LABEL_SCHEMA_VERSION,
        "meta_game_date": _clean(feature.get("date")) or _clean(label.get("date")),
        "meta_game_id": _clean(feature.get("game_market_game_id")),
        "meta_player": _clean(feature.get("player")) or _clean(label.get("player")),
        "meta_market": _clean(feature.get("market")) or _clean(label.get("market")),
        "meta_book": _clean(feature.get("book")),
        "meta_model_version": "",
        "meta_source": _clean(feature.get("source")),
        "meta_source_row_id": _clean(feature.get("source_row_id")) or _clean(label.get("source_row_id")),
        "meta_prop_key": _clean(feature.get("prop_key")) or _clean(label.get("prop_key")),
        "meta_team": _clean(feature.get("team")) or _clean(label.get("team")),
        "meta_opponent": _clean(feature.get("opponent")) or _clean(label.get("opponent")),
        "meta_season": _clean(feature.get("season")) or _clean(label.get("season")),
    }


def _target_payload(label: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "target_result": label.get("result", ""),
        "target_hit": label.get("hit", False),
        "target_push": label.get("push", False),
        "target_void": label.get("void", False),
        "target_actual_value": label.get("actual_value", ""),
        "target_grade": label.get("grade", ""),
        "target_profit_1u": label.get("profit_1u", ""),
        "target_graded_at": label.get("graded_at", ""),
        "target_label_status": label.get("label_status", ""),
        "target_label_reason": label.get("label_reason", ""),
    }


def _flatten_structured(row: Mapping[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
    features = row.get("features") if isinstance(row.get("features"), Mapping) else {}
    targets = row.get("targets") if isinstance(row.get("targets"), Mapping) else {}
    label = row.get("label") if isinstance(row.get("label"), Mapping) else {}
    return {**dict(metadata), **dict(features), **dict(targets), **dict(label)}


def _normalize_existing_training_rows(rows: Any, warnings: list[str]) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    normalized: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        try:
            normalized.append(_normalize_training_row_contract(dict(raw)))
        except ValueError as error:
            warnings.append(f"Existing training row failed Sprint 18 contract: {error}")
    return normalized


def _normalize_training_row_contract(row: Mapping[str, Any]) -> dict[str, Any]:
    if any(is_prefixed_training_column(str(key)) for key in row):
        prefixed = {str(key): value for key, value in row.items() if is_prefixed_training_column(str(key))}
        assert_training_row_contract(prefixed)
        return _complete_training_row(prefixed)

    blocked = _unprefixed_blocked_fields(row)
    if blocked:
        raise ValueError(f"Unprefixed blocked fields are not allowed: {', '.join(sorted(blocked))}")

    metadata = {
        "meta_training_schema_version": _clean(row.get("training_schema_version")) or TRAINING_SCHEMA_VERSION,
        "meta_training_join_key": _clean(row.get("training_join_key")) or _join_key(row),
        "meta_feature_schema_version": _clean(row.get("feature_schema_version")) or FEATURE_SCHEMA_VERSION,
        "meta_label_schema_version": _clean(row.get("label_schema_version")) or LABEL_SCHEMA_VERSION,
        "meta_game_date": _clean(row.get("date")),
        "meta_game_id": _clean(row.get("game_market_game_id")),
        "meta_player": _clean(row.get("player")),
        "meta_market": _clean(row.get("market")),
        "meta_book": _clean(row.get("book")),
        "meta_model_version": _clean(row.get("model_version")),
        "meta_source": _clean(row.get("source")),
        "meta_source_row_id": _clean(row.get("source_row_id")),
        "meta_prop_key": _clean(row.get("prop_key")),
        "meta_team": _clean(row.get("team")),
        "meta_opponent": _clean(row.get("opponent")),
        "meta_season": _clean(row.get("season")),
    }
    features = {f"feature_{name}": row.get(name, "") for name in FEATURE_SOURCE_COLUMNS}
    targets = {name: row.get(name, "") for name in TARGET_COLUMNS}
    normalized = _complete_training_row({**metadata, **features, **targets})
    assert_training_row_contract(normalized)
    return normalized


def _complete_training_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **{name: row.get(name, "") for name in METADATA_COLUMNS},
        **{name: row.get(name, "") for name in FEATURE_COLUMNS},
        **{name: row.get(name, "") for name in TARGET_COLUMNS},
    }


def _structure_training_row(row: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    normalized = _normalize_training_row_contract(row)
    return split_training_row(normalized)


def _csv_columns(manifest: Mapping[str, Any]) -> list[str]:
    return (
        list(manifest.get("metadata_columns") or METADATA_COLUMNS)
        + list(manifest.get("feature_columns") or FEATURE_COLUMNS)
        + list(manifest.get("target_columns") or TARGET_COLUMNS)
    )


def _planned_training_paths(output_dir: Path, date_label: str, output_format: str) -> dict[str, Path]:
    selected = _normal_format(output_format)
    paths: dict[str, Path] = {}
    if selected in {"csv", "both"}:
        paths["csv"] = output_dir / f"player_prop_training_{date_label}.csv"
    if selected in {"json", "both"}:
        paths["json"] = output_dir / f"player_prop_training_{date_label}.json"
    paths["manifest"] = output_dir / f"player_prop_training_manifest_{date_label}.json"
    return paths


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field)) for field in fieldnames})


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _join_key(row: Mapping[str, Any]) -> str:
    return _clean(row.get("prop_key")) or _clean(row.get("source_row_id"))


def _blocked_fields(row: Mapping[str, Any]) -> set[str]:
    blocked = {name.lower() for name in blocked_feature_names()} | {"actual_value", "result", "hit", "push", "graded_at"}
    return {str(key) for key in row if str(key).lower() in blocked}


def _unprefixed_blocked_fields(row: Mapping[str, Any]) -> set[str]:
    return {field for field in _blocked_fields(row) if not is_target_column(field)}


def _training_contract_leaks(row: Mapping[str, Any]) -> set[str]:
    leaks: set[str] = set()
    for field in row:
        text = str(field)
        if is_feature_column(text):
            base = text[len("feature_") :]
            if base.lower() in {name.lower() for name in blocked_feature_names()}:
                leaks.add(text)
        elif not is_prefixed_training_column(text):
            leaks.add(text)
    return leaks


def _market_from_training_row(row: Mapping[str, Any]) -> str:
    return (
        _clean(row.get("feature_market"))
        or _clean(row.get("meta_market"))
        or _clean(row.get("market"))
        or "unknown"
    )


def _normal_source(source: str) -> str:
    text = _clean(source).lower().replace("_", "-") or DEFAULT_SOURCE
    if text in {"edge", "edgeboard"}:
        return "edge-board"
    if text in {"player", "player-board"}:
        return "playerboard"
    return text if text in {"playerboard", "edge-board", "both"} else DEFAULT_SOURCE


def _normal_format(value: str) -> str:
    text = _clean(value).lower() or "both"
    return text if text in {"csv", "json", "both"} else "both"


def _display_path(path: Path, settings: Settings) -> str:
    try:
        return str(Path("data") / path.resolve().relative_to(settings.data_dir.resolve())).replace("\\", "/")
    except (OSError, ValueError):
        try:
            return str(path.resolve().relative_to(settings.root_dir.resolve())).replace("\\", "/")
        except (OSError, ValueError):
            return str(path).replace("\\", "/")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
