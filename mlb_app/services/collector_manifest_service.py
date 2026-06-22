from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from mlb_app.config import Settings, settings as default_settings

MAX_MANIFEST_FILE_LIST = 150
MAX_MANIFEST_ERRORS = 25
MAX_TRACEBACK_TAIL_CHARS = 4000

ARTIFACT_CRITICAL_PATHS: tuple[str, ...] = (
    "data/odds",
    "data/warehouse/odds_snapshots",
    "data/warehouse/raw",
    "data/warehouse/summaries",
    "data/warehouse/logs",
)

RAW_ARTIFACT_DIRS: tuple[str, ...] = (
    "odds",
    "warehouse/raw",
)

NORMALIZED_ARTIFACT_DIRS: tuple[str, ...] = (
    "playerboard",
    "edge_board",
    "backtests",
    "audit",
    "ml",
    "training",
    "cache/odds_movement",
)

WAREHOUSE_ARTIFACT_DIRS: tuple[str, ...] = (
    "warehouse/odds_snapshots",
    "warehouse/raw",
    "warehouse/summaries",
    "warehouse/logs",
)


@dataclass(frozen=True)
class CollectorManifestWriteResult:
    manifest: dict[str, Any]
    manifest_path: Path
    latest_path: Path


class CollectorManifestService:
    """Write and read compact collector manifests for production health checks."""

    def __init__(
        self,
        *,
        settings: Settings = default_settings,
        data_dir: Path | None = None,
        now_provider: Any | None = None,
    ) -> None:
        self.settings = settings
        self.data_dir = Path(data_dir or settings.data_dir)
        self.health_dir = self.data_dir / "health"
        self.manifest_dir = self.health_dir / "collector_manifests"
        self.latest_path = self.health_dir / "latest_collector_manifest.json"
        self._now_provider = now_provider

    def write_manifest(
        self,
        summary: dict[str, Any],
        *,
        requested_markets: Iterable[str] | None = None,
    ) -> CollectorManifestWriteResult:
        manifest = self.build_manifest(summary, requested_markets=requested_markets)
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        self.latest_path.parent.mkdir(parents=True, exist_ok=True)

        date_label = _safe_label(manifest["date"] or self._now().date().isoformat())
        run_id = _safe_label(manifest["run_id"] or self._now().strftime("%Y%m%dT%H%M%SZ"))
        manifest_path = self.manifest_dir / f"collector_manifest_{date_label}_{run_id}.json"

        _atomic_write_json(manifest_path, manifest)
        _atomic_write_json(self.latest_path, manifest)
        return CollectorManifestWriteResult(manifest=manifest, manifest_path=manifest_path, latest_path=self.latest_path)

    def build_manifest(
        self,
        summary: dict[str, Any],
        *,
        requested_markets: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        date_label = str(summary.get("date") or "")
        result = _as_dict(summary.get("result"))
        data_hub = _as_dict(result.get("dataHub"))
        logs = _as_dict(result.get("logs"))
        playerboard = _as_dict(summary.get("playerboard"))

        raw_files = self._files_for_date(RAW_ARTIFACT_DIRS, date_label)
        normalized_files = self._files_for_date(NORMALIZED_ARTIFACT_DIRS, date_label)
        warehouse_files = self._files_for_date(WAREHOUSE_ARTIFACT_DIRS, date_label)
        present, missing = self._artifact_critical_paths()
        warnings = _dedupe_text(_collect_warnings(summary))
        errors = _dedupe_text(_collect_errors(summary))[:MAX_MANIFEST_ERRORS]
        playerboard_path = self.data_dir / "playerboard" / f"playerboard_{_season(date_label)}.csv"
        playerboard_rows, market_counts = self._playerboard_counts(playerboard_path, date_label)

        manifest = {
            "run_id": str(summary.get("runId") or summary.get("run_id") or ""),
            "date": date_label,
            "run_type": str(summary.get("runType") or summary.get("run_type") or ""),
            "started_at": str(summary.get("startedAt") or summary.get("started_at") or ""),
            "finished_at": str(summary.get("finishedAt") or summary.get("finished_at") or ""),
            "success": bool(summary.get("success")),
            "requested_markets": [str(market).strip() for market in (requested_markets or []) if str(market).strip()],
            "source_counts": _numeric_counts(data_hub) | _numeric_counts(logs),
            "market_counts": market_counts,
            "playerboard_rows": _first_int(
                playerboard.get("rowCount"),
                playerboard.get("rowsSaved"),
                playerboard.get("rows"),
                playerboard_rows,
            ),
            "edge_board_rows": self._latest_edge_board_rows(date_label),
            "raw_files_written": raw_files,
            "normalized_files_written": normalized_files,
            "warehouse_files_written": warehouse_files,
            "artifact_critical_files_present": present,
            "artifact_critical_files_missing": missing,
            "warnings": warnings,
            "errors": errors,
            "traceback_tail": _tail(str(summary.get("traceback") or "")),
            "freshness_status": _manifest_status(success=bool(summary.get("success")), missing=missing, warnings=warnings, errors=errors),
        }
        return manifest

    def load_latest_manifest(self) -> dict[str, Any] | None:
        for path in self._latest_candidates():
            payload = _read_json(path)
            if isinstance(payload, dict):
                return _coerce_manifest(payload)
        return None

    def _latest_candidates(self) -> list[Path]:
        candidates: list[Path] = []
        if self.latest_path.exists():
            candidates.append(self.latest_path)
        if self.manifest_dir.exists():
            manifests = sorted(
                self.manifest_dir.glob("collector_manifest_*.json"),
                key=lambda path: _safe_mtime(path),
                reverse=True,
            )
            candidates.extend(path for path in manifests if path not in candidates)
        return candidates

    def _files_for_date(self, folders: Iterable[str], date_label: str) -> list[str]:
        files: list[str] = []
        for folder in folders:
            root = self.data_dir / folder
            if not root.exists():
                continue
            for path in sorted(root.rglob("*"), key=lambda item: str(item).lower()):
                if not path.is_file():
                    continue
                if date_label and date_label not in path.name:
                    continue
                files.append(_relative_data_path(path, self.data_dir))
                if len(files) >= MAX_MANIFEST_FILE_LIST:
                    return files
        return files

    def _artifact_critical_paths(self) -> tuple[list[str], list[str]]:
        present: list[str] = []
        missing: list[str] = []
        for relative in ARTIFACT_CRITICAL_PATHS:
            suffix = relative.removeprefix("data/").lstrip("/")
            path = self.data_dir / suffix if relative.startswith("data/") else self.data_dir / relative
            if path.exists() and (path.is_file() or any(path.iterdir())):
                present.append(relative)
            else:
                missing.append(relative)
        return present, missing

    def _playerboard_counts(self, path: Path, date_label: str) -> tuple[int, dict[str, int]]:
        if not path.exists():
            return 0, {}
        rows = 0
        market_counts: dict[str, int] = {}
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    if date_label and str(row.get("date") or "").strip() != date_label:
                        continue
                    rows += 1
                    market = str(row.get("market") or row.get("market_key") or "").strip()
                    if market:
                        market_counts[market] = market_counts.get(market, 0) + 1
        except OSError:
            return 0, {}
        return rows, dict(sorted(market_counts.items()))

    def _latest_edge_board_rows(self, date_label: str) -> int | None:
        edge_dir = self.data_dir / "edge_board"
        if not edge_dir.exists():
            return None
        candidates = sorted(
            (
                path
                for pattern in ("*.csv", "*.json")
                for path in edge_dir.rglob(pattern)
                if not date_label or date_label in path.name
            ),
            key=lambda path: _safe_mtime(path),
            reverse=True,
        )
        if not candidates:
            return None
        latest = candidates[0]
        if latest.suffix.lower() == ".json":
            return _count_json_rows(latest)
        return _count_csv_rows(latest)

    def _now(self) -> datetime:
        if self._now_provider is not None:
            value = self._now_provider()
            if isinstance(value, datetime):
                return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _collect_warnings(value: Any) -> list[str]:
    warnings: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "warnings" and isinstance(item, list):
                warnings.extend(str(entry) for entry in item if str(entry).strip())
            elif key == "status" and str(item).lower() == "warning":
                warnings.append("Collector step reported warning status.")
            else:
                warnings.extend(_collect_warnings(item))
    elif isinstance(value, list):
        for item in value:
            warnings.extend(_collect_warnings(item))
    return warnings


def _collect_errors(value: Any) -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"error", "errors"}:
                if isinstance(item, list):
                    errors.extend(str(entry) for entry in item if str(entry).strip())
                elif str(item).strip():
                    errors.append(str(item))
            else:
                errors.extend(_collect_errors(item))
    elif isinstance(value, list):
        for item in value:
            errors.extend(_collect_errors(item))
    return errors


def _coerce_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": str(payload.get("run_id") or ""),
        "date": str(payload.get("date") or ""),
        "run_type": str(payload.get("run_type") or ""),
        "started_at": str(payload.get("started_at") or ""),
        "finished_at": str(payload.get("finished_at") or ""),
        "success": bool(payload.get("success")),
        "requested_markets": _string_list(payload.get("requested_markets")),
        "source_counts": _int_dict(payload.get("source_counts")),
        "market_counts": _int_dict(payload.get("market_counts")),
        "playerboard_rows": _optional_int(payload.get("playerboard_rows")) or 0,
        "edge_board_rows": _optional_int(payload.get("edge_board_rows")),
        "raw_files_written": _string_list(payload.get("raw_files_written")),
        "normalized_files_written": _string_list(payload.get("normalized_files_written")),
        "warehouse_files_written": _string_list(payload.get("warehouse_files_written")),
        "artifact_critical_files_present": _string_list(payload.get("artifact_critical_files_present")),
        "artifact_critical_files_missing": _string_list(payload.get("artifact_critical_files_missing")),
        "warnings": _string_list(payload.get("warnings")),
        "errors": _string_list(payload.get("errors")),
        "traceback_tail": _tail(str(payload.get("traceback_tail") or "")),
        "freshness_status": str(payload.get("freshness_status") or "missing"),
    }


def _count_csv_rows(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return sum(1 for _ in csv.DictReader(handle))
    except OSError:
        return 0


def _count_json_rows(path: Path) -> int:
    payload = _read_json(path)
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("rows", "top", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
    return 0


def _dedupe_text(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _first_int(*values: Any) -> int:
    for value in values:
        parsed = _optional_int(value)
        if parsed is not None:
            return parsed
    return 0


def _int_dict(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, item in value.items():
        parsed = _optional_int(item)
        if parsed is not None:
            result[str(key)] = parsed
    return result


def _manifest_status(*, success: bool, missing: list[str], warnings: list[str], errors: list[str]) -> str:
    if missing:
        return "missing"
    if not success or errors:
        return "warning"
    if warnings:
        return "warning"
    return "fresh"


def _numeric_counts(*payloads: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for payload in payloads:
        for key, value in payload.items():
            parsed = _optional_int(value)
            if parsed is not None:
                counts[str(key)] = parsed
    return counts


def _optional_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return int(value)
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _relative_data_path(path: Path, data_dir: Path) -> str:
    try:
        return str(Path("data") / path.resolve().relative_to(data_dir.resolve())).replace("\\", "/")
    except ValueError:
        return path.name


def _safe_label(value: str) -> str:
    text = str(value or "").strip()
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text)[:120] or "unknown"


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _season(date_label: str) -> str:
    return str(date_label or "")[:4] or str(datetime.now(timezone.utc).year)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _tail(value: str) -> str:
    return value[-MAX_TRACEBACK_TAIL_CHARS:] if value else ""
