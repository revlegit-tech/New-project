from __future__ import annotations

from collections import Counter
from typing import Any

from mlb_app.services.grading_state_service import GradingStateService
from mlb_app.services.model_readiness_service import ModelReadinessService
from mlb_app.services.product_state_service import ProductStateService

try:  # Hot-path dependency; imported once so health/board calls do not re-import.
    from playerboard import (
        PLAYERBOARD_FIELDS,
        build_playerboard,
        clean,
        load_saved_playerboard,
        normalize_market,
        playerboard_file,
        playerboard_row_looks_shifted,
        playerboard_schema_issue,
        read_csv_rows,
    )
except Exception:  # pragma: no cover - surfaced as explicit runtime errors below.
    PLAYERBOARD_FIELDS = []
    build_playerboard = None
    clean = None
    load_saved_playerboard = None
    normalize_market = None
    playerboard_file = None
    playerboard_row_looks_shifted = None
    playerboard_schema_issue = None
    read_csv_rows = None


class PlayerboardService:
    """Read-only playerboard API logic extracted from the legacy handler."""

    def __init__(
        self,
        *,
        grading_service: GradingStateService | None = None,
        readiness_service: ModelReadinessService | None = None,
        product_state_service: ProductStateService | None = None,
    ) -> None:
        self.grading_service = grading_service or GradingStateService()
        self.readiness_service = readiness_service or ModelReadinessService()
        self.product_state_service = product_state_service or ProductStateService()

    def health_payload(self, query: dict[str, list[str]]) -> dict[str, Any]:
        _require_playerboard_symbols(
            PLAYERBOARD_FIELDS=PLAYERBOARD_FIELDS,
            clean=clean,
            normalize_market=normalize_market,
            playerboard_file=playerboard_file,
            playerboard_row_looks_shifted=playerboard_row_looks_shifted,
            playerboard_schema_issue=playerboard_schema_issue,
            read_csv_rows=read_csv_rows,
        )

        season = int((query.get("season") or ["2026"])[0])
        requested_date = str((query.get("date") or [""])[0] or "")
        market = str((query.get("market") or [""])[0] or "")
        target_market = normalize_market(market) if market else ""

        path = playerboard_file(season)
        rows = read_csv_rows(path)
        available_dates = sorted({clean(row.get("date")) for row in rows if clean(row.get("date"))})
        latest_available_date = available_dates[-1] if available_dates else ""
        date_label = requested_date or latest_available_date

        filtered = []
        for row in rows:
            if date_label and clean(row.get("date")) != date_label:
                continue
            if target_market and normalize_market(row.get("market")) != target_market:
                continue
            filtered.append(row)

        market_counts = Counter(normalize_market(row.get("market")) for row in filtered if clean(row.get("market")))
        missing_market_display = [row for row in filtered if not clean(row.get("marketDisplay"))]
        bad_shifted_rows = [row for row in filtered if playerboard_row_looks_shifted(row)]
        snapshots = sorted({clean(row.get("snapshotAt")) for row in filtered if clean(row.get("snapshotAt"))})
        latest_snapshot = snapshots[-1] if snapshots else ""
        schema_issue = playerboard_schema_issue(path, PLAYERBOARD_FIELDS)
        grading = self.grading_service.payload({"date": [date_label]} if date_label else {})
        readiness = self.readiness_service.payload(tuple(sorted(market_counts)), latest_graded_date=grading.get("latestFullyGradedDate", ""))
        product_state = self.product_state_service.payload(
            production_eligible_markets=len(readiness.get("productionEligibleMarkets", [])),
            grading_ok=bool(grading.get("ok")),
        )

        ok = bool(path.exists() and not schema_issue and len(filtered) > 0 and not bad_shifted_rows)
        data_confidence = self._data_confidence(ok=ok, grading_state=str(grading.get("state") or ""), rows=len(filtered))

        return {
            "season": season,
            "date": date_label,
            "requestedDate": requested_date,
            "latestAvailableDate": latest_available_date,
            "availableDates": available_dates[-30:],
            "usedLatestAvailableDate": bool(requested_date and requested_date != date_label and date_label == latest_available_date),
            "market": market,
            "file": str(path),
            "exists": path.exists(),
            "schemaVersion": "PLAYERBOARD_FIELDS_v2",
            "schemaOk": path.exists() and not schema_issue,
            "schemaIssue": schema_issue,
            "expectedColumnCount": len(PLAYERBOARD_FIELDS),
            "expectedColumns": PLAYERBOARD_FIELDS,
            "rowsLoaded": len(filtered),
            "totalRowsInFile": len(rows),
            "marketsPresent": dict(sorted(market_counts.items())),
            "missingMarketDisplayRows": len(missing_market_display),
            "badShiftedRows": len(bad_shifted_rows),
            "latestSnapshotAt": latest_snapshot,
            "snapshots": snapshots[-10:],
            "sampleBadRows": bad_shifted_rows[:5],
            "sampleMissingMarketDisplayRows": missing_market_display[:5],
            "ok": ok,
            "productState": product_state,
            "grading": grading,
            "latestFullyGradedDate": grading.get("latestFullyGradedDate", ""),
            "dataConfidence": data_confidence,
            "slateStatus": self._slate_status(rows=len(filtered), latest_snapshot=latest_snapshot, grading_state=str(grading.get("state") or "")),
            "modelReadiness": readiness,
            "trust": {
                "mode": product_state["state"],
                "banner": product_state["label"],
                "message": product_state["message"],
                "decisionLabels": product_state["allowedDecisionLabels"],
                "latestFullyGradedDate": grading.get("latestFullyGradedDate", ""),
                "canShowConfidentPicks": bool(readiness.get("productionEligibleMarkets")),
            },
        }

    def board_payload(self, query: dict[str, list[str]]) -> dict[str, Any]:
        _require_playerboard_symbols(build_playerboard=build_playerboard, load_saved_playerboard=load_saved_playerboard)

        season = int((query.get("season") or ["2026"])[0])
        date_label = str((query.get("date") or [""])[0] or "")
        market = str((query.get("market") or [""])[0] or "")
        limit = int((query.get("limit") or ["50"])[0])
        save = str((query.get("save") or ["0"])[0]).lower() in {"1", "true", "yes"}
        refresh = str((query.get("refresh") or ["0"])[0]).lower() in {"1", "true", "yes"}
        build_if_missing = str((query.get("buildIfMissing") or ["0"])[0]).lower() in {"1", "true", "yes"}

        if not save and not refresh:
            cached = load_saved_playerboard(season=season, date_label=date_label, market=market, limit=limit)
            if cached.get("cacheHit") or not build_if_missing:
                return self._attach_trust(cached, query)

        payload = build_playerboard(season=season, date_label=date_label, market=market, limit=limit, save=save)
        return self._attach_trust(payload, query)

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


def _require_playerboard_symbols(**symbols: Any) -> None:
    missing = [name for name, value in symbols.items() if value is None]
    if missing:
        raise RuntimeError(
            "playerboard module failed to import required symbols: " + ", ".join(sorted(missing))
        )
