from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FlexibleResponse(BaseModel):
    """Typed FastAPI response base that preserves existing JSON contracts.

    Sprint 4 introduces response models without forcing a disruptive payload
    rewrite. Known fields are documented below while ``extra='allow'`` keeps the
    legacy UI contract stable during the native route migration.
    """

    model_config = ConfigDict(extra="allow")


class AppStatusResponse(FlexibleResponse):
    status: str = "ok"
    ok: bool | None = None
    season: int | None = None
    warnings: list[str] = Field(default_factory=list)
    productState: str | None = None
    dataConfidence: str | None = None
    playerboard: dict[str, Any] = Field(default_factory=dict)
    grading: dict[str, Any] = Field(default_factory=dict)
    workflows: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


class EdgeBoardResponse(FlexibleResponse):
    status: str = "ok"
    version: str | None = None
    season: int | None = None
    date: str | None = None
    rows: list[dict[str, Any]] = Field(default_factory=list)
    rowCount: int | None = None
    source: dict[str, Any] = Field(default_factory=dict)
    filters: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    trust: dict[str, Any] = Field(default_factory=dict)
    dataConfidence: str | None = None


class PlayerboardResponse(FlexibleResponse):
    status: str = "ok"
    season: int | None = None
    date: str | None = None
    rows: list[dict[str, Any]] = Field(default_factory=list)
    top: list[dict[str, Any]] = Field(default_factory=list)
    trust: dict[str, Any] = Field(default_factory=dict)
    productState: dict[str, Any] | None = None
    dataConfidence: str | None = None


class PlayerboardHealthResponse(FlexibleResponse):
    season: int | None = None
    ok: bool | None = None
    schemaVersion: str | None = None
    schemaOk: bool | None = None
    rowsLoaded: int | None = None
    totalRowsInFile: int | None = None
    latestAvailableDate: str | None = None
    dataConfidence: str | None = None


class PropDetailResponse(FlexibleResponse):
    status: str = "ok"
    prop: dict[str, Any] = Field(default_factory=dict)
    row: dict[str, Any] = Field(default_factory=dict)
    modelCard: dict[str, Any] = Field(default_factory=dict)


class ModelCardsResponse(FlexibleResponse):
    status: str = "ok"
    markets: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class PredictionEventsResponse(FlexibleResponse):
    status: str = "ok"
    events: list[dict[str, Any]] = Field(default_factory=list)
    eventCount: int | None = None
    storage: dict[str, Any] = Field(default_factory=dict)


class PickResponse(FlexibleResponse):
    status: str = "ok"
    pick: dict[str, Any] | None = None
    picks: list[dict[str, Any]] = Field(default_factory=list)
    pickCount: int | None = None
    exposure: dict[str, Any] = Field(default_factory=dict)


class BankrollSettingsResponse(FlexibleResponse):
    status: str = "ok"
    settings: dict[str, Any] = Field(default_factory=dict)
    policy: dict[str, Any] = Field(default_factory=dict)


class ExposureSummaryResponse(FlexibleResponse):
    status: str = "ok"
    settings: dict[str, Any] = Field(default_factory=dict)
    exposure: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    ok: bool
    checks: dict[str, Any] = Field(default_factory=dict)
