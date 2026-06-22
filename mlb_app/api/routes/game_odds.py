from __future__ import annotations

from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, Request, Response

from mlb_app.api.dependencies import (
    get_blocking_work_limiter,
    get_container,
    get_historical_game_odds_import_service,
    get_historical_game_odds_repository,
)
from mlb_app.api.models import (
    HistoricalGameOddsImportResponse,
    HistoricalGameOddsRowsResponse,
    HistoricalGameOddsStatusResponse,
)
from mlb_app.api.routes._utils import apply_payload_status, enforce_native_mutation, with_schema_version
from mlb_app.container import AppContainer
from mlb_app.repositories.historical_game_odds_repository import HistoricalGameOddsRepository
from mlb_app.services.blocking_work import BlockingWorkLimiter
from mlb_app.services.historical_game_odds_import_service import HISTORICAL_GAME_ODDS_SCHEMA_VERSION, HistoricalGameOddsImportService

router = APIRouter(prefix="/api", tags=["game-odds"])


@router.post(
    "/admin/historical-game-odds/import",
    response_model=HistoricalGameOddsImportResponse,
    name="native_admin_import_historical_game_odds",
)
async def import_historical_game_odds(
    request: Request,
    response: Response,
    service: Annotated[HistoricalGameOddsImportService, Depends(get_historical_game_odds_import_service)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    enforce_native_mutation(request, owner="data_ops", risk="high", kind="historical_game_odds_import")
    payload = body or {}
    source_file = _first_query_or_body(request, payload, "sourceFile") or _first_query_or_body(request, payload, "source_file")
    export_csv = _boolish(_first_query_or_body(request, payload, "exportCsv", "0"))
    skip_init = _boolish(_first_query_or_body(request, payload, "skipInit", "0"))
    result = await limiter.run(
        service.import_file,
        source_file=source_file or None,
        export_csv=export_csv,
        initialize_schema=not skip_init,
        timeout_seconds=1800.0,
        route_name="POST /api/admin/historical-game-odds/import",
    )
    return apply_payload_status(result.to_payload(), response, schema_version=HISTORICAL_GAME_ODDS_SCHEMA_VERSION)


@router.get("/game-odds/status", response_model=HistoricalGameOddsStatusResponse, name="native_game_odds_status")
async def game_odds_status(
    repository: Annotated[HistoricalGameOddsRepository, Depends(get_historical_game_odds_repository)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
) -> dict[str, Any]:
    raw = await limiter.run(repository.status, route_name="/api/game-odds/status")
    return with_schema_version(_status_payload(raw), HISTORICAL_GAME_ODDS_SCHEMA_VERSION)


@router.get("/game-odds/lines", response_model=HistoricalGameOddsRowsResponse, name="native_game_odds_lines")
async def game_odds_lines(
    request: Request,
    repository: Annotated[HistoricalGameOddsRepository, Depends(get_historical_game_odds_repository)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    date_label = str(request.query_params.get("date") or "")
    payload = await limiter.run(
        _safe_rows,
        repository.query_lines_by_date,
        date_label,
        timeout_seconds=container.settings.playerboard_timeout_seconds,
        route_name="/api/game-odds/lines",
    )
    return with_schema_version(payload, HISTORICAL_GAME_ODDS_SCHEMA_VERSION)


@router.get("/game-odds/features", response_model=HistoricalGameOddsRowsResponse, name="native_game_odds_features")
async def game_odds_features(
    request: Request,
    repository: Annotated[HistoricalGameOddsRepository, Depends(get_historical_game_odds_repository)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    date_label = str(request.query_params.get("date") or "")
    payload = await limiter.run(
        _safe_rows,
        repository.query_features_by_date,
        date_label,
        timeout_seconds=container.settings.playerboard_timeout_seconds,
        route_name="/api/game-odds/features",
    )
    return with_schema_version(payload, HISTORICAL_GAME_ODDS_SCHEMA_VERSION)


@router.get("/game-odds/grades", response_model=HistoricalGameOddsRowsResponse, name="native_game_odds_grades")
async def game_odds_grades(
    request: Request,
    repository: Annotated[HistoricalGameOddsRepository, Depends(get_historical_game_odds_repository)],
    limiter: Annotated[BlockingWorkLimiter, Depends(get_blocking_work_limiter)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    date_label = str(request.query_params.get("date") or "")
    payload = await limiter.run(
        _safe_rows,
        repository.query_grades_by_date,
        date_label,
        timeout_seconds=container.settings.playerboard_timeout_seconds,
        route_name="/api/game-odds/grades",
    )
    return with_schema_version(payload, HISTORICAL_GAME_ODDS_SCHEMA_VERSION)


def _safe_rows(query: Callable[[str], list[dict[str, Any]]], date_label: str) -> dict[str, Any]:
    try:
        rows = query(date_label)
        return {"status": "ok", "date": date_label, "rowCount": len(rows), "rows": rows, "warnings": []}
    except Exception as error:
        return {
            "status": "ok",
            "date": date_label,
            "rowCount": 0,
            "rows": [],
            "warnings": [f"Historical game odds warehouse unavailable: {type(error).__name__}: {error}"],
        }


def _status_payload(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "ok",
        "enabled": bool(raw.get("enabled")),
        "reachable": bool(raw.get("reachable")),
        "dialect": str(raw.get("dialect") or ""),
        "reason": str(raw.get("reason") or ""),
        "error": str(raw.get("error") or ""),
        "games": int(raw.get("games") or 0),
        "lineRows": int(raw.get("line_rows") or 0),
        "featureRows": int(raw.get("feature_rows") or 0),
        "gradeRows": int(raw.get("grade_rows") or 0),
        "latestImportAt": str(raw.get("latest_import_at") or ""),
        "latestImportStatus": str(raw.get("latest_import_status") or ""),
        "sourceFilePresent": bool(raw.get("source_file_present")),
        "warnings": [str(item) for item in raw.get("warnings", []) if str(item).strip()],
    }


def _first_query_or_body(request: Request, body: dict[str, Any], key: str, fallback: str = "") -> str:
    value = request.query_params.get(key)
    if value is not None:
        return str(value)
    candidate = body.get(key, fallback)
    return str(candidate if candidate is not None else fallback)


def _boolish(value: str, *, default: bool = False) -> bool:
    if value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
