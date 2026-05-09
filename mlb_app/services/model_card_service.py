from __future__ import annotations

import copy
import json
import math
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Hashable, Iterable

from mlb_app.config import Settings, settings as default_settings
from mlb_app.repositories.csv_store import CsvStore
from mlb_app.repositories.model_store import normalize_market_key
from mlb_app.services.board_cache import FileSignature
from mlb_app.services.grading_state_service import GradingStateService
from mlb_app.services.model_readiness_service import ModelReadinessService
from mlb_app.services.model_registry_service import DEFAULT_MARKETS, ModelRegistryService

MODEL_CARD_VERSION = "2026-05-trust-card-v1"


@dataclass(frozen=True)
class BacktestMetrics:
    graded: int = 0
    wins: int = 0
    losses: int = 0
    pushes: int = 0
    profit_units: float | None = None
    roi_percent: float | None = None
    win_rate_percent: float | None = None
    brier_score: float | None = None
    log_loss: float | None = None
    avg_clv_percent: float | None = None
    source: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "graded": self.graded,
            "wins": self.wins,
            "losses": self.losses,
            "pushes": self.pushes,
            "profitUnits": round(self.profit_units, 2) if self.profit_units is not None else None,
            "roiPercent": round(self.roi_percent, 2) if self.roi_percent is not None else None,
            "winRatePercent": round(self.win_rate_percent, 2) if self.win_rate_percent is not None else None,
            "brierScore": round(self.brier_score, 4) if self.brier_score is not None else None,
            "logLoss": round(self.log_loss, 4) if self.log_loss is not None else None,
            "avgClvPercent": round(self.avg_clv_percent, 2) if self.avg_clv_percent is not None else None,
            "source": self.source,
        }


@dataclass(frozen=True)
class ModelSnapshot:
    """Shared model-card inputs loaded once per TTL window.

    The snapshot is process-local and mtime-aware. It avoids repeatedly loading
    registry, grading, and backtest state when EdgeBoard enriches many markets
    or PropDetail renders multiple drilldowns from cached board rows.
    """

    registry: dict[str, Any]
    grading: dict[str, Any]
    backtest_source: str
    backtest_rows: tuple[dict[str, Any], ...]
    market_statuses: dict[str, dict[str, Any]] = field(default_factory=dict)
    loaded_at: float = 0.0
    signatures: tuple[FileSignature, ...] = field(default_factory=tuple)

    @property
    def latest_graded_date(self) -> str:
        return str(self.grading.get("latestFullyGradedDate") or "")


@dataclass(frozen=True)
class ModelSnapshotCacheResult:
    snapshot: ModelSnapshot
    hit: bool
    reason: str
    key: Hashable
    age_seconds: float
    ttl_remaining_seconds: float


@dataclass
class _ModelSnapshotCacheEntry:
    snapshot: ModelSnapshot
    created_at: float
    ttl_seconds: float
    signatures: tuple[FileSignature, ...]
    hits: int = 0
    last_hit_at: float | None = None

    def age_seconds(self, now: float) -> float:
        return max(0.0, now - self.created_at)

    def ttl_remaining_seconds(self, now: float) -> float:
        return max(0.0, self.ttl_seconds - self.age_seconds(now))


class ModelSnapshotCache:
    """Thread-safe, mtime-aware cache for shared model-card inputs."""

    def __init__(self, *, ttl_seconds: float = 30.0, now: Callable[[], float] | None = None) -> None:
        self.ttl_seconds = float(ttl_seconds)
        self._now = now or time.monotonic
        self._lock = threading.RLock()
        self._key_locks: dict[Hashable, threading.RLock] = {}
        self._entries: dict[Hashable, _ModelSnapshotCacheEntry] = {}
        self._hits = 0
        self._misses = 0
        self._builds = 0
        self._invalidations = 0

    def get(self, key: Hashable, *, dependency_paths: Iterable[str | Path] = ()) -> ModelSnapshotCacheResult | None:
        signatures = _file_signatures(dependency_paths)
        now = self._now()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                return None
            if entry.age_seconds(now) > entry.ttl_seconds:
                self._entries.pop(key, None)
                self._misses += 1
                self._invalidations += 1
                return None
            if entry.signatures != signatures:
                self._entries.pop(key, None)
                self._misses += 1
                self._invalidations += 1
                return None
            entry.hits += 1
            entry.last_hit_at = now
            self._hits += 1
            return ModelSnapshotCacheResult(
                snapshot=copy.deepcopy(entry.snapshot),
                hit=True,
                reason="hit",
                key=key,
                age_seconds=entry.age_seconds(now),
                ttl_remaining_seconds=entry.ttl_remaining_seconds(now),
            )

    def get_or_build(
        self,
        key: Hashable,
        builder: Callable[[tuple[FileSignature, ...]], ModelSnapshot],
        *,
        dependency_paths: Iterable[str | Path] = (),
        ttl_seconds: float | None = None,
    ) -> ModelSnapshotCacheResult:
        dependency_paths = tuple(dependency_paths)
        cached = self.get(key, dependency_paths=dependency_paths)
        if cached is not None:
            return cached

        key_lock = self._key_lock_for(key)
        with key_lock:
            cached = self.get(key, dependency_paths=dependency_paths)
            if cached is not None:
                return cached
            signatures = _file_signatures(dependency_paths)
            snapshot = builder(signatures)
            ttl = float(self.ttl_seconds if ttl_seconds is None else ttl_seconds)
            now = self._now()
            entry = _ModelSnapshotCacheEntry(
                snapshot=copy.deepcopy(snapshot),
                created_at=now,
                ttl_seconds=ttl,
                signatures=signatures,
            )
            with self._lock:
                self._entries[key] = entry
                self._builds += 1
            return ModelSnapshotCacheResult(
                snapshot=copy.deepcopy(snapshot),
                hit=False,
                reason="miss_build",
                key=key,
                age_seconds=0.0,
                ttl_remaining_seconds=ttl,
            )

    def status(self) -> dict[str, Any]:
        now = self._now()
        with self._lock:
            return {
                "ttlSeconds": self.ttl_seconds,
                "entryCount": len(self._entries),
                "hits": self._hits,
                "misses": self._misses,
                "builds": self._builds,
                "invalidations": self._invalidations,
                "entries": [
                    {
                        "key": repr(key),
                        "ageSeconds": round(entry.age_seconds(now), 3),
                        "ttlRemainingSeconds": round(entry.ttl_remaining_seconds(now), 3),
                        "hitCount": entry.hits,
                        "dependencyCount": len(entry.signatures),
                    }
                    for key, entry in self._entries.items()
                ],
            }

    def invalidate(self, key: Hashable | None = None) -> None:
        with self._lock:
            if key is None:
                removed = len(self._entries)
                self._entries.clear()
            else:
                removed = 1 if key in self._entries else 0
                self._entries.pop(key, None)
            self._invalidations += removed

    def _key_lock_for(self, key: Hashable) -> threading.RLock:
        with self._lock:
            lock = self._key_locks.get(key)
            if lock is None:
                lock = threading.RLock()
                self._key_locks[key] = lock
            return lock


DEFAULT_MODEL_SNAPSHOT_CACHE = ModelSnapshotCache(ttl_seconds=30.0)


class ModelCardService:
    """Builds bettor-facing model cards from registry, grading, and backtest data.

    The card intentionally defaults to conservative status when data is missing.
    Missing ROI or calibration is not an error; it is a trust signal shown to the UI.
    """

    def __init__(
        self,
        settings: Settings = default_settings,
        *,
        csv_store: CsvStore | None = None,
        registry_service: ModelRegistryService | None = None,
        readiness_service: ModelReadinessService | None = None,
        grading_service: GradingStateService | None = None,
        snapshot_cache: ModelSnapshotCache | None = None,
    ) -> None:
        self.settings = settings
        self.csv_store = csv_store or CsvStore()
        self.registry_service = registry_service or ModelRegistryService(settings, csv_store=self.csv_store)
        self.readiness_service = readiness_service or ModelReadinessService(self.registry_service)
        self.grading_service = grading_service or GradingStateService(settings, data_dir=settings.data_dir)
        self.snapshot_cache = snapshot_cache or DEFAULT_MODEL_SNAPSHOT_CACHE

    def payload(self, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
        query = query or {}
        requested_market = _query_value(query, "market")
        markets = [normalize_market_key(requested_market)] if requested_market else list(DEFAULT_MARKETS)
        snapshot_result = self.snapshot()
        cards = [self.card_for_market(market, snapshot=snapshot_result.snapshot) for market in markets]
        return {
            "status": "ok",
            "version": MODEL_CARD_VERSION,
            "markets": cards,
            "summary": self.summary(cards),
            "policy": {
                "researchFirst": self.settings.research_mode_default,
                "requiresMarketSpecificArtifact": True,
                "requiresCalibrationForConfidentPick": True,
                "requiresLatestGradedDateForConfidentPick": True,
            },
            "modelSnapshot": {
                "hit": snapshot_result.hit,
                "reason": snapshot_result.reason,
                "ageSeconds": round(snapshot_result.age_seconds, 3),
                "ttlRemainingSeconds": round(snapshot_result.ttl_remaining_seconds, 3),
                "backtestSource": snapshot_result.snapshot.backtest_source,
                "backtestRows": len(snapshot_result.snapshot.backtest_rows),
            },
        }

    def snapshot(self) -> ModelSnapshotCacheResult:
        key = (
            "model-card-snapshot",
            str(self.settings.root_dir.resolve()),
            str(self.settings.data_dir.resolve()),
            str(self.settings.model_dir.resolve()),
            MODEL_CARD_VERSION,
        )
        dependency_paths = self._snapshot_dependency_paths()
        return self.snapshot_cache.get_or_build(key, self._build_snapshot, dependency_paths=dependency_paths)

    def _build_snapshot(self, signatures: tuple[FileSignature, ...]) -> ModelSnapshot:
        registry = self.registry_service.model_store.load_registry(self.settings.model_registry_path)
        grading = self.grading_service.payload({})
        source, rows = self._load_backtest_rows_from_disk()
        return ModelSnapshot(
            registry=registry,
            grading=grading,
            backtest_source=source,
            backtest_rows=tuple(rows),
            loaded_at=time.monotonic(),
            signatures=signatures,
        )

    def card_for_market(self, market: str, *, snapshot: ModelSnapshot | None = None) -> dict[str, Any]:
        key = normalize_market_key(market)
        snapshot = snapshot or self.snapshot().snapshot
        status = self._market_status_from_snapshot(key, snapshot)
        latest_graded_date = snapshot.latest_graded_date
        gate = self.readiness_service.gate_for_market(key, latest_graded_date=latest_graded_date).as_dict()
        entry = _registry_entry_from_snapshot(snapshot, key)
        backtest = self.backtest_metrics(key, snapshot=snapshot).as_dict()
        calibration = self.calibration_payload(entry, backtest)
        warnings = self.warnings_for(status, gate, backtest, calibration)
        production_status = gate["readiness"]

        production_ready = bool(gate.get("canShowConfidentPick")) and bool(status.get("hashVerified", True))
        return {
            "market": key,
            "marketName": _title(key),
            "version": status.get("version") or entry.get("version") or "",
            "status": status.get("status") or "not_ready",
            "modelStatus": status.get("status") or "not_ready",
            "productionStatus": production_status,
            "readinessLabel": gate["label"],
            "canShowConfidentPick": bool(gate["canShowConfidentPick"]),
            "reason": gate.get("reason") or status.get("reason") or "",
            "trainingRows": int(status.get("trainingRows") or 0),
            "positiveRows": int(status.get("positiveRows") or 0),
            "negativeRows": int(status.get("negativeRows") or 0),
            "classCounts": status.get("classCounts") or {},
            "trainedAt": str(status.get("trainedAt") or entry.get("trained_at") or ""),
            "latestGradedDate": latest_graded_date,
            "artifactExists": bool(status.get("artifactExists")),
            "metadataExists": bool(status.get("metadataExists")),
            "artifact": status.get("artifact") or "",
            "artifactSha256": status.get("artifactSha256") or "",
            "artifactHashPrefix": status.get("artifactHashPrefix") or "",
            "featuresSha256": status.get("featuresSha256") or "",
            "metricsSha256": status.get("metricsSha256") or "",
            "hashVerified": bool(status.get("hashVerified", False)),
            "artifactVerification": status.get("artifactVerification") or {},
            "featureSchema": self.feature_schema_payload(key, status),
            "calibrated": bool(status.get("calibrated")),
            "calibration": calibration,
            "backtest": backtest,
            "metrics": status.get("registryMetrics") or backtest,
            "trainingWindow": status.get("trainingWindow") or {},
            "lastPromotedAt": status.get("lastPromotedAt") or "",
            "knownLimitations": status.get("knownLimitations") or [],
            "researchOnly": not production_ready,
            "productionReady": production_ready,
            "trustWarnings": warnings,
            "decisionPolicy": self.decision_policy(gate, backtest, warnings),
        }

    def feature_schema_payload(self, market: str, status: dict[str, Any]) -> dict[str, Any]:
        try:
            schema = self.registry_service.artifact_repository.load_feature_schema(market)
        except Exception as error:
            return {"version": "unavailable", "featureCount": 0, "featureNames": [], "error": str(error)}
        payload = schema.as_dict()
        verification = (status.get("artifactVerification") or {}).get("features") or {}
        if verification:
            payload["verified"] = bool(verification.get("verified"))
            payload["verification"] = verification
        return payload

    def backtest_metrics(self, market: str, *, snapshot: ModelSnapshot | None = None) -> BacktestMetrics:
        if snapshot is None:
            snapshot = self.snapshot().snapshot
        source = snapshot.backtest_source
        rows = list(snapshot.backtest_rows)
        if not rows:
            return BacktestMetrics(source=source)

        key = normalize_market_key(market)
        market_rows = [row for row in rows if _same_market(row, key)]
        if not market_rows:
            return BacktestMetrics(source=source)

        summary_metrics = _summary_metrics(market_rows, source)
        if summary_metrics is not None:
            return summary_metrics

        graded_rows = [row for row in market_rows if _is_graded(row)]
        graded = len(graded_rows)
        if graded == 0:
            return BacktestMetrics(source=source)

        wins = sum(1 for row in graded_rows if _result_value(row) == "win")
        losses = sum(1 for row in graded_rows if _result_value(row) == "loss")
        pushes = sum(1 for row in graded_rows if _result_value(row) == "push")
        profit_values = [_float_or_none(_first(row, "profit", "profit_units", "profitUnits", "units")) for row in graded_rows]
        profit_values = [value for value in profit_values if value is not None]
        profit = sum(profit_values) if profit_values else None
        roi = profit / graded * 100 if profit is not None and graded else _float_or_none(_first(graded_rows[-1], "roi", "roi_percent", "roiPercent"))
        if roi is not None and abs(roi) <= 1.5:
            roi *= 100
        win_rate = wins / max(wins + losses, 1) * 100
        brier = _average_metric(graded_rows, "brier", "brier_score", "brierScore")
        log_loss = _average_metric(graded_rows, "log_loss", "logLoss")
        clv = _average_metric(graded_rows, "clv", "clv_percent", "closing_line_value", "avgClvPercent")
        if clv is not None and abs(clv) <= 1.5:
            clv *= 100

        return BacktestMetrics(
            graded=graded,
            wins=wins,
            losses=losses,
            pushes=pushes,
            profit_units=profit,
            roi_percent=roi,
            win_rate_percent=win_rate,
            brier_score=brier,
            log_loss=log_loss,
            avg_clv_percent=clv,
            source=source,
        )

    def calibration_payload(self, entry: dict[str, Any], backtest: dict[str, Any]) -> dict[str, Any]:
        buckets = entry.get("calibration_buckets") or entry.get("calibrationBuckets") or []
        if not isinstance(buckets, list):
            buckets = []
        return {
            "status": "calibrated" if entry.get("calibrated") else "uncalibrated",
            "brierScore": backtest.get("brierScore"),
            "logLoss": backtest.get("logLoss"),
            "buckets": buckets,
            "message": "Calibration metrics available." if entry.get("calibrated") else "Calibration is not yet verified; confidence labels stay conservative.",
        }

    def warnings_for(
        self,
        status: dict[str, Any],
        gate: dict[str, Any],
        backtest: dict[str, Any],
        calibration: dict[str, Any],
    ) -> list[str]:
        warnings: list[str] = []
        if not status.get("artifactExists"):
            warnings.append("Missing market-specific model artifact.")
        if not status.get("metadataExists"):
            warnings.append("Missing feature metadata for this market.")
        if int(status.get("trainingRows") or 0) < 100:
            warnings.append("Training sample is small; treat output as research only.")
        if not status.get("canTrain"):
            warnings.append("Training data does not currently satisfy minimum two-class requirements.")
        if not gate.get("latestGradedDate"):
            warnings.append("No latest fully graded slate is available.")
        if calibration.get("status") != "calibrated":
            warnings.append("Probability calibration is not verified.")
        roi = backtest.get("roiPercent")
        if roi is None:
            warnings.append("Market-level backtest ROI is unavailable.")
        elif float(roi) < 0:
            warnings.append("Recent market-level ROI is negative.")
        return warnings

    def decision_policy(self, gate: dict[str, Any], backtest: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
        if gate.get("canShowConfidentPick") and not warnings:
            primary = "Potential edge"
        elif gate.get("readiness") in {"experimental", "production_candidate", "production"}:
            primary = "Watchlist"
        else:
            primary = "No bet"
        return {
            "primaryLabel": primary,
            "allowedLabels": ["No bet", "Watchlist", "Model lean"] if primary != "Potential edge" else ["No bet", "Watchlist", "Model lean", "Potential edge"],
            "copy": "No confident pick language until artifact, grading, sample-size, and calibration gates pass.",
        }

    def summary(self, cards: list[dict[str, Any]]) -> dict[str, Any]:
        production = [card for card in cards if card.get("canShowConfidentPick")]
        missing = [card for card in cards if not card.get("artifactExists")]
        return {
            "totalMarkets": len(cards),
            "productionEligibleMarkets": len(production),
            "researchOnlyMarkets": len(cards) - len(production),
            "missingArtifacts": len(missing),
        }

    def _market_status_from_snapshot(self, market: str, snapshot: ModelSnapshot) -> dict[str, Any]:
        key = normalize_market_key(market)
        cached = snapshot.market_statuses.get(key)
        if cached is not None:
            return copy.deepcopy(cached)

        status = self.registry_service.market_status(key)
        snapshot.market_statuses[key] = copy.deepcopy(status)
        return status

    def _load_backtest_rows_from_disk(self) -> tuple[str, list[dict[str, Any]]]:
        for path in self._backtest_candidates():
            rows = _read_csv_rows_cached(self.csv_store, path)
            if rows:
                return str(path), rows
        summary_json = self.settings.data_dir / "health" / "latest_backtest_summary.json"
        if summary_json.exists():
            try:
                payload = json.loads(summary_json.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return str(summary_json), []
            markets = payload.get("markets") if isinstance(payload, dict) else None
            if isinstance(markets, list):
                return str(summary_json), [row for row in markets if isinstance(row, dict)]
        return "", []

    def _snapshot_dependency_paths(self) -> tuple[Path, ...]:
        paths = [self.settings.model_registry_path, self.grading_service.latest_summary_path]
        paths.extend(self._backtest_candidates())
        paths.append(self.settings.data_dir / "health" / "latest_backtest_summary.json")
        return tuple(paths)

    def _backtest_candidates(self) -> list[Path]:
        data = self.settings.data_dir
        return [
            data / "backtests" / "playerboard_backtest_summary.csv",
            data / "backtests" / "playerboard_backtest.csv",
            data / "backtest" / "playerboard_backtest_summary.csv",
            data / "backtest" / "playerboard_backtest.csv",
            data / "playerboard_backtest_summary.csv",
            data / "playerboard_backtest.csv",
            data / "prop_model_backtest_summary.csv",
            data / "prediction_history.csv",
        ]



def _read_csv_rows_cached(csv_store: Any, path: Path) -> list[dict[str, Any]]:
    reader = getattr(csv_store, "read_rows_cached", None)
    if callable(reader):
        return reader(path, max_age_seconds=60.0)
    return csv_store.read_rows(path)


def _file_signatures(paths: Iterable[str | Path]) -> tuple[FileSignature, ...]:
    return tuple(FileSignature.from_path(path) for path in sorted({str(Path(path).resolve()) for path in paths}))


def _registry_entry_from_snapshot(snapshot: ModelSnapshot, market: str) -> dict[str, Any]:
    raw = snapshot.registry.get(normalize_market_key(market), {})
    return copy.deepcopy(raw) if isinstance(raw, dict) else {}


def _query_value(query: dict[str, list[str]], name: str, default: str = "") -> str:
    values = query.get(name) or []
    return str(values[0]).strip() if values else default


def _title(market: str) -> str:
    return market.replace("_", " ").title()


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in {"", None}:
            return row[key]
    return None


def _float_or_none(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        number = float(str(value).replace("%", "").strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _average_metric(rows: list[dict[str, Any]], *keys: str) -> float | None:
    values = [_float_or_none(_first(row, *keys)) for row in rows]
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


def _summary_metrics(rows: list[dict[str, Any]], source: str) -> BacktestMetrics | None:
    for row in rows:
        wins = _float_or_none(_first(row, "wins", "win"))
        losses = _float_or_none(_first(row, "losses", "loss"))
        graded = _float_or_none(_first(row, "graded", "graded_props", "gradedProps", "total", "count"))
        if wins is None and losses is None and graded is None:
            continue
        wins_i = int(wins or 0)
        losses_i = int(losses or 0)
        pushes_i = int(_float_or_none(_first(row, "pushes", "push")) or 0)
        graded_i = int(graded or wins_i + losses_i + pushes_i)
        profit = _float_or_none(_first(row, "profit", "profit_units", "profitUnits", "units"))
        roi = _float_or_none(_first(row, "roi", "roi_percent", "roiPercent"))
        if roi is not None and abs(roi) <= 1.5:
            roi *= 100
        win_rate = _float_or_none(_first(row, "win_rate", "winRate", "win_rate_percent", "winRatePercent"))
        if win_rate is None and wins_i + losses_i > 0:
            win_rate = wins_i / (wins_i + losses_i) * 100
        elif win_rate is not None and abs(win_rate) <= 1.5:
            win_rate *= 100
        clv = _float_or_none(_first(row, "clv", "clv_percent", "closing_line_value", "avgClvPercent"))
        if clv is not None and abs(clv) <= 1.5:
            clv *= 100
        return BacktestMetrics(
            graded=graded_i,
            wins=wins_i,
            losses=losses_i,
            pushes=pushes_i,
            profit_units=profit,
            roi_percent=roi,
            win_rate_percent=win_rate,
            brier_score=_float_or_none(_first(row, "brier", "brier_score", "brierScore")),
            log_loss=_float_or_none(_first(row, "log_loss", "logLoss")),
            avg_clv_percent=clv,
            source=source,
        )
    return None


def _same_market(row: dict[str, Any], market: str) -> bool:
    row_market = normalize_market_key(str(_first(row, "market", "market_key", "marketKey", "prop_market") or ""))
    if row_market == market:
        return True
    # Older summaries may use display names such as "Batter hits".
    display = normalize_market_key(str(_first(row, "name", "marketName", "Market") or ""))
    return display == market


def _is_graded(row: dict[str, Any]) -> bool:
    result = _result_value(row)
    if result in {"win", "loss", "push"}:
        return True
    graded = str(_first(row, "graded", "is_graded", "isGraded") or "").strip().lower()
    return graded in {"1", "true", "yes", "y"}


def _result_value(row: dict[str, Any]) -> str:
    raw = str(_first(row, "result", "grade", "outcome", "status") or "").strip().lower()
    if raw in {"w", "won", "win", "1", "true"}:
        return "win"
    if raw in {"l", "lost", "loss", "0", "false"}:
        return "loss"
    if raw in {"p", "push", "void", "cancelled", "canceled"}:
        return "push"
    wins = _float_or_none(_first(row, "wins", "win"))
    losses = _float_or_none(_first(row, "losses", "loss"))
    if wins is not None and losses is not None:
        return "summary"
    return raw
