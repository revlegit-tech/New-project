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
from mlb_app.services.game_market_feature_lookup_service import GameMarketFeatureLookupService
from mlb_app.services.ml_feature_schema import (
    FEATURE_SCHEMA_VERSION,
    assert_no_leakage_fields,
    blocked_feature_names,
    filter_safe_features,
    leakage_fields_in_payload,
    safe_feature_names,
    safe_game_market_feature_names,
)

DEFAULT_OUTPUT_RELATIVE_DIR = Path("warehouse") / "ml_features"
DEFAULT_SOURCE = "edge-board"
MAX_EXPORT_ROWS = 10000

EXPORT_FIELD_ORDER: tuple[str, ...] = tuple(safe_feature_names())


@dataclass(frozen=True)
class FeatureBuildResult:
    rows: list[dict[str, Any]]
    raw_rows: list[dict[str, Any]]
    manifest: dict[str, Any]


class MLFeatureExportService:
    """Build safe, auditable player-prop ML feature snapshots."""

    def __init__(
        self,
        *,
        settings: Settings = default_settings,
        playerboard_service: Any | None = None,
        edge_board_service: Any | None = None,
        game_market_feature_lookup_service: GameMarketFeatureLookupService | None = None,
    ) -> None:
        self.settings = settings
        self.playerboard_service = playerboard_service
        self.edge_board_service = edge_board_service
        self.game_market_feature_lookup_service = game_market_feature_lookup_service

    def build_features(
        self,
        *,
        date_label: str,
        season: int | None = None,
        source: str = DEFAULT_SOURCE,
        exported_at: datetime | None = None,
    ) -> FeatureBuildResult:
        exported_at = exported_at or datetime.now(timezone.utc)
        selected_date = _clean(date_label) or exported_at.date().isoformat()
        selected_season = int(season or self.settings.current_season)
        raw_rows, load_warnings = self._load_source_rows(date_label=selected_date, season=selected_season, source=source)
        raw_rows = raw_rows[:MAX_EXPORT_ROWS]
        raw_rows = self._ensure_game_market_context(raw_rows)

        blocked_seen: set[str] = set()
        feature_rows: list[dict[str, Any]] = []
        for raw in raw_rows:
            blocked_seen.update(leakage_fields_in_payload(raw))
            source_name = _clean(raw.get("_ml_export_source")) or _normal_source(source)
            row = _normalize_feature_row(
                raw,
                date_label=selected_date,
                season=selected_season,
                source=source_name,
                exported_at=exported_at,
            )
            safe_row = filter_safe_features(row)
            assert_no_leakage_fields(safe_row)
            feature_rows.append(safe_row)

        manifest = self._manifest(
            rows=feature_rows,
            raw_rows=raw_rows,
            date_label=selected_date,
            season=selected_season,
            source=_normal_source(source),
            exported_at=exported_at,
            blocked_seen=blocked_seen,
            warnings=load_warnings,
            dry_run=True,
            output_format="both",
            output_dir=self.default_output_dir(),
        )
        return FeatureBuildResult(rows=feature_rows, raw_rows=raw_rows, manifest=manifest)

    def export(
        self,
        *,
        date_label: str,
        season: int | None = None,
        source: str = DEFAULT_SOURCE,
        output_format: str = "both",
        dry_run: bool = False,
        output_dir: Path | str | None = None,
    ) -> dict[str, Any]:
        selected_format = _normal_format(output_format)
        target_dir = Path(output_dir) if output_dir is not None else self.default_output_dir()
        build = self.build_features(date_label=date_label, season=season, source=source)
        manifest = self._manifest(
            rows=build.rows,
            raw_rows=build.raw_rows,
            date_label=build.manifest["date"],
            season=int(build.manifest["season"]),
            source=_normal_source(source),
            exported_at=_parse_exported_at(build.manifest["exported_at"]),
            blocked_seen=set(build.manifest.get("leakage_blocked_fields") or []),
            warnings=list(build.manifest.get("warnings") or []),
            dry_run=dry_run,
            output_format=selected_format,
            output_dir=target_dir,
        )
        if dry_run:
            return manifest

        target_dir.mkdir(parents=True, exist_ok=True)
        paths = _planned_paths(target_dir, str(manifest["date"]), selected_format)
        if "csv" in paths:
            _write_feature_csv(paths["csv"], build.rows)
        if "json" in paths:
            _write_feature_json(paths["json"], manifest=manifest, rows=build.rows)
        _write_json(paths["manifest"], manifest)
        manifest["written"] = {key: _display_path(path, self.settings) for key, path in paths.items()}
        manifest["output_paths"] = dict(manifest["written"])
        return manifest

    def preview(
        self,
        *,
        date_label: str,
        season: int | None = None,
        limit: int = 25,
        source: str = DEFAULT_SOURCE,
    ) -> dict[str, Any]:
        selected_date = _clean(date_label) or datetime.now(timezone.utc).date().isoformat()
        existing_rows, existing_warnings = _read_existing_export(self.settings, selected_date)
        if existing_rows:
            rows = existing_rows
            warnings = existing_warnings
        else:
            build = self.build_features(date_label=selected_date, season=season, source=source)
            rows = build.rows
            warnings = list(build.manifest.get("warnings") or [])
        preview_rows = rows[: max(0, min(int(limit), 250))]
        for row in preview_rows:
            assert_no_leakage_fields(row)
        return {
            "status": "ok",
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "date": selected_date,
            "row_count": len(rows),
            "rows": preview_rows,
            "warnings": warnings,
        }

    def status_payload(self) -> dict[str, Any]:
        latest = latest_ml_feature_export_status(self.settings)
        warnings = list(latest.get("warnings") or [])
        if not latest.get("latest_export_date"):
            warnings.append("No ML feature exports found yet.")
        return {
            "status": "ok",
            "enabled": True,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "database": {
                "enabled": bool(self.settings.db_enabled),
                "fallback_to_csv": bool(self.settings.db_fallback_to_csv),
                "fallback_mode": latest.get("fallback_mode") or "no_exports",
            },
            "latest_export_date": latest.get("latest_export_date") or "",
            "latest_export_row_count": int(latest.get("latest_export_rows") or 0),
            "safe_feature_count": len(safe_feature_names()),
            "blocked_feature_count": len(blocked_feature_names()),
            "game_market_feature_availability": {
                "feature_count": len(safe_game_market_feature_names()),
                "coverage_pct": latest.get("game_market_feature_coverage_pct"),
            },
            "warnings": _dedupe(warnings)[:20],
        }

    def default_output_dir(self) -> Path:
        return self.settings.data_dir / DEFAULT_OUTPUT_RELATIVE_DIR

    def _load_source_rows(self, *, date_label: str, season: int, source: str) -> tuple[list[dict[str, Any]], list[str]]:
        selected_source = _normal_source(source)
        rows: list[dict[str, Any]] = []
        warnings: list[str] = []
        sources = ("playerboard", "edge-board") if selected_source == "both" else (selected_source,)
        for source_name in sources:
            try:
                if source_name == "playerboard":
                    loaded = self._load_playerboard_rows(date_label=date_label, season=season)
                elif source_name == "edge-board":
                    loaded = self._load_edge_board_rows(date_label=date_label, season=season)
                else:
                    loaded = []
                    warnings.append(f"Unsupported source: {source_name}")
            except Exception as error:
                loaded = []
                warnings.append(f"{source_name} snapshot unavailable: {type(error).__name__}: {error}")
            for row in loaded:
                item = dict(row)
                item["_ml_export_source"] = source_name
                rows.append(item)
        if not rows:
            warnings.append(f"No rows found for ML feature export on {date_label}.")
        return rows, warnings

    def _load_playerboard_rows(self, *, date_label: str, season: int) -> list[dict[str, Any]]:
        service = self.playerboard_service
        if service is None:
            from mlb_app.services.playerboard_service import PlayerboardService

            service = PlayerboardService(
                game_market_feature_lookup_service=self.game_market_feature_lookup_service,
                settings=self.settings,
            )
        query = {"season": [str(season)], "date": [date_label]}
        snapshot_for_query = getattr(service, "snapshot_for_query", None)
        if callable(snapshot_for_query):
            snapshot = snapshot_for_query(query)
            return [dict(row) for row in getattr(snapshot, "rows", []) if isinstance(row, Mapping)]
        payload = service.board_payload(query) if hasattr(service, "board_payload") else service.payload(query)
        return _rows_from_payload(payload)

    def _load_edge_board_rows(self, *, date_label: str, season: int) -> list[dict[str, Any]]:
        artifact_rows = _read_edge_board_artifact(self.settings.data_dir, date_label)
        if artifact_rows:
            return artifact_rows
        service = self.edge_board_service
        if service is None:
            from mlb_app.services.edge_board_service import EdgeBoardService
            from mlb_app.services.playerboard_service import PlayerboardService

            playerboard_service = self.playerboard_service or PlayerboardService(
                game_market_feature_lookup_service=self.game_market_feature_lookup_service,
                settings=self.settings,
            )
            service = EdgeBoardService(
                playerboard_service=playerboard_service,
                game_market_feature_lookup_service=self.game_market_feature_lookup_service,
                settings=self.settings,
            )
        payload = service.payload({"season": [str(season)], "date": [date_label], "limit": [str(MAX_EXPORT_ROWS)]})
        return _rows_from_payload(payload)

    def _ensure_game_market_context(self, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        output = [dict(row) for row in rows]
        if not output:
            return []
        if all("game_market_enrichment_status" in row for row in output):
            return output
        if self.game_market_feature_lookup_service is not None:
            try:
                return self.game_market_feature_lookup_service.enrich_rows(output)
            except Exception:
                pass
        return [
            dict(row) | {"game_market_available": False, "game_market_enrichment_status": "warehouse_unavailable"}
            for row in output
        ]

    def _manifest(
        self,
        *,
        rows: Sequence[Mapping[str, Any]],
        raw_rows: Sequence[Mapping[str, Any]],
        date_label: str,
        season: int,
        source: str,
        exported_at: datetime,
        blocked_seen: set[str],
        warnings: list[str],
        dry_run: bool,
        output_format: str,
        output_dir: Path,
    ) -> dict[str, Any]:
        market_counts = Counter(_clean(row.get("market")) or "unknown" for row in rows)
        source_counts = Counter(_clean(row.get("source")) or "unknown" for row in rows)
        matched = sum(1 for row in rows if _clean(row.get("game_market_enrichment_status")) == "matched" or bool(row.get("game_market_available")))
        row_count = len(rows)
        coverage = round((matched / row_count) * 100.0, 2) if row_count else 0.0
        planned = _planned_paths(output_dir, date_label, output_format)
        leakage_check_passed = True
        try:
            for row in rows:
                assert_no_leakage_fields(row)
        except ValueError:
            leakage_check_passed = False
        return {
            "status": "ok",
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "exported_at": exported_at.isoformat(),
            "date": date_label,
            "season": int(season),
            "source": source,
            "format": output_format,
            "dry_run": bool(dry_run),
            "row_count": row_count,
            "raw_row_count": len(raw_rows),
            "market_counts": dict(sorted(market_counts.items())),
            "source_counts": dict(sorted(source_counts.items())),
            "safe_feature_count": len(safe_feature_names()),
            "blocked_feature_count": len(blocked_feature_names()),
            "export_column_count": len(EXPORT_FIELD_ORDER),
            "game_market_match_count": matched,
            "game_market_missing_count": max(0, row_count - matched),
            "game_market_coverage_pct": coverage,
            "leakage_blocked_fields": sorted(blocked_seen),
            "leakage_blocked_field_count": len(blocked_seen),
            "leakage_check_passed": leakage_check_passed,
            "output_paths": {key: _display_path(path, self.settings) for key, path in planned.items()},
            "warnings": _dedupe(warnings)[:25],
        }


def latest_ml_feature_export_status(settings: Settings = default_settings) -> dict[str, Any]:
    export_dir = settings.data_dir / DEFAULT_OUTPUT_RELATIVE_DIR
    manifest_paths = sorted(export_dir.glob("ml_feature_export_manifest_*.json"), key=_safe_mtime, reverse=True)
    if not manifest_paths:
        return {
            "enabled": True,
            "latest_export_date": "",
            "latest_export_rows": 0,
            "latest_manifest_path": "",
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "leakage_check_passed": None,
            "game_market_feature_coverage_pct": None,
            "fallback_mode": "no_exports",
            "warnings": ["No ML feature export manifests found."],
        }
    latest_path = manifest_paths[0]
    try:
        manifest = json.loads(latest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {
            "enabled": True,
            "latest_export_date": "",
            "latest_export_rows": 0,
            "latest_manifest_path": _display_path(latest_path, settings),
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "leakage_check_passed": False,
            "game_market_feature_coverage_pct": None,
            "fallback_mode": "manifest_unreadable",
            "warnings": [f"Latest ML feature export manifest is unreadable: {type(error).__name__}: {error}"],
        }
    return {
        "enabled": True,
        "latest_export_date": _clean(manifest.get("date")),
        "latest_export_rows": int(manifest.get("row_count") or 0),
        "latest_manifest_path": _display_path(latest_path, settings),
        "feature_schema_version": _clean(manifest.get("feature_schema_version")) or FEATURE_SCHEMA_VERSION,
        "leakage_check_passed": bool(manifest.get("leakage_check_passed")),
        "game_market_feature_coverage_pct": manifest.get("game_market_coverage_pct"),
        "fallback_mode": "generated_artifact",
        "warnings": [str(item) for item in manifest.get("warnings", []) if str(item).strip()],
    }


def _normalize_feature_row(
    row: Mapping[str, Any],
    *,
    date_label: str,
    season: int,
    source: str,
    exported_at: datetime,
) -> dict[str, Any]:
    feature: dict[str, Any] = {
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "exported_at": exported_at.isoformat(),
        "source": source,
        "source_row_id": _clean(_first(row, "id", "propKey", "prop_key")),
        "prop_key": _clean(_first(row, "propKey", "prop_key", "id")),
        "date": _clean(_first(row, "date", "game_date", "slateDate")) or date_label,
        "season": _clean(_first(row, "season")) or int(season),
        "player": _clean(_first(row, "player", "playerName", "name")),
        "team": _clean(_first(row, "team", "team_abbr", "teamAbbr", "teamCode")),
        "opponent": _clean(_first(row, "opponent", "opponent_abbr", "opponentAbbr", "opponentCode")),
        "market": _clean(_first(row, "market", "market_key", "marketKey")),
        "side": _clean(_first(row, "side", "rawLabel", "pickSide", "outcome")),
        "line": _first(row, "line", "propLine"),
        "book": _clean(_first(row, "book", "sportsbook", "bestBook", "bookmaker", "sourceBook")),
        "american_odds": _first(row, "americanOdds", "american_odds", "odds", "price"),
        "implied_probability_percent": _first(
            row,
            "impliedProbabilityPercent",
            "sportsbookImpliedPercent",
            "bookImpliedProbabilityPercent",
            "impliedPercent",
            "implied_probability_percent",
        ),
        "model_probability_percent": _first(
            row,
            "modelProbabilityPercent",
            "finalProbabilityPercent",
            "probabilityPercent",
            "model_probability_percent",
            "probability",
        ),
    }
    hit_summary = _hit_rate_summary(_first(row, "hitRates", "hit_rates", "hitRateSummary"))
    if hit_summary:
        feature["hit_rate_summary"] = hit_summary
    for name in safe_game_market_feature_names():
        if name in row:
            feature[name] = row.get(name)
    feature.setdefault("game_market_available", False)
    feature.setdefault("game_market_enrichment_status", "warehouse_unavailable")
    return feature


def _read_existing_export(settings: Settings, date_label: str) -> tuple[list[dict[str, Any]], list[str]]:
    export_dir = settings.data_dir / DEFAULT_OUTPUT_RELATIVE_DIR
    json_path = export_dir / f"player_prop_features_{date_label}.json"
    csv_path = export_dir / f"player_prop_features_{date_label}.csv"
    warnings: list[str] = []
    if json_path.exists():
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            rows = payload.get("rows") if isinstance(payload, dict) else payload
            return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else [], warnings
        except (OSError, json.JSONDecodeError) as error:
            warnings.append(f"Existing JSON export unreadable: {type(error).__name__}: {error}")
    if csv_path.exists():
        try:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                return [dict(row) for row in csv.DictReader(handle)], warnings
        except OSError as error:
            warnings.append(f"Existing CSV export unreadable: {type(error).__name__}: {error}")
    return [], warnings


def _rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    if not isinstance(payload, Mapping):
        return []
    rows = payload.get("rows") or payload.get("top") or payload.get("items")
    return [dict(row) for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []


def _read_edge_board_artifact(data_dir: Path, date_label: str) -> list[dict[str, Any]]:
    root = data_dir / "edge_board"
    json_path = root / f"edge_board_{date_label}.json"
    csv_path = root / f"edge_board_{date_label}.csv"
    if json_path.exists():
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            return _rows_from_payload(payload)
        except (OSError, json.JSONDecodeError):
            return []
    if csv_path.exists():
        try:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                return [dict(row) for row in csv.DictReader(handle)]
        except OSError:
            return []
    return []


def _planned_paths(output_dir: Path, date_label: str, output_format: str) -> dict[str, Path]:
    selected = _normal_format(output_format)
    paths: dict[str, Path] = {}
    if selected in {"csv", "both"}:
        paths["csv"] = output_dir / f"player_prop_features_{date_label}.csv"
    if selected in {"json", "both"}:
        paths["json"] = output_dir / f"player_prop_features_{date_label}.json"
    paths["manifest"] = output_dir / f"ml_feature_export_manifest_{date_label}.json"
    return paths


def _write_feature_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(EXPORT_FIELD_ORDER), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field)) for field in EXPORT_FIELD_ORDER})


def _write_feature_json(path: Path, *, manifest: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> None:
    _write_json(path, {"feature_schema_version": FEATURE_SCHEMA_VERSION, "manifest": dict(manifest), "rows": list(rows)})


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _hit_rate_summary(value: Any) -> dict[str, Any]:
    parsed = _maybe_json(value)
    if isinstance(parsed, list):
        return {"available": True, "entry_count": len(parsed)}
    if not isinstance(parsed, Mapping):
        return {}
    summary: dict[str, Any] = {}
    blocked = blocked_feature_names()
    blocked_lower = {name.lower() for name in blocked}
    for key, item in parsed.items():
        text = str(key)
        if text in blocked or text.lower() in blocked_lower:
            continue
        if isinstance(item, (str, int, float, bool)) or item is None:
            summary[text] = item
    return summary


def _maybe_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = _clean(value)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and value != "":
            return value
    return ""


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _normal_source(source: str) -> str:
    text = _clean(source).lower().replace("_", "-") or DEFAULT_SOURCE
    if text in {"edge", "edgeboard"}:
        return "edge-board"
    if text in {"player", "player-board"}:
        return "playerboard"
    if text in {"playerboard", "edge-board", "both"}:
        return text
    return DEFAULT_SOURCE


def _normal_format(value: str) -> str:
    text = _clean(value).lower() or "both"
    return text if text in {"csv", "json", "both"} else "both"


def _parse_exported_at(value: Any) -> datetime:
    text = _clean(value)
    if not text:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _display_path(path: Path, settings: Settings) -> str:
    try:
        return str(Path("data") / path.resolve().relative_to(settings.data_dir.resolve())).replace("\\", "/")
    except (OSError, ValueError):
        try:
            return str(path.resolve().relative_to(settings.root_dir.resolve())).replace("\\", "/")
        except (OSError, ValueError):
            return str(path).replace("\\", "/")


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


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
