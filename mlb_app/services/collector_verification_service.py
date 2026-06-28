from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.repositories.board_snapshot_repository import BoardSnapshotRepository
from mlb_app.services.edge_board_service import EdgeBoardService
from mlb_app.services.runtime_status_service import RuntimeStatusService, safe_relpath
from mlb_app.services.data_source_capability_service import DataSourceCapabilityService
from mlb_app.services.umpire_context_service import UmpireContextService

SCHEMA_VERSION = "collector-check.v1"


def classify_collector_state(
    *,
    props_rows: int,
    active_playerboard_rows: int,
    edge_board_rows: int,
    odds_snapshot_count: int,
    checking_today: bool = False,
    latest_active_date: str = "",
    target_date: str = "",
) -> str:
    if props_rows <= 0 and active_playerboard_rows <= 0:
        if checking_today and latest_active_date and target_date and latest_active_date < target_date:
            return "stale"
        return "failed"
    if props_rows > 0 and active_playerboard_rows > 0 and edge_board_rows > 0:
        return "ok"
    if props_rows > 0 and (active_playerboard_rows <= 0 or odds_snapshot_count <= 0):
        return "partial"
    return "partial"


class CollectorVerificationService:
    def __init__(
        self,
        *,
        settings: Settings = default_settings,
        board_snapshot_repository: BoardSnapshotRepository | None = None,
        edge_board_service: EdgeBoardService | None = None,
        runtime_status_service: RuntimeStatusService | None = None,
    ) -> None:
        self.settings = settings
        self.board_snapshot_repository = board_snapshot_repository or BoardSnapshotRepository(settings)
        self.edge_board_service = edge_board_service or EdgeBoardService(settings=settings)
        self.runtime_status_service = runtime_status_service or RuntimeStatusService(settings)

    def payload(self, *, date_label: str | None = None, season: int | None = None) -> dict[str, Any]:
        target_date, mode = resolve_date_mode(date_label)
        selected_season = int(season or self.settings.current_season)
        today = _today_label()
        checking_today = target_date == today
        recommendations: list[str] = []

        props_check = self._props_file_check(target_date)
        odds_check = self._file_group_check(
            "oddsSnapshots",
            self.settings.data_dir / "warehouse" / "odds_snapshots",
            f"propline_props_{target_date}_*.csv",
        )
        normalized_check = self._normalized_odds_check(target_date)
        game_markets_check = self._game_markets_check(target_date)
        umpire_check = UmpireContextService(self.settings).status(date_label=target_date, season=selected_season)
        active_board_check = self._active_playerboard_check(selected_season, target_date)
        edge_board_check = self._edge_board_check(selected_season, target_date)
        default_date_check = self._default_date_check(selected_season, target_date)
        runtime_check = self._runtime_db_check()
        capability_summary = DataSourceCapabilityService(self.settings).capability_summary(
            date_label=target_date,
            season=selected_season,
        )

        status = classify_collector_state(
            props_rows=int(props_check.get("rows") or 0),
            active_playerboard_rows=int(active_board_check.get("rows") or 0),
            edge_board_rows=int(edge_board_check.get("rows") or 0),
            odds_snapshot_count=int(odds_check.get("count") or 0),
            checking_today=checking_today,
            latest_active_date=str(active_board_check.get("latestActiveDate") or ""),
            target_date=target_date,
        )
        self._append_recommendations(
            recommendations,
            props_check=props_check,
            odds_check=odds_check,
            active_board_check=active_board_check,
            edge_board_check=edge_board_check,
            runtime_check=runtime_check,
            status=status,
        )
        if not game_markets_check.get("ok"):
            recommendations.append("Normalized game-market artifact is missing; board can continue, but modeling quality is reduced.")
        if not umpire_check.get("available"):
            recommendations.append("Umpire context is using neutral fallback; this is optional for board readiness.")

        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": status,
            "date": target_date,
            "season": selected_season,
            "resolvedDateMode": mode,
            "checks": {
                "propsFile": props_check,
                "oddsSnapshots": odds_check,
                "normalizedOdds": normalized_check,
                "gameMarkets": game_markets_check,
                "umpires": umpire_check,
                "activePlayerboard": active_board_check,
                "edgeBoard": edge_board_check,
                "defaultDate": default_date_check,
                "runtimeDb": runtime_check,
            },
            "counts": {
                "propsRows": int(props_check.get("rows") or 0),
                "oddsSnapshots": int(odds_check.get("count") or 0),
                "normalizedOddsFiles": int(normalized_check.get("count") or 0),
                "gameMarketRows": int(game_markets_check.get("rows") or 0),
                "umpireRows": int(umpire_check.get("rows") or 0),
                "activePlayerboardRows": int(active_board_check.get("rows") or 0),
                "edgeBoardRows": int(edge_board_check.get("rows") or 0),
            },
            "files": {
                "propsFile": props_check.get("path", ""),
                "latestOddsSnapshot": odds_check.get("latestPath", ""),
                "latestNormalizedOdds": normalized_check.get("latestPath", ""),
                "gameMarkets": game_markets_check.get("path", ""),
                "umpires": (umpire_check.get("paths") or [""])[-1] if isinstance(umpire_check.get("paths"), list) else "",
            },
            "runtime": {
                "dbEnabled": runtime_check.get("dbEnabled", ""),
                "databaseUrlKind": runtime_check.get("databaseUrlKind", ""),
                "databaseUrlConfigured": runtime_check.get("databaseUrlConfigured", False),
                "ok": runtime_check.get("ok", False),
            },
            "capabilitySummary": capability_summary,
            "recommendations": recommendations,
        }

    def _props_file_check(self, date_label: str) -> dict[str, Any]:
        path = self.settings.data_dir / "odds" / f"propline_props_{date_label}.csv"
        rows = _count_csv_rows(path)
        return {
            "ok": path.is_file() and rows > 0,
            "exists": path.is_file(),
            "rows": rows,
            "path": safe_relpath(path, self.settings.root_dir),
        }

    def _file_group_check(self, name: str, directory: Path, pattern: str) -> dict[str, Any]:
        files = sorted(path for path in directory.glob(pattern) if path.is_file()) if directory.exists() else []
        latest = files[-1] if files else None
        return {
            "ok": bool(files),
            "count": len(files),
            "latestPath": safe_relpath(latest, self.settings.root_dir) if latest is not None else "",
            "path": safe_relpath(directory, self.settings.root_dir),
            "name": name,
        }

    def _normalized_odds_check(self, date_label: str) -> dict[str, Any]:
        candidates: list[Path] = []
        patterns = [
            (self.settings.data_dir / "warehouse" / "normalized" / "odds", f"*{date_label}*.csv"),
            (self.settings.data_dir / "warehouse" / "normalized" / "actionnetwork", f"*{date_label}*.csv"),
            (self.settings.data_dir / "edge_board", f"edge_board_{date_label}*.json"),
        ]
        for directory, pattern in patterns:
            if directory.exists():
                candidates.extend(path for path in directory.glob(pattern) if path.is_file())
        files = sorted(set(candidates))
        latest = files[-1] if files else None
        return {
            "ok": bool(files),
            "count": len(files),
            "latestPath": safe_relpath(latest, self.settings.root_dir) if latest is not None else "",
            "paths": [safe_relpath(path, self.settings.root_dir) for path in files[-10:]],
        }

    def _game_markets_check(self, date_label: str) -> dict[str, Any]:
        path = self.settings.data_dir / "warehouse" / "normalized" / "game_markets" / f"game_markets_{date_label}.csv"
        rows = _count_csv_rows(path)
        return {
            "ok": path.is_file() and rows > 0,
            "exists": path.is_file(),
            "rows": rows,
            "path": safe_relpath(path, self.settings.root_dir),
        }

    def _active_playerboard_check(self, season: int, date_label: str) -> dict[str, Any]:
        latest_active_date = ""
        try:
            latest_active_date = self.board_snapshot_repository.latest_active_date(season)
            read_result = self.board_snapshot_repository.read_active_playerboard(season=season, date_label=date_label)
        except Exception as error:
            return {
                "ok": False,
                "rows": 0,
                "snapshotAt": "",
                "snapshotId": "",
                "latestActiveDate": latest_active_date,
                "error": type(error).__name__,
            }
        if read_result is None:
            return {"ok": False, "rows": 0, "snapshotAt": "", "snapshotId": "", "latestActiveDate": latest_active_date}
        return {
            "ok": bool(read_result.rows),
            "rows": len(read_result.rows),
            "snapshotAt": read_result.snapshot_at,
            "snapshotId": ",".join(read_result.snapshot_ids),
            "latestActiveDate": latest_active_date,
            "source": read_result.source,
        }

    def _edge_board_check(self, season: int, date_label: str) -> dict[str, Any]:
        try:
            payload = self.edge_board_service.payload(
                {"season": [str(season)], "date": [date_label], "limit": ["50"]}
            )
        except Exception as error:
            return {"ok": False, "rows": 0, "error": type(error).__name__}
        rows = payload.get("rows")
        row_count = len(rows) if isinstance(rows, list) else int(payload.get("rowCount") or 0)
        return {
            "ok": row_count > 0,
            "rows": row_count,
            "date": str(payload.get("date") or ""),
            "source": payload.get("meta", {}).get("source") if isinstance(payload.get("meta"), dict) else "",
        }

    def _default_date_check(self, season: int, target_date: str) -> dict[str, Any]:
        try:
            today = _today_label()
            today_result = self.board_snapshot_repository.read_active_playerboard(season=season, date_label=today)
            default_date = today if today_result is not None and today_result.rows else self.board_snapshot_repository.latest_active_date(season)
        except Exception as error:
            return {"ok": False, "date": "", "error": type(error).__name__}
        return {"ok": default_date == target_date, "date": default_date}

    def _runtime_db_check(self) -> dict[str, Any]:
        try:
            runtime = self.runtime_status_service.runtime_status()
            live = runtime.get("liveRuntime") if isinstance(runtime.get("liveRuntime"), dict) else {}
            environment = live.get("environment") if isinstance(live.get("environment"), dict) else {}
        except Exception as error:
            return {
                "ok": False,
                "dbEnabled": "1" if self.settings.db_enabled else "0",
                "databaseUrlKind": "configured" if self.settings.database_url else "unset",
                "databaseUrlConfigured": bool(self.settings.database_url),
                "error": type(error).__name__,
            }
        db_enabled = str(environment.get("dbEnabled") or ("1" if self.settings.db_enabled else "0"))
        database_url_kind = str(environment.get("databaseUrlKind") or ("configured" if self.settings.database_url else "unset"))
        configured = bool(environment.get("databaseUrlConfigured") or self.settings.database_url)
        return {
            "ok": db_enabled in {"1", "true", "True"} or bool(self.settings.db_enabled),
            "dbEnabled": db_enabled,
            "databaseUrlKind": database_url_kind,
            "databaseUrlConfigured": configured,
        }

    @staticmethod
    def _append_recommendations(
        recommendations: list[str],
        *,
        props_check: dict[str, Any],
        odds_check: dict[str, Any],
        active_board_check: dict[str, Any],
        edge_board_check: dict[str, Any],
        runtime_check: dict[str, Any],
        status: str,
    ) -> None:
        if not props_check.get("ok"):
            recommendations.append("No usable PropLine props file was found for this date.")
        if not odds_check.get("ok"):
            recommendations.append("No PropLine odds snapshot files were found for this date.")
        if not active_board_check.get("ok"):
            recommendations.append("No active Playerboard serving snapshot was found for this date.")
        if not edge_board_check.get("ok"):
            recommendations.append("EdgeBoard returned no rows for this date.")
        if not runtime_check.get("ok"):
            recommendations.append("Runtime DB settings are not enabled/configured for the serving store.")
        if status == "stale":
            recommendations.append("The current active Playerboard date is older than today.")


def resolve_date_mode(value: str | None) -> tuple[str, str]:
    text = str(value or "").strip()
    if not text:
        return _today_label(), "default"
    if text.lower() == "today":
        return _today_label(), "today"
    return text[:10], "explicit"


def _today_label() -> str:
    return datetime.now().astimezone().date().isoformat()


def _count_csv_rows(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return sum(1 for _ in csv.DictReader(handle))
    except Exception:
        return 0
