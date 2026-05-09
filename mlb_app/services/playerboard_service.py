from __future__ import annotations

from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.contracts.playerboard_schema import PLAYERBOARD_SCHEMA_VERSION
from mlb_app.repositories.playerboard_repository import PlayerboardRepository
from mlb_app.services.grading_state_service import GradingStateService
from mlb_app.services.model_readiness_service import ModelReadinessService
from mlb_app.services.playerboard_builder import build_playerboard
from mlb_app.services.playerboard_read_service import PlayerboardReadService, PlayerboardSnapshot
from mlb_app.services.product_state_service import ProductStateService


class PlayerboardService:
    """Read-only playerboard API logic backed by the playerboard contract layer."""

    def __init__(
        self,
        *,
        repository: PlayerboardRepository | None = None,
        grading_service: GradingStateService | None = None,
        readiness_service: ModelReadinessService | None = None,
        product_state_service: ProductStateService | None = None,
        read_service: PlayerboardReadService | None = None,
        settings: Settings = default_settings,
    ) -> None:
        self.settings = settings
        self.repository = repository or PlayerboardRepository(settings=settings)
        self.grading_service = grading_service or GradingStateService()
        self.readiness_service = readiness_service or ModelReadinessService()
        self.product_state_service = product_state_service or ProductStateService(settings=settings)
        self.read_service = read_service or PlayerboardReadService(
            repository=self.repository,
            grading_service=self.grading_service,
            readiness_service=self.readiness_service,
            product_state_service=self.product_state_service,
            settings=self.settings,
        )

    def snapshot_for_query(self, query: dict[str, list[str]]) -> PlayerboardSnapshot:
        season = self.settings.season_from_query(query)
        requested_date = str((query.get("date") or [""])[0] or "")
        market = str((query.get("market") or [""])[0] or "")
        return self.read_service.get_snapshot(season=season, date_label=requested_date, market=market)

    def health_payload(self, query: dict[str, list[str]]) -> dict[str, Any]:
        return self.snapshot_for_query(query).health.to_dict()

    def board_payload(self, query: dict[str, list[str]]) -> dict[str, Any]:
        season = self.settings.season_from_query(query)
        date_label = str((query.get("date") or [""])[0] or "")
        market = str((query.get("market") or [""])[0] or "")
        limit = int((query.get("limit") or ["50"])[0])
        save = str((query.get("save") or ["0"])[0]).lower() in {"1", "true", "yes"}
        refresh = str((query.get("refresh") or ["0"])[0]).lower() in {"1", "true", "yes"}
        build_if_missing = str((query.get("buildIfMissing") or ["0"])[0]).lower() in {"1", "true", "yes"}
        replace_date = str((query.get("replaceDate") or ["0"])[0]).lower() in {"1", "true", "yes"}
        source_mode = str((query.get("sourceMode") or ["auto"])[0] or "auto")

        if not save and not refresh and not replace_date:
            snapshot = self.read_service.get_snapshot(season=season, date_label=date_label, market=market)
            payload = self._payload_from_snapshot(snapshot, market=market, limit=limit)
            if payload.get("cacheHit") or not build_if_missing:
                return payload

        payload = build_playerboard(
            season=season,
            date_label=date_label,
            market=market,
            limit=limit,
            save=save,
            replace_date=replace_date,
            source_mode=source_mode,
        )
        return self._attach_trust(payload, query)

    def _payload_from_snapshot(self, snapshot: PlayerboardSnapshot, *, market: str, limit: int) -> dict[str, Any]:
        rows = list(snapshot.rows)[:limit]
        health = snapshot.health.to_dict()
        return {
            "status": "ok",
            "season": snapshot.season,
            "date": snapshot.date,
            "market": market,
            "propsLoaded": len(snapshot.rows),
            "cardsBuilt": len(snapshot.rows),
            "errors": [],
            "saved": {
                "source": "playerboard_snapshot",
                "snapshotAt": health.get("latestSnapshotAt", ""),
                "snapshotsUsed": health.get("snapshots", []),
                "rowsLoaded": len(rows),
                "file": str(snapshot.path),
                "snapshotSignature": snapshot.source_meta().get("snapshotSignature"),
            } if rows else None,
            "top": rows,
            "rows": rows,
            "source": "playerboard_snapshot",
            "cacheHit": bool(rows),
            "message": "Loaded latest saved Playerboard snapshot." if rows else f"No saved Playerboard snapshot found for {snapshot.date or 'latest date'}. Run the scheduled collector or request refresh=1 to rebuild.",
            "productState": dict(snapshot.product_state),
            "latestFullyGradedDate": health.get("latestFullyGradedDate", ""),
            "dataConfidence": health.get("dataConfidence", "Missing"),
            "modelReadiness": dict(snapshot.model_readiness),
            "trust": dict(snapshot.trust),
            "schemaVersion": snapshot.schema_version,
            "sourceMeta": snapshot.source_meta(),
            "freshness": health.get("freshness", {}),
        }

    def _attach_trust(self, payload: dict[str, Any], query: dict[str, list[str]]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return payload
        health = self.health_payload(query)
        enriched = dict(payload)
        enriched.setdefault("productState", health.get("productState"))
        enriched.setdefault("latestFullyGradedDate", health.get("latestFullyGradedDate", ""))
        enriched.setdefault("dataConfidence", health.get("dataConfidence", "Missing"))
        enriched.setdefault("modelReadiness", health.get("modelReadiness", {}))
        enriched.setdefault("trust", health.get("trust", {}))
        enriched.setdefault("schemaVersion", PLAYERBOARD_SCHEMA_VERSION)
        return enriched

    @staticmethod
    def _data_confidence(*, ok: bool, grading_state: str, rows: int) -> str:
        if rows <= 0:
            return "Missing"
        if not ok:
            return "Partial"
        if grading_state in {"failed", "not_started"}:
            return "Partial"
        if grading_state in {"partial", "waiting_for_finals"}:
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
        return {
            "label": label,
            "latestOddsTimestamp": latest_snapshot,
            "gradingState": grading_state,
        }


def _clean(value: Any) -> str:
    return str(value or "").strip()
