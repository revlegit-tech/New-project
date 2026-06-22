from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictResponse(BaseModel):
    """Strict FastAPI response base for native production contracts."""

    model_config = ConfigDict(extra="forbid")


class StrictPayload(BaseModel):
    """Strict nested payload base for canonical native API objects."""

    model_config = ConfigDict(extra="forbid")


class ErrorResponse(StrictResponse):
    status: str = "error"
    code: str
    message: str
    error: str | None = None
    requestId: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class EdgeBoardRow(StrictPayload):
    """Canonical row contract for board-like native responses.

    Some values are still strings because the existing CSV/source rows preserve
    raw sportsbook/source values. The contract is intentionally explicit even
    where values remain flexible during migration.
    """

    propKey: str = ""
    id: str | None = None
    date: str | None = None
    playerId: str | None = None
    player: str = ""
    team: str = ""
    opponent: str = ""
    pitcher: str | None = None
    market: str = ""
    marketDisplay: str | None = None
    baseMarket: str | None = None
    originalMarket: str | None = None
    marketFamily: str | None = None
    rawLabel: str | None = None
    side: str | None = None
    line: Any = None
    book: str | None = None
    bookKey: str | None = None
    bookCount: Any = None
    books: list[Any] = Field(default_factory=list)
    americanOdds: Any = None
    modelProbabilityPercent: Any = None
    impliedProbabilityPercent: Any = None
    edgePercent: Any = None
    finalProbabilityPercent: Any = None
    sportsbookImpliedPercent: Any = None
    finalEdgePercent: Any = None
    confidence: str | None = None
    recommendation: str | None = None
    weatherAdjustmentPercent: Any = None
    savantAdjustmentPercent: Any = None
    oddsMovementAdjustmentPercent: Any = None
    missingData: list[Any] = Field(default_factory=list)
    hitRates: dict[str, Any] = Field(default_factory=dict)
    recentGames: list[dict[str, Any]] = Field(default_factory=list)
    rank: int | None = None
    gameTime: str | None = None
    readinessLabel: str = ""
    decisionLabel: str = ""
    decisionTone: str | None = None
    productionStatus: str | None = None
    canShowConfidentPick: bool | None = None
    trainingRows: Any = None
    positiveRows: Any = None
    negativeRows: Any = None
    latestGradedDate: str | None = None
    calibrationStatus: str | None = None
    warningCount: int | None = None
    trustWarnings: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    suggestedStake: str | None = None
    modelCard: dict[str, Any] = Field(default_factory=dict)
    trust: dict[str, Any] = Field(default_factory=dict)
    freshness: dict[str, Any] = Field(default_factory=dict)
    isAltMarket: bool | str | None = None


class ModelCardItem(StrictPayload):
    market: str = ""
    marketName: str | None = None
    version: str | None = None
    status: str | None = None
    modelStatus: str | None = None
    productionStatus: str | None = None
    readinessLabel: str | None = None
    canShowConfidentPick: bool | None = None
    reason: str | None = None
    trainingRows: int | None = None
    positiveRows: int | None = None
    negativeRows: int | None = None
    classCounts: dict[str, Any] = Field(default_factory=dict)
    trainedAt: str | None = None
    latestGradedDate: str | None = None
    artifactExists: bool | None = None
    metadataExists: bool | None = None
    artifact: str | None = None
    artifactSha256: str | None = None
    artifactHashPrefix: str | None = None
    featuresSha256: str | None = None
    metricsSha256: str | None = None
    hashVerified: bool | None = None
    artifactVerification: dict[str, Any] = Field(default_factory=dict)
    featureSchema: dict[str, Any] = Field(default_factory=dict)
    calibrated: bool | None = None
    calibration: dict[str, Any] = Field(default_factory=dict)
    backtest: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    trainingWindow: dict[str, Any] = Field(default_factory=dict)
    lastPromotedAt: str | None = None
    knownLimitations: list[str] = Field(default_factory=list)
    researchOnly: bool | None = None
    productionReady: bool | None = None
    trustWarnings: list[str] = Field(default_factory=list)
    decisionPolicy: dict[str, Any] = Field(default_factory=dict)


class PickItem(StrictPayload):
    id: str = ""
    status: str = ""
    source: str | None = None
    date: str | None = None
    player: str | None = None
    team: str | None = None
    opponent: str | None = None
    market: str | None = None
    marketDisplay: str | None = None
    side: str | None = None
    line: Any = None
    book: str | None = None
    americanOdds: Any = None
    confidence: str | None = None
    notes: str | None = None
    warnings: list[str] = Field(default_factory=list)
    createdAt: str | None = None
    updatedAt: str | None = None
    stakeUnits: float | None = None
    stakeAmount: float | None = None
    decisionLabel: str | None = None
    readinessLabel: str | None = None
    modelProbabilityPercent: Any = None
    impliedProbabilityPercent: Any = None
    edgePercent: Any = None
    latestGradedDate: str | None = None
    suggestedStake: str | None = None
    profitUnits: float | None = None
    gameKey: str | None = None


class ExposureSummaryPayload(StrictPayload):
    activePickCount: int = 0
    totalStakeUnits: float = 0.0
    totalStakeAmount: float = 0.0
    byGameUnits: list[dict[str, Any]] = Field(default_factory=list)
    byPlayerUnits: list[dict[str, Any]] = Field(default_factory=list)
    byMarketUnits: list[dict[str, Any]] = Field(default_factory=list)
    settledPickCount: int = 0
    profitUnits: float = 0.0
    profitAmount: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    caps: dict[str, Any] = Field(default_factory=dict)


class PropDetailPayload(StrictPayload):
    id: str | None = None
    propKey: str | None = None
    overview: dict[str, Any] = Field(default_factory=dict)
    priceComparison: dict[str, Any] = Field(default_factory=dict)
    modelExplanation: dict[str, Any] = Field(default_factory=dict)
    playerContext: dict[str, Any] = Field(default_factory=dict)
    trendProfile: dict[str, Any] = Field(default_factory=dict)
    gameContext: dict[str, Any] = Field(default_factory=dict)
    riskContext: dict[str, Any] = Field(default_factory=dict)
    tracking: dict[str, Any] = Field(default_factory=dict)


class DataHealthResponse(StrictResponse):
    schemaVersion: str | None = None
    date: str | None = None
    season: int | str | None = None
    dataRoot: str | None = None
    latestLocalSummary: dict[str, Any] = Field(default_factory=dict)
    latestCloudRun: dict[str, Any] = Field(default_factory=dict)
    health: dict[str, Any] = Field(default_factory=dict)
    files: dict[str, Any] = Field(default_factory=dict)
    timestamps: dict[str, Any] = Field(default_factory=dict)
    savant: dict[str, Any] = Field(default_factory=dict)
    batterVsPitcher: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    ok: bool | None = None
    grading: dict[str, Any] = Field(default_factory=dict)
    productState: dict[str, Any] = Field(default_factory=dict)
    latestFullyGradedDate: str | None = None
    trust: dict[str, Any] = Field(default_factory=dict)


class DataHealthDashboardResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    ok: bool | None = None
    version: str | None = None
    season: int | str | None = None
    date: str | None = None
    generatedAt: str | None = None
    overallStatus: str | None = None
    dataConfidence: str | None = None
    productState: dict[str, Any] = Field(default_factory=dict)
    latestBoardDate: str | None = None
    latestFullyGradedDate: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    cards: list[dict[str, Any]] = Field(default_factory=list)
    workflowPhases: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    advancedLinks: list[dict[str, Any]] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class GradingHealthResponse(StrictResponse):
    schemaVersion: str | None = None
    state: str
    ok: bool
    date: str = ""
    latestFullyGradedDate: str = ""
    checkedAt: str = ""
    file: str = ""
    exists: bool = False
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    requestedDate: str = ""


class WorkflowHealthResponse(StrictResponse):
    schemaVersion: str | None = None
    ok: bool
    healthDir: str
    summaries: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class PropMlStatusResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    mode: str | None = None
    markets: list[dict[str, Any]] = Field(default_factory=list)
    readyMarkets: list[str] = Field(default_factory=list)
    notReadyMarkets: list[str] = Field(default_factory=list)
    trainedMarkets: list[str] = Field(default_factory=list)
    productionEligibleMarkets: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    marketsWithHashIssues: list[str] = Field(default_factory=list)
    policy: dict[str, Any] = Field(default_factory=dict)


class MetricsSeries(StrictPayload):
    name: str
    labels: dict[str, Any] = Field(default_factory=dict)
    value: float | None = None
    count: int | None = None
    min: float | None = None
    max: float | None = None
    avg: float | None = None
    p50: float | None = None
    p95: float | None = None
    p99: float | None = None


class ObservabilityMetricsResponse(StrictResponse):
    status: str = "ok"
    counters: list[MetricsSeries] = Field(default_factory=list)
    histograms: list[MetricsSeries] = Field(default_factory=list)
    gauges: list[MetricsSeries] = Field(default_factory=list)


class AppStatusResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    ok: bool | None = None
    season: int | None = None
    warnings: list[str] = Field(default_factory=list)
    checkedAt: str | None = None
    generatedAt: str | None = None
    productState: str | None = None
    productStateDetail: dict[str, Any] = Field(default_factory=dict)
    latestFullyGradedDate: str | None = None
    latestBoardDate: str | None = None
    researchMode: bool | None = None
    trainedMarkets: list[str] = Field(default_factory=list)
    productionEligibleMarkets: list[str] = Field(default_factory=list)
    dataConfidence: str | None = None
    dataConfidenceDetail: dict[str, Any] = Field(default_factory=dict)
    runtime: dict[str, Any] = Field(default_factory=dict)
    modelReadiness: dict[str, Any] = Field(default_factory=dict)
    modelPolicy: dict[str, Any] = Field(default_factory=dict)
    alerts: list[dict[str, Any]] = Field(default_factory=list)
    alertCount: int | None = None
    observability: dict[str, Any] = Field(default_factory=dict)
    playerboard: dict[str, Any] = Field(default_factory=dict)
    grading: dict[str, Any] = Field(default_factory=dict)
    workflows: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)
    snapshotAgeSeconds: float | None = None
    boardCacheStatus: dict[str, Any] = Field(default_factory=dict)
    contractErrors: list[str] = Field(default_factory=list)


class EdgeBoardResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    version: str | None = None
    season: int | None = None
    date: str | None = None
    rows: list[EdgeBoardRow] = Field(default_factory=list)
    top: list[EdgeBoardRow] = Field(default_factory=list)
    rowCount: int | None = None
    latestFullyGradedDate: str | None = None
    productState: dict[str, Any] | str | None = None
    modelReadiness: dict[str, Any] = Field(default_factory=dict)
    boardCache: dict[str, Any] = Field(default_factory=dict)
    cacheHit: bool | None = None
    source: dict[str, Any] = Field(default_factory=dict)
    filters: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    trust: dict[str, Any] = Field(default_factory=dict)
    dataConfidence: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    freshness: dict[str, Any] = Field(default_factory=dict)


class ResearchReportCard(StrictPayload):
    id: str = ""
    propKey: str = ""
    player: str = ""
    team: str = ""
    opponent: str = ""
    matchup: str = ""
    market: str = ""
    marketDisplay: str = ""
    side: str = ""
    line: Any = None
    americanOdds: Any = None
    book: str = ""
    score: int = 0
    grade: str = ""
    riskBucket: str = ""
    confidence: str = ""
    edgePercent: float = 0.0
    modelProbabilityPercent: float | None = None
    impliedProbabilityPercent: float | None = None
    decisionLabel: str = ""
    readinessLabel: str = ""
    suggestedStake: str = ""
    sourceRowRank: int = 0
    freshness: dict[str, Any] = Field(default_factory=dict)
    trust: dict[str, Any] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ResearchReportSection(StrictPayload):
    key: str
    title: str
    description: str = ""
    publishTier: str = "premium"
    cardCount: int = 0
    cards: list[ResearchReportCard] = Field(default_factory=list)
    emptyState: str = ""


class ResearchReportResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    version: str | None = None
    date: str | None = None
    season: int | None = None
    product: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    sections: list[ResearchReportSection] = Field(default_factory=list)
    pricing: dict[str, Any] = Field(default_factory=dict)
    publishPlan: list[dict[str, Any]] = Field(default_factory=list)
    trust: dict[str, Any] = Field(default_factory=dict)
    freshness: dict[str, Any] = Field(default_factory=dict)
    source: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


class PlayerboardResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    season: int | None = None
    date: str | None = None
    rows: list[EdgeBoardRow] = Field(default_factory=list)
    message: str | None = None
    market: str | None = None
    cardsBuilt: int | None = None
    propsLoaded: int | None = None
    saved: dict[str, Any] = Field(default_factory=dict)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    latestFullyGradedDate: str | None = None
    modelReadiness: dict[str, Any] = Field(default_factory=dict)
    cacheHit: bool | None = None
    top: list[EdgeBoardRow] = Field(default_factory=list)
    trust: dict[str, Any] = Field(default_factory=dict)
    productState: dict[str, Any] | str | None = None
    dataConfidence: str | None = None
    source: dict[str, Any] | str | None = None
    sourceMeta: dict[str, Any] = Field(default_factory=dict)
    filters: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)
    freshness: dict[str, Any] = Field(default_factory=dict)


class PlayerboardHealthResponse(StrictResponse):
    status: str | None = None
    schemaVersion: str | None = None
    season: int | None = None
    ok: bool | None = None
    schemaOk: bool | None = None
    rowsLoaded: int | None = None
    totalRowsInFile: int | None = None
    latestAvailableDate: str | None = None
    latestSnapshotAt: str | None = None
    requestedDate: str | None = None
    date: str | None = None
    market: str | None = None
    exists: bool | None = None
    file: str | None = None
    schemaIssue: str | None = None
    expectedColumnCount: int | None = None
    expectedColumns: list[str] = Field(default_factory=list)
    availableDates: list[str] = Field(default_factory=list)
    snapshots: list[Any] = Field(default_factory=list)
    marketsPresent: list[str] | dict[str, Any] = Field(default_factory=list)
    missingMarketDisplayRows: int | None = None
    sampleMissingMarketDisplayRows: list[dict[str, Any]] = Field(default_factory=list)
    badShiftedRows: int | None = None
    sampleBadRows: list[dict[str, Any]] = Field(default_factory=list)
    schemaValidation: dict[str, Any] = Field(default_factory=dict)
    slateStatus: dict[str, Any] = Field(default_factory=dict)
    usedLatestAvailableDate: bool | None = None
    productState: dict[str, Any] | str | None = None
    modelReadiness: dict[str, Any] = Field(default_factory=dict)
    grading: dict[str, Any] = Field(default_factory=dict)
    dataConfidence: str | None = None
    latestFullyGradedDate: str | None = None
    trust: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)
    freshness: dict[str, Any] = Field(default_factory=dict)


class PropDetailResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    prop: dict[str, Any] = Field(default_factory=dict)
    row: dict[str, Any] = Field(default_factory=dict)
    modelCard: dict[str, Any] = Field(default_factory=dict)
    detail: PropDetailPayload = Field(default_factory=PropDetailPayload)
    version: str | None = None
    source: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class ModelCardsResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    markets: list[ModelCardItem] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    modelCard: ModelCardItem | dict[str, Any] = Field(default_factory=dict)
    version: str | None = None
    policy: dict[str, Any] = Field(default_factory=dict)
    modelSnapshot: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


class PredictionEventsResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    event: dict[str, Any] = Field(default_factory=dict)
    eventCount: int | None = None
    storage: dict[str, Any] = Field(default_factory=dict)
    filters: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


class PickResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    pick: PickItem | None = None
    picks: list[PickItem] = Field(default_factory=list)
    pickCount: int | None = None
    version: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    storage: dict[str, Any] = Field(default_factory=dict)
    lifecycle: dict[str, Any] | list[str] = Field(default_factory=dict)
    exposure: ExposureSummaryPayload = Field(default_factory=ExposureSummaryPayload)
    policy: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class BankrollSettingsResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    policy: dict[str, Any] = Field(default_factory=dict)
    allowedStakingMethods: list[str] = Field(default_factory=list)
    storage: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class ExposureSummaryResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    exposure: ExposureSummaryPayload = Field(default_factory=ExposureSummaryPayload)
    policy: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class ProplineSyncResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    date: str | None = None
    sport: str | None = None
    timezone: str | None = None
    markets: list[str] = Field(default_factory=list)
    eventCount: int | None = None
    totalEventCount: int | None = None
    attemptedEventCount: int | None = None
    maxEvents: int | None = None
    propCount: int | None = None
    savedPath: str | None = None
    snapshotPath: str | None = None
    warnings: list[str] = Field(default_factory=list)
    eventErrors: list[dict[str, Any]] = Field(default_factory=list)
    emptyEvents: list[dict[str, Any]] = Field(default_factory=list)
    eventsPreview: list[dict[str, Any]] = Field(default_factory=list)
    tokenGuard: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(StrictResponse):
    status: str
    ok: bool
    checks: dict[str, Any] = Field(default_factory=dict)
