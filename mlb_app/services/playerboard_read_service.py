from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from mlb_app.config import Settings, settings as default_settings
from mlb_app.contracts.playerboard_schema import PLAYERBOARD_FIELDS, PLAYERBOARD_SCHEMA_VERSION, normalize_market_value
from mlb_app.observability.metrics import MetricsRegistry
from mlb_app.repositories.board_snapshot_repository import BoardSnapshotRepository
from mlb_app.repositories.playerboard_snapshot_repository import PlayerboardSnapshotRepository
from mlb_app.repositories.playerboard_repository import PlayerboardReadResult, PlayerboardRepository
from mlb_app.services.board_cache import FileSignature
from mlb_app.services.grading_state_service import GradingStateService
from mlb_app.services.game_market_feature_lookup_service import GameMarketFeatureLookupService
from mlb_app.services.model_readiness_service import ModelReadinessService
from mlb_app.services.playerboard_builder import playerboard_row_looks_shifted, rank_value, saved_card_from_row
from mlb_app.services.product_state_service import ProductStateService


@dataclass(frozen=True)
class PlayerboardHealth:
    payload: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.payload)


@dataclass(frozen=True)
class PlayerboardSnapshot:
    season: int
    date: str
    path: Path
    file_signature: FileSignature
    rows: tuple[dict[str, Any], ...]
    raw_rows: tuple[dict[str, Any], ...]
    health: PlayerboardHealth
    trust: Mapping[str, Any]
    model_readiness: Mapping[str, Any]
    product_state: Mapping[str, Any]
    schema_version: str = PLAYERBOARD_SCHEMA_VERSION
    cache_hit: bool = False
    prop_index: Mapping[str, dict[str, Any]] = field(default_factory=dict)
    source: str = "csv"
    snapshot_ids: tuple[str, ...] = ()
    snapshot_at: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.prop_index, MappingProxyType):
            object.__setattr__(self, "prop_index", MappingProxyType(dict(self.prop_index)))

    def row_for_prop_key(self, prop_key: str) -> dict[str, Any]:
        row = self.prop_index.get(prop_key)
        return dict(row) if isinstance(row, dict) else {}

    def source_meta(self) -> dict[str, Any]:
        return {
            "file": str(self.path),
            "fileSignature": {
                "path": self.file_signature.path,
                "exists": self.file_signature.exists,
                "mtimeNs": self.file_signature.mtime_ns,
                "size": self.file_signature.size,
            },
            "snapshotSignature": snapshot_signature(self.file_signature),
            "rows": len(self.rows),
            "source": self.source,
            "snapshotIds": list(self.snapshot_ids),
            "snapshotAt": self.snapshot_at,
        }


def prop_key_for_row(row: Mapping[str, Any]) -> str:
    """Generate a deterministic prop identity for board/detail handoff."""

    player_identity = _clean(_first(row, "playerId", "player_id", "mlbamId"))
    if player_identity:
        player_part = f"id:{player_identity}"
    else:
        player = _slug(_first(row, "player", "playerName", "name"))
        team = _slug(row.get("team"))
        opponent = _slug(row.get("opponent"))
        player_part = f"name:{player}:{team}:{opponent}"

    parts = [
        _clean(row.get("date")),
        player_part,
        _slug(row.get("market")),
        _clean(row.get("line")),
        _slug(_detail_side(row)),
        _slug(_first(row, "book", "sportsbook", "bestBook", "bookmaker", "sourceBook") or "best_available"),
    ]
    return "|".join(part for part in parts if part)


def snapshot_signature(signature: FileSignature) -> str:
    if not signature.exists:
        return f"missing:{signature.path}"
    return f"{signature.path}:{signature.mtime_ns}:{signature.size}"


class PlayerboardReadService:
    """One-read snapshot boundary for hot playerboard consumers.

    Sprint 3 keeps the existing CSV store as the physical source but changes the
    service contract: edge board, playerboard health, and prop detail derive from
    one immutable snapshot object instead of independently reading/rebuilding.
    """

    def __init__(
        self,
        *,
        repository: PlayerboardRepository | None = None,
        snapshot_repository: BoardSnapshotRepository | None = None,
        db_snapshot_repository: PlayerboardSnapshotRepository | None = None,
        grading_service: GradingStateService | None = None,
        readiness_service: ModelReadinessService | None = None,
        product_state_service: ProductStateService | None = None,
        game_market_feature_lookup_service: GameMarketFeatureLookupService | None = None,
        settings: Settings = default_settings,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository or PlayerboardRepository(settings=settings)
        self.snapshot_repository = snapshot_repository
        self.db_snapshot_repository = db_snapshot_repository
        self.grading_service = grading_service or GradingStateService(settings=settings)
        self.readiness_service = readiness_service or ModelReadinessService()
        self.product_state_service = product_state_service or ProductStateService(settings=settings)
        self.game_market_feature_lookup_service = game_market_feature_lookup_service
        self.metrics = metrics

    def snapshot_for_query(self, query: dict[str, list[str]]) -> PlayerboardSnapshot:
        season = self.settings.season_from_query(query)
        requested_date = str((query.get("date") or [""])[0] or "")
        market = str((query.get("market") or [""])[0] or "")
        prop_key = str((query.get("propKey") or query.get("id") or [""])[0] or "")
        return self.get_snapshot(season=season, date_label=requested_date, market=market, prop_key=prop_key)

    def get_snapshot(self, *, season: int, date_label: str = "", market: str = "", prop_key: str = "") -> PlayerboardSnapshot:
        started_at = time.perf_counter()
        read_result = self._read_result(season=season, date_label=date_label, market=market, prop_key=prop_key)
        selected_date = _selected_date(read_result, date_label)
        selected_rows = _latest_snapshot_rows(read_result.rows, date_label=selected_date, market=market)
        selected_rows = self._enrich_game_market_rows(selected_rows)
        market_counts = Counter(normalize_market_value(row.get("market")) for row in selected_rows if _clean(row.get("market")))
        grading = self.grading_service.payload({"date": [selected_date]} if selected_date else {})
        readiness = self.readiness_service.payload(
            tuple(sorted(market_counts)), latest_graded_date=grading.get("latestFullyGradedDate", "")
        )
        product_state = self.product_state_service.payload(
            production_eligible_markets=len(readiness.get("productionEligibleMarkets", [])),
            grading_ok=bool(grading.get("ok")),
        )
        health_payload = self._health_payload(
            season=season,
            read_result=read_result,
            selected_date=selected_date,
            requested_date=date_label,
            requested_market=market,
            selected_rows=selected_rows,
            market_counts=market_counts,
            grading=grading,
            readiness=readiness,
            product_state=product_state,
        )
        prop_index = {prop_key_for_row(row): row for row in selected_rows if prop_key_for_row(row)}
        snapshot = PlayerboardSnapshot(
            season=season,
            date=selected_date,
            path=read_result.path,
            file_signature=FileSignature.from_path(read_result.path),
            rows=tuple(selected_rows),
            raw_rows=tuple(dict(row) for row in read_result.rows),
            health=PlayerboardHealth(MappingProxyType(health_payload)),
            trust=MappingProxyType(dict(health_payload.get("trust") or {})),
            model_readiness=MappingProxyType(dict(readiness or {})),
            product_state=MappingProxyType(dict(product_state or {})),
            schema_version=read_result.schema_version or PLAYERBOARD_SCHEMA_VERSION,
            cache_hit=bool(selected_rows),
            prop_index=prop_index,
            source=read_result.source,
            snapshot_ids=read_result.snapshot_ids,
            snapshot_at=read_result.snapshot_at,
        )
        self._emit_snapshot_metrics(snapshot, build_ms=(time.perf_counter() - started_at) * 1000.0)
        return snapshot


    def _read_result(self, *, season: int, date_label: str, market: str, prop_key: str = "") -> PlayerboardReadResult:
        """Read from warehouse DB, then SQLite active snapshots, then CSV fallback."""

        if self.db_snapshot_repository is not None and self.settings.db_enabled:
            try:
                db_result = self.db_snapshot_repository.read_latest_playerboard(
                    season=season,
                    date_label=date_label,
                    market=market,
                    prop_key=prop_key,
                )
                if db_result is not None:
                    return db_result
            except Exception:
                # The historical warehouse must not break the live board. CSV
                # and existing SQLite serving snapshots remain the recovery path.
                pass

        if self.snapshot_repository is not None:
            db_result = self.snapshot_repository.read_active_playerboard(
                season=season,
                date_label=date_label,
                market=market,
                prop_key=prop_key,
            )
            if db_result is not None:
                return db_result
        return self.repository.read_current_playerboard(season=season)

    def _emit_snapshot_metrics(self, snapshot: PlayerboardSnapshot, *, build_ms: float) -> None:
        if self.metrics is None:
            return
        health = snapshot.health.to_dict()
        freshness = health.get("freshness") if isinstance(health.get("freshness"), dict) else {}
        age = freshness.get("ageSeconds")
        if isinstance(age, (int, float)):
            self.metrics.observe("board_snapshot_age_seconds", float(age))
        self.metrics.observe("board_build_duration_ms", round(float(build_ms), 3))
        self.metrics.set("board_snapshot_rows", len(snapshot.rows))
        self.metrics.increment("board_cache_hits_total" if snapshot.cache_hit else "board_cache_misses_total", labels={"layer": "playerboard_snapshot"})

    def _health_payload(
        self,
        *,
        season: int,
        read_result: PlayerboardReadResult,
        selected_date: str,
        requested_date: str,
        requested_market: str,
        selected_rows: list[dict[str, Any]],
        market_counts: Counter[str],
        grading: dict[str, Any],
        readiness: dict[str, Any],
        product_state: dict[str, Any],
    ) -> dict[str, Any]:
        all_rows = read_result.rows
        available_dates = sorted({_clean(row.get("date")) for row in all_rows if _clean(row.get("date"))})
        missing_market_display = [row for row in selected_rows if not _clean(row.get("marketDisplay"))]
        bad_shifted_rows = [row for row in selected_rows if playerboard_row_looks_shifted(row)]
        snapshots = sorted({_clean(row.get("snapshotAt")) for row in selected_rows if _clean(row.get("snapshotAt"))})
        latest_snapshot = snapshots[-1] if snapshots else ""
        target_market = normalize_market_value(requested_market) if requested_market else ""
        date_rows = [
            row for row in all_rows
            if _clean(row.get("date")) == selected_date
            and (not target_market or normalize_market_value(row.get("market")) == target_market)
        ]
        date_snapshots = sorted({_clean(row.get("snapshotAt")) for row in date_rows if _clean(row.get("snapshotAt"))})
        latest_recent_game_date, stale_recent_game_rows, rows_with_recent_games = _recent_games_diagnostics(
            date_rows,
            selected_date=selected_date,
        )
        recent_games_age_days = _date_age_days(selected_date, latest_recent_game_date)
        health_warnings = _playerboard_health_warnings(
            rows_loaded=len(selected_rows),
            date_rows_in_file=len(date_rows),
            snapshot_group_count=len(date_snapshots),
            latest_recent_game_date=latest_recent_game_date,
            recent_games_age_days=recent_games_age_days,
            rows_with_recent_games=rows_with_recent_games,
            stale_recent_game_rows=stale_recent_game_rows,
        )
        validation = read_result.validation
        ok = bool(read_result.exists and validation.ok and len(selected_rows) > 0 and not bad_shifted_rows)
        data_confidence = self._data_confidence(ok=ok, grading_state=str(grading.get("state") or ""), rows=len(selected_rows))
        schema_issue = "" if validation.ok else validation.actionable_message
        return {
            "season": season,
            "date": selected_date,
            "requestedDate": requested_date,
            "latestAvailableDate": available_dates[-1] if available_dates else "",
            "availableDates": available_dates[-30:],
            "usedLatestAvailableDate": bool(requested_date and requested_date != selected_date and selected_date == (available_dates[-1] if available_dates else "")),
            "market": requested_market,
            "file": str(read_result.path),
            "exists": read_result.exists,
            "schemaVersion": PLAYERBOARD_SCHEMA_VERSION,
            "schemaOk": read_result.exists and validation.ok,
            "schemaIssue": schema_issue,
            "schemaValidation": validation.to_dict(),
            "expectedColumnCount": len(PLAYERBOARD_FIELDS),
            "expectedColumns": PLAYERBOARD_FIELDS,
            "rowsLoaded": len(selected_rows),
            "totalRowsInFile": read_result.total_rows,
            "dateRowsInFile": len(date_rows),
            "marketsPresent": dict(sorted(market_counts.items())),
            "missingMarketDisplayRows": len(missing_market_display),
            "badShiftedRows": len(bad_shifted_rows),
            "latestSnapshotAt": latest_snapshot,
            "snapshots": snapshots[-10:],
            "snapshotGroupCount": len(date_snapshots),
            "snapshotGroups": date_snapshots[-10:],
            "sampleBadRows": bad_shifted_rows[:5],
            "sampleMissingMarketDisplayRows": missing_market_display[:5],
            "latestRecentGameDate": latest_recent_game_date,
            "recentGamesAgeDays": recent_games_age_days,
            "rowsWithRecentGames": rows_with_recent_games,
            "staleRecentGameRows": stale_recent_game_rows,
            "warnings": health_warnings,
            "ok": ok,
            "productState": product_state,
            "grading": grading,
            "latestFullyGradedDate": grading.get("latestFullyGradedDate", ""),
            "dataConfidence": data_confidence,
            "slateStatus": self._slate_status(rows=len(selected_rows), latest_snapshot=latest_snapshot, grading_state=str(grading.get("state") or "")),
            "modelReadiness": readiness,
            "trust": {
                "mode": product_state.get("state"),
                "banner": product_state.get("label"),
                "message": product_state.get("message"),
                "decisionLabels": product_state.get("allowedDecisionLabels"),
                "latestFullyGradedDate": grading.get("latestFullyGradedDate", ""),
                "canShowConfidentPicks": bool(readiness.get("productionEligibleMarkets")),
            },
            "freshness": freshness_from_snapshot(selected_date=selected_date, latest_snapshot=latest_snapshot, signature=FileSignature.from_path(read_result.path), rows=len(selected_rows)),
            "gameMarketEnrichment": self._game_market_enrichment_status(selected_rows),
        }

    def _enrich_game_market_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return rows
        if self.game_market_feature_lookup_service is None:
            return [dict(row) | {"game_market_available": False, "game_market_enrichment_status": "warehouse_unavailable"} for row in rows]
        try:
            return self.game_market_feature_lookup_service.enrich_rows(rows)
        except Exception:
            return [dict(row) | {"game_market_available": False, "game_market_enrichment_status": "warehouse_unavailable"} for row in rows]

    def _game_market_enrichment_status(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        status_counts = Counter(_clean(row.get("game_market_enrichment_status")) or "unknown" for row in rows)
        service_status = (
            self.game_market_feature_lookup_service.status_payload()
            if self.game_market_feature_lookup_service is not None
            else {}
        )
        return {
            "enabled": bool(getattr(self.settings, "game_market_enrichment_enabled", True)),
            "availableRows": sum(1 for row in rows if bool(row.get("game_market_available"))),
            "matchedRows": status_counts.get("matched", 0),
            "statusCounts": dict(status_counts),
            "source": service_status.get("source") or "historical_game_market_features",
            "warnings": list(service_status.get("warnings") or []),
        }

    @staticmethod
    def _data_confidence(*, ok: bool, grading_state: str, rows: int) -> str:
        if rows <= 0:
            return "Missing"
        if not ok or grading_state in {"failed", "not_started", "partial", "waiting_for_finals"}:
            return "Partial"
        return "Good"

    @staticmethod
    def _slate_status(*, rows: int, latest_snapshot: str, grading_state: str) -> dict[str, Any]:
        if rows <= 0:
            label = "No saved board"
        elif grading_state == "graded":
            label = "Board ready · latest graded slate available"
        else:
            label = "Today board: live odds / research mode"
        return {"label": label, "latestOddsTimestamp": latest_snapshot, "gradingState": grading_state}



def _recent_games_diagnostics(rows: list[dict[str, Any]], *, selected_date: str) -> tuple[str, int, int]:
    latest_dates: list[str] = []
    stale_rows = 0
    rows_with_recent_games = 0

    for row in rows:
        game_dates = _recent_game_dates(row.get("recentGames"))
        if not game_dates:
            continue

        rows_with_recent_games += 1
        latest = max(game_dates)
        latest_dates.append(latest)

        age_days = _date_age_days(selected_date, latest)
        if age_days is not None and age_days > 7:
            stale_rows += 1

    return (max(latest_dates) if latest_dates else "", stale_rows, rows_with_recent_games)


def _recent_game_dates(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    elif isinstance(value, list):
        parsed = value
    else:
        return []

    dates: list[str] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        date_text = _clean(item.get("date"))[:10]
        if _parse_date_label(date_text) is not None:
            dates.append(date_text)
    return dates


def _date_age_days(selected_date: str, candidate_date: str) -> int | None:
    selected = _parse_date_label(selected_date)
    candidate = _parse_date_label(candidate_date)
    if selected is None or candidate is None:
        return None
    return (selected - candidate).days


def _parse_date_label(value: str) -> Any:
    text = _clean(value)[:10]
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _playerboard_health_warnings(
    *,
    rows_loaded: int,
    date_rows_in_file: int,
    snapshot_group_count: int,
    latest_recent_game_date: str,
    recent_games_age_days: int | None,
    rows_with_recent_games: int,
    stale_recent_game_rows: int,
) -> list[str]:
    warnings: list[str] = []

    if snapshot_group_count > 1:
        warnings.append(f"Multiple playerboard snapshot groups detected for this date ({snapshot_group_count}).")

    if rows_loaded > 10000 or (rows_loaded > 0 and date_rows_in_file > max(10000, rows_loaded * 2)):
        warnings.append(
            f"Playerboard row count is unusually high for one slate ({date_rows_in_file} date rows, {rows_loaded} loaded rows)."
        )

    if latest_recent_game_date and recent_games_age_days is not None and recent_games_age_days > 7:
        warnings.append(f"Playerboard recentGames context appears stale; latest recent game date is {latest_recent_game_date}.")

    if rows_with_recent_games and stale_recent_game_rows / rows_with_recent_games >= 0.25:
        warnings.append(f"{stale_recent_game_rows} playerboard rows have stale recentGames context.")

    return warnings[:6]


def freshness_from_snapshot(*, selected_date: str, latest_snapshot: str, signature: FileSignature, rows: int) -> dict[str, Any]:
    status = "missing"
    reason = "snapshot_missing"
    age_seconds = _snapshot_age_seconds(latest_snapshot=latest_snapshot, signature=signature)
    if rows > 0 and signature.exists:
        status = "fresh" if latest_snapshot else "degraded"
        reason = "ok" if latest_snapshot else "missing_snapshot_timestamp"
    return {
        "snapshotBuiltAt": latest_snapshot,
        "sourceMtime": str(signature.mtime_ns or ""),
        "ageSeconds": age_seconds,
        "status": status,
        "reason": reason,
        "date": selected_date,
    }


def _snapshot_age_seconds(*, latest_snapshot: str, signature: FileSignature) -> float | None:
    parsed = _parse_datetime(latest_snapshot)
    if parsed is not None:
        return round(max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds()), 3)
    if signature.exists and signature.mtime_ns is not None:
        mtime_seconds = signature.mtime_ns / 1_000_000_000
        return round(max(0.0, datetime.now(timezone.utc).timestamp() - mtime_seconds), 3)
    return None


def _parse_datetime(value: str) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _selected_date(read_result: PlayerboardReadResult, requested_date: str) -> str:
    requested = _clean(requested_date)
    if requested:
        return requested
    dates = sorted({_clean(row.get("date")) for row in read_result.rows if _clean(row.get("date"))})
    return dates[-1] if dates else ""


def _latest_snapshot_rows(rows: list[dict[str, Any]], *, date_label: str, market: str) -> list[dict[str, Any]]:
    target_market = normalize_market_value(market) if market else ""
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if date_label and _clean(row.get("date")) != date_label:
            continue
        if target_market and normalize_market_value(row.get("market")) != target_market:
            continue
        if not _clean(row.get("snapshotAt")):
            continue
        filtered.append(row)
    if not filtered:
        return []
    selected: list[dict[str, Any]] = []
    if target_market:
        latest = max(_clean(row.get("snapshotAt")) for row in filtered)
        selected = [row for row in filtered if _clean(row.get("snapshotAt")) == latest]
    else:
        by_market: dict[str, list[dict[str, Any]]] = {}
        for row in filtered:
            by_market.setdefault(normalize_market_value(row.get("market")), []).append(row)
        for market_rows in by_market.values():
            latest = max(_clean(row.get("snapshotAt")) for row in market_rows)
            selected.extend(row for row in market_rows if _clean(row.get("snapshotAt")) == latest)

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for row in selected:
        card = saved_card_from_row(row)
        card["propKey"] = prop_key_for_row(card)
        card["id"] = card.get("id") or card["propKey"]
        key = (
            _clean(card.get("market")),
            _clean(card.get("player")).lower(),
            _clean(card.get("team")).upper(),
            _clean(card.get("opponent")).upper(),
            _clean(card.get("pitcher")).lower(),
            _clean(card.get("line")),
            _clean(card.get("americanOdds")),
            _clean(card.get("book")).lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(card)
    return sorted(deduped, key=rank_value, reverse=True)


def _detail_side(row: Mapping[str, Any]) -> str:
    label = _clean(row.get("rawLabel") or row.get("side") or row.get("outcome")).casefold()
    market = _clean(row.get("market")).lower()
    player = _clean(row.get("player")).casefold()
    if "under" in label or label in {"no", "n"}:
        return "under"
    if "over" in label or label in {"yes", "y"}:
        return "over"
    if player and player in label:
        return "over"
    if market.startswith(("batter_", "pitcher_")):
        return "over"
    return label or "over"


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in {None, ""}:
            return value
    return ""


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _slug(value: Any) -> str:
    text = _clean(value).lower()
    return "-".join(part for part in text.replace("|", " ").split() if part)
