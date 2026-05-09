from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.data_health_service import DataHealthService
from mlb_app.services.grading_state_service import GradingStateService
from mlb_app.services.model_registry_service import ModelRegistryService
from mlb_app.services.playerboard_service import PlayerboardService
from mlb_app.services.product_state_service import ProductStateService
from mlb_app.services.workflow_health_service import WorkflowHealthService

Status = str


@dataclass(frozen=True)
class HealthCard:
    key: str
    label: str
    status: Status
    summary: str
    detail: str
    metric: str | int | float = "--"
    timestamp: str = ""
    warnings: tuple[str, ...] = ()
    repairTarget: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "status": self.status,
            "summary": self.summary,
            "detail": self.detail,
            "metric": self.metric,
            "timestamp": self.timestamp,
            "warnings": list(self.warnings),
            "repairTarget": self.repairTarget,
        }


class DataHealthDashboardService:
    """Build a product-grade data confidence dashboard from lower-level health payloads."""

    def __init__(
        self,
        *,
        data_health_service: DataHealthService | None = None,
        playerboard_service: PlayerboardService | None = None,
        grading_service: GradingStateService | None = None,
        workflow_service: WorkflowHealthService | None = None,
        product_state_service: ProductStateService | None = None,
        model_registry_service: ModelRegistryService | None = None,
        settings: Settings = default_settings,
    ) -> None:
        self.settings = settings
        self.grading_service = grading_service or GradingStateService(settings=self.settings)
        self.product_state_service = product_state_service or ProductStateService(settings=self.settings)
        self.data_health_service = data_health_service or DataHealthService(
            grading_service=self.grading_service,
            product_state_service=self.product_state_service,
            settings=self.settings,
        )
        self.playerboard_service = playerboard_service or PlayerboardService(
            grading_service=self.grading_service,
            product_state_service=self.product_state_service,
            settings=self.settings,
        )
        self.workflow_service = workflow_service or WorkflowHealthService(settings=self.settings)
        self.model_registry_service = model_registry_service or ModelRegistryService(settings=self.settings)

    def payload(self, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
        query = query or {}
        season_raw = str(self.settings.season_from_query(query))
        date_label = str((query.get("date") or [datetime.now().strftime("%Y-%m-%d")])[0] or "")

        data_health = self.data_health_service.payload({"date": [date_label]})
        playerboard = self.playerboard_service.health_payload({"season": [season_raw], "date": [date_label]})
        if (playerboard.get("rowsLoaded") or 0) <= 0 and playerboard.get("latestAvailableDate"):
            playerboard = self.playerboard_service.health_payload(
                {"season": [season_raw], "date": [str(playerboard["latestAvailableDate"])]}
            )
        grading = self.grading_service.payload({"date": [str(playerboard.get("date") or date_label)]})
        workflows = self.workflow_service.payload()
        model_status = self.model_registry_service.status_payload()
        product_state = self.product_state_service.payload(
            production_eligible_markets=len(model_status.get("productionEligibleMarkets", [])),
            grading_ok=bool(grading.get("ok")),
        )

        cards = self._build_cards(data_health, playerboard, grading, workflows, model_status)
        phases = self._build_workflow_phases(data_health, playerboard, grading, workflows, model_status)
        warnings = self._combined_warnings(data_health, playerboard, grading, workflows, model_status)
        overall_status = self._overall_status(cards)

        return {
            "status": "ok",
            "ok": overall_status in {"Good", "Partial"},
            "version": "data-health-dashboard-v1",
            "season": int(season_raw) if season_raw.isdigit() else season_raw,
            "date": date_label,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "overallStatus": overall_status,
            "dataConfidence": self._data_confidence(overall_status),
            "productState": product_state,
            "latestBoardDate": playerboard.get("date") or playerboard.get("latestAvailableDate") or "",
            "latestFullyGradedDate": grading.get("latestFullyGradedDate", ""),
            "summary": {
                "good": sum(1 for card in cards if card.status == "Good"),
                "partial": sum(1 for card in cards if card.status == "Partial"),
                "stale": sum(1 for card in cards if card.status == "Stale"),
                "missing": sum(1 for card in cards if card.status == "Missing"),
                "failed": sum(1 for card in cards if card.status == "Failed"),
                "warnings": len(warnings),
            },
            "cards": [card.as_dict() for card in cards],
            "workflowPhases": phases,
            "warnings": warnings,
            "advancedLinks": [
                {"label": "Pipeline runner", "target": "pipeline"},
                {"label": "Daily workflow", "target": "daily-workflow"},
                {"label": "Raw data health JSON", "target": "raw-health"},
                {"label": "Grading repair", "target": "grading-repair"},
            ],
            "raw": {
                "dataHealth": self._trim_data_health(data_health),
                "playerboard": self._trim_playerboard(playerboard),
                "grading": self._trim_grading(grading),
                "workflows": self._trim_workflows(workflows),
                "modelStatus": self._trim_model_status(model_status),
            },
        }

    def _build_cards(
        self,
        data: dict[str, Any],
        playerboard: dict[str, Any],
        grading: dict[str, Any],
        workflows: dict[str, Any],
        model_status: dict[str, Any],
    ) -> list[HealthCard]:
        health = data.get("health") or {}
        timestamps = data.get("timestamps") or {}
        savant = data.get("savant") or {}
        bvp = data.get("batterVsPitcher") or {}
        markets_present = playerboard.get("marketsPresent") or {}
        model_markets = model_status.get("markets") or []
        production_markets = model_status.get("productionEligibleMarkets") or []
        workflow_summaries = workflows.get("summaries") or {}

        return [
            HealthCard(
                key="odds_freshness",
                label="Odds freshness",
                status=self._status_from_count(health.get("propCount"), good=1, partial=1),
                summary=f"{health.get('propCount', 0)} props loaded",
                detail="Latest player-prop and game-market source coverage for the selected slate.",
                metric=health.get("propCount", 0),
                timestamp=str(timestamps.get("latestOddsSnapshot") or timestamps.get("propsFile") or ""),
                warnings=self._warnings_matching(data, ["PropLine", "odds", "snapshot"]),
                repairTarget="pipeline",
            ),
            HealthCard(
                key="playerboard_freshness",
                label="Playerboard freshness",
                status=self._bool_status(bool(playerboard.get("ok")), exists=bool(playerboard.get("exists"))),
                summary=f"{playerboard.get('rowsLoaded', 0)} rows for {playerboard.get('date') or '--'}",
                detail="Research board rows, schema alignment, market display labels, and shifted-row checks.",
                metric=playerboard.get("rowsLoaded", 0),
                timestamp=str(playerboard.get("latestSnapshotAt") or ""),
                warnings=tuple(self._playerboard_warnings(playerboard)),
                repairTarget="playerboard-repair",
            ),
            HealthCard(
                key="schedule_coverage",
                label="Schedule coverage",
                status=self._status_from_count(health.get("mlbGames"), good=1, partial=1),
                summary=f"{health.get('mlbGames', 0)} games, {health.get('finalGames', 0)} final",
                detail="Game slate availability and final-game recognition for grading readiness.",
                metric=health.get("mlbGames", 0),
                warnings=self._warnings_matching(data, ["schedule", "game summary"]),
                repairTarget="daily-workflow",
            ),
            HealthCard(
                key="prop_coverage",
                label="Prop coverage by market",
                status=self._status_from_count(len(markets_present), good=3, partial=1),
                summary=f"{len(markets_present)} markets present",
                detail=self._market_detail(markets_present),
                metric=len(markets_present),
                warnings=tuple([] if markets_present else ["No playerboard markets are present for this slate."]),
                repairTarget="pipeline",
            ),
            HealthCard(
                key="weather_coverage",
                label="Weather coverage",
                status=self._status_from_count(health.get("weatherRows"), good=1, partial=1),
                summary=f"{health.get('weatherRows', 0)} weather rows",
                detail="Weather and park context that may affect totals, run environment, and player props.",
                metric=health.get("weatherRows", 0),
                warnings=self._warnings_matching(data, ["weather"]),
                repairTarget="weather-sync",
            ),
            HealthCard(
                key="pitcher_coverage",
                label="Pitcher coverage",
                status=self._status_from_count(health.get("pitcherLogRows"), good=25, partial=1),
                summary=f"{health.get('pitcherLogRows', 0)} pitcher log rows",
                detail="Probable-pitcher and pitcher-game-log coverage used by matchup and strikeout markets.",
                metric=health.get("pitcherLogRows", 0),
                warnings=self._warnings_matching(data, ["pitcher"]),
                repairTarget="season-logs",
            ),
            HealthCard(
                key="lineup_coverage",
                label="Lineup coverage",
                status="Partial" if health.get("mlbGames", 0) else "Missing",
                summary="Lineup confirmation not automated",
                detail="Lineup status is treated as a risk flag until confirmed-lineup ingestion is available.",
                metric="Manual",
                warnings=("Confirmed lineup coverage is not yet a trusted automated source.",),
                repairTarget="lineups",
            ),
            HealthCard(
                key="bvp_coverage",
                label="BvP coverage",
                status=self._coverage_from_payload(bvp),
                summary=self._coverage_summary(bvp, "BvP rows"),
                detail="Batter-vs-pitcher history coverage. Missing BvP reduces confidence but does not block research.",
                metric=self._coverage_metric(bvp),
                warnings=tuple([] if self._coverage_metric(bvp) else ["No BvP coverage detected for the selected slate."]),
                repairTarget="bvp-import",
            ),
            HealthCard(
                key="savant_coverage",
                label="Savant coverage",
                status=self._coverage_from_payload(savant),
                summary=self._coverage_summary(savant, "Savant rows"),
                detail="Savant quality-of-contact and advanced profile coverage for model/context explanation.",
                metric=self._coverage_metric(savant),
                warnings=tuple([] if self._coverage_metric(savant) else ["No Savant coverage detected for the selected slate."]),
                repairTarget="savant-sync",
            ),
            HealthCard(
                key="grading_status",
                label="Grading status",
                status=self._grading_status(grading),
                summary=f"{grading.get('state', 'not_started')} · latest graded {grading.get('latestFullyGradedDate') or '--'}",
                detail="Latest fully graded slate is kept separate from live odds/playerboard dates.",
                metric=(grading.get("summary") or {}).get("gradedBacktestRowsForDate", 0),
                timestamp=str(grading.get("checkedAt") or ""),
                warnings=tuple(grading.get("warnings") or []),
                repairTarget="grading-repair",
            ),
            HealthCard(
                key="model_artifacts",
                label="Model artifacts",
                status=self._model_status(model_markets, production_markets),
                summary=f"{len(production_markets)} production-eligible markets",
                detail=f"{len(model_markets)} registry markets checked; missing artifacts stay research-only.",
                metric=len(production_markets),
                warnings=tuple(model_status.get("warnings") or []),
                repairTarget="model-room",
            ),
            HealthCard(
                key="workflow_summaries",
                label="Workflow summaries",
                status=self._workflow_status(workflows, workflow_summaries),
                summary=self._workflow_summary(workflow_summaries),
                detail="Morning, postgame, and weekly workflow summary files used for operational observability.",
                metric=sum(1 for item in workflow_summaries.values() if item.get("exists")),
                warnings=tuple(workflows.get("warnings") or []),
                repairTarget="workflow-summaries",
            ),
        ]

    def _build_workflow_phases(
        self,
        data: dict[str, Any],
        playerboard: dict[str, Any],
        grading: dict[str, Any],
        workflows: dict[str, Any],
        model_status: dict[str, Any],
    ) -> list[dict[str, Any]]:
        health = data.get("health") or {}
        summaries = workflows.get("summaries") or {}
        daily_health = summaries.get("dailyHealth") or {}
        daily_grading = summaries.get("dailyGrading") or {}
        weekly_repair = summaries.get("weeklyRepair") or {}
        production_markets = model_status.get("productionEligibleMarkets") or []
        trained_markets = model_status.get("trainedMarkets") or []

        return [
            self._phase("morning", "Morning / Pre-slate", [
                ("Schedule", (health.get("mlbGames") or 0) > 0),
                ("Odds", (health.get("propCount") or 0) > 0),
                ("Weather", (health.get("weatherRows") or 0) > 0),
                ("Playerboard", (playerboard.get("rowsLoaded") or 0) > 0),
            ], daily_health),
            self._phase("pre_lock", "Pre-lock", [
                ("Latest odds snapshot", bool((data.get("timestamps") or {}).get("latestOddsSnapshot"))),
                ("Best prices", (health.get("propCount") or 0) > 0),
                ("Readiness gates", bool(model_status.get("markets"))),
            ], daily_health),
            self._phase("postgame", "Postgame", [
                ("Finals", (health.get("finalGames") or 0) > 0),
                ("Boxscores", (health.get("boxscoresSaved") or 0) > 0),
                ("Grading", grading.get("state") == "graded"),
            ], daily_grading),
            self._phase("weekly", "Weekly", [
                ("Retraining summary", bool(production_markets) or bool(trained_markets)),
                ("Calibration/model cards", bool(model_status.get("markets"))),
                ("Weekly repair summary", bool(weekly_repair.get("exists"))),
            ], weekly_repair),
        ]

    @staticmethod
    def _phase(key: str, label: str, checks: list[tuple[str, bool]], summary: dict[str, Any]) -> dict[str, Any]:
        passed = sum(1 for _name, ok in checks if ok)
        total = len(checks)
        if passed == total:
            status = "Good"
        elif passed:
            status = "Partial"
        elif summary.get("exists") and not summary.get("ok", True):
            status = "Failed"
        else:
            status = "Missing"
        return {
            "key": key,
            "label": label,
            "status": status,
            "progress": {"passed": passed, "total": total},
            "lastRunDate": summary.get("date", ""),
            "checkedAt": summary.get("checkedAt", ""),
            "checks": [{"label": name, "ok": ok} for name, ok in checks],
            "warnings": list(summary.get("warnings") or []),
            "errors": list(summary.get("errors") or []),
        }

    @staticmethod
    def _status_from_count(value: Any, *, good: int, partial: int) -> Status:
        try:
            count = int(value or 0)
        except (TypeError, ValueError):
            count = 0
        if count >= good:
            return "Good"
        if count >= partial:
            return "Partial"
        return "Missing"

    @staticmethod
    def _bool_status(ok: bool, *, exists: bool = True) -> Status:
        if not exists:
            return "Missing"
        return "Good" if ok else "Failed"

    @staticmethod
    def _coverage_metric(payload: dict[str, Any]) -> int:
        if not isinstance(payload, dict):
            return 0
        for key in ("rows", "rowCount", "count", "matchedRows", "coverageRows"):
            try:
                value = int(payload.get(key) or 0)
            except (TypeError, ValueError):
                value = 0
            if value:
                return value
        return 0

    def _coverage_from_payload(self, payload: dict[str, Any]) -> Status:
        metric = self._coverage_metric(payload)
        if metric > 50:
            return "Good"
        if metric > 0:
            return "Partial"
        return "Missing"

    def _coverage_summary(self, payload: dict[str, Any], label: str) -> str:
        metric = self._coverage_metric(payload)
        if metric:
            return f"{metric} {label}"
        if isinstance(payload, dict) and payload.get("status"):
            return str(payload.get("status"))
        return f"0 {label}"

    @staticmethod
    def _grading_status(grading: dict[str, Any]) -> Status:
        state = str(grading.get("state") or "not_started")
        if state == "graded":
            return "Good"
        if state in {"partial", "waiting_for_finals", "boxscores_loaded", "grading_running"}:
            return "Partial"
        if state == "failed":
            return "Failed"
        return "Missing"

    @staticmethod
    def _model_status(markets: list[dict[str, Any]], production_markets: list[Any]) -> Status:
        if production_markets:
            return "Good"
        if markets:
            return "Partial"
        return "Missing"

    @staticmethod
    def _workflow_status(workflows: dict[str, Any], summaries: dict[str, Any]) -> Status:
        if workflows.get("ok") and any(item.get("exists") for item in summaries.values()):
            return "Good"
        if summaries:
            return "Partial"
        return "Missing"

    @staticmethod
    def _workflow_summary(summaries: dict[str, Any]) -> str:
        if not summaries:
            return "No summaries found"
        existing = [key for key, item in summaries.items() if item.get("exists")]
        if existing:
            return f"{len(existing)} summary file(s) present"
        return "Summary files not generated yet"

    @staticmethod
    def _market_detail(markets_present: dict[str, Any]) -> str:
        if not markets_present:
            return "No market rows are present in the current playerboard."
        top = sorted(markets_present.items(), key=lambda item: int(item[1] or 0), reverse=True)[:5]
        return ", ".join(f"{market}: {count}" for market, count in top)

    @staticmethod
    def _warnings_matching(payload: dict[str, Any], needles: list[str]) -> tuple[str, ...]:
        warnings = [str(w) for w in payload.get("warnings", [])]
        lower_needles = [needle.lower() for needle in needles]
        matched = [warning for warning in warnings if any(needle in warning.lower() for needle in lower_needles)]
        return tuple(matched[:3])

    @staticmethod
    def _playerboard_warnings(playerboard: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        if not playerboard.get("exists"):
            warnings.append("Playerboard file does not exist yet.")
        if not playerboard.get("schemaOk"):
            warnings.append(f"Schema issue: {playerboard.get('schemaIssue') or 'unknown'}")
        if (playerboard.get("rowsLoaded") or 0) <= 0:
            warnings.append("No playerboard rows loaded for this date/filter.")
        if (playerboard.get("badShiftedRows") or 0) > 0:
            warnings.append(f"{playerboard.get('badShiftedRows')} shifted rows detected.")
        if (playerboard.get("missingMarketDisplayRows") or 0) > 0:
            warnings.append(f"{playerboard.get('missingMarketDisplayRows')} rows missing market display labels.")
        return warnings[:4]

    @staticmethod
    def _combined_warnings(*payloads: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        for payload in payloads:
            for warning in payload.get("warnings") or []:
                text = str(warning)
                if text not in warnings:
                    warnings.append(text)
            for error in payload.get("errors") or []:
                text = str(error)
                if text not in warnings:
                    warnings.append(text)
        return warnings[:20]

    @staticmethod
    def _overall_status(cards: list[HealthCard]) -> Status:
        statuses = [card.status for card in cards]
        if any(status == "Failed" for status in statuses):
            return "Failed"
        if any(status in {"Missing", "Stale"} for status in statuses):
            return "Partial"
        if any(status == "Partial" for status in statuses):
            return "Partial"
        return "Good"

    @staticmethod
    def _data_confidence(overall_status: Status) -> str:
        return {"Good": "Good", "Partial": "Partial", "Stale": "Stale", "Missing": "Missing", "Failed": "Failed"}.get(overall_status, "Partial")

    @staticmethod
    def _trim_data_health(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": payload.get("ok"),
            "date": payload.get("date"),
            "health": payload.get("health", {}),
            "timestamps": payload.get("timestamps", {}),
            "warnings": (payload.get("warnings") or [])[:10],
        }

    @staticmethod
    def _trim_playerboard(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": payload.get("ok"),
            "exists": payload.get("exists"),
            "date": payload.get("date"),
            "latestAvailableDate": payload.get("latestAvailableDate"),
            "rowsLoaded": payload.get("rowsLoaded"),
            "marketsPresent": payload.get("marketsPresent", {}),
            "dataConfidence": payload.get("dataConfidence"),
        }

    @staticmethod
    def _trim_grading(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": payload.get("ok"),
            "state": payload.get("state"),
            "date": payload.get("date"),
            "latestFullyGradedDate": payload.get("latestFullyGradedDate"),
            "summary": payload.get("summary", {}),
            "warnings": (payload.get("warnings") or [])[:10],
        }

    @staticmethod
    def _trim_workflows(payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": payload.get("ok"), "summaries": payload.get("summaries", {}), "warnings": (payload.get("warnings") or [])[:10]}

    @staticmethod
    def _trim_model_status(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": payload.get("status"),
            "trainedMarkets": payload.get("trainedMarkets", []),
            "productionEligibleMarkets": payload.get("productionEligibleMarkets", []),
            "policy": payload.get("policy", {}),
        }
